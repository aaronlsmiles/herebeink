"""KR1 of Part 2: how much of the hallway does the answer-key pass measure past the doorway?

Counts the COLMAP points that three or more registered answer-key images saw and that lie past the
door plane, in the measured world frame Part 1 settled (scale.json's world_from_colmap, metres,
+y up). The door plane is the door's centre with its outward normal, which points out of the room.
Writes work/ladder/answer_key.json and a plan view, work/ladder/answer_key.png.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial.transform import Rotation

import plots
from colmap_model import Model, read_model

WORK = Path(__file__).resolve().parent / "work"
KEY_MARK = "/4key_"
# The same bar colmap_report.py uses for a registered image, so the 92 of 140 it prints is the set used here.
MIN_OBS = 15
MIN_KEY_VIEWS = 3
# Frozen in the Part 2 plan, section 5.
KR1_MIN_POINTS = 200
KR1_MIN_REACH_M = 0.5
# A wall has thickness, and points on its far face are not hallway; the primary count takes none of it
# away, the others show how much it matters.
MARGINS_M = (0.0, 0.10, 0.25)
ROOM_RADIUS_M = 6.0


def key_images(model: Model, min_obs: int = MIN_OBS) -> dict[int, str]:
    """Image id -> the answer-key sample it belongs to (the rig's views of one sample share a stem)."""
    return {i: Path(im.name).stem for i, im in model.images.items()
            if KEY_MARK in im.name and im.n_obs >= min_obs}


def centre_of(img) -> np.ndarray:
    r = Rotation.from_quat(img.qvec, scalar_first=True).as_matrix()
    return -r.T @ np.array(img.tvec)


def to_world(xyz: np.ndarray, world_from_colmap: np.ndarray) -> np.ndarray:
    xyz = np.atleast_2d(np.asarray(xyz, float))
    return xyz @ world_from_colmap[:3, :3].T + world_from_colmap[:3, 3]


def door_plane(scale: dict) -> tuple[np.ndarray, np.ndarray]:
    d = scale["door"]
    c = np.asarray(d["centre"], float)
    n = np.asarray(d["outward"], float)
    return c, n / np.linalg.norm(n)


def _reach(dist: np.ndarray) -> dict:
    if not len(dist):
        return {"count": 0, "max_m": None, "p90_m": None, "median_m": None}
    return {"count": int(len(dist)), "max_m": round(float(dist.max()), 3),
            "p90_m": round(float(np.percentile(dist, 90)), 3), "median_m": round(float(np.median(dist)), 3)}


def analyse(model: Model, world_from_colmap: np.ndarray, centre: np.ndarray, normal: np.ndarray,
            min_obs: int = MIN_OBS) -> dict:
    """The numbers and the arrays behind them; `arrays` is dropped before the JSON is written."""
    keys = key_images(model, min_obs)
    ids = list(model.points)
    xyz = to_world(np.array([model.points[i].xyz for i in ids]).reshape(-1, 3), world_from_colmap)
    n_views = np.array([len({t[0] for t in model.points[i].track} & keys.keys()) for i in ids])
    n_samples = np.array([len({keys[t[0]] for t in model.points[i].track if t[0] in keys}) for i in ids])
    dist = (xyz - centre) @ normal
    lateral = (xyz - centre) @ np.array([-normal[2], 0.0, normal[0]])
    seen3 = n_views >= MIN_KEY_VIEWS

    past = seen3 & (dist > 0)
    by_margin = {f"{m:.2f}": _reach(dist[seen3 & (dist > m)]) for m in MARGINS_M}
    by_sample = _reach(dist[(n_samples >= MIN_KEY_VIEWS) & (dist > 0)])

    samples: dict[str, list[np.ndarray]] = {}
    for i, stem in keys.items():
        samples.setdefault(stem, []).append(centre_of(model.images[i]))
    cams = to_world(np.array([np.mean(v, axis=0) for v in samples.values()]).reshape(-1, 3), world_from_colmap)
    cam_dist = (cams - centre) @ normal

    horiz = np.hypot(*(xyz[past][:, [0, 2]] - centre[[0, 2]]).T) if past.any() else np.array([])
    result = {
        "key_images_registered": len(keys),
        "key_samples_registered": len(samples),
        "points_in_model": len(ids),
        "points_seen_by_3_plus_key_images": int(seen3.sum()),
        "points_past_door": _reach(dist[past]),
        "points_past_door_by_margin_m": by_margin,
        "points_past_door_seen_by_3_plus_samples": by_sample,
        "points_past_door_lateral_m": ({"min": round(float(lateral[past].min()), 3),
                                        "max": round(float(lateral[past].max()), 3)} if past.any() else None),
        "points_past_door_horizontal_reach_m": ({"p90": round(float(np.percentile(horiz, 90)), 3),
                                                 "max": round(float(horiz.max()), 3)} if past.any() else None),
        "key_cameras_past_door": {**_reach(cam_dist[cam_dist > 0]), "of": len(cams)},
    }
    p90 = result["points_past_door"]["p90_m"]
    result["kr1"] = kr1(result["points_past_door"]["count"], p90)
    return {"result": result, "arrays": {"xyz": xyz, "dist": dist, "past": past, "cams": cams, "cam_dist": cam_dist}}


def kr1(count: int, p90_reach_m: float | None) -> dict:
    """Fewer than 200 points, or a reach under 0.5 m, leaves the hallway unscored. Reach is the 90th
    percentile along the normal: the maximum alone would let one stray point rescue it."""
    few = count < KR1_MIN_POINTS
    short = p90_reach_m is None or p90_reach_m < KR1_MIN_REACH_M
    return {"hallway_scored": not (few or short), "fewer_than_200_points": few,
            "reach_under_0.5_m": short, "rule": "fewer than 200 points, or p90 reach under 0.5 m: hallway unscored"}


def plan_png(path: Path, arrays: dict, centre: np.ndarray, normal: np.ndarray, width_m: float) -> Path:
    xyz, dist, past, cams, cam_dist = (arrays[k] for k in ("xyz", "dist", "past", "cams", "cam_dist"))
    near = np.hypot(*(xyz[:, [0, 2]] - centre[[0, 2]]).T) <= ROOM_RADIUS_M
    band = (xyz[:, 1] >= 0.1) & (xyz[:, 1] <= 2.3)
    room = xyz[near & band & ~past][:, [0, 2]]
    hall = xyz[past][:, [0, 2]]
    # A few stray points a long way off would shrink everything else; the window ignores the outer 1 %.
    core = hall[(hall >= np.percentile(hall, 1, axis=0)).all(axis=1) & (hall <= np.percentile(hall, 99, axis=0)).all(axis=1)] \
        if len(hall) > 100 else hall
    close = room[np.hypot(*(room - centre[[0, 2]]).T) <= 3.5]
    focus = np.vstack([core, cams[:, [0, 2]], centre[[0, 2]][None], close])
    lo, hi = focus.min(axis=0) - 0.4, focus.max(axis=0) + 0.4
    px_per_m = 160
    size = np.ceil((hi - lo) * px_per_m).astype(int)
    img = Image.new("RGB", (max(int(size[0]), 760), int(size[1]) + 70), "white")
    draw = ImageDraw.Draw(img)
    panel = plots.Panel((0, 0, int(size[0]), int(size[1])), lo, hi, top=True)
    panel.points(draw, room, (170, 170, 170))
    panel.points(draw, hall, (200, 40, 40))
    for p in panel.px(hall):
        draw.ellipse([p[0] - 1.5, p[1] - 1.5, p[0] + 1.5, p[1] + 1.5], fill=(200, 40, 40))
    for p, past_door in zip(panel.px(cams[:, [0, 2]]), cam_dist > 0):
        col = (20, 60, 200) if past_door else (90, 120, 220)
        draw.polygon([(p[0], p[1] - 6), (p[0] + 6, p[1] + 5), (p[0] - 6, p[1] + 5)], fill=col)
    along = np.array([-normal[2], normal[0]])
    half = width_m / 2
    a, b = panel.px(np.array([centre[[0, 2]] - along * half, centre[[0, 2]] + along * half]))
    draw.line([tuple(a), tuple(b)], fill=(0, 0, 0), width=5)
    # The plane itself, far enough either side to see which points fall beyond it.
    p0, p1 = panel.px(np.array([centre[[0, 2]] - along * 1.5, centre[[0, 2]] + along * 1.5]))
    draw.line([tuple(p0), tuple(p1)], fill=(0, 0, 0), width=1)
    font = ImageFont.load_default(size=15)
    panel.axes(draw, font)
    y = int(size[1]) + 6
    draw.text((8, y), "plan view from above: x right, z down the page; points 0.1 to 2.3 m above the floor", fill=(0, 0, 0), font=font)
    draw.text((8, y + 20), "grey: room points; red: points seen by 3+ answer-key images past the door plane", fill=(0, 0, 0), font=font)
    draw.text((8, y + 40), "triangles: answer-key camera centres (dark blue past the plane); black bar: the door; 1 m = "
              f"{px_per_m} px", fill=(0, 0, 0), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def run(work: Path) -> dict:
    scale = json.loads((work / "scale.json").read_text())
    world_from_colmap = np.array(scale["world_from_colmap"], float)
    model = read_model(work / "colmap" / "sparse_txt" / "0")
    centre, normal = door_plane(scale)
    out = analyse(model, world_from_colmap, centre, normal)
    doc = out["result"]
    # The pano's reference view must land where Part 1 put the pano; if it does not, the frame is wrong.
    pano = next((im for im in model.images.values() if im.name == "rig/y000p00/5pano_0000.jpg"), None)
    frame_check = None
    if pano is not None and "pano" in scale:
        frame_check = round(float(np.linalg.norm(to_world(centre_of(pano), world_from_colmap)[0] - np.array(scale["pano"]))), 4)
    doc = {
        "door": {"centre_m": [round(float(v), 4) for v in centre], "normal_out_of_room": [round(float(v), 4) for v in normal],
                 "width_tape_m": scale["door"].get("width_tape_m")},
        "frame": "measured world frame of scale.json (metres, +y up, pano near the origin)",
        "pano_centre_error_m": frame_check,
        "min_obs_for_registered": MIN_OBS, "min_key_images_per_point": MIN_KEY_VIEWS,
        **doc,
    }
    ladder = work / "ladder"
    ladder.mkdir(parents=True, exist_ok=True)
    (ladder / "answer_key.json").write_text(json.dumps(doc, indent=2) + "\n")
    plan_png(ladder / "answer_key.png", out["arrays"], centre, normal, scale["door"].get("width_tape_m") or 0.72)
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, default=WORK)
    a = ap.parse_args(argv)
    doc = run(a.work)
    print(json.dumps(doc, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

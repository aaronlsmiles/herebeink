"""The ladder mode's dev fixture: synth_world's room and Marble-like world, split per rung by its own frustums.

    uv run python make_ladder_fixture.py            # -> ../web/public/fixture-ladder/ (about 1.5 MB, under a minute)
    uv run python make_ladder_fixture.py --out DIR

Not a scoring of anything. From the camera point c (the synthetic pano's centre), each rung's flat views
are 66 x 51.94 degree frustums at pitch 0, the first facing the door. A Marble-like splat is seen when it
lies in a frustum and on the real room; otherwise it is imagined. Imagined splats are wrong when they are
the invented hallway, or furniture this rung's world put in the wrong place (moved here, so it looks
wrong too). The shown and seen-of-key shares are computed from the frustums; the imagined shares and the
scan's agreement are made up, plausibly. R4r is written as not placed, so the page's "not placed" state
has something to show. The map's seen floor and coastline are the plan-view fans of the views out to the
walls: an approximation that only this fixture uses.

Files keep Marble's raw frame (OpenCV axes of the pano camera) and carry the true similarity, so the
page places them exactly as it will place real rungs. Seeds and the timestamp are fixed.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

import export
import schema_check
import splats
import spz
import synth_world as sw

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "fixture-ladder"
DENSITY = 250
STAMP = "2026-11-23T00:00:00Z"
H_FOV, V_FOV = 66.0, 51.94
C = sw.PANO_W.copy()
REAL_X_MAX = sw.DOOR_X + 0.02
FAN_START_M = 0.25
README = """# Ladder fixture (synthetic)

Made by `pipeline/make_ladder_fixture.py`, not from any capture or any Marble world: the viewer fixture's
synthetic room and Marble-like world, split per rung into seen, imagined and wrong by the rung's own
frustums. The shown shares come from the frustums; the imagined shares and the scan's agreement are made
up. R4r is written as not placed. `ladder.json` follows `pipeline/schema/ladder.schema.json`.
Regenerate with `uv run python make_ladder_fixture.py` in `pipeline/`.
"""

# id, label, photos, mode, azimuths (degrees from +x towards +z; 0 faces the door), world seed, furniture it misplaces
RUNGS = [
    ("R1", "1 photo", 1, "flat", [0], 11, ("shelf", "bed")),
    ("R2", "2 photos", 2, "flat", [0, 180], 12, ("shelf", "bed")),
    ("R4", "4 photos", 4, "flat", [0, 90, 180, 270], 13, ("shelf",)),
    ("R4b", "4 photos (second seed)", 4, "flat", [0, 90, 180, 270], 14, ("bed",)),
    ("R8", "8 photos", 8, "reconstruction", list(range(0, 360, 45)), 15, ()),
    ("R4r", "4 photos, reconstruction mode", 4, "reconstruction", [0, 90, 180, 270], 16, ()),
    ("P", "the 360 still", 0, "pano", [], 17, ()),
]
STEPS = ["R1", "R2", "R4", "R8", "P"]
NOT_PLACED = {"R4r"}
PHONE_FILES = {"P"}
# Made up: how far each world's imagined share sits above the floor 1 - s; and the scan's agreement with COLMAP.
IMAGINED_ABOVE_FLOOR = {"R1": 0.03, "R2": 0.05, "R4": 0.08, "R4b": 0.11, "R8": 0.10, "P": 0.03}
KEY_AGREEMENT = {"R1": (0.31, 0.44), "R2": (0.36, 0.52), "R4": (0.58, 0.71), "R4b": (0.58, 0.71),
                 "R8": (0.66, 0.79), "R4r": (0.58, 0.71), "P": (0.72, 0.84)}
# How far each piece of furniture lands from where it is, when a world misplaces it (metres, world frame).
MISPLACE = {"shelf": np.array([0.0, 0.0, 0.55]), "bed": np.array([0.0, 0.0, -0.6])}


def forward(az_deg: float) -> np.ndarray:
    a = np.radians(az_deg)
    return np.array([np.cos(a), 0.0, np.sin(a)])


def frustums(azimuths: list[float]) -> list[dict]:
    return [{"forward": [round(float(v), 9) + 0.0 for v in forward(a)], "up": [0.0, 1.0, 0.0], "hFovDeg": H_FOV, "vFovDeg": V_FOV}
            for a in azimuths]


def in_any(dirs: np.ndarray, azimuths: list[float]) -> np.ndarray:
    """Directions (not necessarily unit) inside any of the views; every direction for the pano."""
    if not azimuths:
        return np.ones(len(dirs), bool)
    up = np.array([0.0, 1.0, 0.0])
    out = np.zeros(len(dirs), bool)
    th, tv = np.tan(np.radians(H_FOV / 2)), np.tan(np.radians(V_FOV / 2))
    for a in azimuths:
        f = forward(a)
        right = np.cross(f, up)
        z = dirs @ f
        zs = np.where(z > 1e-9, z, 1.0)
        out |= (z > 1e-9) & (np.abs(dirs @ right) / zs <= th) & (np.abs(dirs @ up) / zs <= tv)
    return out


def sphere(n: int = 200_000) -> np.ndarray:
    """Evenly spread unit directions (a Fibonacci sphere)."""
    i = np.arange(n) + 0.5
    y = 1 - 2 * i / n
    r = np.sqrt(1 - y * y)
    phi = np.pi * (3 - np.sqrt(5)) * i
    return np.stack([r * np.cos(phi), y, r * np.sin(phi)], 1)


def through_door(dirs: np.ndarray) -> np.ndarray:
    """Directions from c that leave the room through the door opening (the hallway, which the key scores apart)."""
    t = (sw.DOOR_X - C[0]) / np.where(dirs[:, 0] > 1e-9, dirs[:, 0], np.inf)
    hit = C + t[:, None] * dirs
    return (dirs[:, 0] > 1e-9) & (np.abs(hit[:, 2]) < sw.DOOR_HALF) & (hit[:, 1] > 0) & (hit[:, 1] < sw.DOOR_H)


def world(seed: int, misplaced: tuple[str, ...], azimuths: list[float]):
    """The rung's Marble-like world in the world frame, and its classes: 0 seen, 1 imagined, 2 wrong."""
    rng = np.random.default_rng(seed)
    groups: list[tuple[str, list]] = []
    for f in sw.room_faces():
        name = f.paint if f.paint in ("bed", "desk", "shelf") else "room"
        if groups and groups[-1][0] == name:
            groups[-1][1].append(f)
        else:
            groups.append((name, [f]))
    groups.append(("hall", sw.hall_faces(3.1, real=False)))
    parts = []
    for name, faces in groups:
        xyz, rgb, n, t = sw.sample(faces, DENSITY, rng, shift=0.06, noise=0.01)
        cls = np.ones(len(xyz), int)
        seen = in_any(xyz - C, azimuths) & (xyz[:, 0] <= REAL_X_MAX)
        if name == "hall":
            cls[:] = 2
        elif name in misplaced and seen.mean() < 0.5:
            # A world that never saw a piece of furniture can put all of it somewhere else.
            xyz = xyz + MISPLACE[name]
            cls[:] = 2
        else:
            cls[seen] = 0
        parts.append((xyz, rgb, n, t, cls))
    return [np.concatenate([p[i] for p in parts]) for i in range(5)]


ROOM_LO, ROOM_HI = sw.ROOM[0][[0, 2]], sw.ROOM[1][[0, 2]]


def to_wall(theta: np.ndarray) -> np.ndarray:
    """Plan-view points where rays from c at these angles (radians, from +x towards +z) meet the room's walls."""
    d = np.stack([np.cos(theta), np.sin(theta)], 1)
    c = C[[0, 2]]
    with np.errstate(divide="ignore"):
        tx = np.where(d[:, 0] > 0, (ROOM_HI[0] - c[0]) / d[:, 0], (ROOM_LO[0] - c[0]) / d[:, 0])
        tz = np.where(d[:, 1] > 0, (ROOM_HI[1] - c[1]) / d[:, 1], (ROOM_LO[1] - c[1]) / d[:, 1])
    t = np.minimum(np.abs(tx), np.abs(tz))
    return c + t[:, None] * d


def intervals(azimuths: list[float]) -> list[tuple[float, float]] | None:
    """The union of the views' horizontal spans, in degrees; None when they go all the way round."""
    spans = sorted(((a - H_FOV / 2) % 360, (a - H_FOV / 2) % 360 + H_FOV) for a in azimuths)
    merged: list[list[float]] = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    if len(merged) > 1 and merged[-1][1] >= merged[0][0] + 360:
        merged[0][0] = merged.pop()[0] - 360
    if any(hi - lo >= 360 for lo, hi in merged):
        return None
    return [(lo, hi) for lo, hi in merged]


def pt(p) -> list[float]:
    return [round(float(p[0]), 3) + 0.0, round(float(p[1]), 3) + 0.0]


def plan(azimuths: list[float]) -> dict:
    c = C[[0, 2]]
    spans = intervals(azimuths) if azimuths else None
    if spans is None:
        corners = [(ROOM_LO[0], ROOM_LO[1]), (ROOM_HI[0], ROOM_LO[1]), (ROOM_HI[0], ROOM_HI[1]), (ROOM_LO[0], ROOM_HI[1])]
        return {"seenFloor": [[pt(p) for p in corners + corners[:1]]], "coastline": []}
    floor, coast = [], []
    for lo, hi in spans:
        theta = np.radians(np.linspace(lo, hi, max(3, int((hi - lo) / 2) + 1)))
        edge = to_wall(theta)
        floor.append([pt(c)] + [pt(p) for p in edge] + [pt(c)])
        for a in (theta[0], theta[-1]):
            d = np.array([np.cos(a), np.sin(a)])
            coast.append([pt(c + FAN_START_M * d), pt(to_wall(np.array([a]))[0])])
    return {"seenFloor": floor, "coastline": coast}


def write_files(folder: Path, name: str, xyz, rgb, n, t, cls, keep: np.ndarray | None = None) -> dict:
    m = sw.world_from_marble_true()
    size = sw.splat_size(DENSITY)
    xyz_r, n_r, t_r = sw.to_native(m, xyz, n, t)
    files = {}
    with tempfile.TemporaryDirectory() as tmp:
        jobs = []
        counts = {}
        for key, k in (("seen", 0), ("imagined", 1), ("wrong", 2)):
            sel = cls == k if keep is None else (cls == k) & keep
            if not sel.any():
                raise ValueError(f"{folder.name}: no {key} splats; every class needs at least one")
            ply = Path(tmp) / f"{key}.ply"
            splats.write_splats(ply, xyz_r[sel], rgb[sel], n_r[sel], t_r[sel], size=size / sw.MSF_TRUE, thickness=0.002 / sw.MSF_TRUE)
            jobs.append((ply, folder / f"{key}{name}.spz"))
            counts[key] = int(sel.sum())
        folder.mkdir(parents=True, exist_ok=True)
        spz.transcode(jobs, max_sh=0)
        for key, (_, out) in zip(("seen", "imagined", "wrong"), jobs):
            entry = export.splat_entry(out, counts[key], 0 if key == "seen" else 1, m)
            entry["url"] = f"{folder.name}/{out.name}"
            files[key] = entry
    return files


def build(out: Path, log=print) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    dirs = sphere()
    door = through_door(dirs)
    rungs = []
    for rid, label, photos, mode, az, seed, misplaced in RUNGS:
        shown = float(in_any(dirs, az).mean())
        s = float((in_any(dirs, az) & ~door).sum() / (~door).sum())
        placed = rid not in NOT_PLACED
        w15, w30 = KEY_AGREEMENT[rid]
        rung = {"id": rid, "label": label, "photos": photos, "mode": mode, "placed": placed,
                "shown": round(shown, 4), "imagined": round(min(1.0, 1 - s + IMAGINED_ABOVE_FLOOR[rid]), 4) if placed else None,
                "seenShareOfKey": round(s, 4), "keyAgreement": {"within15": w15, "within30": w30},
                "frustums": frustums(az)}
        if placed:
            xyz, rgb, n, t, cls = world(seed, misplaced, az)
            rung["splats"] = write_files(out / rid, "", xyz, rgb, n, t, cls)
            if rid in PHONE_FILES:
                keep = np.random.default_rng(seed).random(len(xyz)) < 0.5
                rung["splatsPhone"] = write_files(out / rid, "-phone", xyz, rgb, n, t, cls, keep)
            rung["map"] = plan(az)
            log(f"{rid}: shown {shown:.3f}, s {s:.3f}, splats {len(xyz)}")
        else:
            log(f"{rid}: not placed")
        rung["worldId"] = f"fixture-{rid.lower()}"
        rung["model"] = "marble-1.1-plus"
        rungs.append(rung)
    doc = {"schemaVersion": 1, "units": "m", "generatedAt": STAMP, "camera": {"c": [float(v) for v in C]},
           "steps": STEPS, "rungs": rungs, "credit": export.CREDIT}
    schema_check.check(doc, "ladder.schema.json")
    (out / "ladder.json").write_text(json.dumps(doc, indent=1) + "\n")
    (out / "README.md").write_text(README)
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    build(args.out)
    total = sum(p.stat().st_size for p in args.out.rglob("*") if p.is_file())
    print(f"ladder fixture written: {args.out} ({total / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

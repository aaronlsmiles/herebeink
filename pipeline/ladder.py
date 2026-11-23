"""Part 2's scoring: each placed rung's world, direction by direction from c, against the frozen answer key.

    uv run python ladder.py                 # every placed rung in ladder_worlds.json
    uv run python ladder.py --rung R4       # one

The rules are STATUS's "Part 2 criteria (frozen 22 Nov 2026)" with Amendments 1 and 2. Marble's placed world
(its splats at opacity 0.2 or more) is rendered from c by the key's own recipe, so each direction has one
Marble surface and one key surface, and falls in exactly one class:

- seen: inside a frustum, Marble within tau of the key;
- imagined and right: outside every frustum, Marble within tau of the key;
- imagined and wrong: Marble beyond tau where the key says what is there (in view or not); past the door
  plane only where Marble's surface lies within 0.5 m of a hallway key point;
- empty: a key surface but no Marble surface (reported, counted as neither);
- unscored: no key surface (not scanned), the key surface outside the scored volume V (outside), or past the
  door with no key point near Marble's surface (hall unscored).

The published shares are direction counts weighted by solid angle. Per-splat classes only colour the page.
Right, wrong and completeness are written to work/ladder/ (gitignored) and never to a public file
(publication stance A): the public outputs are the seen and imagined shares and the page's splat files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

import door_edge
import splats
import visibility as vis

WORK = Path(__file__).resolve().parent / "work"
WORLDS = Path(__file__).resolve().parent / "ladder_worlds.json"
TAU_M = vis.TAU_M
SENSITIVITY_M = (0.05, 0.30)
HALL_NEAR_M = 0.5
CLASSES = ("seen", "right", "wrong", "empty", "notScanned", "outside", "hallUnscored")
SEEN, IMAGINED, WRONG = 0, 1, 2


def classify(key, in_v, past, marble, frustum, hall_ok, tau: float = TAU_M) -> dict:
    """Per-direction classes on the panorama grid. key, marble: depth from c (inf where no surface); in_v: the
    key surface lies inside V; past: the key surface lies past the door plane; hall_ok: Marble's surface point
    lies within 0.5 m of a hallway key point; frustum: the direction is inside one of the rung's views."""
    has_key, has_m = np.isfinite(key), np.isfinite(marble)
    scored = has_key & in_v
    close = scored & has_m & (np.abs(np.where(has_m, marble, 0) - np.where(has_key, key, 0)) <= tau)
    far = scored & has_m & ~close
    return {"seen": close & frustum, "right": close & ~frustum, "wrong": far & (~past | hall_ok),
            "empty": scored & ~has_m, "notScanned": ~has_key, "outside": has_key & ~in_v,
            "hallUnscored": far & past & ~hall_ok}


def shares(c: dict, wt: np.ndarray, frustum: np.ndarray) -> dict:
    """Shares of the scored directions (seen, imagined, empty), of the imagined (imaginedRight), of the scored
    directions out of view (completeness), and of all directions (scored, notScanned, outside, hallUnscored)."""
    w = lambda m: float(wt[m].sum())  # noqa: E731
    total = float(wt.sum())
    scored = c["seen"] | c["right"] | c["wrong"] | c["empty"]
    s = w(scored)
    imagined = w(c["right"]) + w(c["wrong"])
    out_of_view = w(scored & ~frustum)
    return {"scored": w(scored) / total, "seen": w(c["seen"]) / s, "imagined": imagined / s, "empty": w(c["empty"]) / s,
            "imaginedRight": w(c["right"]) / imagined if imagined else None,
            "completeness": w(c["right"]) / out_of_view if out_of_view else None,
            "notScanned": w(c["notScanned"]) / total, "outside": w(c["outside"]) / total,
            "hallUnscored": w(c["hallUnscored"]) / total}


def splat_classes(key_flat, cell, r, in_v, past, near_key_pt, frustum, tau: float = TAU_M) -> np.ndarray:
    """Each splat by its own distance to the key along its ray: SEEN (in view, within tau), WRONG (beyond tau,
    inside V, where the key says what is there) or IMAGINED (everything else, the right ones included)."""
    k = key_flat[cell]
    has = np.isfinite(k)
    close = has & (np.abs(r - np.where(has, k, 0)) <= tau)
    wrong = has & ~close & in_v & (~past | near_key_pt)
    out = np.full(len(r), IMAGINED, np.int8)
    out[close & frustum] = SEEN
    out[wrong] = WRONG
    return out


def kr3(values: dict) -> dict:
    """Frozen KR3 for one quantity: R4's two seeds against the smaller neighbouring step (R4 their mean)."""
    r4 = (values["R4"] + values["R4b"]) / 2
    steps = [abs(r4 - values[n]) for n in ("R2", "R8") if values.get(n) is not None]
    gap = abs(values["R4"] - values["R4b"])
    smaller = min(steps)
    return {"seedGap": gap, "smallerStep": smaller, "withinNoise": bool(gap > smaller)}


# ---- the run on real data ----

def frustum_mask(manifest: dict, rung: str, deg: float) -> np.ndarray:
    dirs, _ = vis.equirect_dirs(deg)
    return vis.in_rung(dirs.reshape(-1, 3), manifest, "R4" if rung == "R4b" else rung).reshape(vis.grid(deg))


def manifest_rung(rung: str) -> str:
    return "R4" if rung == "R4b" else rung


def marble_placed(work: Path, world_id: str):
    align = json.loads((work / "align" / world_id / "align.json").read_text())
    t = np.array(align["world_from_marble"], float)
    ply = splats.read(work / "marble" / f"marble_{world_id}.ply", quiet=True)
    v = ply["vertex"].data
    xyz = splats.apply(t, splats.centres(ply))
    sigma = np.exp(np.stack([v["scale_0"], v["scale_1"], v["scale_2"]], 1).astype(float)).max(1) * splats.split(t)[0]
    return align, t, ply, xyz, splats.opacity(ply), sigma


def score_rung(work: Path, rung: str, world_id: str, ctx: dict, deg: float = vis.DEG) -> dict:
    pose, key, key_flat = ctx["pose"], ctx["key"], ctx["key"].reshape(-1)
    align, t, ply, xyz, op, sigma = marble_placed(work, world_id)
    if not align["gateA"]["pass"]:
        return {"rung": rung, "worldId": world_id, "placed": False}
    marble = vis.footprint_depth(pose, xyz, op, sigma, "rendered", deg, min_opacity=vis.OPAQUE_MIN)
    frustum = np.ones(key.shape, bool) if rung == "P" else frustum_mask(ctx["manifest"], rung, deg)
    dirs, wt = vis.equirect_dirs(deg)
    m_ok = np.isfinite(marble)
    m_pts = np.full(dirs.shape, np.nan)
    m_pts[m_ok] = pose.c_world + vis.world_dirs(pose, dirs[m_ok]) * marble[m_ok][:, None]
    hall_ok = np.zeros(key.shape, bool)
    if len(ctx["key_pts"]):
        d, _ = ctx["key_tree"].query(m_pts[m_ok], workers=-1)
        hall_ok[m_ok] = d <= HALL_NEAR_M
    out = {"rung": rung, "worldId": world_id, "placed": True, "cellDeg": deg,
           "shareOfDirections": round(float(wt[frustum].sum()), 4), "byTau": {}}
    for tau in (TAU_M, *SENSITIVITY_M):
        c = classify(key, ctx["in_v"], ctx["past"], marble, frustum, hall_ok, tau)
        s = shares(c, wt, frustum)
        s["seenPastDoor"] = float(wt[c["seen"] & ctx["past"]].sum() / wt[c["seen"] | c["right"] | c["wrong"] | c["empty"]].sum())
        out["byTau"][str(tau)] = {k: (None if v is None else round(v, 4)) for k, v in s.items()}
        if tau == TAU_M:
            classes = c
    # the instrument's own error in this rung's scored view, hallway key-point cells left out
    scored = classes["seen"] | classes["right"] | classes["wrong"] | classes["empty"]
    mask = scored & frustum & ctx["not_key_pt"]
    out["keyAgreesWithColmap"] = {str(tau): vis.agreement(key, ctx["colmap"], wt, mask, tau=tau) for tau in (0.15, 0.30)}
    out["counts"] = {k: int(v.sum()) for k, v in classes.items()}

    # per splat, for the page's colours
    rd, r = vis.rig_dirs(pose, xyz)
    row, col = vis.cell_of(rd, deg)
    cell = row * key.shape[1] + col
    in_v = ctx["volume"].contains(xyz)
    past = door_edge.past_plane(xyz, ctx["scale"])
    near = np.zeros(len(xyz), bool)
    if len(ctx["key_pts"]) and past.any():
        d, _ = ctx["key_tree"].query(xyz[past], workers=-1)
        near[past] = d <= HALL_NEAR_M
    in_frustum = np.ones(len(xyz), bool) if rung == "P" else vis.in_rung(rd, ctx["manifest"], manifest_rung(rung))
    k = splat_classes(key_flat, cell, r, in_v, past, near, in_frustum, TAU_M)
    out["splats"] = {"seen": int((k == SEEN).sum()), "imagined": int((k == IMAGINED).sum()), "wrong": int((k == WRONG).sum())}
    return {**out, "_classes": k, "_ply": ply, "_t": t, "_xyz": xyz, "_op": op, "_align": align}


def context(work: Path, deg: float = vis.DEG) -> dict:
    scale = json.loads((work / "scale.json").read_text())
    manifest = json.loads((work / "ladder" / "views" / "manifest.json").read_text())
    pose, key = vis.answer_key_depth(work, "rendered", deg)
    kp, kc = vis.key_points(work)
    pts, _ = vis.surface_points(pose, key)
    volume = vis.ScoredVolume.build(pts, scale["door"], kp, kc)
    finite = np.isfinite(key)
    in_v = np.zeros(key.shape, bool)
    in_v[finite] = volume.contains(pts)
    past = np.zeros(key.shape, bool)
    past[finite] = door_edge.past_plane(pts, scale)
    return {"scale": scale, "manifest": manifest, "pose": pose, "key": key, "in_v": in_v, "past": past, "volume": volume,
            "key_pts": kp, "key_tree": cKDTree(kp) if len(kp) else None, "colmap": vis.colmap_depth(pose, work, deg),
            "not_key_pt": ~np.isfinite(vis.point_depth(pose, kp, deg))}


def worlds(path: Path = WORLDS) -> dict:
    return json.loads(path.read_text())["rungs"]


def run(work: Path, only: list[str] | None = None, write_files=None) -> dict:
    ctx = context(work)
    results = {}
    for rung, world_id in worlds().items():
        if only and rung not in only:
            continue
        r = score_rung(work, rung, world_id, ctx)
        if write_files is not None and r["placed"]:
            write_files(work, rung, r, ctx)
        results[rung] = {k: v for k, v in r.items() if not k.startswith("_")}
        d = work / "ladder" / rung
        d.mkdir(parents=True, exist_ok=True)
        (d / "counts.json").write_text(json.dumps(results[rung], indent=1) + "\n")
    placed = {k: v for k, v in results.items() if v["placed"]}
    summary_path = work / "ladder" / "scores.json"
    old = json.loads(summary_path.read_text())["rungs"] if summary_path.exists() else {}
    old.update(results)
    doc = {"rungs": old, "tauM": TAU_M}
    q = {"imagined": "imagined", "imaginedRight": "imaginedRight"}
    if all(n in old and old[n]["placed"] for n in ("R4", "R4b")):
        doc["kr3"] = {name: kr3({n: old[n]["byTau"][str(TAU_M)][key] for n in ("R2", "R4", "R4b", "R8")
                                 if n in old and old[n]["placed"]}) for name, key in q.items()}
    summary_path.write_text(json.dumps(doc, indent=1) + "\n")
    return {"rungs": placed, **({"kr3": doc["kr3"]} if "kr3" in doc else {})}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=WORK)
    ap.add_argument("--rung", action="append", default=None)
    ap.add_argument("--no-files", action="store_true", help="score only; write no splat files for the page")
    a = ap.parse_args(argv)
    import ladder_export
    doc = run(a.work, a.rung, None if a.no_files else ladder_export.write_rung)
    for rung, r in doc["rungs"].items():
        s = r["byTau"][str(TAU_M)]
        print(f"{rung:4s} shown {r['shareOfDirections']:.3f}; of the scored directions seen {s['seen']:.3f}, imagined "
              f"{s['imagined']:.3f}, empty {s['empty']:.3f}; not scanned {s['notScanned']:.3f} of all")
    print(f"written: {a.work / 'ladder' / 'scores.json'} (right, wrong and completeness stay there: stance A)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

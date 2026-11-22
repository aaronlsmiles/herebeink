"""The kill rule's second stage: a Marble world made from a still at the threshold, aligned on the door frame.

    uv run python align.py --world WORLD_ID --mode doorway --notes ../capture/NOTES.md
    ./run_part2.sh WORLD_ID doorway

It may never run: it is for when the pano world fails Gate A twice. The door frame's four inside corners
are known in the measured frame: A and B where the jambs meet the floor, E and F at the top (clicked in
door_points.py's page like the others, so scale.json has them). In Marble's world they are picked by hand,
because the still Marble was made from is not registered in COLMAP: open marble_<id>.ply in SuperSplat,
pick the same four corners in the order A B E F, and paste the four positions SuperSplat shows on one line
of NOTES.md:

    - Doorway corners in the Marble world (A B E F, four 3D points): x y z ; x y z ; x y z ; x y z

SuperSplat may show a file turned over, so the file's frame and the two half-turns door_points.py tries are
tried here too, and the picks must lie on Marble's splat. A similarity (Umeyama, with scale) from the four
corners starts it. The corners are coplanar, so a mirror through the door's plane fits them exactly as
well: both handednesses go on to rigid ICP on the centres within 0.5 m of the frame, and the one that ends
closer to the measured frame region (both ways, as align.two_way) is kept. Scale stays the corners': on a
region this small, ICP's scaling round drifted (47 cm at the hallway's end on the synthetic doorway). The
frozen residual is then read exactly as in the pano mode, over every Marble centre. Gate A here is
the residual, the four corners' fit (5 cm RMS at most), the gravity check and the metric factor's range;
the photometric check does not apply (the threshold still is not registered) and nor does the ICP share
(a world made at the threshold looks mostly away from the measured room).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

import align
import door_points
import splats

PICK_RE = re.compile(r"^- Doorway corners in the Marble world \(A B E F, four 3D points\):[ \t]*(.*)$", re.M)
NEAR_FRAME_M = 0.5
MAX_CORNER_RMS_M = 0.05
# A pick sits on the splat when a centre lies within this share of Marble's extent: a person picks a
# splat, and splats near a frame's corner are a centimetre or two apart.
ON_SPLAT_SHARE = 0.01


def umeyama(src: np.ndarray, dst: np.ndarray, reflect: bool = False) -> np.ndarray:
    """The similarity (scale, rotation, translation) taking src onto dst in least squares; with reflect, the
    orthogonal part is improper."""
    mu_s, mu_d = src.mean(axis=0), dst.mean(axis=0)
    a, b = src - mu_s, dst - mu_d
    u, sig, vt = np.linalg.svd(b.T @ a / len(src))
    d = np.ones(3)
    want = -1.0 if reflect else 1.0
    if np.sign(np.linalg.det(u) * np.linalg.det(vt)) != want:
        d[-1] = -1.0
    r = u @ np.diag(d) @ vt
    s = (sig * d).sum() / (a * a).sum() * len(src)
    m = np.eye(4)
    m[:3, :3] = s * r
    m[:3, 3] = mu_d - s * r @ mu_s
    return m


def read_picks(notes: str) -> np.ndarray:
    m = PICK_RE.search(notes)
    if not m:
        raise ValueError("no '- Doorway corners in the Marble world (A B E F, four 3D points):' line in NOTES.md; "
                         "pick the four corners in SuperSplat (see doorway.py)")
    parts = [p.split() for p in m.group(1).split(";")]
    if len(parts) != 4 or any(len(p) != 3 for p in parts):
        raise ValueError("the doorway corners line needs four points of three numbers, separated by ';'")
    return np.array([[float(v) for v in p] for p in parts])


def as_stored(picks: np.ndarray, centres: np.ndarray) -> tuple[str, np.ndarray]:
    """The picks in the file's own frame: the display turn under which they sit on the splat."""
    tree = cKDTree(centres)
    extent = float(np.ptp(centres, axis=0).max())
    best = None
    for label, flip in door_points.FLIPS.items():
        pts = picks @ flip.T
        d, _ = tree.query(pts)
        if best is None or d.max() < best[2].max():
            best = (label, pts, d)
    label, pts, d = best
    if d.max() > ON_SPLAT_SHARE * extent:
        raise ValueError(f"the picked corners do not sit on Marble's splat in any frame tried (worst {d.max():.3g} units "
                         "from a centre); pick them again on the splat")
    return label, pts


def run(work: Path, world_id: str, notes: Path, accept_by_eye: str | None = None) -> dict:
    scale = json.loads((work / "scale.json").read_text())
    door = scale["door"]
    if "top" not in door:
        raise ValueError("scale.json has no top corners: click E and F (the frame's top inside corners) in "
                         "work/door/pick.html, paste them into NOTES.md and run the scale stage again")
    corners = np.array([door["a"], door["b"], door["top"][0], door["top"][1]])
    w_from_c = np.array(scale["world_from_colmap"])
    world = json.loads((work / "marble" / f"{world_id}.json").read_text())
    msf, ground = align.metric_factor(world)
    measured = splats.apply(w_from_c, splats.centres(splats.read(work / "splat" / "measured.ply")))
    marble_raw = splats.centres(splats.read(work / "marble" / f"marble_{world_id}.ply"))
    shown, picks = as_stored(read_picks(notes.read_text()), marble_raw)

    lo, hi = corners.min(axis=0) - NEAR_FRAME_M, corners.max(axis=0) + NEAR_FRAME_M
    near = measured[np.all((measured >= lo) & (measured <= hi), axis=1)]
    tree_near, target = cKDTree(near), align.cloud(near, normals=True)
    fits = []
    for reflect in (False, True):
        start = umeyama(picks, corners, reflect)
        rms = float(np.sqrt(np.mean(np.sum((splats.apply(start, picks) - corners) ** 2, axis=1))))
        t = align.icp(start, marble_raw, tree_near, target, scale_round=False, gate_m=NEAR_FRAME_M)
        moved = splats.apply(t, marble_raw)
        inside = marble_raw[np.all((moved >= lo) & (moved <= hi), axis=1)]
        score = align.two_way(t, inside, tree_near, near) if len(inside) else np.inf
        fits.append((score, rms, reflect, start, t))
    _, rms0, mirrored, t0, t = min(fits, key=lambda f: f[0])
    corner_rms = float(np.sqrt(np.mean(np.sum((splats.apply(t, picks) - corners) ** 2, axis=1))))
    down = min((align.gravity_deg(t, flip), flip) for flip in (False, True))
    res = align.residual(t, marble_raw, cKDTree(measured))
    s_final = splats.split(t)[0]
    r = {"world_from_marble": t.tolist(), "initial": t0.tolist(), "mode": "doorway",
         "hypothesis": {"yawDeg": 0, "mirror": bool(mirrored), "flip": bool(down[1]), "rawDown": "-y" if down[1] else "+y"},
         "picks": {"shownAs": shown, "cornerRmsBeforeIcpM": round(rms0, 4),
                   "twoWayCmByHandedness": {("mirrored" if f[2] else "as is"): round(float(f[0]) * 100, 2) for f in fits}},
         "chosen": {"gravityDeg": round(down[0], 2), "rawDown": "-y" if down[1] else "+y"},
         "scale": {"metricFactor": msf, "metresPerRawUnit": s_final, "ratioToMetricFactor": round(s_final / msf, 5),
                   "from": "the four door corners"},
         "residual": res, "marbleSplats": int(len(marble_raw))}
    full = align.gate({**r, "photometric": {"score": None, "reason": "n/a"}}, accept_by_eye)
    reasons = [x for x in full["reasons"] if not x.startswith("photometric") and "ICP set holds" not in x]
    corner_fit = {"pass": corner_rms <= MAX_CORNER_RMS_M, "rmsM": round(corner_rms, 4), "limitM": MAX_CORNER_RMS_M}
    if not corner_fit["pass"]:
        reasons.append(f"the four door corners fit to {corner_rms * 100:.1f} cm RMS (limit {MAX_CORNER_RMS_M * 100:.0f} cm): "
                       "a pick is on the wrong corner, or in the wrong order (A B E F)")
    automatic = full["gravity"]["pass"] and full["metricRatio"]["pass"] and corner_fit["pass"]
    r["gateA"] = {"thresholdCm": align.GATE_A_CM, "residualPass": full["residualPass"],
                  "pass": bool(full["residualPass"] and (automatic or bool(accept_by_eye))),
                  "gravity": full["gravity"], "metricRatio": full["metricRatio"], "cornerFit": corner_fit,
                  "acceptedByEye": accept_by_eye or None, "reasons": reasons}
    r.update({"worldId": world_id, "model": world.get("model"), "groundPlaneOffset": ground, "note": align.NOTE,
              "panoHeightM": float(scale["pano"][1])})
    out = work / "align" / world_id
    r["contactSheet"] = str(align.contact_sheet(measured, marble_raw, t0, t, out / "contact.png", door["centre"], scale["pano"]))
    align.write_json(out / "align.json", r)
    return r


def main(args) -> int:
    r = run(args.work, args.world, args.notes, args.accept_by_eye)
    g, res = r["gateA"], r["residual"]
    print(f"doorway: picks as SuperSplat showed them ({r['picks']['shownAs']}); corners fit to "
          f"{g['cornerFit']['rmsM'] * 100:.1f} cm RMS after ICP{' (mirrored)' if r['hypothesis']['mirror'] else ''}")
    if res["medianCm"] is not None:
        print(f"residual: median {res['medianCm']:.2f} cm, 90th percentile {res['p90Cm']:.2f} cm, over {res['icpSet']} "
              "Marble centres within 1 m of a measured centre")
    for reason in g["reasons"]:
        print(f"  - {reason}")
    print(f"Gate A (doorway): {'PASS' if g['pass'] else 'FAIL'}. {align.NOTE}")
    print(f"written: {args.work / 'align' / args.world / 'align.json'}, {r['contactSheet']}")
    return 0 if g["pass"] else 1

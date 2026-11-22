"""Scale, floor and the world frame for the measured splat: work/scale.json.

    uv run python scale.py

The world frame: metres, the floor at y = 0 and +y up, the room's long axis along +x (signed so the door
is on the +x side of the pano), origin on the floor under the pano still. It is one similarity
(world_from_colmap) applied to COLMAP's frame; no splat file is rewritten.

- Scale: door width by tape over the distance between the two door corners (door_points.py), checked
  against the second tape length.
- Up: COLMAP's frame has no up; the cameras do. The X3 was held upright, so the mean of the cameras'
  "down" axes gives up to within a few degrees; the floor plane then sets it exactly.
- Floor: RANSAC plane through the lowest 20 % of splat centres along that up (2 cm inliers), turned so
  the cameras are above it. It must pass within 3 cm of both door corners (clicked where the jambs meet
  the floor) and put the head pass's cameras 1.2 to 2.0 m up and the hip pass's 0.6 to 1.3 m. A glossy
  floor reflects the ceiling under it, and the lowest points are then the reflection; so when the first
  plane fails, a second search keeps only planes through both door corners. When the splat shows too little
  floor for either (the cut views look level or up, and a dark carpet gives few splats), the floor is the
  level plane through the door corners: at right angles to the cameras' up. Every route must stay within
  5 degrees of that up. If none passes, scale.py stops with the numbers.
- Evidence: each clicked corner's reprojection RMS (3 px at most) and the widest angle between its rays
  (5 degrees at least), the corners' height above the floor, the camera heights, the floor's tilt from the
  cameras' up and the check length (within 1.5 %) are checked; any failure stops scale.py with what to do,
  unless --accept "reason" is given, which scale.json and scene.json record. Two tape readings more than 5 mm apart are a warning.
- Long axis: the rotation that gives the smallest rectangle round the walls (splat centres 0.3 to 2.0 m up).
- Walkable: every floor cell within 0.5 m of the head pass's path (the path dilated, which is what an
  alpha shape of the path would give for a loop and a figure of eight, without its radius to tune).
- Start: the pano's position at eye height, looking at the door's centre.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial.transform import Rotation

import door_points
import grid2d
import splats
from colmap_model import Model, read_model

EYE_HEIGHT = 1.6
FLOOR_SHARE = 0.20
FLOOR_INLIER_M = 0.02
CORNER_ON_FLOOR_M = 0.03
CAMERA_HEIGHTS_M = {"head": (1.2, 2.0), "hip": (0.6, 1.3)}
MAX_CHECK_ERROR_PCT = 1.5
TAPE_WARN_MM = 5.0
FLOOR_SEARCH_POINTS = 200_000
# A real floor stays within a few degrees of the cameras' up (the real room's door jambs stood within 0.5 degrees
# of it); a plane through the door corners free to lean further can swing up into a desk top.
MAX_FLOOR_TILT_DEG = 5.0
# A plane forced through two corners always exists; it is the floor only if about as many centres lie on it
# as on the plane it replaces (a reflected ceiling is a whole plane too, a strip along a mis-clicked jamb is not).
MIN_FLOOR_SUPPORT = 0.5
WALL_BAND_M = (0.3, 2.0)
WALK_DILATE_M = 0.5
GRID_M = 0.1
TAPE_RE = re.compile(r"^- \*\*Door frame inside width \(tape\), in metres:\*\*[ \t]*([0-9]*\.?[0-9]+)", re.M)
TAPE2_RE = re.compile(r"^- Door frame inside width, second tape \(cross-check\), in metres:[ \t]*([0-9]*\.?[0-9]+)", re.M)
CHECK_RE = re.compile(r"^- Check length \(what it is, and its length in metres\):[ \t]*(.*?)[ \t,]*([0-9]*\.?[0-9]+)[ \t]*m?[ \t]*$", re.M)


def camera_centres(model: Model) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Frame name -> (centre, camera-from-model rotation) for each sphere's reference view."""
    out = {}
    for im in model.images.values():
        if im.name.startswith("rig/y000p00/"):
            r = Rotation.from_quat(im.qvec, scalar_first=True).as_matrix()
            out[Path(im.name).stem] = (-r.T @ np.array(im.tvec), r)
    return out


def up_from_cameras(cams) -> np.ndarray:
    down = np.mean([r[1] for _, r in cams.values()], axis=0)
    return -down / np.linalg.norm(down)


def fit_plane(p: np.ndarray) -> tuple[np.ndarray, float]:
    """Least-squares plane (unit normal n, offset d with n . x = d) from the 3 x 3 covariance; an SVD of the
    points themselves would build an n x n matrix (8 GB killed it at 1.5M splats)."""
    centroid = p.mean(axis=0)
    q = p - centroid
    n = np.linalg.eigh(q.T @ q)[1][:, 0]
    return n, float(n @ centroid)


def ransac_plane(pts: np.ndarray, inlier: float, rng: np.random.Generator, iters: int = 400) -> tuple[np.ndarray, float, np.ndarray]:
    best = None
    for _ in range(iters):
        a, b, c = pts[rng.choice(len(pts), 3, replace=False)]
        n = np.cross(b - a, c - a)
        if np.linalg.norm(n) < 1e-12:
            continue
        n /= np.linalg.norm(n)
        inl = np.abs((pts - a) @ n) < inlier
        if best is None or inl.sum() > best.sum():
            best = inl
    n, d = fit_plane(pts[best])
    return n, d, best


def plane_through(a: np.ndarray, b: np.ndarray, sub: np.ndarray, up: np.ndarray, inlier: float,
                  rng: np.random.Generator, iters: int = 400) -> tuple[np.ndarray, float, np.ndarray] | None:
    """The plane through both door corners (and a third point from the splat) that most centres lie on."""
    best = None
    for _ in range(iters):
        c = sub[rng.integers(len(sub))]
        n = np.cross(b - a, c - a)
        if np.linalg.norm(n) < 1e-12:
            continue
        n /= np.linalg.norm(n)
        if np.degrees(np.arccos(min(1.0, abs(n @ up)))) > MAX_FLOOR_TILT_DEG:
            continue
        inl = np.abs((sub - a) @ n) < inlier
        if best is None or inl.sum() > best[1].sum():
            best = (n, inl)
    if best is None:
        return None
    n, d = fit_plane(sub[best[1]])
    return n, d, best[1]


def long_axis(xz: np.ndarray) -> float:
    """Angle (radians) of the rectangle side that is longest, over the rotation with the smallest robust box."""
    best = None
    for deg in np.arange(0, 90, 0.5):
        a = np.radians(deg)
        rot = xz @ np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        lo, hi = np.percentile(rot, 2, axis=0), np.percentile(rot, 98, axis=0)
        ext = hi - lo
        if best is None or ext.prod() < best[0]:
            best = (ext.prod(), a, ext)
    _, a, ext = best
    return a if ext[0] >= ext[1] else a + np.pi / 2


def solve(model: Model, centres_c: np.ndarray, frames: list[dict], notes: str, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    cams = camera_centres(model)
    tape = TAPE_RE.search(notes)
    if not tape:
        raise ValueError("the tape width is not in NOTES.md")
    width_m = float(tape.group(1))
    tape2 = TAPE2_RE.search(notes)

    # A first scale from the door lets the 2 cm inlier band be set in model units.
    door = door_points.from_clicks(model, notes)
    if door is None:
        spread = np.ptp(np.array([c for c, _ in cams.values()]), axis=0).max()
        door = door_points.from_splat_picks(notes, centres_c, unit_hint=spread / 3)
    if door is None:
        raise ValueError("no door points: run door_points.py page and paste the clicks, or the SuperSplat picks")
    a_c, b_c = np.array(door["A"]["colmap"]), np.array(door["B"]["colmap"])
    s = width_m / np.linalg.norm(a_c - b_c)

    up0 = up_from_cameras(cams)
    h = centres_c @ up0
    low = centres_c[h <= np.quantile(h, FLOOR_SHARE)]
    cam_pts = np.array([c for c, _ in cams.values()])
    by_pass_c: dict[str, list[np.ndarray]] = {}
    for f in frames:
        if f["name"] in cams:
            by_pass_c.setdefault(f["pass"], []).append(cams[f["name"]][0])

    def judge(n, d):
        if np.mean(cam_pts @ n - d) < 0:
            n, d = -n, -d
        corners = {k: float((np.array(door[k]["colmap"]) @ n - d) * s) for k in "AB"}
        heights = {p: float(np.median((np.array(v) @ n - d) * s)) for p, v in by_pass_c.items()}
        ok = all(abs(v) <= CORNER_ON_FLOOR_M for v in corners.values()) and all(
            lo <= heights[p] <= hi for p, (lo, hi) in CAMERA_HEIGHTS_M.items() if p in heights) and (
            np.degrees(np.arccos(np.clip(abs(n @ up0), -1, 1))) <= MAX_FLOOR_TILT_DEG)
        return n, d, corners, heights, ok

    n, d, inl = ransac_plane(low, FLOOR_INLIER_M / s, rng)
    n, d, corners_h, heights_c, ok = judge(n, d)
    floor_route, first_try = "lowest 20 % of centres", None
    floor_pts = low
    if not ok:
        first_try = {"cornerHeightsCm": {k: round(v * 100, 1) for k, v in corners_h.items()},
                     "cameraHeightsM": {k: round(v, 3) for k, v in heights_c.items()}}
        sub = centres_c[rng.choice(len(centres_c), min(len(centres_c), FLOOR_SEARCH_POINTS), replace=False)]
        found = plane_through(a_c, b_c, sub, up0, FLOOR_INLIER_M / s, rng)
        if found is not None:
            n2, d2, inl2 = found
            support = inl2.sum() / max(1, (np.abs(sub @ n - d) < FLOOR_INLIER_M / s).sum())
            first_try["supportOfDoorPlane"] = round(float(support), 3)
            n2, d2, c2, h2, ok2 = judge(n2, d2)
            if ok2 and support >= MIN_FLOOR_SUPPORT:
                n, d, inl, corners_h, heights_c = n2, d2, inl2, c2, h2
                floor_route = "through the door corners (the lowest centres gave another plane)"
                floor_pts = centres_c
                ok = True
    if not ok:
        n3, d3 = up0, float((a_c + b_c) / 2 @ up0)
        n3, d3, c3, h3, ok3 = judge(n3, d3)
        if ok3:
            n, d, corners_h, heights_c = n3, d3, c3, h3
            inl = np.abs(centres_c @ n - d) < FLOOR_INLIER_M / s
            floor_route = "level through the door corners (the splat shows too little floor to fit one)"
            floor_pts = centres_c
    up_tilt = float(np.degrees(np.arccos(np.clip(n @ up0, -1, 1))))

    # an orthonormal basis on the floor, then the long axis inside it
    e1 = np.cross(n, [1.0, 0, 0]) if abs(n[0]) < 0.9 else np.cross(n, [0, 0, 1.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(e1, n)
    height = (centres_c @ n - d) * s
    band = (height > WALL_BAND_M[0]) & (height < WALL_BAND_M[1])
    xz = np.stack([centres_c[band] @ e1, centres_c[band] @ e2], -1)
    ang = long_axis(xz)
    x_axis = np.cos(ang) * e1 + np.sin(ang) * e2
    pano_c = cams["5pano_0000"][0]
    door_c = (a_c + b_c) / 2
    if (door_c - pano_c) @ x_axis < 0:
        x_axis = -x_axis
    z_axis = np.cross(x_axis, n)
    r_world = np.stack([x_axis, n, z_axis])  # rows: world axes in COLMAP coordinates
    origin_c = pano_c - (pano_c @ n - d) * n
    world_from_colmap = splats.sim3(s, r_world, -s * r_world @ origin_c)

    def w(p):
        return splats.apply(world_from_colmap, np.atleast_2d(p))

    a_w, b_w = w(a_c)[0], w(b_c)[0]
    door_centre = (a_w + b_w) / 2
    pano_w = w(pano_c)[0]
    outward = np.array([door_centre[0] - pano_w[0], 0, door_centre[2] - pano_w[2]])
    outward /= np.linalg.norm(outward)
    by_pass: dict[str, list[np.ndarray]] = {}
    for f in frames:
        if f["name"] in cams:
            by_pass.setdefault(f["pass"], []).append(w(cams[f["name"]][0])[0])
    heights = {p: round(float(np.median(np.array(v)[:, 1])), 3) for p, v in by_pass.items()}

    head = np.array(by_pass.get("head") or by_pass.get("raised"))[:, [0, 2]]
    grid = grid2d.Grid.around(head, GRID_M, margin_cells=int(WALK_DILATE_M / GRID_M) + 3)
    # the middle of a loop is walkable floor too, so holes in the dilated path are filled
    walk = ndimage.binary_fill_holes(grid2d.close(grid.disks(head, WALK_DILATE_M)))
    to_door = door_centre - np.array([pano_w[0], EYE_HEIGHT, pano_w[2]])
    yaw = float(np.degrees(np.arctan2(-to_door[0], -to_door[2])))
    on_floor = floor_pts[np.abs(floor_pts @ n - d) * s < FLOOR_INLIER_M]
    floor_rms = float(np.sqrt(np.mean(((on_floor @ n - d) * s) ** 2)) * 100)
    check = None
    m_check = CHECK_RE.search(notes)
    if m_check and "C" in door and "D" in door:
        model_len = float(np.linalg.norm(np.array(door["C"]["colmap"]) - np.array(door["D"]["colmap"])) * s)
        tape_len = float(m_check.group(2))
        check = {"what": m_check.group(1).strip(), "tape_m": tape_len, "model_m": round(model_len, 4),
                 "error_pct": round(100 * (model_len - tape_len) / tape_len, 3)}
    band_w = w(centres_c[band])
    wall_band = [np.percentile(band_w[:, [0, 2]], 2, axis=0).round(3).tolist(),
                 np.percentile(band_w[:, [0, 2]], 98, axis=0).round(3).tolist()]
    width2 = float(tape2.group(1)) if tape2 else None
    evidence = scale_evidence(door, corners_h, heights_c, check, width_m, width2, tilt_deg=up_tilt)
    door_out = {"route": door["route"], "a": a_w.tolist(), "b": b_w.tolist(), "centre": door_centre.tolist(),
                "outward": outward.tolist(), "width_tape_m": width_m, "width_check_m": width2,
                "rms_px": [door[k].get("rms_px") for k in "AB"]}
    if "E" in door and "F" in door:
        door_out["top"] = [w(np.array(door[k]["colmap"]))[0].tolist() for k in "EF"]
    return {
        "world_from_colmap": world_from_colmap.tolist(),
        "metres_per_unit": s,
        "door": door_out,
        "floor": {"route": floor_route, "inliers": int(inl.sum()), "of": int(len(inl)), "rms_cm": round(floor_rms, 3),
                  "tilt_from_camera_up_deg": round(up_tilt, 3), "first_try": first_try},
        "evidence": evidence,
        "wall_band_xz": wall_band,
        "check_length": check,
        "camera_heights_m": heights,
        "pano": pano_w.tolist(),
        "eye_height_m": EYE_HEIGHT,
        "start": {"position": [float(pano_w[0]), EYE_HEIGHT, float(pano_w[2])], "yawDeg": round(yaw, 3), "pitchDeg": 0.0},
        "walkable_measured": grid2d.polygons(grid, walk),
        "room_cameras_xz": [[round(float(x), 3), round(float(z), 3)] for p in ("raised", "head", "hip")
                            for x, _, z in by_pass.get(p, [])],
        "walk_path_xz": [[round(float(x), 3), round(float(z), 3)] for x, z in head],
    }


def scale_evidence(door: dict, corners_h: dict, heights: dict, check: dict | None, tape: float, tape2: float | None,
                   tilt_deg: float | None = None) -> dict:
    """Every check on the scale and the floor, with its value, its limit and what to do when it fails."""
    checks = []

    def add(name, value, limit, ok, fix):
        checks.append({"name": name, "value": value, "limit": limit, "pass": bool(ok), "fix": fix})

    for k in "ABCDEF":
        r = door.get(k)
        if not isinstance(r, dict) or "rms_px" not in r:
            continue
        add(f"corner {k} reprojection RMS", r["rms_px"], f"at most {door_points.MAX_CLICK_RMS_PX:g} px",
            r["rms_px"] <= door_points.MAX_CLICK_RMS_PX,
            f"the clicks for {k} disagree: re-click {k} in every view, zoomed in, on the same physical corner")
        add(f"corner {k} ray angle", r["ray_angle_deg"], f"at least {door_points.MIN_RAY_ANGLE_DEG:g} degrees",
            r["ray_angle_deg"] >= door_points.MIN_RAY_ANGLE_DEG,
            f"the views for {k} were taken from nearly one place: add clicks from a view across the room or another pass")
    for k, v in corners_h.items():
        add(f"corner {k} height above the floor", round(v * 100, 2), f"within {CORNER_ON_FLOOR_M * 100:g} cm",
            abs(v) <= CORNER_ON_FLOOR_M,
            f"corner {k} is not on the fitted floor: re-click it where the jamb meets the floor; if the corners are "
            "right, the floor fit is wrong (a glossy floor's reflection?) and the floor numbers above say how")
    for p, (lo, hi) in CAMERA_HEIGHTS_M.items():
        if p in heights:
            add(f"{p} pass camera height", round(heights[p], 3), f"{lo:g} to {hi:g} m", lo <= heights[p] <= hi,
                f"the {p} pass's cameras come out {heights[p]:.2f} m above the fitted floor: the floor fit or the "
                "scale is wrong; look at the floor numbers and the door clicks")
    if tilt_deg is not None:
        add("floor tilt from the cameras' up", round(tilt_deg, 3), f"at most {MAX_FLOOR_TILT_DEG:g} degrees",
            tilt_deg <= MAX_FLOOR_TILT_DEG,
            "the fitted floor leans away from the cameras' up, so it is a plane through something else: "
            "look at the floor numbers above")
    if check:
        add("check length error", check["error_pct"], f"within {MAX_CHECK_ERROR_PCT:g} %",
            abs(check["error_pct"]) <= MAX_CHECK_ERROR_PCT,
            "the scale and the check length disagree: re-measure the check length, re-click C and D, then the door")
    warnings = []
    if tape2 is not None and abs(tape - tape2) * 1000 > TAPE_WARN_MM:
        warnings.append(f"the two tape readings differ by {abs(tape - tape2) * 1000:.0f} mm (more than {TAPE_WARN_MM:g} mm): "
                        "the scale uses the first; measure the door again if you can")
    return {"checks": checks, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--notes", type=Path, default=Path("../capture/NOTES.md"))
    ap.add_argument("--splat", type=Path, default=None, help="default work/splat/splat_raw.ply")
    ap.add_argument("--accept", default=None, metavar="REASON",
                    help="write scale.json despite failed checks, after looking; the reason is recorded")
    args = ap.parse_args(argv)
    model = read_model(args.work / json.loads((args.work / "colmap_report.json").read_text())["model_dir"])
    frames = json.loads((args.work / "frames.json").read_text())["frames"]
    ply = splats.read(args.splat or args.work / "splat" / "splat_raw.ply")
    keep = splats.opacity(ply) > 0.5
    out = args.work / "scale.json"
    out.unlink(missing_ok=True)  # a stale scale.json must never outlive a run that refuses or fails
    r = solve(model, splats.centres(ply)[keep], frames, args.notes.read_text())
    failed = [c for c in r["evidence"]["checks"] if not c["pass"]]
    for wmsg in r["evidence"]["warnings"]:
        print(f"WARNING: {wmsg}")
    if r["floor"]["first_try"]:
        ft = r["floor"]["first_try"]
        print(f"floor: the lowest centres' plane put the door corners at {ft['cornerHeightsCm']} cm and the cameras at "
              f"{ft['cameraHeightsM']} m; the floor used is {r['floor']['route']}")
    if failed:
        for c in failed:
            print(f"REFUSED {c['name']}: {c['value']} (needs {c['limit']}). {c['fix']}")
        if not args.accept:
            print("scale.json not written. Fix the above, or after looking pass --accept \"reason\" to go on.")
            return 1
        r["evidence"]["accepted"] = args.accept
        print(f"accepted despite the above: {args.accept}")
    out.write_text(json.dumps(r, indent=2, allow_nan=False) + "\n")
    d = r["door"]
    width_model = np.linalg.norm(np.array(d["a"]) - np.array(d["b"]))
    print(f"scale: {r['metres_per_unit']:.5f} m per COLMAP unit, from the door ({d['route']}); "
          f"clicks RMS {d['rms_px']} px")
    if d["width_check_m"]:
        print(f"tape {d['width_tape_m']:.3f} m, second tape {d['width_check_m']:.3f} m: differ by "
              f"{abs(d['width_tape_m'] - d['width_check_m']) * 1000:.0f} mm")
    print(f"door width in the scaled model: {width_model:.4f} m")
    if r["check_length"]:
        c = r["check_length"]
        print(f"check length ({c['what']}): tape {c['tape_m']:.3f} m, model {c['model_m']:.3f} m, {c['error_pct']:+.2f} %")
    else:
        print("no check length clicked (C and D); the scale rests on the door alone")
    f = r["floor"]
    print(f"floor: {f['inliers']} of {f['of']} low centres within 2 cm, RMS {f['rms_cm']:.2f} cm, "
          f"{f['tilt_from_camera_up_deg']:.1f} degrees from the cameras' up")
    print("camera heights (median, m): " + ", ".join(f"{k} {v:.2f}" for k, v in r["camera_heights_m"].items()))
    print(f"pano at {np.round(r['pano'], 3).tolist()}; start yaw {r['start']['yawDeg']:.1f} degrees; "
          f"walkable outlines: {len(r['walkable_measured'])}")
    print(f"written: {args.work / 'scale.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Marble's world into the measured world frame: work/align/<world_id>/align.json, the residual Gate A reads.

    uv run python align.py --world WORLD_ID [--start YAW[,mirror][,flip]] [--accept-by-eye "REASON"]
    uv run python align.py --world WORLD_ID --mode doorway --notes ../capture/NOTES.md
    uv run python align.py --world WORLD_ID --rung R1 --fit-mask seen     # a world made from the ladder's flat views

1. Initial transform. Marble builds its world from the pano still, so its origin is the pano camera and
   its raw axes are that camera's axes, in units that become metres when multiplied by
   metric_scale_factor. The pano's pose in the measured frame is COLMAP's (rig/y000p00/5pano_0000.jpg).
   How those raw axes sit on the camera is not settled (World Labs' docs call raw +x "left", which is a
   mirror of OpenCV; a y-up export is a half-turn about x; the yaw of Marble's forward is undocumented), so
   48 starts are scored: every yaw in 30 degree steps, mirrored or not, and turned over or not.
2. Each start is scored two ways on a seeded sample of Marble's splats: geometrically (the residual before
   ICP) and photometrically (photo.py: Marble's coloured centres drawn into the pano's registered views and
   correlated with the real images; from the pano's own centre that does not depend on scale). The best
   three of each, and the documented start, go on to ICP.
3. ICP: one point-to-point round with scaling, three point-to-plane rounds (Huber) at 30, 15 and 8 cm on
   Marble centres within 1 m of a measured centre, both clouds at 2 cm voxels, and a last round solving
   rotation, translation and scale together in the point-to-plane distance (point-to-point scaling is
   biased when the clouds are two samplings of one surface).
4. The choice: among starts that ended with their own "down" pointing down and whose two-way geometric
   score (both directions, capped at 25 cm) is within half again of the best, the one that looks most like
   the pano. A box room fits nearly as well turned round, mirrored or upside down; the photograph does not.
5. The residual, as frozen in STATUS: the median nearest-neighbour distance, in cm, from Marble centres
   within 1 m of a measured centre (the ICP set), over every Marble centre, after alignment and before the
   provenance split. It is this room's fit, never a Marble accuracy score.
6. Gate A passes when the residual is under 10 cm and the added checks hold: the chosen start's down lands
   within 10 degrees of the world's down, its photometric score is clearly the best of every distinct pose,
   enough of Marble is in the ICP set, and the scale ICP found agrees with Marble's metric factor. A person
   who has looked can overrule the added checks (never the residual) with --accept-by-eye "reason".
7. A ladder rung (--rung, --fit-mask seen): only Marble splats whose direction from c falls inside the rung's
   frustums (visibility.in_rung, under each candidate pose) take part in the scoring, ICP, the residual and
   the colour check, and the colour check draws into the rung's own input views. Marble's origin is held at
   c and only rotation and scale are fitted (point-to-plane at 30, 15 and 8 cm, pivoting about c). Then one
   round at 8 cm releases translation (at the held scale, along the directions the fit set's surfaces pin;
   see release): where the fit set's target normals span two non-parallel surfaces, a move of the origin of
   0.10 m or more fails Gate A and no one can overrule it; otherwise align.json says "translation not
   testable". The residual keeps the frozen definition over the fit set only, and the ICP share is taken
   over the fit set. The world's recovered yaw is recorded.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import open3d as o3d
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

import photo
import plots
import splats
from colmap_model import read_model

ICP_GATE_M = 1.0
VOXEL_M = 0.02
ROUNDS_M = (0.30, 0.15, 0.08)
GATE_A_CM = 10.0
YAW_STEP = 30
HYPOTHESES = [(yaw, mirror, flip) for flip in (False, True) for mirror in (False, True) for yaw in range(0, 360, YAW_STEP)]
PRIOR = (0, False, False)
KEEP_GEOMETRIC = 3
KEEP_PHOTOMETRIC = 3
CAP_M = 0.25
# Near-ties: the half-turned box room scored 10.1 cm two-way against 6.7 cm for the right pose (1.5 x),
# and with a re-imagined room every start came within 3 %; within 1.5 x, geometry is not allowed to decide.
GEOMETRIC_TIE = 1.5
SAMPLE_SPLATS = 300_000
PHOTO_SPLATS = 100_000
PHOTO_MIN_OPACITY = 0.2
GRAVITY_MAX_DEG = 10.0
# Two poses are the same answer when they share handedness and differ by less than this; it sits between
# the 7 degrees ICP typically moves a start and the 30 degree spacing of the starts.
SAME_POSE_DEG = 25.0
# Photometric margin: on the synthetic variants the right pose beat every other distinct pose by 0.23 to 0.4
# in correlation (tests/test_align_variants.py prints the table); a real Marble world re-imagines the room,
# so the bar is set at half the smallest synthetic margin.
PHOTO_MARGIN = 0.10
# A fit that covers under this share of Marble's world is fitting a corner of it: the pano sees the whole
# room, so most of what Marble makes from it lies within a metre of the measured room.
MIN_ICP_SHARE = 0.30
# ICP's scale against the metric factor's: the synthetic factor is 4 % off and fits 20 % off still converge;
# outside these bounds the factor is wrong or ICP has shrunk or stretched the world to fit part of it.
METRIC_RATIO_RANGE = (2 / 3, 1.5)
# Released from a held fit, the origin moving this far means the world is not built at c (Gate A fails).
RELEASE_MAX_M = 0.10
# Two surfaces are non-parallel enough to pin translation when the second eigenvalue of the fit set's
# target-normal scatter is at least this share of the largest.
TWO_SURFACES = 0.1
RUNGS = ("R1", "R2", "R4", "R8", "R4r")
FIT_MASKS = ("all", "seen")
NOTE = ("This is the fit of Marble's world to this room after alignment; it is not a measure of Marble's "
        "accuracy and is never shown beside another model's numbers.")


def metric_factor(world: dict) -> tuple[float, float | None]:
    meta = ((world.get("assets") or {}).get("splats") or {}).get("semantics_metadata") or {}
    if "metric_scale_factor" not in meta:
        raise ValueError("the world JSON has no assets.splats.semantics_metadata.metric_scale_factor")
    msf = float(meta["metric_scale_factor"])
    if not np.isfinite(msf) or msf <= 0:
        raise ValueError(f"the world JSON's metric_scale_factor is {msf}, not a positive number")
    return msf, meta.get("ground_plane_offset")


def pano_pose(model) -> tuple[np.ndarray, np.ndarray]:
    im = next((i for i in model.images.values() if i.name == "rig/y000p00/5pano_0000.jpg"), None)
    if im is None:
        raise ValueError("the pano's front view is not in the COLMAP model; Gate A cannot start without its pose")
    r = Rotation.from_quat(im.qvec, scalar_first=True).as_matrix()
    return -r.T @ np.array(im.tvec), r


def hypothesis(yaw_deg: float, mirror: bool, flip: bool = False) -> np.ndarray:
    """Raw axes into the pano camera's axes: mirror x first, then turn over about x, then the yaw about y."""
    h = Rotation.from_euler("y", yaw_deg, degrees=True).as_matrix()
    if flip:
        h = h @ np.diag([1.0, -1.0, -1.0])
    if mirror:
        h = h @ np.diag([-1.0, 1.0, 1.0])
    return h


def raw_down(flip: bool) -> np.ndarray:
    """The raw axis a start takes for down: +y for OpenCV axes, -y for a world exported y-up."""
    return np.array([0.0, -1.0, 0.0]) if flip else np.array([0.0, 1.0, 0.0])


def parse_start(text: str) -> tuple[float, bool, bool]:
    yaw, *flags = [p.strip() for p in text.split(",")]
    unknown = set(flags) - {"mirror", "flip", ""}
    if unknown:
        raise ValueError(f"--start takes YAW[,mirror][,flip]; did not understand {sorted(unknown)}")
    return float(yaw), "mirror" in flags, "flip" in flags


def label(h: tuple) -> str:
    yaw, mirror, flip = h
    return f"yaw {yaw:g}" + (", mirrored" if mirror else "") + (", turned over" if flip else "")


def initial(world_from_colmap: np.ndarray, pano_c: np.ndarray, r_cam: np.ndarray, msf: float, h: np.ndarray) -> np.ndarray:
    s = splats.split(world_from_colmap)[0]
    m = np.eye(4)
    m[:3, :3] = r_cam.T @ h * (msf / s)
    m[:3, 3] = pano_c
    return world_from_colmap @ m


def cloud(pts: np.ndarray, normals: bool = False) -> o3d.geometry.PointCloud:
    pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pts)).voxel_down_sample(VOXEL_M)
    if normals:
        pc.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=4 * VOXEL_M, max_nn=30))
    return pc


def residual(t: np.ndarray, marble_raw: np.ndarray, tree: cKDTree) -> dict:
    d, _ = tree.query(splats.apply(t, marble_raw), distance_upper_bound=ICP_GATE_M, workers=-1)
    d = d[np.isfinite(d)]
    if len(d) == 0:
        return {"medianCm": None, "p90Cm": None, "icpSet": 0}
    return {"medianCm": round(float(np.median(d) * 100), 3), "p90Cm": round(float(np.percentile(d, 90) * 100), 3),
            "icpSet": int(len(d))}


def two_way(t: np.ndarray, marble_raw: np.ndarray, tree: cKDTree, measured_world: np.ndarray) -> float:
    """Mean capped distance both ways, over each side's points within 1 m of the other: low only if the shapes agree."""
    pts = splats.apply(t, marble_raw)
    d1, _ = tree.query(pts, distance_upper_bound=ICP_GATE_M, workers=-1)
    d2, _ = cKDTree(pts).query(measured_world, distance_upper_bound=ICP_GATE_M, workers=-1)
    d1, d2 = d1[np.isfinite(d1)], d2[np.isfinite(d2)]
    if len(d1) == 0 or len(d2) == 0:
        return float("inf")
    return float(np.minimum(d1, CAP_M).mean() + np.minimum(d2, CAP_M).mean())


def similarity_round(t: np.ndarray, src: np.ndarray, tgt: np.ndarray, normals: np.ndarray, dist: float,
                     iters: int = 20, hold: np.ndarray | None = None, free: np.ndarray | None = None,
                     scale: bool = True) -> np.ndarray:
    """Point-to-plane ICP over rotation, translation and scale (about the source centroid), Huber-weighted.
    With hold (a world point), rotation and scale pivot about hold and translation is solved only along the
    columns of free (3 x k; none by default), so a pose that sends Marble's origin to hold moves it only
    along those directions; scale=False keeps the scale as it is."""
    tree = cKDTree(tgt)
    k = dist / 3
    for _ in range(iters):
        p = splats.apply(t, src)
        d, idx = tree.query(p, distance_upper_bound=dist, workers=-1)
        ok = np.isfinite(d)
        if ok.sum() < 7:
            break
        p, q, n = p[ok], tgt[idx[ok]], normals[idx[ok]]
        c = p.mean(axis=0) if hold is None else np.asarray(hold, float)
        r = ((p - q) * n).sum(axis=1)
        if hold is None:
            jac = np.c_[np.cross(p - c, n), n, ((p - c) * n).sum(axis=1)]
        else:
            basis = np.zeros((3, 0)) if free is None else np.asarray(free, float).reshape(3, -1)
            jac = np.c_[np.cross(p - c, n), n @ basis] if not scale else \
                np.c_[np.cross(p - c, n), n @ basis, ((p - c) * n).sum(axis=1)]
        w = np.where(np.abs(r) <= k, 1.0, k / np.maximum(np.abs(r), 1e-12))
        delta = np.linalg.solve(jac.T @ (jac * w[:, None]) + 1e-9 * np.eye(jac.shape[1]), -jac.T @ (w * r))
        rot = Rotation.from_rotvec(delta[:3]).as_matrix() * (1 + delta[-1] if hold is None or scale else 1.0)
        m = np.eye(4)
        m[:3, :3] = rot
        m[:3, 3] = (c + delta[3:6] - rot @ c) if hold is None else (c + basis @ delta[3:3 + basis.shape[1]] - rot @ c)
        t = m @ t
        if np.abs(delta).max() < 1e-7:
            break
    return t


def icp(t: np.ndarray, marble_raw: np.ndarray, tree: cKDTree, target: o3d.geometry.PointCloud, scale_round: bool,
        gate_m: float = ICP_GATE_M, mask_fn=None) -> np.ndarray:
    crit = o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=60)
    reg = o3d.pipelines.registration

    def near(t_now):
        d, _ = tree.query(splats.apply(t_now, marble_raw), distance_upper_bound=gate_m, workers=-1)
        return np.isfinite(d) if mask_fn is None else np.isfinite(d) & mask_fn(t_now, marble_raw)

    def src(t_now):
        return cloud(splats.apply(t_now, marble_raw)[near(t_now)])

    if scale_round:
        est = reg.TransformationEstimationPointToPoint(with_scaling=True)
        t = reg.registration_icp(src(t), target, ROUNDS_M[0], np.eye(4), est, crit).transformation @ t
    for dist in ROUNDS_M:
        est = reg.TransformationEstimationPointToPlane(reg.HuberLoss(k=dist / 3))
        t = reg.registration_icp(src(t), target, dist, np.eye(4), est, crit).transformation @ t
    if scale_round:
        sel = cloud(marble_raw[near(t)] * 1.0)
        t = similarity_round(t, np.asarray(sel.points), np.asarray(target.points), np.asarray(target.normals), ROUNDS_M[-1])
    return t


def fit_set(t: np.ndarray, marble_raw: np.ndarray, tree: cKDTree, mask_fn=None, gate_m: float = ICP_GATE_M) -> np.ndarray:
    """The raw points that take part in the fit under pose t: within gate_m of a measured centre and, given a
    mask, inside it."""
    d, _ = tree.query(splats.apply(t, marble_raw), distance_upper_bound=gate_m, workers=-1)
    ok = np.isfinite(d)
    if mask_fn is not None:
        ok &= mask_fn(t, marble_raw)
    return marble_raw[ok]


def icp_held(t: np.ndarray, marble_raw: np.ndarray, tree: cKDTree, target: o3d.geometry.PointCloud, hold: np.ndarray,
             mask_fn=None, gate_m: float = ICP_GATE_M) -> np.ndarray:
    """Rotation and scale only, about hold, in the point-to-plane distance at each of ROUNDS_M."""
    tgt, nrm = np.asarray(target.points), np.asarray(target.normals)
    for dist in ROUNDS_M:
        sel = fit_set(t, marble_raw, tree, mask_fn, gate_m)
        if len(sel) < 7:
            break
        t = similarity_round(t, np.asarray(cloud(sel).points), tgt, nrm, dist, hold=hold)
    return t


def release(t: np.ndarray, marble_raw: np.ndarray, tree: cKDTree, target: o3d.geometry.PointCloud, mask_fn=None) -> dict:
    """One round from a held pose with translation released: how far Marble's origin moves, and whether the
    fit set can say.

    The round frees rotation and translation and keeps the held fit's scale. With scale free too, the move is
    not defined on a frustum's worth of room: two or three walls that meet at a corner fit as well scaled
    about any point of that corner, so a free round shrinks the world into it and the origin slides by metres
    (1.3 m on the synthetic corner). Translation is pinned only along the directions the fit set's target
    normals span, so it is freed only along their strong directions (eigenvalue at least TWO_SURFACES of the
    largest), pivoting about the held origin. One such direction is one flat surface: not testable."""
    tgt, nrm = np.asarray(target.points), np.asarray(target.normals)
    pts = fit_set(t, marble_raw, tree, mask_fn)
    if len(pts) < 7:
        return {"translationReleaseM": None, "translationTestable": False, "translationNormalRatio": None}
    _, idx = cKDTree(tgt).query(splats.apply(t, pts), workers=-1)
    n = nrm[idx]
    ev, vec = np.linalg.eigh(n.T @ n / len(n))
    ev, vec = ev[::-1], vec[:, ::-1]
    ratio = float(ev[1] / ev[0]) if ev[0] > 0 else 0.0
    strong = vec[:, ev >= TWO_SURFACES * ev[0]]
    free = similarity_round(t, np.asarray(cloud(pts).points), tgt, nrm, ROUNDS_M[-1], hold=t[:3, 3], free=strong, scale=False)
    return {"translationReleaseM": round(float(np.linalg.norm(free[:3, 3] - t[:3, 3])), 4),
            "translationTestable": bool(ratio >= TWO_SURFACES), "translationNormalRatio": round(ratio, 4)}


def world_yaw_deg(t: np.ndarray, world_from_colmap: np.ndarray, r_cam: np.ndarray) -> float:
    """The yaw of Marble's raw forward (+z) in the pano rig frame: lon from +z towards +x, as the views were cut."""
    f = splats.split(t)[1] @ np.array([0.0, 0.0, 1.0])
    d = r_cam @ splats.split(world_from_colmap)[1].T @ f
    return round(float(np.degrees(np.arctan2(d[0], d[2]))), 3)


def rung_mask(pose, manifest: dict, rung: str):
    """mask_fn(t, raw) for a rung: which raw points, placed by t, lie inside the rung's frustums seen from c."""
    import visibility

    def mask(t: np.ndarray, pts: np.ndarray) -> np.ndarray:
        return visibility.in_rung(visibility.rig_dirs(pose, splats.apply(t, pts))[0], manifest, rung)
    return mask


def ladder_input_views(manifest: dict, rung: str, pose, size: int = photo.SIZE, root: Path | None = None) -> list:
    """The rung's input images as photo.View's, posed at c: a view cut at pano yaw a looks along Ry(-a) of the
    pano rig frame, with the pinhole ladder_views cut it with."""
    import ladder_views as lv
    root = lv.ROOT if root is None else Path(root)
    fov = manifest.get("fov_deg") or {}
    h_fov, v_fov = float(fov.get("h", lv.H_FOV_DEG)), float(fov.get("v", lv.V_FOV_DEG))
    w0, h0 = manifest.get("size") or lv.SIZE
    h = max(1, round(size * h0 / w0))
    k = np.array([[(size / 2) / np.tan(np.radians(h_fov / 2)), 0, size / 2],
                  [0, (h / 2) / np.tan(np.radians(v_fov / 2)), h / 2], [0, 0, 1.0]])
    yaw_of = {v["file"]: float(v["pano_yaw_deg"]) for v in manifest["views"]}
    pitch = float(manifest.get("pitch_deg") or 0.0)
    out = []
    for f in manifest["rungs"]["R4" if rung == "R4r" else rung]:
        rot = (Rotation.from_euler("x", -pitch, degrees=True) * Rotation.from_euler("y", -yaw_of[f], degrees=True)).as_matrix()
        m = np.eye(4)
        m[:3, :3] = rot @ pose.rig_from_world
        m[:3, 3] = -m[:3, :3] @ np.asarray(pose.c_world, float)
        img = Image.open(root / f).convert("L").resize((size, h), Image.Resampling.BOX)
        out.append(photo.View(Path(f).name, ndimage.gaussian_filter(np.asarray(img, np.float64) / 255.0, photo.BLUR_PX), k, m))
    return out


def gravity_deg(t: np.ndarray, flip: bool) -> float:
    """Angle between where a pose sends the raw axis its start called down and the world's down (-y)."""
    v = t[:3, :3] @ raw_down(flip)
    v = v / np.linalg.norm(v)
    return float(np.degrees(np.arccos(np.clip(-v[1], -1.0, 1.0))))


def pose_angle(a: np.ndarray, b: np.ndarray) -> float:
    """Degrees between two poses' orientations; infinite when one is mirrored and the other not."""
    if splats.parity(a) != splats.parity(b):
        return float("inf")
    ra, rb = splats.split(a)[1], splats.split(b)[1]
    return float(np.degrees(Rotation.from_matrix(ra.T @ rb).magnitude()))


def sample(n: int, k: int, seed: int = 0) -> np.ndarray:
    return np.arange(n) if n <= k else np.sort(np.random.default_rng(seed).choice(n, k, replace=False))


def photo_pick(pick: np.ndarray, opacity: np.ndarray | None, n: int = PHOTO_SPLATS, seed: int = 2) -> np.ndarray:
    """A seeded random share of the sample, opaque splats only: Marble writes its splats in no spatial order we
    know, so the first n would be one part of the world."""
    keep = pick if opacity is None else pick[opacity[pick] >= PHOTO_MIN_OPACITY]
    return keep if len(keep) <= n else np.sort(np.random.default_rng(seed).choice(keep, n, replace=False))


def search(measured_world: np.ndarray, marble_raw: np.ndarray, world_from_colmap: np.ndarray, pano_c: np.ndarray,
           r_cam: np.ndarray, msf: float, views: list | None = None, marble_lum: np.ndarray | None = None,
           marble_opacity: np.ndarray | None = None, start: tuple | None = None, log=print, mask_fn=None,
           hold: np.ndarray | None = None, fit_target: np.ndarray | None = None) -> dict:
    """Score every start, run ICP from the promising ones, choose, and compute the frozen residual once.

    mask_fn(t, raw) -> bool per raw point: only the points it keeps under pose t are scored, fitted and read
    in the residual (a rung's frustums; default every point). hold, a world point: every pose sends Marble's
    origin there and only rotation and scale are fitted; the result then carries the release check and the
    world's yaw. fit_target, world points: what the starts are scored against and the fit aims at (for a flat
    rung, the answer-key surface inside its view, because the trained splat's haze pulls a one-view world
    towards the camera; hub call 95); the frozen residual is still read against every measured centre."""
    t_start = time.time()
    tree = cKDTree(measured_world)
    aim = measured_world if fit_target is None else np.asarray(fit_target, float)
    aim_tree = tree if fit_target is None else cKDTree(aim)
    target = cloud(aim, normals=True)
    pick = sample(len(marble_raw), SAMPLE_SPLATS)
    raw_s = marble_raw[pick]
    meas_s = aim[sample(len(aim), SAMPLE_SPLATS, seed=1)]
    photo_ok = bool(views) and marble_lum is not None
    if photo_ok:
        keep = photo_pick(pick, marble_opacity)
        raw_p, lum_p = marble_raw[keep], marble_lum[keep]

    def fit(t, pts):
        return pts if mask_fn is None else pts[mask_fn(t, pts)]

    def photometric(t):
        if not photo_ok:
            return None
        if mask_fn is None:
            return photo.score(views, splats.apply(t, raw_p), lum_p)["score"]
        m = mask_fn(t, raw_p)
        return photo.score(views, splats.apply(t, raw_p[m]), lum_p[m])["score"]

    meas_fit = meas_s if mask_fn is None else meas_s[mask_fn(np.eye(4), meas_s)]

    table = []
    for h in HYPOTHESES if start is None else HYPOTHESES + ([start] if start not in HYPOTHESES else []):
        t0 = initial(world_from_colmap, pano_c, r_cam, msf, hypothesis(*h))
        if hold is not None:
            t0[:3, 3] = hold
        table.append({"yawDeg": h[0], "mirror": h[1], "flip": h[2], "rawDown": "-y" if h[2] else "+y",
                      "before": residual(t0, fit(t0, raw_s), aim_tree)["medianCm"], "photoBefore": photometric(t0), "t0": t0})
    far = lambda v: np.inf if v is None else v  # noqa: E731
    key = lambda e: (e["yawDeg"], e["mirror"], e["flip"])  # noqa: E731
    if start is not None:
        wanted = {tuple(start)}
    else:
        by_geo = sorted(table, key=lambda e: far(e["before"]))[:KEEP_GEOMETRIC]
        by_photo = sorted((e for e in table if e["photoBefore"] is not None), key=lambda e: -e["photoBefore"])[:KEEP_PHOTOMETRIC]
        wanted = {PRIOR} | {key(e) for e in by_geo + by_photo}
    tried = [e for e in table if key(e) in wanted]
    for e in tried:
        if hold is None:
            e["t"] = icp(e["t0"], raw_s, aim_tree, target, scale_round=True, mask_fn=mask_fn)
        else:
            e["t"] = icp_held(e["t0"], raw_s, aim_tree, target, hold, mask_fn)
        fitted = fit(e["t"], raw_s)
        e["after"] = residual(e["t"], fitted, aim_tree)["medianCm"]
        tw = two_way(e["t"], fitted, aim_tree, meas_fit) if len(fitted) and len(meas_fit) else float("inf")
        e["twoWayCm"] = round(tw * 100, 3) if np.isfinite(tw) else None
        e["gravityDeg"] = round(gravity_deg(e["t"], e["flip"]), 2)
        e["photo"] = photometric(e["t"])
    upright = [e for e in tried if e["gravityDeg"] <= GRAVITY_MAX_DEG] or tried
    best_geo = min(far(e["twoWayCm"]) for e in upright)
    near_ties = [e for e in upright if far(e["twoWayCm"]) <= GEOMETRIC_TIE * best_geo] or upright
    if photo_ok and any(e["photo"] is not None for e in near_ties):
        chosen = max(near_ties, key=lambda e: -np.inf if e["photo"] is None else e["photo"])
    else:
        chosen = min(near_ties, key=lambda e: far(e["twoWayCm"]))
    t = chosen["t"]

    # photometric runner-up: the best-looking pose that is a different answer from the chosen one
    rivals = []
    for e in table:
        if e is chosen:
            continue
        pose = e.get("t", e["t0"])
        if pose_angle(pose, t) < SAME_POSE_DEG:
            continue
        s = [x for x in (e["photoBefore"], e.get("photo")) if x is not None]
        if s:
            rivals.append((max(s), e))
    runner = max(rivals, key=lambda r: r[0]) if rivals else None
    if not photo_ok:
        photometric_out = {"score": None, "runnerUp": None, "reason": "no pano views on disk or no colours in the Marble file"}
    elif chosen.get("photo") is None:
        photometric_out = {"score": None, "runnerUp": None, "reason": "the pano views do not see enough of the chosen pose"}
    else:
        photometric_out = {"score": chosen["photo"],
                           "runnerUp": None if runner is None else {"yawDeg": runner[1]["yawDeg"], "mirror": runner[1]["mirror"],
                                                                     "flip": runner[1]["flip"], "score": runner[0]},
                           "views": len(views)}

    s_init, s_final = splats.split(chosen["t0"])[0], splats.split(t)[0]
    in_fit = None if mask_fn is None else mask_fn(t, marble_raw)
    full = residual(t, marble_raw if in_fit is None else marble_raw[in_fit], tree)
    log(f"alignment search: {len(table)} starts, {len(tried)} through ICP, {time.time() - t_start:.0f} s")
    out = {
        "world_from_marble": t.tolist(), "initial": chosen["t0"].tolist(),
        "hypothesis": {"yawDeg": chosen["yawDeg"], "mirror": chosen["mirror"], "flip": chosen["flip"], "rawDown": chosen["rawDown"]},
        "hypotheses": [{k: e[k] for k in ("yawDeg", "mirror", "flip", "rawDown", "before", "photoBefore", "after", "twoWayCm",
                                          "gravityDeg", "photo") if k in e} for e in table],
        "chosen": {"gravityDeg": chosen["gravityDeg"], "rawDown": chosen["rawDown"]},
        "photometric": photometric_out,
        "scale": {"metricFactor": msf, "metresPerRawUnit": s_final, "ratioToMetricFactor": round(s_final / s_init, 5)},
        "residual": full,
        "marbleSplats": int(len(marble_raw)),
        "sampleSplats": int(len(raw_s)),
        "seconds": round(time.time() - t_start, 1),
    }
    if in_fit is not None:
        out["fitSetSplats"] = int(in_fit.sum())
    if fit_target is not None:
        out["fitTarget"] = "answer-key surface"
        out["keyResidual"] = residual(t, marble_raw if in_fit is None else marble_raw[in_fit], aim_tree)
    if hold is not None:
        out.update(release(t, raw_s, aim_tree, target, mask_fn))
        out["worldYawDeg"] = world_yaw_deg(t, world_from_colmap, r_cam)
        out["seconds"] = round(time.time() - t_start, 1)
    return out


def gate(r: dict, accept_by_eye: str | None = None) -> dict:
    """Gate A's verdict. The frozen residual decides alone whether the fit is close; the added checks decide
    whether it is the right fit, and only they can be overruled by a person who has looked."""
    res = r["residual"]
    reasons = []
    residual_pass = res["medianCm"] is not None and res["medianCm"] < GATE_A_CM
    if res["medianCm"] is None:
        reasons.append("no Marble centre lies within 1 m of a measured centre: there is no residual to read")
    elif not residual_pass:
        reasons.append(f"residual median {res['medianCm']:.2f} cm is not under {GATE_A_CM:.0f} cm")
    translation = None
    if "translationTestable" in r:
        translation = {"testable": r["translationTestable"], "releaseM": r["translationReleaseM"], "maxM": RELEASE_MAX_M}
        if not r["translationTestable"]:
            translation.update({"pass": True, "note": "translation not testable"})
        else:
            translation["pass"] = r["translationReleaseM"] < RELEASE_MAX_M
            if not translation["pass"]:
                reasons.append(f"released, Marble's origin moves {r['translationReleaseM']:.3f} m from c (limit "
                               f"{RELEASE_MAX_M:.2f} m): the world is not built at the camera its inputs were taken from, "
                               "so its translation cannot be held")
    g = r["chosen"]
    gravity = {"pass": g["gravityDeg"] <= GRAVITY_MAX_DEG, "angleDeg": g["gravityDeg"], "limitDeg": GRAVITY_MAX_DEG,
               "rawDown": g["rawDown"]}
    if not gravity["pass"]:
        reasons.append(f"Marble's raw {g['rawDown']} (the start's down) lands {g['gravityDeg']:.0f} degrees from the "
                       f"world's down (limit {GRAVITY_MAX_DEG:.0f}): the fit is tilted or upside down")
    p = r["photometric"]
    ph = {"score": p.get("score"), "runnerUp": p.get("runnerUp"), "minMargin": PHOTO_MARGIN}
    if p.get("score") is None:
        ph.update({"pass": False, "margin": None})
        reasons.append(f"photometric check not possible: {p.get('reason', 'no score')}")
    else:
        margin = p["score"] - (p["runnerUp"]["score"] if p.get("runnerUp") else -1.0)
        ph.update({"pass": margin >= PHOTO_MARGIN, "margin": round(margin, 4)})
        if margin < PHOTO_MARGIN:
            ru = p["runnerUp"]
            reasons.append(f"photometric score {p['score']:.3f} is not clearly the best: "
                           f"{label((ru['yawDeg'], ru['mirror'], ru['flip']))} scores {ru['score']:.3f} "
                           f"(margin {margin:.3f}, needs {PHOTO_MARGIN})")
    of = r["fitSetSplats"] if "fitSetSplats" in r else r["marbleSplats"]
    share = res["icpSet"] / max(of, 1)
    icp_share = {"pass": share >= MIN_ICP_SHARE, "share": round(share, 4), "min": MIN_ICP_SHARE}
    if not icp_share["pass"]:
        whose = "the Marble splats inside the rung's frustums" if "fitSetSplats" in r else "Marble's splats"
        reasons.append(f"the ICP set holds only {share:.0%} of {whose} (minimum share {MIN_ICP_SHARE:.0%}): "
                       "the fit covers a corner of Marble's world")
    ratio = r["scale"]["ratioToMetricFactor"]
    lo, hi = METRIC_RATIO_RANGE
    metric = {"pass": lo <= ratio <= hi, "ratio": ratio, "range": [round(lo, 4), hi]}
    if not metric["pass"]:
        reasons.append(f"ICP's scale is {ratio:.3f} x the metric factor's (allowed {lo:.2f} to {hi:.2f}): the metric "
                       "factor is wrong, or ICP shrank or stretched the world to fit part of it")
    automatic = gravity["pass"] and ph["pass"] and icp_share["pass"] and metric["pass"]
    held = translation is None or translation["pass"]
    out = {"thresholdCm": GATE_A_CM, "residualPass": residual_pass,
           "pass": bool(residual_pass and held and (automatic or bool(accept_by_eye))),
           "gravity": gravity, "photometric": ph, "icpShare": icp_share, "metricRatio": metric,
           "acceptedByEye": accept_by_eye or None, "reasons": reasons}
    if translation is not None:
        out["translation"] = translation
    return out


def contact_sheet(measured_world: np.ndarray, marble_raw: np.ndarray, t0: np.ndarray, t: np.ndarray, out: Path,
                  door_centre=None, pano=None, marble_raw_before: np.ndarray | None = None,
                  title: str = "measured grey, Marble orange") -> Path:
    m = plots.thin(measured_world, 60000)
    raw = plots.thin(marble_raw, 60000, seed=1)
    raw0 = raw if marble_raw_before is None else plots.thin(marble_raw_before, 60000, seed=1)
    before, after = splats.apply(t0, raw0), splats.apply(t, raw)
    lo, hi = np.percentile(m, 1, axis=0) - 1.0, np.percentile(m, 99, axis=0) + 1.0
    img = Image.new("RGB", (1280, 1030), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=16)
    titles = ((0, 0, "before ICP, from above: x right, z down the page; 0.3 to 1.5 m above the floor"),
              (640, 0, "after ICP, from above (same slice)"),
              (0, 500, "before ICP, from the side: x right, y up (looking along -z)"),
              (640, 500, "after ICP, from the side"))
    for (x0, y0, title), cloud_k, top in zip(titles, (before, after, before, after), (True, True, False, False)):
        box = (x0 + 4, y0 + 26, x0 + 636, y0 + 496)
        draw.rectangle(box, outline=(120, 120, 120))
        draw.text((x0 + 6, y0 + 4), title, fill=(20, 20, 20), font=font)
        if top:
            panel = plots.Panel(box, lo[[0, 2]], hi[[0, 2]], top=True)
            # Marble first, so the measured points on top stay readable where the two agree
            panel.points(draw, plots.band(cloud_k)[:, [0, 2]], (214, 110, 30))
            panel.points(draw, plots.band(m)[:, [0, 2]], (60, 60, 60))
            if door_centre is not None and pano is not None:
                panel.arrow(draw, np.asarray(pano)[[0, 2]], np.asarray(door_centre)[[0, 2]], "door", font)
        else:
            panel = plots.Panel(box, lo[[0, 1]], hi[[0, 1]], top=False)
            panel.points(draw, cloud_k[:, [0, 1]], (214, 110, 30))
            panel.points(draw, m[:, [0, 1]], (60, 60, 60))
        panel.axes(draw, font)
    draw.text((8, 1006), title, fill=(0, 0, 0), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, allow_nan=False) + "\n")


def print_table(r: dict) -> None:
    print("start                          before  photo0 |   after  two-way  down   photo")
    for e in r["hypotheses"]:
        if "after" not in e and (e["photoBefore"] or 0) < 0.3 and (e["before"] is None or e["before"] > 20):
            continue
        num = lambda v, f: "   -  " if v is None else format(v, f)  # noqa: E731
        line = f"{label((e['yawDeg'], e['mirror'], e['flip'])):30s} {num(e['before'], '6.2f')}  {num(e['photoBefore'], '6.3f')}"
        if "after" in e:
            line += f" | {num(e['after'], '6.2f')}  {num(e['twoWayCm'], '7.2f')}  {e['gravityDeg']:4.0f}  {num(e['photo'], '.3f')}"
        print(line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--world", required=True, help="the Marble world id (work/marble/<id>.json, marble_<id>.ply)")
    ap.add_argument("--start", default=None, help="YAW[,mirror][,flip]: skip the search and start from this, e.g. 0 or 172,mirror")
    ap.add_argument("--accept-by-eye", default=None, metavar="REASON",
                    help="a person has looked at contact.png and the table and overrules the added checks (never the residual)")
    ap.add_argument("--mode", choices=["pano", "doorway"], default="pano")
    ap.add_argument("--notes", type=Path, default=Path("../capture/NOTES.md"), help="doorway mode: the Marble corner picks")
    ap.add_argument("--rung", choices=RUNGS, default=None,
                    help="a world made from this ladder rung's flat views (work/ladder/views/manifest.json); needs --fit-mask seen")
    ap.add_argument("--fit-mask", choices=FIT_MASKS, default="all",
                    help="all: every Marble splat (Part 1); seen: only those inside the rung's frustums, origin held at c")
    args = ap.parse_args(argv)
    if args.fit_mask == "seen" and args.rung is None:
        ap.error("--fit-mask seen needs --rung: the rung's frustums are the fit set")
    if args.rung is not None and args.fit_mask != "seen":
        ap.error("--rung places a flat rung on what it saw and needs --fit-mask seen")
    if args.rung is not None and args.mode == "doorway":
        ap.error("--rung is for a world made from the ladder's views, not the doorway fallback")
    if args.mode == "doorway":
        import doorway
        return doorway.main(args)
    scale = json.loads((args.work / "scale.json").read_text())
    w_from_c = np.array(scale["world_from_colmap"])
    model = read_model(args.work / json.loads((args.work / "colmap_report.json").read_text())["model_dir"])
    pano_c, r_cam = pano_pose(model)
    world = json.loads((args.work / "marble" / f"{args.world}.json").read_text())
    msf, ground = metric_factor(world)
    measured = splats.apply(w_from_c, splats.centres(splats.read(args.work / "splat" / "measured.ply")))
    marble = splats.read(args.work / "marble" / f"marble_{args.world}.ply")
    marble_raw = splats.centres(marble)
    colour = splats.base_colour(marble)
    mask_fn = hold = manifest = key_in_view = None
    if args.rung is None:
        views = photo.pano_views(model, args.work / "images", w_from_c)
        print(f"photometric check: {len(views)} pano view(s) on disk in {args.work / 'images'}")
    else:
        import ladder_views
        import visibility
        root = args.work.resolve().parent.parent
        try:
            manifest = ladder_views.verify_manifest(args.work / "ladder" / "views" / "manifest.json", root)
        except ladder_views.LadderError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 1
        pose = visibility.pose_from_work(args.work)
        views = ladder_input_views(manifest, args.rung, pose, root=root)
        mask_fn, hold = rung_mask(pose, manifest, args.rung), pose.c_world
        key_pose, key = visibility.answer_key_depth(args.work)
        key_pts, _ = visibility.surface_points(key_pose, key)
        key_in_view = key_pts[visibility.in_rung(visibility.rig_dirs(pose, key_pts)[0], manifest, args.rung)]
        print(f"photometric check: {len(views)} input view(s) of {args.rung}; fit set: Marble splats inside its frustums; "
              f"origin held at c {np.round(hold, 3).tolist()}; the fit aims at the answer-key surface in view "
              f"({len(key_in_view)} points), the residual at every measured centre")
    r = search(measured, marble_raw, w_from_c, pano_c, r_cam, msf, views,
               None if colour is None else photo.luminance(colour),
               splats.opacity(marble) if "opacity" in marble["vertex"].data.dtype.names else None,
               parse_start(args.start) if args.start else None, mask_fn=mask_fn, hold=hold, fit_target=key_in_view)
    out = args.work / "align" / args.world
    t0, t1 = np.array(r["initial"]), np.array(r["world_from_marble"])
    if args.rung is None:
        sheet = contact_sheet(measured, marble_raw, t0, t1, out / "contact.png", scale["door"]["centre"], scale["pano"])
    else:
        # only what the rung saw: the key surface in view, and Marble's splats inside the frustums under each pose
        sheet = contact_sheet(key_in_view, marble_raw[mask_fn(t1, marble_raw)], t0, t1, out / "contact.png",
                              scale["door"]["centre"], scale["pano"], marble_raw_before=marble_raw[mask_fn(t0, marble_raw)],
                              title="inside the rung's view only: answer-key surface grey, Marble orange")
    g = gate(r, args.accept_by_eye)
    r.update({"worldId": args.world, "mode": "pano", "model": world.get("model"), "groundPlaneOffset": ground,
              "panoHeightM": float(scale["pano"][1]), "gateA": g, "note": NOTE, "contactSheet": str(sheet)})
    if args.rung is not None:
        r.update({"rung": args.rung, "fitMask": args.fit_mask,
                  # Marble's quickstart azimuths: 0 front (the door, d), 90 right, 180 back, 270 left
                  "worldAzimuthDeg": round((r["worldYawDeg"] - float(manifest["d_yaw_deg"])) % 360, 3),
                  "inputAzimuthsDeg": [v["azimuth"] for v in manifest["views"]
                                       if v["file"] in manifest["rungs"]["R4" if args.rung == "R4r" else args.rung]]})
    write_json(out / "align.json", r)
    print_table(r)
    h, res = r["hypothesis"], r["residual"]
    print(f"chosen start: {label((h['yawDeg'], h['mirror'], h['flip']))} (raw {h['rawDown']} taken as down); scale "
          f"{r['scale']['metresPerRawUnit']:.4f} m per raw unit, {r['scale']['ratioToMetricFactor']:.3f} x the metric factor {msf}")
    if h["mirror"]:
        print("NOTE: the chosen start is mirrored; export.py bakes the mirror into the files so the viewer's matrix stays proper")
    print(f"ground plane offset (as Marble gives it): {ground}; pano height measured {scale['pano'][1]:.2f} m")
    if res["medianCm"] is None:
        print("residual: none (no Marble centre within 1 m of a measured centre)")
    elif args.rung is None:
        print(f"residual: median {res['medianCm']:.2f} cm, 90th percentile {res['p90Cm']:.2f} cm, over {res['icpSet']} "
              f"Marble centres within 1 m of a measured centre ({g['icpShare']['share']:.0%} of {r['marbleSplats']})")
    else:
        print(f"residual: median {res['medianCm']:.2f} cm, 90th percentile {res['p90Cm']:.2f} cm, over {res['icpSet']} "
              f"Marble centres inside {args.rung}'s frustums within 1 m of a measured centre "
              f"({g['icpShare']['share']:.0%} of the {r['fitSetSplats']} inside)")
        tr = g["translation"]
        print("translation: not testable (the fit set does not span two non-parallel surfaces)" if not tr["testable"] else
              f"translation: released, the origin moves {tr['releaseM']:.3f} m from c (limit {RELEASE_MAX_M:.2f} m)")
        print(f"world yaw: raw forward at pano yaw {r['worldYawDeg']:.1f} deg, azimuth {r['worldAzimuthDeg']:.1f} deg "
              f"from the door (inputs at {r['inputAzimuthsDeg']})")
    p = g["photometric"]
    if p["score"] is not None:
        ru = p["runnerUp"]
        print(f"photometric: {p['score']:.3f}; next best distinct pose "
              + (f"{label((ru['yawDeg'], ru['mirror'], ru['flip']))} {ru['score']:.3f}" if ru else "none")
              + f"; margin {p['margin']:.3f} (needs {PHOTO_MARGIN})")
    print(f"gravity: raw {h['rawDown']} lands {g['gravity']['angleDeg']:.1f} degrees from the world's down (limit {GRAVITY_MAX_DEG:.0f})")
    for reason in g["reasons"]:
        print(f"  - {reason}")
    if g["acceptedByEye"]:
        print(f"accepted by eye: {g['acceptedByEye']}")
    print(f"Gate A: {'PASS' if g['pass'] else 'FAIL'} (median under {GATE_A_CM:.0f} cm and the added checks). {NOTE}")
    print(f"written: {out / 'align.json'}, {sheet}")
    return 0 if g["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

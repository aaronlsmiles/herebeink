"""Part 2, Task 0.5: what each rung of the ladder saw, and the answer key it is marked against, before any spend.

    uv run python visibility.py [--rule rendered|opaque]   # work/ladder/visibility.json, work/ladder/<rung>/visibility.png

Everything is in the rig frame of the pano's reference view (rig/y000p00/5pano_0000.jpg: x right, y down,
z forward), the frame the ladder's views were cut in, from the camera point c. A rung's seen region is the
union of its views' pinhole frustums (the projection ladder_views.project uses).

The answer key is a depth panorama from c at 0.25 degrees per cell, built from the trained splat by one of
two rules: "opaque" (splats at opacity 0.2 or more, the nearest footprint wins) or "rendered" (splats at
0.05 or more, composited front to back, the surface where accumulated opacity first reaches 0.5). The
hallway key points are drawn into the same panorama as opaque points. Which rule the ladder's plan freezes
is hub Amendment 1; a third, "planes" (the room as a box fitted to the splat, with the rendered surface
where it stands more than tau in front: the furniture), is compared with them under hub call 92. All are computed so the instrument can be compared with COLMAP's own points.
Through the doorway no measured splat forms the key: nothing past the frame was measured (door_edge.py).

A Gaussian's footprint seen from c is an isotropic approximation of its ellipse: angular sigma =
atan(largest axis / distance), at least half a cell and otherwise not capped; drawn out to 2 sigma, the
reach capped at 6 degrees; weighted exp(-0.5 (theta / sigma)^2) and cut below 0.05.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation

import door_edge
import ladder_views as lv
import plots
import splats

WORK = Path(__file__).resolve().parent / "work"
DEG = 0.25
TAU_M = 0.15
OPAQUE_MIN = 0.2
RENDERED_MIN = 0.05
HALF_OPACITY = 0.5
MAX_FOOTPRINT_DEG = 6.0
WEIGHT_CUT = 0.05
ROOM_BAND_M = (0.3, 2.3)
CORRIDOR_GROW_M = 0.3
RULES = ("rendered", "opaque", "planes")
BOX_REGION_M = 0.6
BOX_STRONG = 0.3
BOX_BIN_M = 0.02
CEILING_FROM_M = 2.5
RUNG_NAMES = ("R1", "R2", "R4", "R8", "R4r", "P")
BATCH = 50_000


@dataclass(frozen=True)
class Pose:
    c_world: np.ndarray
    rig_from_world: np.ndarray  # a rotation


def pose_from_work(work: Path) -> Pose:
    from answer_key import centre_of, to_world
    from colmap_model import read_model

    scale = json.loads((work / "scale.json").read_text())
    w_from_c = np.array(scale["world_from_colmap"], float)
    model = read_model(work / "colmap" / "sparse_txt" / "0")
    img = next((i for i in model.images.values() if i.name == "rig/y000p00/5pano_0000.jpg"), None)
    if img is None:
        raise ValueError("the COLMAP model has no rig/y000p00/5pano_0000.jpg: the pano's pose is unknown")
    cam_from_model = Rotation.from_quat(img.qvec, scalar_first=True).as_matrix()
    rot_w = splats.split(w_from_c)[1]
    return Pose(to_world(centre_of(img), w_from_c)[0], cam_from_model @ rot_w.T)


def rig_dirs(pose: Pose, pts_world: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    v = (np.atleast_2d(pts_world) - pose.c_world) @ pose.rig_from_world.T
    r = np.linalg.norm(v, axis=1)
    return v / np.maximum(r, 1e-12)[:, None], r


def world_dirs(pose: Pose, dirs_rig: np.ndarray) -> np.ndarray:
    return dirs_rig @ pose.rig_from_world


# ---- frustums ----

def in_view(dirs: np.ndarray, yaw: float, h_fov: float = lv.H_FOV_DEG, v_fov: float = lv.V_FOV_DEG,
            pitch: float = 0.0) -> np.ndarray:
    rot = (Rotation.from_euler("x", -pitch, degrees=True) * Rotation.from_euler("y", -yaw, degrees=True)).as_matrix()
    p = np.asarray(dirs, float).reshape(-1, 3) @ rot.T
    z = p[:, 2]
    ok = z > 1e-9
    zs = np.where(ok, z, 1.0)
    return ok & (np.abs(p[:, 0] / zs) <= np.tan(np.radians(h_fov / 2))) & (np.abs(p[:, 1] / zs) <= np.tan(np.radians(v_fov / 2)))


def rung_yaws(manifest: dict, rung: str) -> list[float]:
    files = manifest["rungs"]["R4" if rung == "R4r" else rung]
    by = {v["file"]: v["pano_yaw_deg"] for v in manifest["views"]}
    return [float(by[f]) for f in files]


def in_rung(dirs: np.ndarray, manifest: dict, rung: str) -> np.ndarray:
    d = np.asarray(dirs, float).reshape(-1, 3)
    if rung == "P":
        return np.ones(len(d), bool)
    fov = manifest.get("fov_deg", {})
    h, v = fov.get("h", lv.H_FOV_DEG), fov.get("v", lv.V_FOV_DEG)
    out = np.zeros(len(d), bool)
    for yaw in rung_yaws(manifest, rung):
        out |= in_view(d, yaw, h, v)
    return out


# ---- the panorama ----

def grid(deg: float = DEG) -> tuple[int, int]:
    return int(round(180 / deg)), int(round(360 / deg))


def equirect_dirs(deg: float = DEG) -> tuple[np.ndarray, np.ndarray]:
    h, w = grid(deg)
    lat = np.radians(90 - (np.arange(h) + 0.5) * deg)[:, None] * np.ones((1, w))
    lon = np.radians(-180 + (np.arange(w) + 0.5) * deg)[None, :] * np.ones((h, 1))
    dirs = np.stack([np.cos(lat) * np.sin(lon), -np.sin(lat), np.cos(lat) * np.cos(lon)], -1)
    wt = np.cos(lat)
    return dirs, wt / wt.sum()


def cell_of(dirs: np.ndarray, deg: float = DEG) -> tuple[np.ndarray, np.ndarray]:
    d = np.asarray(dirs, float).reshape(-1, 3)
    h, w = grid(deg)
    lon = np.degrees(np.arctan2(d[:, 0], d[:, 2]))
    lat = np.degrees(np.arcsin(np.clip(-d[:, 1], -1, 1)))
    return (np.clip(((90 - lat) / deg).astype(int), 0, h - 1), np.clip(((lon + 180) / deg).astype(int) % w, 0, w - 1))


def share_by_construction(manifest: dict, rung: str, deg: float = DEG) -> float:
    dirs, wt = equirect_dirs(deg)
    return float(wt.reshape(-1)[in_rung(dirs.reshape(-1, 3), manifest, rung)].sum())


def _fragments(dirs: np.ndarray, r: np.ndarray, sigma_deg: np.ndarray, deg: float):
    """(cell index, distance, weight, splat index) for every cell each footprint reaches."""
    h, w = grid(deg)
    cdirs, _ = equirect_dirs(deg)
    cdirs = cdirs.reshape(-1, 3)
    row, col = cell_of(dirs, deg)
    lat = np.arcsin(np.clip(-dirs[:, 1], -1, 1))
    reach = np.minimum(2 * sigma_deg, MAX_FOOTPRINT_DEG)
    kr = np.ceil(reach / deg).astype(int)
    kc = np.minimum(np.ceil(reach / deg / np.maximum(np.cos(lat), 0.02)).astype(int), w // 2)
    out = []
    for key in np.unique(np.c_[kr, kc], axis=0):
        sel = np.flatnonzero((kr == key[0]) & (kc == key[1]))
        dj, di = np.mgrid[-key[0]:key[0] + 1, -key[1]:key[1] + 1]
        dj, di = dj.ravel(), di.ravel()
        for start in range(0, len(sel), max(1, 2_000_000 // len(dj))):
            s = sel[start:start + max(1, 2_000_000 // len(dj))]
            rr = row[s][:, None] + dj[None, :]
            cc = (col[s][:, None] + di[None, :]) % w
            ok = (rr >= 0) & (rr < h)
            cell = np.where(ok, rr, 0) * w + cc
            cos = np.einsum("nkc,nc->nk", cdirs[cell], dirs[s])
            theta = np.degrees(np.arccos(np.clip(cos, -1, 1)))
            wgt = np.exp(-0.5 * (theta / sigma_deg[s][:, None]) ** 2)
            ok &= (theta <= reach[s][:, None] + 1e-9) & (wgt >= WEIGHT_CUT)
            n, k = np.nonzero(ok)
            out.append((cell[n, k], r[s][n], wgt[n, k], s[n]))
    if not out:
        return np.zeros(0, int), np.zeros(0), np.zeros(0), np.zeros(0, int)
    return tuple(np.concatenate(x) for x in zip(*out))


def footprint_depth(pose: Pose, xyz: np.ndarray, opacity: np.ndarray, sigma_m: np.ndarray, rule: str,
                    deg: float = DEG) -> np.ndarray:
    """The answer-key depth panorama (metres from c; inf where nothing)."""
    if rule not in RULES:
        raise ValueError(f"rule must be one of {RULES}")
    h, w = grid(deg)
    depth = np.full(h * w, np.inf)
    keep = opacity >= (OPAQUE_MIN if rule == "opaque" else RENDERED_MIN)
    if not keep.any():
        return depth.reshape(h, w)
    dirs, r = rig_dirs(pose, xyz[keep])
    a = opacity[keep]
    sig = np.maximum(np.degrees(np.arctan2(sigma_m[keep], r)), deg / 2)
    order = np.argsort(r)
    if rule == "opaque":
        cell, dist, _, _ = _fragments(dirs, r, sig, deg)
        np.minimum.at(depth, cell, dist)
        return depth.reshape(h, w)
    log_t = np.zeros(h * w)
    for start in range(0, len(order), BATCH):
        idx = order[start:start + BATCH]
        cell, dist, wgt, src = _fragments(dirs[idx], r[idx], sig[idx], deg)
        alpha = np.clip(a[idx][src] * wgt, 0, 0.999)
        o = np.lexsort((dist, cell))
        cell, dist, lt = cell[o], dist[o], np.log1p(-alpha[o])
        cum = np.cumsum(lt)
        starts = np.r_[0, np.flatnonzero(np.diff(cell)) + 1]
        before = np.repeat(cum[starts] - lt[starts], np.diff(np.r_[starts, len(cell)]))
        acc = 1 - np.exp(log_t[cell] + cum - before)
        hit = np.flatnonzero((acc >= HALF_OPACITY) & ~np.isfinite(depth[cell]))
        if len(hit):
            u, first = np.unique(cell[hit], return_index=True)
            depth[u] = dist[hit[first]]
        np.add.at(log_t, cell, lt)
    return depth.reshape(h, w)


@dataclass(frozen=True)
class RoomBox:
    """The room as a box on the door wall's axes: u along the door's outward normal, v along the wall."""
    u: np.ndarray
    v: np.ndarray
    u_min: float
    u_max: float
    v_min: float
    v_max: float
    y_min: float
    y_max: float


def _outermost_strong(x: np.ndarray, w: np.ndarray, side: int) -> float:
    """The outermost 2 cm layer, within 0.6 m of the extreme, holding at least 0.3 of that region's densest layer."""
    edge = np.percentile(x, 99.5 if side > 0 else 0.5)
    lo, hi = (edge - BOX_REGION_M, edge) if side > 0 else (edge, edge + BOX_REGION_M)
    keep = (x >= lo) & (x <= hi)
    h, e = np.histogram(x[keep], bins=np.arange(lo, hi + BOX_BIN_M, BOX_BIN_M), weights=w[keep])
    strong = np.flatnonzero(h >= BOX_STRONG * h.max())
    k = strong[-1] if side > 0 else strong[0]
    return float((e[k] + e[k + 1]) / 2)


def fit_room_box(xyz: np.ndarray, opacity: np.ndarray, scale: dict) -> RoomBox:
    """Floor y = 0 (scale.json's), the door wall on the door plane, the other walls and the ceiling as the
    outermost strong layers of the splat's splats at opacity 0.05 or more (furniture stands inside them)."""
    o = door_edge.opening(scale)
    keep = opacity >= RENDERED_MIN
    p, w = xyz[keep], opacity[keep]
    band = (p[:, 1] >= ROOM_BAND_M[0]) & (p[:, 1] <= ROOM_BAND_M[1])
    pu, pv = p[band] @ o.normal, p[band] @ o.lateral
    up = p[:, 1] >= CEILING_FROM_M
    return RoomBox(o.normal, o.lateral, _outermost_strong(pu, w[band], -1), float(o.centre @ o.normal),
                   _outermost_strong(pv, w[band], -1), _outermost_strong(pv, w[band], 1),
                   0.0, _outermost_strong(p[up, 1], w[up], 1))


def box_depth(pose: Pose, box: RoomBox, deg: float = DEG) -> np.ndarray:
    dirs, _ = equirect_dirs(deg)
    d = world_dirs(pose, dirs.reshape(-1, 3))
    axes = np.stack([box.u, np.array([0.0, 1.0, 0.0]), box.v])
    lo = np.array([box.u_min, box.y_min, box.v_min])
    hi = np.array([box.u_max, box.y_max, box.v_max])
    return box_distance(axes @ pose.c_world, d @ axes.T, lo, hi).reshape(grid(deg))


def through_door(pose: Pose, scale: dict, deg: float = DEG) -> np.ndarray:
    dirs, _ = equirect_dirs(deg)
    return door_edge.through_opening(pose.c_world, world_dirs(pose, dirs.reshape(-1, 3)), scale).reshape(grid(deg))


def key_depth(pose: Pose, xyz: np.ndarray, opacity: np.ndarray, sigma_m: np.ndarray, key_pts: np.ndarray,
              scale: dict, rule: str, deg: float = DEG) -> np.ndarray:
    """The answer key: the measured surface by `rule`, except through the doorway, where nothing past the
    frame was measured (hub calls 62, 90) and only the hallway key points form it."""
    if rule == "planes":
        rendered = footprint_depth(pose, xyz, opacity, sigma_m, "rendered", deg)
        measured = box_depth(pose, fit_room_box(xyz, opacity, scale), deg)
        front = np.isfinite(rendered) & (rendered < measured - TAU_M)
        measured[front] = rendered[front]
    else:
        measured = footprint_depth(pose, xyz, opacity, sigma_m, rule, deg)
    measured[through_door(pose, scale, deg)] = np.inf
    return combine(measured, point_depth(pose, key_pts, deg))


def point_depth(pose: Pose, pts: np.ndarray, deg: float = DEG) -> np.ndarray:
    """Points drawn as opaque, one cell across; the nearest wins."""
    h, w = grid(deg)
    depth = np.full(h * w, np.inf)
    if len(pts):
        dirs, r = rig_dirs(pose, pts)
        cell, dist, _, _ = _fragments(dirs, r, np.full(len(r), deg / 2), deg)
        np.minimum.at(depth, cell, dist)
    return depth.reshape(h, w)


def combine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.minimum(a, b)


def surface_points(pose: Pose, depth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    deg = 180 / depth.shape[0]
    dirs, wt = equirect_dirs(deg)
    ok = np.isfinite(depth)
    pts = pose.c_world + world_dirs(pose, dirs[ok]) * depth[ok][:, None]
    return pts, wt[ok]


def box_distance(c: np.ndarray, dirs: np.ndarray, lo, hi) -> np.ndarray:
    """Distance along each ray from c (inside the box) to the box's walls."""
    d = np.asarray(dirs, float)
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(d > 0, (hi - c) / d, np.where(d < 0, (lo - c) / d, np.inf))
    return t.min(axis=1)


def agreement(depth: np.ndarray, colmap: np.ndarray, wt: np.ndarray, mask: np.ndarray, tau: float = TAU_M) -> dict:
    both = np.isfinite(depth) & np.isfinite(colmap) & mask
    if not both.any():
        return {"cells": 0, "withinTau": None}
    diff = depth[both] - colmap[both]
    return {"cells": int(both.sum()), "withinTau": round(float(np.mean(np.abs(diff) <= tau)), 4),
            "weightedWithinTau": round(float((wt[both] * (np.abs(diff) <= tau)).sum() / wt[both].sum()), 4),
            "medianM": round(float(np.median(diff)), 4), "p10M": round(float(np.percentile(diff, 10)), 4),
            "p90M": round(float(np.percentile(diff, 90)), 4)}


# ---- the scored volume ----

@dataclass
class ScoredVolume:
    room_eq: np.ndarray  # plan-view hull equations (x, z), unit normals
    y_range: tuple[float, float]
    corridor_eq: np.ndarray | None  # 3D hull equations, unit normals

    @classmethod
    def build(cls, answer_pts: np.ndarray, door: dict, key_pts: np.ndarray, key_cams: np.ndarray) -> "ScoredVolume":
        scale = {"door": door}
        room = answer_pts[~door_edge.past_plane(answer_pts, scale)]
        band = room[(room[:, 1] >= ROOM_BAND_M[0]) & (room[:, 1] <= ROOM_BAND_M[1])]
        hull = ConvexHull(band[:, [0, 2]])
        top = float(np.percentile(room[:, 1], 99)) + TAU_M
        corridor = None
        hall = np.vstack([p for p in (key_pts, key_cams) if len(p)]) if (len(key_pts) or len(key_cams)) else np.zeros((0, 3))
        if len(hall) >= 4:
            corridor = ConvexHull(hall).equations
        return cls(hull.equations, (-TAU_M, top), corridor)

    def contains(self, pts: np.ndarray) -> np.ndarray:
        p = np.atleast_2d(pts)
        xz = p[:, [0, 2]]
        room = ((xz @ self.room_eq[:, :2].T + self.room_eq[:, 2]) <= TAU_M).all(axis=1)
        room &= (p[:, 1] >= self.y_range[0]) & (p[:, 1] <= self.y_range[1])
        if self.corridor_eq is None:
            return room
        corridor = ((p @ self.corridor_eq[:, :3].T + self.corridor_eq[:, 3]) <= CORRIDOR_GROW_M).all(axis=1)
        return room | corridor


# ---- the run ----

def colmap_depth(pose: Pose, work: Path, deg: float = DEG) -> np.ndarray:
    from answer_key import to_world
    from colmap_model import read_model

    scale = json.loads((work / "scale.json").read_text())
    model = read_model(work / "colmap" / "sparse_txt" / "0")
    pts = np.array([p.xyz for p in model.points.values() if len(p.track) >= 3]).reshape(-1, 3)
    dirs, r = rig_dirs(pose, to_world(pts, np.array(scale["world_from_colmap"], float)))
    h, w = grid(deg)
    depth = np.full(h * w, np.inf)
    row, col = cell_of(dirs, deg)
    np.minimum.at(depth, row * w + col, r)
    return depth.reshape(h, w)


def key_points(work: Path) -> tuple[np.ndarray, np.ndarray]:
    import answer_key
    from colmap_model import read_model

    scale = json.loads((work / "scale.json").read_text())
    model = read_model(work / "colmap" / "sparse_txt" / "0")
    c, n = door_edge.door_plane(scale)
    a = answer_key.analyse(model, np.array(scale["world_from_colmap"], float), c, n)["arrays"]
    return a["xyz"][a["past"]], a["cams"][a["cam_dist"] > 0]


def answer_key_depth(work: Path, rule: str = "rendered", deg: float = DEG) -> tuple[Pose, np.ndarray]:
    """The frozen answer key (STATUS, Part 2 criteria) as a depth panorama from c."""
    scale = json.loads((work / "scale.json").read_text())
    pose = pose_from_work(work)
    ply = splats.read(work / "splat" / "measured.ply", quiet=True)
    v = ply["vertex"].data
    w_from_c = np.array(scale["world_from_colmap"], float)
    xyz = splats.apply(w_from_c, splats.centres(ply))
    sigma = np.exp(np.stack([v["scale_0"], v["scale_1"], v["scale_2"]], 1).astype(float)).max(1) * splats.split(w_from_c)[0]
    kp, _ = key_points(work)
    return pose, key_depth(pose, xyz, splats.opacity(ply), sigma, kp, scale, rule, deg)


def map_png(path: Path, pose: Pose, manifest: dict, rung: str, pts: np.ndarray, seen: np.ndarray, door: dict,
            shares: dict) -> Path:
    font = ImageFont.load_default(size=15)
    xz = pts[:, [0, 2]]
    lo, hi = np.percentile(xz, 1, axis=0) - 0.5, np.percentile(xz, 99, axis=0) + 0.5
    img = Image.new("RGB", (900, 820), "white")
    draw = ImageDraw.Draw(img)
    panel = plots.Panel((10, 10, 890, 740), lo, hi, top=True)
    thin = np.random.default_rng(0).permutation(len(pts))[:150_000]
    panel.points(draw, xz[thin][~seen[thin]], (185, 185, 185))
    panel.points(draw, xz[thin][seen[thin]], (200, 90, 20))
    c = pose.c_world[[0, 2]]
    for yaw in (rung_yaws(manifest, rung) if rung != "P" else []):
        for edge in (-lv.H_FOV_DEG / 2, lv.H_FOV_DEG / 2):
            d = world_dirs(pose, Rotation.from_euler("y", yaw + edge, degrees=True).as_matrix() @ np.array([0, 0, 1.0]))
            a, b = panel.px(np.array([c, c + 3.0 * d[[0, 2]] / max(np.linalg.norm(d[[0, 2]]), 1e-9)]))
            draw.line([tuple(a), tuple(b)], fill=(40, 40, 40), width=1)
    o = door_edge.opening({"door": door})
    lat = o.lateral[[0, 2]]
    a, b = panel.px(np.array([o.centre[[0, 2]] - lat * 0.36, o.centre[[0, 2]] + lat * 0.36]))
    draw.line([tuple(a), tuple(b)], fill=(0, 0, 0), width=5)
    pc = panel.px(c[None])[0]
    draw.ellipse([pc[0] - 4, pc[1] - 4, pc[0] + 4, pc[1] + 4], fill=(0, 0, 0))
    draw.text((10, 750), f"{rung}: plan view, x right, z down the page; answer-key surface grey, seen by the rung orange; "
              "lines: the views' edges; black bar: the door", fill=(0, 0, 0), font=font)
    draw.text((10, 772), f"share of directions shown {shares['shareOfDirections']:.3f}; share of the key seen "
              f"{shares['seenShareOfKey']:.3f}; not scanned in view {shares['notScannedInView']:.3f}", fill=(0, 0, 0), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def run(work: Path, rule: str = "rendered", deg: float = DEG) -> dict:
    scale = json.loads((work / "scale.json").read_text())
    manifest = json.loads((work / "ladder" / "views" / "manifest.json").read_text())
    pose = pose_from_work(work)
    ply = splats.read(work / "splat" / "measured.ply", quiet=True)
    v = ply["vertex"].data
    w_from_c = np.array(scale["world_from_colmap"], float)
    xyz = splats.apply(w_from_c, splats.centres(ply))
    sigma = np.exp(np.stack([v["scale_0"], v["scale_1"], v["scale_2"]], 1).astype(float)).max(1) * splats.split(w_from_c)[0]
    op = splats.opacity(ply)
    kp, kc = key_points(work)
    dirs, wt = equirect_dirs(deg)
    flat = dirs.reshape(-1, 3)
    cm = colmap_depth(pose, work, deg)
    doc = {"frame": "pano rig frame of rig/y000p00/5pano_0000.jpg, from c", "cMetres": [round(float(x), 4) for x in pose.c_world],
           "cellDeg": deg, "tauM": TAU_M, "footprint": __doc__.split("A Gaussian's footprint")[1].strip().replace("\n", " "),
           "rules": {}, "rungs": {}}
    out = None
    for rl in RULES:
        depth = key_depth(pose, xyz, op, sigma, kp, scale, rl, deg)
        finite = np.isfinite(depth)
        pts, pw = surface_points(pose, depth)
        vol = ScoredVolume.build(pts, scale["door"], kp, kc)
        in_v = np.zeros(depth.size, bool)
        in_v[np.flatnonzero(finite.reshape(-1))] = vol.contains(pts)
        door = through_door(pose, scale, deg)
        rd = {"directionsWithSurface": round(float(wt[finite].sum()), 4),
              "doorway": {"shareOfDirections": round(float(wt[door].sum()), 4),
                          "withSurface": round(float(wt[door & finite].sum() / max(wt[door].sum(), 1e-12)), 4)},
              "notScanned": round(float(wt[~finite].sum()), 4),
              "agreementWithColmap": {t: agreement(depth, cm, wt, np.ones(depth.shape, bool), tau=t) for t in (0.05, 0.15, 0.30)}}
        not_key = ~np.isfinite(point_depth(pose, kp, deg))
        pooled = {"cells": 0, "within": 0}
        rd["inViewOutsideKeyPoints"] = {}
        for rung in ("R1", "R2", "R4", "R8"):
            m = in_rung(flat, manifest, rung).reshape(depth.shape) & not_key
            a = agreement(depth, cm, wt, m)
            rd["inViewOutsideKeyPoints"][rung] = a
            if a["cells"]:
                pooled["cells"] += a["cells"]
                pooled["within"] += round(a["withinTau"] * a["cells"])
        rd["call92Pooled"] = {"cells": pooled["cells"], "withinTau": round(pooled["within"] / max(pooled["cells"], 1), 4)}
        if rl == "planes":
            b = fit_room_box(xyz, op, scale)
            rd["box"] = {k: round(float(getattr(b, k)), 3) for k in ("u_min", "u_max", "v_min", "v_max", "y_min", "y_max")}
        doc["rules"][rl] = rd
        if rl == rule:
            out = (depth, finite, pts, in_v)
    depth, finite, pts, in_v = out
    fin = finite.reshape(-1)
    for rung in RUNG_NAMES:
        m = in_rung(flat, manifest, rung)
        key_mask = fin & in_v
        shares = {"shareOfDirections": round(float(wt.reshape(-1)[m].sum()), 4),
                  "seenShareOfKey": round(float(wt.reshape(-1)[key_mask & m].sum() / wt.reshape(-1)[key_mask].sum()), 4),
                  "notScannedInView": round(float(wt.reshape(-1)[~fin & m].sum() / max(wt.reshape(-1)[m].sum(), 1e-12)), 4),
                  "agreementInView": {t: agreement(depth, cm, wt, m.reshape(depth.shape), tau=t) for t in (0.15, 0.30)}}
        doc["rungs"][rung] = shares
        seen_pts = m[fin]
        map_png(work / "ladder" / rung / "visibility.png", pose, manifest, rung, pts, seen_pts, scale["door"], shares)
    doc["rule"] = rule
    (work / "ladder" / "visibility.json").write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=WORK)
    ap.add_argument("--rule", choices=RULES, default="rendered")
    a = ap.parse_args(argv)
    doc = run(a.work, a.rule)
    for rl, rd in doc["rules"].items():
        r8 = rd["inViewOutsideKeyPoints"]["R8"]
        print(f"{rl:9s}: call 92 pooled R1+R2+R4+R8 in view, within 0.15 m of COLMAP: {rd['call92Pooled']['withinTau']:.1%} "
              f"of {rd['call92Pooled']['cells']} cells; union (R8's view) {r8['withinTau']:.1%} of {r8['cells']}"
              + (f"; box {rd['box']}" if "box" in rd else ""))
    for rl, rd in doc["rules"].items():
        ag = rd["agreementWithColmap"]
        print(f"{rl:9s}: surface in {rd['directionsWithSurface']:.1%} of directions; agrees with COLMAP within "
              f"0.05 / 0.15 / 0.30 m in {ag[0.05]['withinTau']:.0%} / {ag[0.15]['withinTau']:.0%} / {ag[0.30]['withinTau']:.0%} "
              f"of {ag[0.15]['cells']} shared cells")
    for rung, s in doc["rungs"].items():
        print(f"{rung:4s} shown {s['shareOfDirections']:.3f} of directions; sees {s['seenShareOfKey']:.3f} of the key; "
              f"{s['notScannedInView']:.3f} of its view not scanned")
    print(f"written: {a.work / 'ladder' / 'visibility.json'} and a map per rung (rule {doc['rule']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""A synthetic measured room and a Marble-like world of it, for part 2's tests and the viewer fixture.

World frame (the one scale.py builds): metres, floor y = 0, +y up, the room's long axis along +x, the
door in the wall at x = +2. The room is 4 m x 3.2 m x 2.5 m with a bed, a desk, a shelf and a picture.
The real hallway is grey and the passes saw only its first half metre; the Marble-like world re-imagines
the room (slightly different colours, 1 cm noise) and invents the hallway in sage green with a turn.

Native frames, as the real files will arrive:
- measured: a COLMAP-like frame (y down, 0.37 m a unit, turned and tilted), with a fake COLMAP model
  holding the pano camera and the three passes' cameras;
- Marble: raw OpenCV axes of the pano camera (x right, y down, z towards the door), units such that
  metres = raw x metric_scale_factor, where the reported factor is 4 % off and the yaw 7 degrees off.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial.transform import Rotation

import photo
import splats
import views
from colmap_model import Camera, Img, Model, write_model

DOOR_X, DOOR_HALF, DOOR_H = 2.0, 0.45, 2.0
DOOR_WIDTH = 2 * DOOR_HALF
ROOM = (np.array([-2.0, 0.0, -1.6]), np.array([2.0, 2.5, 1.6]))
STUB_END_X = 2.5  # the passes went half a metre past the door frame
PANO_W = np.array([0.0, 1.6, 0.0])
VIEW = 1440
F = VIEW / 2

S_COLMAP = 0.37
R_WORLD_FROM_COLMAP = (Rotation.from_euler("y", 40, degrees=True) * Rotation.from_euler("x", 182, degrees=True)).as_matrix()
T_WORLD_FROM_COLMAP = np.array([0.3, 1.1, -0.4])
# camera axes (x right, y down, z forward) in world columns, for a camera facing +x
CAM_FACING_X = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])
MSF_TRUE = 1.7
MSF_REPORTED = MSF_TRUE * 1.04
MARBLE_YAW_ERR = 7.0
MARBLE_ORIGIN_ERR = np.array([0.03, -0.02, 0.01])


@dataclass
class Face:
    origin: np.ndarray
    u: np.ndarray
    v: np.ndarray
    normal: np.ndarray
    paint: str
    hole: tuple | None = None  # (u0, u1, v0, v1) in metres along u and v


def box_faces(lo, hi, paint, inside=False, skip=()):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    out = []
    for axis in range(3):
        a, b = [i for i in range(3) if i != axis]
        for side, val in ((0, lo[axis]), (1, hi[axis])):
            if (axis, side) in skip:
                continue
            o = lo.copy()
            o[axis] = val
            u = np.zeros(3); u[a] = hi[a] - lo[a]
            v = np.zeros(3); v[b] = hi[b] - lo[b]
            n = np.zeros(3); n[axis] = (-1 if side == 0 else 1) * (-1 if inside else 1)
            out.append(Face(o, u, v, n, paint))
    return out


def _hash(*keys) -> np.ndarray:
    h = np.zeros(np.broadcast(*keys).shape, dtype=np.uint64)
    for k in keys:
        h = (h * np.uint64(1000003)) ^ np.asarray(k, dtype=np.int64).astype(np.uint64)
    h ^= h >> np.uint64(13)
    h *= np.uint64(0x9E3779B97F4A7C15)
    return ((h >> np.uint64(40)) & np.uint64(0xFFFF)).astype(np.float64) / 65535.0


def paint(name: str, p: np.ndarray, rng: np.random.Generator, shift: float = 0.0) -> np.ndarray:
    x, y, z = p.T
    grain = 0.04 * np.sin(x * 40 + 3 * np.sin(z * 7))
    if name == "floor":
        plank = np.floor(z / 0.18)
        tone = 0.45 + 0.15 * _hash(plank, np.floor((x + 13 * plank) / 1.3))
        rgb = np.stack([tone + 0.18, tone, tone - 0.15], 1) + grain[:, None]
    elif name == "wall":
        rgb = np.tile([0.86, 0.83, 0.76], (len(p), 1)) + 0.03 * (_hash(np.floor(x * 9), np.floor(y * 9), np.floor(z * 9))[:, None] - 0.5)
        art = (np.abs(z - 1.6) < 0.01) & (x > -0.6) & (x < 0.4) & (y > 1.2) & (y < 1.9)
        cells = _hash(np.floor(x[art] * 5), np.floor(y[art] * 5))
        rgb[art] = np.stack([0.2 + 0.7 * cells, 0.3 + 0.4 * (1 - cells), 0.6 * cells + 0.2], 1)
        accent = np.abs(x + 2.0) < 0.01
        rgb[accent] = [0.45, 0.55, 0.68]
    elif name == "ceiling":
        rgb = np.tile([0.94, 0.93, 0.9], (len(p), 1))
    elif name == "bed":
        stripe = (np.floor(x / 0.2) % 2)[:, None]
        rgb = np.where(stripe > 0, [0.2, 0.32, 0.55], [0.85, 0.85, 0.88])
    elif name == "desk":
        rgb = np.stack([0.35 + grain, 0.22 + grain, 0.12 + grain], 1)
    elif name == "shelf":
        book = _hash(np.floor(z / 0.05), np.floor(y / 0.35))
        rgb = np.stack([0.3 + 0.6 * book, 0.2 + 0.5 * (1 - book), 0.25 + 0.3 * book], 1)
    elif name == "hall":
        rgb = np.tile([0.62, 0.6, 0.57], (len(p), 1)) + 0.03 * (_hash(np.floor(x * 7), np.floor(z * 7))[:, None] - 0.5)
    elif name == "invented_wall":
        rgb = np.where((y < 0.9)[:, None], [0.34, 0.45, 0.36], [0.62, 0.72, 0.6])
        rgb[np.abs(y - 0.9) < 0.03] = [0.95, 0.94, 0.9]
    elif name == "invented_floor":
        rgb = np.where(((np.floor(x / 0.3) + np.floor(z / 0.3)) % 2 == 0)[:, None], [0.15, 0.15, 0.17], [0.9, 0.88, 0.84])
        rug = (np.abs(z - 1.5) < 0.35) & (x > 2.2) & (x < 3.0)
        rgb[rug] = [0.62, 0.18, 0.15]
    elif name == "invented_thing":
        rgb = np.tile([0.85, 0.6, 0.2], (len(p), 1))
    else:
        raise ValueError(name)
    rgb = rgb + 0.02 * rng.standard_normal(rgb.shape)
    if shift:
        rgb = rgb * (1 + shift * np.array([0.6, -0.2, -0.5]))
    return np.clip(rgb, 0, 1)


def room_faces() -> list[Face]:
    faces = []
    for f in box_faces(*ROOM, "wall", inside=True):
        if f.normal[1] > 0.5:
            f.paint = "floor"
        elif f.normal[1] < -0.5:
            f.paint = "ceiling"
        if f.normal[0] < -0.5 and abs(f.origin[0] - DOOR_X) < 1e-9:
            # the door wall; u runs along y, v along z for an x face
            f.hole = (0.0, DOOR_H, ROOM[0][2] * -1 - DOOR_HALF, ROOM[0][2] * -1 + DOOR_HALF)
        faces.append(f)
    faces += box_faces([-1.9, 0.0, 0.4], [-0.9, 0.5, 1.6], "bed", skip=((1, 0),))
    faces += box_faces([0.8, 0.0, -1.6], [1.9, 0.75, -1.0], "desk", skip=((1, 0),))
    faces += box_faces([-2.0, 0.0, -1.4], [-1.7, 1.8, -0.6], "shelf", skip=((1, 0),))
    return faces


def hall_faces(end_x: float, real: bool) -> list[Face]:
    """The hallway beyond the door: the real one (grey) only to end_x, or Marble's invented one with its turn."""
    wall, floor = ("hall", "hall") if real else ("invented_wall", "invented_floor")
    h = 2.4
    faces = [
        Face(np.array([DOOR_X, 0, -0.5]), np.array([end_x - DOOR_X, 0, 0]), np.array([0, 0, 1.0]), np.array([0, 1.0, 0]), floor),
        Face(np.array([DOOR_X, h, -0.5]), np.array([end_x - DOOR_X, 0, 0]), np.array([0, 0, 1.0]), np.array([0, -1.0, 0]), "ceiling"),
        Face(np.array([DOOR_X, 0, -0.5]), np.array([end_x - DOOR_X, 0, 0]), np.array([0, h, 0]), np.array([0, 0, 1.0]), wall),
    ]
    if real:
        faces.append(Face(np.array([DOOR_X, 0, 0.5]), np.array([end_x - DOOR_X, 0, 0]), np.array([0, h, 0]), np.array([0, 0, -1.0]), wall))
        return faces
    faces += [
        Face(np.array([DOOR_X, 0, 0.5]), np.array([0.1, 0, 0]), np.array([0, h, 0]), np.array([0, 0, -1.0]), wall),
        Face(np.array([3.1, 0, -0.5]), np.array([0, 0, 3.0]), np.array([0, h, 0]), np.array([-1.0, 0, 0]), wall),
        Face(np.array([2.1, 0, 0.5]), np.array([0, 0, 2.0]), np.array([0, h, 0]), np.array([1.0, 0, 0]), wall),
        Face(np.array([2.1, 0, 2.5]), np.array([1.0, 0, 0]), np.array([0, h, 0]), np.array([0, 0, -1.0]), wall),
        Face(np.array([2.1, 0, 0.5]), np.array([1.0, 0, 0]), np.array([0, 0, 2.0]), np.array([0, 1.0, 0]), floor),
        Face(np.array([2.1, h, 0.5]), np.array([1.0, 0, 0]), np.array([0, 0, 2.0]), np.array([0, -1.0, 0]), "ceiling"),
    ]
    faces += box_faces([2.75, 0.0, 1.9], [3.05, 0.8, 2.4], "invented_thing", skip=((1, 0),))
    return faces


def sample(faces: list[Face], density: float, rng: np.random.Generator, shift: float = 0.0, noise: float = 0.0):
    xyz, rgb, nrm, tan = [], [], [], []
    for f in faces:
        lu, lv = np.linalg.norm(f.u), np.linalg.norm(f.v)
        n = rng.poisson(density * lu * lv)
        a, b = rng.random(n), rng.random(n)
        if f.hole:
            u0, u1, v0, v1 = f.hole
            inside = (a * lu >= u0) & (a * lu <= u1) & (b * lv >= v0) & (b * lv <= v1)
            a, b = a[~inside], b[~inside]
        p = f.origin + a[:, None] * f.u + b[:, None] * f.v
        p = p + noise * rng.standard_normal(p.shape)
        xyz.append(p)
        rgb.append(paint(f.paint, p, rng, shift))
        nrm.append(np.tile(f.normal, (len(p), 1)))
        tan.append(np.tile(f.u / lu, (len(p), 1)))
    return np.concatenate(xyz), np.concatenate(rgb), np.concatenate(nrm), np.concatenate(tan)


def measured_world(density: float, seed: int = 1):
    rng = np.random.default_rng(seed)
    return sample(room_faces() + hall_faces(STUB_END_X, real=True), density, rng)


def marble_world(density: float, seed: int = 2, corridor: bool = True):
    rng = np.random.default_rng(seed)
    faces = room_faces() + (hall_faces(3.1, real=False) if corridor else [])
    return sample(faces, density, rng, shift=0.06, noise=0.01)


def world_from_colmap() -> np.ndarray:
    return splats.sim3(S_COLMAP, R_WORLD_FROM_COLMAP, T_WORLD_FROM_COLMAP)


def world_from_marble_true() -> np.ndarray:
    r = Rotation.from_euler("y", MARBLE_YAW_ERR, degrees=True).as_matrix() @ CAM_FACING_X
    return splats.sim3(MSF_TRUE, r, PANO_W + MARBLE_ORIGIN_ERR)


def to_native(m_world_from_native: np.ndarray, xyz, normal, tangent):
    inv = splats.invert(m_world_from_native)
    _, r, _ = splats.split(inv)
    return splats.apply(inv, xyz), normal @ r.T, tangent @ r.T


def camera_poses() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Frame name -> (centre in world, world-from-camera rotation) for the pano and the three passes."""
    poses = {"5pano_0000": (PANO_W.copy(), CAM_FACING_X.copy())}
    for order, name, height, n in ((1, "raised", 2.0, 10), (2, "head", 1.6, 14), (3, "hip", 0.9, 10)):
        for k in range(n):
            a = 2 * np.pi * k / n + 0.3 * order
            c = np.array([1.2 * np.cos(a), height, 0.9 * np.sin(a)])
            heading = np.degrees(a) + 90.0
            r = Rotation.from_euler("y", heading, degrees=True).as_matrix() @ CAM_FACING_X
            poses[f"{order}{name}_{k:04d}"] = (c, r)
    return poses


def write_colmap(model_dir: Path, work: Path) -> Model:
    """A text model with the reference view of every sphere and all eight views of the pano still, and the
    frames.json part 1 would have written."""
    m = splats.invert(world_from_colmap())
    images, frames = {}, []
    for frame, (c_w, r_wc) in camera_poses().items():
        c_c = splats.apply(m, c_w[None])[0]
        r_ref = r_wc.T @ R_WORLD_FROM_COLMAP
        pano = frame.startswith("5pano")
        for view in (views.VIEWS if pano else (views.REF_VIEW,)):
            r_cam_from_colmap = views.cam_from_rig(view) @ r_ref
            t = -r_cam_from_colmap @ c_c
            q = Rotation.from_matrix(r_cam_from_colmap).as_quat(scalar_first=True)
            i = len(images) + 1
            images[i] = Img(i, list(q), list(t), 1, f"rig/{view.name}/{frame}.jpg", [])
        p = frame[1:].split("_")[0]
        frames.append({"name": frame, "pass": p, "sample": int(frame.split("_")[1]),
                       "views": [v.token for v in views.VIEWS] if pano else ["0@0"], "answer_key": False})
    model = Model({1: Camera(1, "PINHOLE", VIEW, VIEW, [F, F, F, F])}, images, {})
    write_model(model, model_dir)
    work.mkdir(parents=True, exist_ok=True)
    (work / "frames.json").write_text(json.dumps({"version": 1, "view_size": VIEW, "focal_px": F, "frames": frames}))
    (work / "colmap_report.json").write_text(json.dumps({"pass": True, "model_dir": Path(os.path.relpath(model_dir, work)).as_posix()}))
    return model


PHOTO_DENSITY = 3000
PHOTO_SIZE = 240
REAL_HALL_END_X = 4.0  # the photograph sees down the real hallway further than the passes went


def render_pano_photos(model: Model, images: Path, seed: int = 7) -> list[Path]:
    """The pano still's eight cut views, as photographs of the measured room (and the real hallway beyond the
    door), drawn from a dense sampling of the room and enlarged to the views' size."""
    rng = np.random.default_rng(seed)
    xyz, rgb, _, _ = sample(room_faces() + hall_faces(REAL_HALL_END_X, real=True), PHOTO_DENSITY, rng)
    w_from_c = world_from_colmap()
    out = []
    for v in photo.pano_views_any(model, w_from_c, PHOTO_SIZE):
        img, cov = photo.draw(v.cam_from_world, v.k, PHOTO_SIZE, PHOTO_SIZE, xyz, rgb)
        # what the dense sampling missed takes its nearest neighbour's colour, as a photograph has no holes
        idx = ndimage.distance_transform_edt(~cov, return_distances=False, return_indices=True)
        img = img[idx[0], idx[1]] if cov.any() else np.full_like(img, 0.5)
        pic = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).resize((VIEW, VIEW), Image.Resampling.BILINEAR)
        path = images / v.name
        path.parent.mkdir(parents=True, exist_ok=True)
        pic.save(path, quality=88)
        out.append(path)
    return out


CHECK_LENGTH = 1.1  # the desk's front top edge


def door_corners_world() -> dict[str, np.ndarray]:
    return {"A": np.array([DOOR_X, 0.0, -DOOR_HALF]), "B": np.array([DOOR_X, 0.0, DOOR_HALF])}


def door_top_world() -> dict[str, np.ndarray]:
    """The frame's top inside corners, E over A and F over B."""
    return {"E": np.array([DOOR_X, DOOR_H, -DOOR_HALF]), "F": np.array([DOOR_X, DOOR_H, DOOR_HALF])}


def check_ends_world() -> dict[str, np.ndarray]:
    return {"C": np.array([0.8, 0.75, -1.0]), "D": np.array([1.9, 0.75, -1.0])}


def project(model: Model, image_name: str, p_world: np.ndarray) -> tuple[float, float] | None:
    im = next(i for i in model.images.values() if i.name == image_name)
    r = Rotation.from_quat(im.qvec, scalar_first=True).as_matrix()
    p_c = splats.apply(splats.invert(world_from_colmap()), p_world[None])[0]
    x = r @ p_c + np.array(im.tvec)
    if x[2] <= 0:
        return None
    u, v = F * x[0] / x[2] + F, F * x[1] / x[2] + F
    return (u, v) if 20 <= u < VIEW - 20 and 20 <= v < VIEW - 20 else None


def views_seeing_the_door(model: Model, n: int = 3) -> list[str]:
    """The pano's front view first, then the passes' views that see both corners, as a person would pick them."""
    names = sorted((i.name for i in model.images.values()), key=lambda s: ("5pano" not in s, s))
    ok = [nm for nm in names if all(project(model, nm, p) for p in door_corners_world().values())]
    return ok[:n]


def views_seeing(model: Model, points: dict, n: int = 3) -> list[str]:
    names = sorted(i.name for i in model.images.values())
    return [nm for nm in names if all(project(model, nm, p) for p in points.values())][:n]


def door_click_lines(model: Model, images=None, jitter: float = 0.0, seed: int = 4, check: bool = True,
                     top: bool = False) -> list[str]:
    rng = np.random.default_rng(seed)
    images = images or views_seeing_the_door(model)
    lines = []
    targets = [(label, p, images) for label, p in door_corners_world().items()]
    if check:
        seen = views_seeing(model, check_ends_world())
        targets += [(label, p, seen) for label, p in check_ends_world().items()]
    if top:
        seen = views_seeing(model, door_top_world())
        targets += [(label, p, seen) for label, p in door_top_world().items()]
    for label, p, views in targets:
        for name in views:
            u, v = project(model, name, p)
            u, v = u + jitter * rng.standard_normal(), v + jitter * rng.standard_normal()
            lines.append(f"- Door click {label} {name}: {u:.2f} {v:.2f}")
    return lines


# The doorway fallback's world: Marble made from a still taken at the threshold, looking into the room,
# so its origin is that camera and it holds the door wall, the near half of the room and the invented
# hallway behind the camera.
DOORWAY_CAM_W = np.array([DOOR_X + 0.05, 1.5, 0.02])
DOORWAY_MSF = 1.3
DOORWAY_YAW_DEG = 180.0 + 6.0


def world_from_doorway_true() -> np.ndarray:
    r = Rotation.from_euler("y", DOORWAY_YAW_DEG, degrees=True).as_matrix() @ CAM_FACING_X
    return splats.sim3(DOORWAY_MSF, r, DOORWAY_CAM_W)


def write_doorway_world(work: Path, world_id: str, density: float, seed: int = 5, display_flip: bool = True) -> str:
    """Write marble_<id>.ply and <id>.json for a doorway world; return the NOTES line of the four corner picks,
    as SuperSplat shows the file (turned over when display_flip, as a viewer that puts y-down files upright)."""
    rng = np.random.default_rng(seed)
    near = [f for f in room_faces() if f.origin[0] + max(f.u[0], 0) + max(f.v[0], 0) > 0.5]
    xyz, rgb, n, t = sample(near + hall_faces(3.1, real=False), density, rng, shift=0.06, noise=0.01)
    xyz, rgb, n, t = xyz[xyz[:, 0] > 0.5], rgb[xyz[:, 0] > 0.5], n[xyz[:, 0] > 0.5], t[xyz[:, 0] > 0.5]
    raw, n_r, t_r = to_native(world_from_doorway_true(), xyz, n, t)
    marble = work / "marble"
    splats.write_splats(marble / f"marble_{world_id}.ply", raw, rgb, n_r, t_r, size=splat_size(density) / DOORWAY_MSF,
                        thickness=0.002 / DOORWAY_MSF)
    j = marble_json(world_id)
    j["assets"]["splats"]["semantics_metadata"]["metric_scale_factor"] = DOORWAY_MSF * 0.95
    (marble / f"{world_id}.json").write_text(json.dumps(j, indent=2))
    corners = np.array([door_corners_world()["A"], door_corners_world()["B"], door_top_world()["E"], door_top_world()["F"]])
    picks = splats.apply(splats.invert(world_from_doorway_true()), corners)
    if display_flip:
        picks = picks * [1.0, -1.0, -1.0]
    return "- Doorway corners in the Marble world (A B E F, four 3D points): " + " ; ".join(
        " ".join(f"{v:.5f}" for v in q) for q in picks)


def marble_json(world_id: str) -> dict:
    return {"world_id": world_id, "model": "marble-1.1",
            "assets": {"splats": {"semantics_metadata": {"metric_scale_factor": MSF_REPORTED,
                                                         "ground_plane_offset": PANO_W[1] / MSF_TRUE}}}}


def splat_size(density: float) -> float:
    """Gaussian sigma in metres that closes the gaps between splats sampled at this density per square metre."""
    return 0.75 / np.sqrt(density)


def write_scene(root: Path, density_measured: float, density_marble: float, world_id: str = "synthworld",
                corridor: bool = True, photos: bool = True, marble_mirrored: bool = False) -> dict:
    """Everything part 2 reads, laid out as on the day: work/, capture/NOTES.md, the trained splat, a Marble
    export, and the pano still's cut views as images."""
    work = root / "pipeline" / "work"
    model = write_colmap(work / "colmap" / "sparse_txt" / "0", work)
    if photos:
        render_pano_photos(model, work / "images")
    xyz, rgb, n, t = measured_world(density_measured)
    xyz_c, n_c, t_c = to_native(world_from_colmap(), xyz, n, t)
    splats.write_splats(work / "splat" / "splat_raw.ply", xyz_c, rgb, n_c, t_c, size=splat_size(density_measured) / S_COLMAP,
                        thickness=0.002 / S_COLMAP)
    xyz_m, rgb_m, n_m, t_m = marble_world(density_marble, corridor=corridor)
    xyz_r, n_r, t_r = to_native(world_from_marble_true(), xyz_m, n_m, t_m)
    marble = work / "marble"
    splats.write_splats(marble / f"marble_{world_id}.ply", xyz_r, rgb_m, n_r, t_r, size=splat_size(density_marble) / MSF_TRUE,
                        thickness=0.002 / MSF_TRUE)
    if marble_mirrored:  # raw +x to the left, as World Labs' docs describe it
        ply = splats.read(marble / f"marble_{world_id}.ply", quiet=True)
        splats.write_subset(ply, np.ones(len(ply["vertex"].data), bool), marble / f"marble_{world_id}.ply",
                            rows=splats.mirror_x(ply["vertex"].data))
    (marble / f"{world_id}.json").write_text(json.dumps(marble_json(world_id), indent=2))
    notes = root / "capture" / "NOTES.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Capture notes (synthetic)", "", "## Scale anchor", "",
             f"- **Door frame inside width (tape), in metres:** {DOOR_WIDTH:.3f}",
             f"- Door frame inside width, second tape (cross-check), in metres: {DOOR_WIDTH + 0.002:.3f}",
             f"- Check length (what it is, and its length in metres): desk top, front edge, {CHECK_LENGTH:.3f}", "",
             "## Later (filled in at cleaning and scaling)", "", "- Cleaning box:",
             "- Door points picked in the splat (two 3D points):", ""]
    lines += door_click_lines(model)
    notes.write_text("\n".join(lines) + "\n")
    return {"work": work, "notes": notes, "world_id": world_id}

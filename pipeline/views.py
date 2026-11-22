"""The eight virtual pinhole cameras cut from every sphere, and the rig COLMAP builds from them.

This table is the only place yaw, pitch, image size and the rig rotations are defined: cut_views.py,
the rig config and the tests all read it.

The rig frame is the OpenCV camera frame of the yaw 0, pitch 0 view (x right, y down, z forward).
ffmpeg's v360 filter (equirect in, flat out, rotation order ypr) turns positive yaw to the right and
positive pitch upwards, so a view's camera-from-rig rotation is Rx(-pitch) @ Ry(-yaw).
tests/test_rig_convention.py proves this against the real ffmpeg; an end-to-end check alone cannot,
because COLMAP still "registers" every image of a rig frame whose pitched views are wrongly rotated.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation

VIEW_SIZE = 1440
FOV_DEG = 90


@dataclass(frozen=True)
class View:
    yaw: int
    pitch: int

    @property
    def name(self) -> str:
        return f"y{self.yaw:03d}p{self.pitch:02d}"

    @property
    def token(self) -> str:
        return f"{self.yaw}@{self.pitch}"

    @property
    def ffmpeg_yaw(self) -> float:
        return wrap_yaw(self.yaw)


def wrap_yaw(deg: float) -> float:
    """Into [-180, 180), which is all v360 accepts."""
    out = ((deg + 180) % 360) - 180
    return int(out) if float(out).is_integer() else out


VIEWS: tuple[View, ...] = (
    View(0, 0), View(90, 0), View(180, 0), View(270, 0),
    View(45, 40), View(135, 40), View(225, 40), View(315, 40),
)
REF_VIEW = VIEWS[0]
VIEW_BY_TOKEN = {v.token: v for v in VIEWS}
VIEW_BY_NAME = {v.name: v for v in VIEWS}

# Call 40: at head and hip height the stick is held upright in front, so the operator fills the
# views behind the camera; the raised pass and the pano still have nobody in frame.
DEFAULT_DROP: dict[str, tuple[str, ...]] = {
    "raised": (),
    "head": ("180@0", "135@40", "225@40"),
    "hip": ("180@0", "135@40", "225@40"),
    "key": ("180@0", "135@40", "225@40"),
    "pano": (),
}


def parse_drop(text: str) -> tuple[str, ...]:
    """'180@0,135@40' -> ('180@0', '135@40'); '' or 'none' -> ()."""
    text = text.strip()
    if text.lower() in ("", "none"):
        return ()
    tokens = tuple(t.strip() for t in text.split(",") if t.strip())
    for t in tokens:
        if t not in VIEW_BY_TOKEN:
            raise ValueError(f"unknown view '{t}'; the views are {', '.join(VIEW_BY_TOKEN)}")
    if REF_VIEW.token in tokens:
        raise ValueError(f"view {REF_VIEW.token} is the rig's reference camera and cannot be dropped")
    return tokens


def kept_views(drop: tuple[str, ...]) -> tuple[View, ...]:
    return tuple(v for v in VIEWS if v.token not in drop)


def focal(size: int = VIEW_SIZE) -> float:
    return size / 2.0  # a 90 degree field of view


def cam_from_rig(view: View) -> np.ndarray:
    r = Rotation.from_euler("x", -view.pitch, degrees=True) * Rotation.from_euler("y", -view.yaw, degrees=True)
    return r.as_matrix()


def quat_wxyz(matrix: np.ndarray) -> list[float]:
    q = Rotation.from_matrix(matrix).as_quat(scalar_first=True)
    if q[0] < 0:
        q = -q
    return [float(round(c, 12)) + 0.0 for c in q]


def direction_from_equirect(u, v, width: int, height: int) -> np.ndarray:
    """Equirect pixel coordinates (continuous; 0 is the left/top edge) -> unit directions in the rig frame."""
    lon = np.asarray(u) / width * 2 * np.pi - np.pi
    lat = np.pi / 2 - np.asarray(v) / height * np.pi
    return np.stack([np.cos(lat) * np.sin(lon), -np.sin(lat), np.cos(lat) * np.cos(lon)], -1)


def equirect_from_direction(d, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    d = np.asarray(d, float)
    d = d / np.linalg.norm(d, axis=-1, keepdims=True)
    lon = np.arctan2(d[..., 0], d[..., 2])
    lat = np.arcsin(np.clip(-d[..., 1], -1, 1))
    return (lon + np.pi) / (2 * np.pi) * width, (np.pi / 2 - lat) / np.pi * height


def project(view: View, d_rig, size: int = VIEW_SIZE) -> tuple[float, float] | None:
    """Where a rig-frame direction lands in a view (continuous pixels; 0 is the top-left edge), or None."""
    p = cam_from_rig(view) @ np.asarray(d_rig, float)
    if p[2] <= 1e-9:
        return None
    f = focal(size)
    x, y = f * p[0] / p[2] + size / 2, f * p[1] / p[2] + size / 2
    if 0 <= x < size and 0 <= y < size:
        return float(x), float(y)
    return None


def v360_filter(view: View, size: int = VIEW_SIZE, yaw_offset: float = 0) -> str:
    """The cut for one view. yaw_offset turns all eight views of a pass together (the rig is unchanged),
    for a pass whose export put the operator somewhere other than behind view 0@0."""
    return (f"v360=e:flat:h_fov={FOV_DEG}:v_fov={FOV_DEG}:yaw={wrap_yaw(view.yaw + yaw_offset)}:pitch={view.pitch}"
            f":roll=0:rorder=ypr:interp=cubic:w={size}:h={size}")


def rig_config() -> list[dict]:
    """COLMAP rig_configurator input: one rig whose cameras are the folders images/rig/<view>/."""
    cameras = []
    for v in VIEWS:
        cam: dict = {"image_prefix": f"rig/{v.name}/"}
        if v == REF_VIEW:
            cam["ref_sensor"] = True
        else:
            cam["cam_from_rig_rotation"] = quat_wxyz(cam_from_rig(v))
            cam["cam_from_rig_translation"] = [0.0, 0.0, 0.0]
        cameras.append(cam)
    return [{"cameras": cameras}]

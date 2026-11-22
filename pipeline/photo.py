"""Does an aligned Marble world look like the pano it was made from? The photometric half of Gate A.

Marble generates its world from the pano still, and the still's eight cut views are registered in COLMAP
(rig/<view>/5pano_0000.jpg). Marble's splat centres, coloured by their degree-0 SH term, are drawn as
points (z-buffered, each point a small square, at a reduced size) into those views from their registered
poses, and compared with the real images by normalised correlation of luminance over the pixels the points
cover. A world turned the wrong way, mirrored or upside down draws a different picture of the same room,
which geometry alone cannot always tell apart: a box room is nearly symmetric.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial.transform import Rotation

import splats

SIZE = 96
FOOTPRINT = 2
BLUR_PX = 1.0
# A view counts only where the points cover a fair part of it; a view of an empty corner of the world
# would otherwise score its few pixels as confidently as a full one.
MIN_COVER = 0.25
PANO_FRAME = "5pano_0000"


@dataclass
class View:
    name: str
    image: np.ndarray  # luminance 0..1 at the working size, blurred
    k: np.ndarray  # intrinsics at the working size
    cam_from_world: np.ndarray  # 4 x 4: world metres to this camera's OpenCV axes (in COLMAP's units)


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb @ np.array([0.299, 0.587, 0.114])


def intrinsics(cam) -> tuple[float, float, float, float]:
    p = cam.params
    if cam.model == "SIMPLE_PINHOLE":
        return p[0], p[0], p[1], p[2]
    return p[0], p[1], p[2], p[3]


def _camera(model, im, world_from_colmap: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray, int]:
    cam = model.cameras[im.camera_id]
    fx, fy, cx, cy = intrinsics(cam)
    h = max(1, round(size * cam.height / cam.width))
    k = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]]) * np.array([[size / cam.width], [h / cam.height], [1.0]])
    cam_from_colmap = np.eye(4)
    cam_from_colmap[:3, :3] = Rotation.from_quat(im.qvec, scalar_first=True).as_matrix()
    cam_from_colmap[:3, 3] = im.tvec
    return k, cam_from_colmap @ splats.invert(world_from_colmap), h


def pano_views_any(model, world_from_colmap: np.ndarray, size: int = SIZE, frame: str = PANO_FRAME) -> list[View]:
    """The pano's registered views without their images (image left empty), for drawing into."""
    out = []
    for im in sorted(model.images.values(), key=lambda i: i.name):
        if im.name.startswith("rig/") and Path(im.name).stem == frame:
            k, m, h = _camera(model, im, world_from_colmap, size)
            out.append(View(im.name, np.zeros((h, size)), k, m))
    return out


def pano_views(model, images: Path, world_from_colmap: np.ndarray, frame: str = PANO_FRAME, size: int = SIZE) -> list[View]:
    """Every registered view of the pano still whose image is on disk, ready to be drawn into."""
    out = []
    for v in pano_views_any(model, world_from_colmap, size, frame):
        if not (images / v.name).is_file():
            continue
        h, w = v.image.shape
        img = Image.open(images / v.name).convert("L").resize((w, h), Image.Resampling.BOX)
        v.image = ndimage.gaussian_filter(np.asarray(img, np.float64) / 255.0, BLUR_PX)
        out.append(v)
    return out


def draw(cam_from_world: np.ndarray, k: np.ndarray, width: int, height: int, pts: np.ndarray, values: np.ndarray,
         footprint: int = FOOTPRINT) -> tuple[np.ndarray, np.ndarray]:
    """Points drawn nearest-first into a width x height image: (image with values.shape[1] channels, covered mask)."""
    x = splats.apply(cam_from_world, pts)
    z = x[:, 2]
    front = z > 1e-6
    x, z, vals = x[front], z[front], values[front]
    u = k[0, 0] * x[:, 0] / z + k[0, 2] - footprint / 2
    v = k[1, 1] * x[:, 1] / z + k[1, 2] - footprint / 2
    iu, iv = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    pix, depth, src = [], [], []
    idx = np.arange(len(z))
    for du in range(footprint):
        for dv in range(footprint):
            a, b = iu + du, iv + dv
            ok = (a >= 0) & (a < width) & (b >= 0) & (b < height)
            pix.append(b[ok] * width + a[ok])
            depth.append(z[ok])
            src.append(idx[ok])
    pix, depth, src = np.concatenate(pix), np.concatenate(depth), np.concatenate(src)
    img = np.zeros((height * width, vals.shape[1]))
    covered = np.zeros(height * width, bool)
    if len(pix):
        order = np.lexsort((depth, pix))
        first = np.unique(pix[order], return_index=True)[1]
        win = order[first]
        img[pix[win]] = vals[src[win]]
        covered[pix[win]] = True
    return img.reshape(height, width, -1), covered.reshape(height, width)


def ncc(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    a, b = a[mask], b[mask]
    if len(a) < 16:
        return 0.0
    a, b = a - a.mean(), b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 1e-12 else 0.0


def drawn(view: View, pts_world: np.ndarray, lum: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The points drawn into view's camera at its size and blurred as its image was: (luminance, covered)."""
    h, w = view.image.shape
    img, cov = draw(view.cam_from_world, view.k, w, h, pts_world, lum[:, None])
    # blur only what was drawn (normalised convolution), so holes do not darken their neighbours
    weight = ndimage.gaussian_filter(cov.astype(float), BLUR_PX)
    return ndimage.gaussian_filter(img[..., 0] * cov, BLUR_PX) / np.maximum(weight, 1e-9), cov


def score(views: list[View], pts_world: np.ndarray, lum: np.ndarray) -> dict:
    """Cover-weighted mean correlation over the views the points cover enough; None when none qualifies."""
    per = {}
    num = den = 0.0
    for view in views:
        smooth, cov = drawn(view, pts_world, lum)
        cover = float(cov.mean())
        r = ncc(smooth, view.image, cov)
        per[view.name] = {"ncc": round(r, 4), "cover": round(cover, 3)}
        if cover >= MIN_COVER:
            num += cover * r
            den += cover
    return {"score": round(num / den, 4) if den else None, "views": per}

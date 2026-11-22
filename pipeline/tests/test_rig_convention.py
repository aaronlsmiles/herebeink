"""Proves that the rotations written into rig_config.json match what ffmpeg's v360 actually cuts.

White dots are painted on an equirect image at known directions; each of the eight views is cut with
the production filter string; every dot must land within a pixel of where the rig config's quaternion
says it should.
"""
import subprocess

import numpy as np
import pytest
from PIL import Image
from scipy import ndimage
from scipy.spatial.transform import Rotation

import views

EQ_W, EQ_H = 2048, 1024
SIZE = 512
DOT_RADIUS_DEG = 1.0
# A regular grid is symmetric left to right and repeats every 30 degrees, so views at yaw 90 and 270 (180
# apart) see identical patterns and the sign of the yaw cannot show. A golden-angle spiral never repeats
# and is not mirror-symmetric, so every view sees its own pattern.
MARKERS = 72
GOLDEN_ANGLE_DEG = 137.50776405
MAX_LAT_SIN = 0.96  # keeps the markers off the poles, where an equirect smears a dot into a stripe


def marker_directions() -> np.ndarray:
    k = np.arange(MARKERS)
    lon = np.radians((k * GOLDEN_ANGLE_DEG) % 360 - 180)
    sin_lat = np.linspace(-MAX_LAT_SIN, MAX_LAT_SIN, MARKERS)
    cos_lat = np.sqrt(1 - sin_lat**2)
    return np.stack([cos_lat * np.sin(lon), -sin_lat, cos_lat * np.cos(lon)], -1)


@pytest.fixture(scope="module")
def equirect(tmp_path_factory):
    v, u = np.mgrid[0:EQ_H, 0:EQ_W]
    d = views.direction_from_equirect(u + 0.5, v + 0.5, EQ_W, EQ_H).reshape(-1, 3)
    cos_r = np.cos(np.radians(DOT_RADIUS_DEG))
    hit = (d @ marker_directions().T).max(axis=1) > cos_r
    img = np.where(hit, 255, 0).astype(np.uint8).reshape(EQ_H, EQ_W)
    path = tmp_path_factory.mktemp("conv") / "markers.png"
    Image.fromarray(img).convert("RGB").save(path)
    return path


def cut(equirect_path, view, out_path):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(equirect_path), "-vf",
                    views.v360_filter(view, SIZE), "-frames:v", "1", str(out_path)], check=True)
    return np.asarray(Image.open(out_path).convert("L"), dtype=float)


def blob_centroids(img: np.ndarray) -> list[tuple[float, float]]:
    labels, n = ndimage.label(img > 128)
    out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(labels == i)
        w = img[ys, xs]
        out.append((float((xs + 0.5) @ w / w.sum()), float((ys + 0.5) @ w / w.sum())))
    return out


def rig_rotations() -> dict[str, np.ndarray]:
    """The rotation each view gets from rig_config.json, read back from its quaternion."""
    out = {}
    for cam in views.rig_config()[0]["cameras"]:
        name = cam["image_prefix"].split("/")[1]
        q = cam.get("cam_from_rig_rotation", [1.0, 0.0, 0.0, 0.0])
        out[name] = Rotation.from_quat(q, scalar_first=True).as_matrix()
    return out


def predicted(R: np.ndarray) -> list[tuple[float, float]]:
    f = views.focal(SIZE)
    out = []
    for d in marker_directions():
        p = R @ d
        if p[2] <= 0:
            continue
        x, y = f * p[0] / p[2] + SIZE / 2, f * p[1] / p[2] + SIZE / 2
        if 0 <= x < SIZE and 0 <= y < SIZE:
            out.append((x, y))
    return out


@pytest.mark.parametrize("view", views.VIEWS, ids=lambda v: v.name)
def test_every_dot_lands_where_the_rig_config_says(equirect, tmp_path, view):
    img = cut(equirect, view, tmp_path / f"{view.name}.png")
    blobs = blob_centroids(img)
    expected = predicted(rig_rotations()[view.name])
    margin = 20

    inner = [p for p in expected if margin <= p[0] < SIZE - margin and margin <= p[1] < SIZE - margin]
    assert len(inner) >= 3, "the marker grid should put several dots well inside every view"
    for px, py in inner:
        dist = min(np.hypot(bx - px, by - py) for bx, by in blobs)
        assert dist < 1.0, f"{view.name}: dot predicted at ({px:.1f}, {py:.1f}) is {dist:.1f} px from any blob"

    for bx, by in blobs:
        if margin <= bx < SIZE - margin and margin <= by < SIZE - margin:
            dist = min(np.hypot(bx - px, by - py) for px, py in expected)
            assert dist < 1.0, f"{view.name}: blob at ({bx:.1f}, {by:.1f}) matches no predicted dot"


def mirrored_yaw_rotation(view: views.View) -> np.ndarray:
    """A convention that gets the yaw sign wrong: Rx(-pitch) @ Ry(+yaw)."""
    return (Rotation.from_euler("x", -view.pitch, degrees=True)
            * Rotation.from_euler("y", view.yaw, degrees=True)).as_matrix()


@pytest.mark.parametrize("token", ["90@0", "270@0", "45@40", "315@40"])
def test_a_mirrored_yaw_sign_is_caught(equirect, tmp_path, token):
    """Guards the test itself: with the yaw sign flipped the predicted dots must miss by tens of pixels."""
    view = views.VIEW_BY_TOKEN[token]
    blobs = blob_centroids(cut(equirect, view, tmp_path / "mirror.png"))
    inner = [p for p in predicted(mirrored_yaw_rotation(view)) if 20 <= p[0] < SIZE - 20 and 20 <= p[1] < SIZE - 20]
    assert inner
    misses = [min(np.hypot(bx - px, by - py) for bx, by in blobs) for px, py in inner]
    assert max(misses) > 20.0


def test_the_marker_grid_tells_yaw_90_from_yaw_270(equirect, tmp_path):
    a = predicted(rig_rotations()["y090p00"])
    b = predicted(rig_rotations()["y270p00"])
    inner = [(x, y) for x, y in a if 20 <= x < SIZE - 20 and 20 <= y < SIZE - 20]
    assert len(inner) >= 3
    same = [1 for x, y in inner if min(np.hypot(x - u, y - v) for u, v in b) < 5.0]
    assert len(same) <= 1


def test_wrong_rotation_order_is_caught(equirect, tmp_path):
    """Guards the test itself: Ry @ Rx instead of Rx @ Ry must fail on a pitched view."""
    view = views.VIEW_BY_TOKEN["45@40"]
    img = cut(equirect, view, tmp_path / "wrong.png")
    blobs = blob_centroids(img)
    wrong = (Rotation.from_euler("y", -view.yaw, degrees=True)
             * Rotation.from_euler("x", -view.pitch, degrees=True)).as_matrix()
    inner = [p for p in predicted(wrong) if 20 <= p[0] < SIZE - 20 and 20 <= p[1] < SIZE - 20]
    misses = [min(np.hypot(bx - px, by - py) for bx, by in blobs) for px, py in inner]
    assert max(misses) > 5.0


@pytest.mark.parametrize("token,offset,acts_as", [("0@0", 90, "90@0"), ("45@40", 180, "225@40"), ("0@0", -90, "270@0")])
def test_yaw_offset_turns_the_views_together(equirect, tmp_path, token, offset, acts_as):
    view = views.VIEW_BY_TOKEN[token]
    out = tmp_path / "offset.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(equirect), "-vf",
                    views.v360_filter(view, SIZE, yaw_offset=offset), "-frames:v", "1", str(out)], check=True)
    img = np.asarray(Image.open(out).convert("L"), dtype=float)
    blobs = blob_centroids(img)
    expected = predicted(rig_rotations()[views.VIEW_BY_TOKEN[acts_as].name])
    inner = [p for p in expected if 20 <= p[0] < SIZE - 20 and 20 <= p[1] < SIZE - 20]
    assert inner
    for px, py in inner:
        assert min(np.hypot(bx - px, by - py) for bx, by in blobs) < 1.0

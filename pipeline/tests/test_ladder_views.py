"""Task 0.4 of Part 2: the nested flat-view sets cut from the pano still, and the manifest Task 1.1's
upload guard will bind to. Real ffmpeg on small synthetic equirects, as test_rig_convention.py does."""
import hashlib
import json
import subprocess

import numpy as np
import pytest
from PIL import Image
from scipy import ndimage
from scipy.spatial.transform import Rotation

import ladder_views as lv
import views

EQ_W, EQ_H = 2048, 1024


def sha(path) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def dot_equirect(path, dots, radius_deg=2.0):
    """White dots at (yaw, pitch) degrees on black, in views.py's convention (yaw right, pitch up)."""
    v, u = np.mgrid[0:EQ_H, 0:EQ_W]
    d = views.direction_from_equirect(u + 0.5, v + 0.5, EQ_W, EQ_H).reshape(-1, 3)
    hit = np.zeros(len(d), bool)
    for yaw, pitch in dots:
        t = np.array([np.cos(np.radians(pitch)) * np.sin(np.radians(yaw)), -np.sin(np.radians(pitch)),
                      np.cos(np.radians(pitch)) * np.cos(np.radians(yaw))])
        hit |= d @ t > np.cos(np.radians(radius_deg))
    img = np.where(hit, 255, 0).astype(np.uint8).reshape(EQ_H, EQ_W)
    Image.fromarray(img).convert("RGB").save(path, quality=98)
    return path


def centroid(png) -> tuple[float, float]:
    img = np.asarray(Image.open(png).convert("L"), float)
    labels, n = ndimage.label(img > 128)
    assert n == 1, f"expected one dot, found {n}"
    ys, xs = np.nonzero(labels)
    return float(xs.mean() + 0.5), float(ys.mean() + 0.5)


def make_root(tmp_path, source_bytes_from=None, sidecar_sha=None):
    """A prototype root with capture/stitched/pano-auto.masked.jpg and the Marble sidecar."""
    root = tmp_path / "proto"
    (root / "capture" / "stitched").mkdir(parents=True)
    (root / "pipeline" / "work" / "marble").mkdir(parents=True)
    src = root / "capture" / "stitched" / "pano-auto.masked.jpg"
    dot_equirect(src, [(35, 0)])
    side = root / "pipeline" / "work" / "marble" / "pano-auto_2560.json"
    side.write_text(json.dumps({"source": "capture/stitched/pano-auto.masked.jpg",
                                "source_sha256": sidecar_sha or sha(src)}))
    return root


DOOR = {"yaw_deg": 35.0, "pitch_deg": -10.0,
        "centre": {"lon": 35.0, "lat": -10.0},
        "corners": [{"lon": 30.0, "lat": -30.0}, {"lon": 40.0, "lat": -30.0},
                    {"lon": 40.0, "lat": 15.0}, {"lon": 30.0, "lat": 15.0}]}


# ---- the geometry constants ----

def test_aspect_matches_the_fields_of_view():
    w, h = lv.SIZE
    assert lv.H_FOV_DEG == 66.0
    assert round(lv.V_FOV_DEG, 2) == 51.94
    ratio = np.tan(np.radians(lv.H_FOV_DEG / 2)) / np.tan(np.radians(lv.V_FOV_DEG / 2))
    assert abs(w / h - ratio) / ratio < 0.001
    assert (w, h) == (1024, 768)


def test_rungs_are_nested_and_azimuths_are_relative_to_the_door():
    assert lv.AZIMUTHS == (0, 45, 90, 135, 180, 225, 270, 315)
    assert lv.RUNGS == {"R1": (0,), "R2": (0, 180), "R4": (0, 90, 180, 270), "R8": lv.AZIMUTHS}
    order = ["R1", "R2", "R4", "R8"]
    for small, big in zip(order, order[1:]):
        assert set(lv.RUNGS[small]) < set(lv.RUNGS[big])


def test_view_names_carry_the_azimuth():
    assert [lv.view_file_name(a) for a in (0, 45, 315)] == ["az000.png", "az045.png", "az315.png"]


# ---- where the door is ----

def test_rig_direction_inverts_a_known_pose():
    rng = np.random.default_rng(3)
    a = Rotation.random(random_state=1).as_matrix() * 0.3
    t = rng.normal(size=3)
    world_from_colmap = np.eye(4)
    world_from_colmap[:3, :3], world_from_colmap[:3, 3] = a, t
    cam_from_model = Rotation.random(random_state=2).as_matrix()
    centre = rng.normal(size=3)
    for lon, lat in [(-10.0, -15.0), (120.0, 20.0), (-170.0, 0.0), (0.0, 0.0)]:
        want = np.array([np.cos(np.radians(lat)) * np.sin(np.radians(lon)), -np.sin(np.radians(lat)),
                         np.cos(np.radians(lat)) * np.cos(np.radians(lon))])
        colmap_pt = centre + cam_from_model.T @ (want * 4.0)
        world_pt = a @ colmap_pt + t
        got = lv.rig_direction(world_pt, world_from_colmap, cam_from_model, centre)
        assert np.allclose(got, want, atol=1e-9)
        assert np.allclose(lv.lon_lat(got), (lon, lat), atol=1e-7)


def test_door_direction_is_the_yaw_of_the_four_corners_mean():
    # With identity transforms the "world" is the rig frame itself (x right, y down, z forward), so a
    # door out along +x is at yaw +90: v360's positive yaw turns right. Its corners' mean is 1 down.
    scale = {"door": {"a": [2.0, 0.0, -0.3], "b": [2.0, 0.0, 0.3],
                      "top": [[2.0, 2.0, -0.3], [2.0, 2.0, 0.3]], "centre": [2.0, 0.0, 0.0]}}
    door = lv.door_direction(scale, np.eye(4), np.eye(3), np.zeros(3))
    assert door["yaw_deg"] == pytest.approx(90.0, abs=1e-3)
    assert door["centre"]["lat"] == pytest.approx(np.degrees(np.arcsin(-1.0 / np.sqrt(5.0))), abs=1e-3)
    assert len(door["corners"]) == 4


# ---- the source and its hash ----

def test_source_must_match_the_sidecar(tmp_path):
    root = make_root(tmp_path)
    src, digest, side = lv.check_source(root)
    assert src.name == "pano-auto.masked.jpg" and digest == side


def test_a_changed_source_is_refused(tmp_path):
    root = make_root(tmp_path, sidecar_sha="0" * 64)
    with pytest.raises(lv.LadderError, match="sidecar"):
        lv.check_source(root)


def test_a_missing_source_is_refused(tmp_path):
    root = make_root(tmp_path)
    (root / "capture" / "stitched" / "pano-auto.masked.jpg").unlink()
    with pytest.raises(lv.LadderError, match="not found"):
        lv.check_source(root)


# ---- the cut itself, against real ffmpeg ----

@pytest.fixture(scope="module")
def cut_once(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ladder")
    root = make_root(tmp)
    # dots at d (az000), d+90 (az090), d+45 (az045) and d+20 (right of az000's centre, 20 above it)
    dot_equirect(root / "capture" / "stitched" / "pano-auto.masked.jpg",
                 [(35, 0), (125, 0), (80, 0)])
    # the sidecar must follow the file just rewritten
    side = root / "pipeline" / "work" / "marble" / "pano-auto_2560.json"
    side.write_text(json.dumps({"source_sha256": sha(root / "capture" / "stitched" / "pano-auto.masked.jpg")}))
    manifest = lv.cut(root, root / "pipeline" / "work", door=DOOR)
    return root, manifest


def test_eight_views_of_the_right_size(cut_once):
    root, manifest = cut_once
    for a in lv.AZIMUTHS:
        with Image.open(root / "pipeline" / "work" / "ladder" / "views" / lv.view_file_name(a)) as im:
            assert im.size == (1024, 768)
    assert [v["azimuth"] for v in manifest["views"]] == list(lv.AZIMUTHS)


def test_a_feature_at_the_door_yaw_lands_at_the_centre_of_az000(cut_once):
    root, _ = cut_once
    x, y = centroid(root / "pipeline" / "work" / "ladder" / "views" / "az000.png")
    assert abs(x - 512) < 1.5 and abs(y - 384) < 1.5


def test_azimuth_counts_from_the_door_towards_the_right(cut_once):
    root, _ = cut_once
    views_dir = root / "pipeline" / "work" / "ladder" / "views"
    # the dot at d+90 is at the centre of az090 and does not appear in az000
    x, y = centroid(views_dir / "az090.png")
    assert abs(x - 512) < 1.5 and abs(y - 384) < 1.5
    x, y = centroid(views_dir / "az045.png")
    assert abs(x - 512) < 1.5 and abs(y - 384) < 1.5


def test_pinhole_law_on_both_axes(tmp_path):
    src = dot_equirect(tmp_path / "e.jpg", [(20, 12)])
    out = tmp_path / "v.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                    views.v360_flat_filter(0, 0, lv.H_FOV_DEG, lv.V_FOV_DEG, *lv.SIZE),
                    "-frames:v", "1", str(out)], check=True)
    x, y = centroid(out)
    fx = 512 / np.tan(np.radians(lv.H_FOV_DEG / 2))
    fy = 384 / np.tan(np.radians(lv.V_FOV_DEG / 2))
    d = np.array([np.cos(np.radians(12)) * np.sin(np.radians(20)), np.sin(np.radians(12)),
                  np.cos(np.radians(12)) * np.cos(np.radians(20))])
    assert x == pytest.approx(512 + fx * d[0] / d[2], abs=2.0)
    assert y == pytest.approx(384 - fy * d[1] / d[2], abs=2.0)
    assert x > 512 and y < 384  # right of centre, above it


def test_the_door_projects_to_the_view_centre_at_az000():
    px, py = lv.project(DOOR["centre"], 35.0)
    assert px == pytest.approx(512, abs=1e-6)
    f = 384 / np.tan(np.radians(lv.V_FOV_DEG / 2))
    assert py == pytest.approx(384 + f * np.tan(np.radians(10)), abs=1e-6)  # 10 degrees below the horizon
    assert lv.project({"lon": 35.0 + 180, "lat": 0.0}, 35.0) is None  # behind the camera


# ---- the manifest ----

def test_manifest_contents(cut_once):
    root, manifest = cut_once
    src = root / "capture" / "stitched" / "pano-auto.masked.jpg"
    assert manifest["source"] == "capture/stitched/pano-auto.masked.jpg"
    assert manifest["source_sha256"] == sha(src) == manifest["sidecar_source_sha256"]
    assert manifest["d_yaw_deg"] == 35.0
    assert manifest["fov_deg"] == {"h": 66.0, "v": round(lv.V_FOV_DEG, 4)}
    assert manifest["size"] == [1024, 768]
    assert manifest["views_clean"] is None
    by_az = {v["azimuth"]: v for v in manifest["views"]}
    assert by_az[0]["pano_yaw_deg"] == 35.0 and by_az[90]["pano_yaw_deg"] == 125.0
    assert by_az[315]["pano_yaw_deg"] == pytest.approx(-10.0)  # 35 + 315 = 350, wrapped
    assert manifest["rungs"] == {name: [by_az[a]["file"] for a in az] for name, az in lv.RUNGS.items()}
    for v in manifest["views"]:
        assert v["sha256"] == sha(root / v["file"])


def test_manifest_round_trips_and_verifies(cut_once):
    root, manifest = cut_once
    path = root / "pipeline" / "work" / "ladder" / "views" / "manifest.json"
    assert json.loads(path.read_text()) == manifest
    assert lv.verify_manifest(path, root) == manifest


def test_a_changed_view_fails_verification(cut_once, tmp_path):
    root, _ = cut_once
    path = root / "pipeline" / "work" / "ladder" / "views" / "manifest.json"
    victim = root / "pipeline" / "work" / "ladder" / "views" / "az180.png"
    original = victim.read_bytes()
    try:
        im = Image.open(victim)
        im.putpixel((0, 0), (1, 2, 3))
        im.save(victim)
        with pytest.raises(lv.LadderError, match="az180"):
            lv.verify_manifest(path, root)
    finally:
        victim.write_bytes(original)
    lv.verify_manifest(path, root)


def test_a_changed_source_fails_verification(cut_once):
    root, _ = cut_once
    path = root / "pipeline" / "work" / "ladder" / "views" / "manifest.json"
    src = root / "capture" / "stitched" / "pano-auto.masked.jpg"
    original = src.read_bytes()
    try:
        src.write_bytes(original + b"\0")
        with pytest.raises(lv.LadderError, match="source"):
            lv.verify_manifest(path, root)
    finally:
        src.write_bytes(original)


# ---- the sheet ----

def test_sheet_is_two_rows_of_four(cut_once):
    root, _ = cut_once
    out = lv.make_sheet(root)
    assert out.name == "contact.jpg"
    with Image.open(out) as im:
        w, h = im.size
    assert w == 4 * lv.SHEET_TILE[0]
    assert h == 2 * (lv.SHEET_TILE[1] + lv.SHEET_LABEL_H)

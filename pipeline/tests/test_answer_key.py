import json

import numpy as np
from PIL import Image

import answer_key as ak
from colmap_model import Camera, Img, Model, Point, write_model

# Door at the origin, plane x = 0, normal +x (out of the room). World frame = COLMAP frame.
EYE = np.eye(4)
CENTRE = np.array([0.0, 0.0, 0.0])
NORMAL = np.array([1.0, 0.0, 0.0])


def _key_img(i, name, n_obs, camera_centre=(-1.0, 1.0, 0.0)):
    # identity rotation, so the camera centre is -tvec
    return Img(i, [1, 0, 0, 0], [-c for c in camera_centre], 1, name, [(0.0, 0.0, 1)] * n_obs)


def _model(points, key_ids=(1, 2, 3), extra_images=()):
    imgs = {i: _key_img(i, f"rig/y000p00/4key_{i:04d}.jpg", 20, (-1.0 + 0.5 * i, 1.0, 0.0)) for i in key_ids}
    imgs.update({im.id: im for im in extra_images})
    pts = {n: Point(n, list(xyz), [0, 0, 0], 0.5, [(i, 0) for i in tracks]) for n, (xyz, tracks) in enumerate(points, 1)}
    return Model({1: Camera(1, "PINHOLE", 10, 10, [5, 5, 5, 5])}, imgs, pts)


def test_points_either_side_of_the_plane_are_counted_and_measured():
    pts = [((0.5 * k, 1.0, 0.1 * k), (1, 2, 3)) for k in range(1, 5)]        # past: 0.5, 1.0, 1.5, 2.0
    pts += [((-0.5 * k, 1.0, 0.0), (1, 2, 3)) for k in range(1, 4)]          # in the room
    out = ak.analyse(_model(pts), EYE, CENTRE, NORMAL)["result"]
    assert out["points_past_door"]["count"] == 4
    assert out["points_past_door"]["max_m"] == 2.0
    assert out["points_past_door"]["median_m"] == 1.25
    assert out["points_seen_by_3_plus_key_images"] == 7


def test_a_point_needs_three_registered_key_images():
    pts = [((1.0, 1.0, 0.0), (1, 2)), ((1.0, 1.0, 1.0), (1, 2, 3)), ((2.0, 1.0, 0.0), (1, 2, 9))]
    other = Img(9, [1, 0, 0, 0], [0, 0, 0], 1, "rig/y000p00/2head_0001.jpg", [(0, 0, 1)] * 20)
    out = ak.analyse(_model(pts, extra_images=[other]), EYE, CENTRE, NORMAL)["result"]
    assert out["points_past_door"]["count"] == 1  # only the (1, 2, 3) track; image 9 is not a key image


def test_a_key_image_below_the_observation_bar_is_not_registered():
    weak = _key_img(3, "rig/y000p00/4key_0003.jpg", 5)
    m = _model([((1.0, 1.0, 0.0), (1, 2, 3))], key_ids=(1, 2))
    m.images[3] = weak
    out = ak.analyse(m, EYE, CENTRE, NORMAL)["result"]
    assert out["key_images_registered"] == 2
    assert out["points_past_door"]["count"] == 0


def test_world_frame_is_applied_before_the_plane():
    # COLMAP units are twice the metres, shifted so that COLMAP x = 1 is the plane.
    w = np.diag([0.5, 0.5, 0.5, 1.0])
    w[0, 3] = -0.5
    pts = [((1.0, 0.0, 0.0), (1, 2, 3)), ((3.0, 0.0, 0.0), (1, 2, 3))]  # world x: 0.0 and 1.0
    out = ak.analyse(_model(pts), w, CENTRE, NORMAL)["result"]
    assert out["points_past_door"]["count"] == 1 and out["points_past_door"]["max_m"] == 1.0


def test_camera_centres_past_the_plane_are_counted_once_per_sample():
    m = _model([], key_ids=(1, 2, 3))   # centres at x = -0.5, 0.0, 0.5
    m.images[4] = _key_img(4, "rig/y090p00/4key_0003.jpg", 20, (0.5, 1.0, 0.0))  # same sample as image 3
    out = ak.analyse(m, EYE, CENTRE, NORMAL)["result"]
    assert out["key_cameras_past_door"] == {"count": 1, "max_m": 0.5, "p90_m": 0.5, "median_m": 0.5, "of": 3}


def test_kr1_needs_both_enough_points_and_enough_reach():
    assert ak.kr1(1434, 1.0)["hallway_scored"]
    assert not ak.kr1(199, 1.0)["hallway_scored"]
    assert not ak.kr1(500, 0.49)["hallway_scored"]
    assert not ak.kr1(0, None)["hallway_scored"]


def test_cli_writes_json_and_png(tmp_path):
    pts = [((0.2 + 0.01 * k, 1.0, 0.05 * k), (1, 2, 3)) for k in range(30)]
    pts += [((-0.5 - 0.01 * k, 1.0, 0.05 * k), (1, 2, 3)) for k in range(30)]
    write_model(_model(pts), tmp_path / "colmap" / "sparse_txt" / "0")
    (tmp_path / "scale.json").write_text(json.dumps({
        "world_from_colmap": EYE.tolist(),
        "door": {"centre": CENTRE.tolist(), "outward": NORMAL.tolist(), "width_tape_m": 0.72}}))
    assert ak.main(["--work", str(tmp_path)]) == 0
    doc = json.loads((tmp_path / "ladder" / "answer_key.json").read_text())
    assert doc["points_past_door"]["count"] == 30 and doc["kr1"]["hallway_scored"] is False
    assert Image.open(tmp_path / "ladder" / "answer_key.png").width >= 760

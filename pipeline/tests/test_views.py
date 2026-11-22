import json

import numpy as np
import pytest

import views


def test_eight_views_in_the_agreed_order():
    assert [v.token for v in views.VIEWS] == ["0@0", "90@0", "180@0", "270@0", "45@40", "135@40", "225@40", "315@40"]
    assert [v.name for v in views.VIEWS][:2] == ["y000p00", "y090p00"]


def test_ffmpeg_yaw_stays_inside_v360_range():
    assert [v.ffmpeg_yaw for v in views.VIEWS] == [0, 90, -180, -90, 45, 135, -135, -45]


def test_focal_is_exact_for_90_degrees():
    assert views.focal(1440) == 720.0


def test_parse_drop():
    assert views.parse_drop("180@0, 135@40") == ("180@0", "135@40")
    assert views.parse_drop("none") == ()
    assert views.parse_drop("") == ()
    with pytest.raises(ValueError, match="unknown view"):
        views.parse_drop("170@0")
    with pytest.raises(ValueError, match="reference camera"):
        views.parse_drop("0@0")


def test_kept_views_respects_drop():
    kept = views.kept_views(views.DEFAULT_DROP["head"])
    assert [v.token for v in kept] == ["0@0", "90@0", "270@0", "45@40", "315@40"]


def test_quaternions_are_unit_and_scalar_first():
    for cam in views.rig_config()[0]["cameras"][1:]:
        q = np.array(cam["cam_from_rig_rotation"])
        assert abs(np.linalg.norm(q) - 1) < 1e-9
        assert q[0] >= 0


def test_known_quaternions():
    by_prefix = {c["image_prefix"]: c for c in views.rig_config()[0]["cameras"]}
    assert by_prefix["rig/y000p00/"]["ref_sensor"] is True
    assert by_prefix["rig/y090p00/"]["cam_from_rig_rotation"] == pytest.approx([0.707106781187, 0, -0.707106781187, 0])
    assert by_prefix["rig/y045p40/"]["cam_from_rig_rotation"] == pytest.approx(
        [0.868162779196, -0.315985410125, -0.359604797490, 0.130885442386])
    assert by_prefix["rig/y315p40/"]["cam_from_rig_rotation"] == pytest.approx(
        [0.868162779196, -0.315985410125, 0.359604797490, -0.130885442386])


def test_view_centre_direction_projects_to_image_centre():
    for v in views.VIEWS:
        lon, lat = np.radians(v.yaw), np.radians(v.pitch)
        d = np.array([np.cos(lat) * np.sin(lon), -np.sin(lat), np.cos(lat) * np.cos(lon)])
        x, y = views.project(v, d, 1440)
        assert (x, y) == pytest.approx((720, 720), abs=1e-6)


def test_equirect_round_trip():
    u, v = np.array([10.5, 2000.25, 5759.0]), np.array([5.5, 1440.0, 2870.75])
    d = views.direction_from_equirect(u, v, 5760, 2880)
    u2, v2 = views.equirect_from_direction(d, 5760, 2880)
    assert u2 == pytest.approx(u) and v2 == pytest.approx(v)


def test_rig_config_is_json_serialisable_and_has_eight_cameras():
    cfg = json.loads(json.dumps(views.rig_config()))
    assert len(cfg) == 1 and len(cfg[0]["cameras"]) == 8
    assert sum(1 for c in cfg[0]["cameras"] if c.get("ref_sensor")) == 1


def test_wrap_yaw_and_offset_filter():
    assert views.wrap_yaw(225) == -135 and views.wrap_yaw(180) == -180 and views.wrap_yaw(-190) == 170
    assert views.wrap_yaw(12.5) == 12.5
    assert ":yaw=-90:" in views.v360_filter(views.VIEW_BY_TOKEN["90@0"], 64, yaw_offset=180)

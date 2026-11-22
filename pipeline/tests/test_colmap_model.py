import pytest

from colmap_model import Camera, Img, Model, Point, read_model, write_model


def test_round_trip_keeps_everything(tmp_path):
    m = Model({1: Camera(1, "PINHOLE", 1440, 1440, [720.0, 720.0, 720.0, 720.0])},
              {7: Img(7, [0.5, 0.5, 0.5, 0.5], [1.0, -2.0, 3.25], 1, "rig/y000p00/2head_0001.jpg",
                      [(1.25, 2.5, 3), (4.0, 5.0, -1)]),
               8: Img(8, [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 1, "rig/y090p00/2head_0001.jpg", [])},
              {3: Point(3, [0.1, 0.2, 0.3], [1, 2, 3], 0.75, [(7, 0), (8, 4)])})
    write_model(m, tmp_path)
    r = read_model(tmp_path)
    assert r.cameras[1].params == [720.0] * 4
    assert r.images[7].points2d == [(1.25, 2.5, 3), (4.0, 5.0, -1)]
    assert r.images[7].n_obs == 1
    assert r.images[8].points2d == [] and r.images[8].name == "rig/y090p00/2head_0001.jpg"
    assert r.points[3].track == [(7, 0), (8, 4)] and r.points[3].error == 0.75


def test_mean_reprojection_error_is_weighted_by_track_length():
    m = Model({}, {}, {1: Point(1, [0, 0, 0], [0, 0, 0], 1.0, [(1, 0), (2, 0)]),
                       2: Point(2, [0, 0, 0], [0, 0, 0], 4.0, [(1, 1), (2, 1), (3, 0), (4, 0)])})
    assert m.mean_reprojection_error() == pytest.approx((1.0 * 2 + 4.0 * 4) / 6)

import numpy as np
import pytest

import grid2d


def test_square_gives_one_closed_outline_on_the_half_cell():
    m = np.zeros((6, 7), bool)
    m[1:4, 2:5] = True
    lines = grid2d.link(grid2d.contour_segments(m))
    assert len(lines) == 1 and lines[0][1] is True
    pts = lines[0][0]
    assert pts[:, 0].min() == 0.5 and pts[:, 0].max() == 3.5 and pts[:, 1].min() == 1.5 and pts[:, 1].max() == 4.5


def test_diagonal_cells_stay_apart():
    m = np.zeros((5, 5), bool)
    m[1, 1] = m[2, 2] = True
    assert [c for _, c in grid2d.link(grid2d.contour_segments(m))] == [True, True]


def test_open_line_from_a_partial_mask():
    m = np.zeros((4, 6), bool)
    m[:, :3] = True
    segs = grid2d.contour_segments(m)
    keep = np.array([abs((a + b)[1] / 2 - 2.5) < 0.01 for a, b in segs])
    lines = grid2d.link(segs[keep])
    assert len(lines) == 1 and lines[0][1] is False
    assert lines[0][0][:, 1].tolist() == [2.5] * 4 and lines[0][0][:, 0].tolist() == [0.0, 1.0, 2.0, 3.0]


def test_chaikin_keeps_the_ends_of_an_open_line():
    out = grid2d.chaikin(np.array([[0.0, 0], [1, 0], [1, 1]]), closed=False, rounds=1)
    assert out[0] == pytest.approx([0, 0]) and out[-1] == pytest.approx([1, 1]) and len(out) == 6


def test_grid_world_coordinates_and_polygons():
    g = grid2d.Grid(0.0, 0.0, 0.1, 7, 6)
    m = np.zeros((6, 7), bool)
    m[1:4, 2:5] = True
    poly = grid2d.polygons(g, m, 0.0)[0]
    xs, zs = [p[0] for p in poly], [p[1] for p in poly]
    assert min(xs) == pytest.approx(0.2) and max(xs) == pytest.approx(0.5)
    assert min(zs) == pytest.approx(0.1) and max(zs) == pytest.approx(0.4)
    assert grid2d.polygons(g, m, 1.0) == []


def test_occupancy_and_disks():
    g = grid2d.Grid.around(np.array([[0.0, 0.0], [1.0, 1.0]]), 0.1, margin_cells=2)
    occ = g.occupancy(np.array([[0.05, 0.05]]))
    assert occ.sum() == 1
    d = g.disks(np.array([[0.5, 0.5]]), 0.2)
    assert 10 < d.sum() < 20

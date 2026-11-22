"""The door plane as a hard edge: past it, inside the opening, nothing was measured (hub call 62)."""
import numpy as np
import pytest

import door_edge

# A door in the plane x = 2, facing +x, 0.72 m between the tapes, the head at 2.0 m.
SCALE = {"door": {"centre": [2.0, 0.0, 0.0], "outward": [1.0, 0.0, 0.0], "width_tape_m": 0.72,
                  "a": [2.0, 0.0, -0.36], "b": [2.0, 0.0, 0.36], "top": [[2.0, 2.0, -0.36], [2.0, 2.0, 0.36]]}}


def test_door_plane_is_the_one_answer_key_uses():
    import answer_key
    c, n = door_edge.door_plane(SCALE)
    c2, n2 = answer_key.door_plane(SCALE)
    assert (c == c2).all() and (n == n2).all() and np.linalg.norm(n) == pytest.approx(1.0)


def test_sealed_is_the_opening_past_the_plane():
    pts = np.array([
        [2.05, 0.01, 0.0],    # the threshold floor just past the frame: sealed
        [2.60, 1.00, 0.30],   # deep in the hallway, inside the opening's prism: sealed
        [1.95, 0.01, 0.0],    # the room side of the plane: not
        [2.05, 1.00, 0.37],   # a jamb's face past the plane: not
        [2.05, 1.00, -0.50],  # inside the wall beside the opening: not
        [2.05, 1.99, 0.0],    # the head jamb: not
    ])
    assert door_edge.sealed(pts, SCALE).tolist() == [True, True, False, False, False, False]


def test_jamb_margin_keeps_splats_that_straddle_the_jamb_face():
    o = door_edge.opening(SCALE)
    assert o.half_width == pytest.approx(0.36 - door_edge.JAMB_MARGIN_M)
    assert o.top == pytest.approx(2.0 - door_edge.HEAD_MARGIN_M)
    assert not door_edge.sealed(np.array([[2.05, 1.0, 0.36 - door_edge.JAMB_MARGIN_M + 0.001]]), SCALE).any()


def test_a_door_without_head_corners_seals_to_any_height():
    s = {"door": {k: v for k, v in SCALE["door"].items() if k != "top"}}
    assert door_edge.opening(s).top == np.inf
    assert door_edge.sealed(np.array([[2.05, 2.5, 0.0]]), s).all()


def test_an_oblique_door_uses_its_own_axes():
    a = np.radians(20)
    n = [np.cos(a), 0.0, np.sin(a)]
    s = {"door": {**SCALE["door"], "outward": n}}
    lateral = np.array([-n[2], 0.0, n[0]])
    c = np.array(SCALE["door"]["centre"])
    inside = c + 0.05 * np.array(n) + 0.30 * lateral + [0, 1.0, 0]
    beside = c + 0.05 * np.array(n) + 0.40 * lateral + [0, 1.0, 0]
    assert door_edge.sealed(np.array([inside, beside]), s).tolist() == [True, False]

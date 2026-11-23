"""Gate A's colour runner-up (Amendment 3, hub call 106): a rival is scored at the stage the chosen pose is,
fitted where the search fitted it, and at its start only where it did not (or where its fit drew no colour)."""
import numpy as np
from scipy.spatial.transform import Rotation

import align


def pose(yaw_deg: float, mirror: bool = False) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = Rotation.from_euler("y", yaw_deg, degrees=True).as_matrix()
    if mirror:
        m = m @ np.diag([-1.0, 1.0, 1.0, 1.0])
    return m


def entry(yaw, before, after=None, fitted=True, mirror=False):
    e = {"yawDeg": yaw, "mirror": mirror, "flip": False, "photoBefore": before, "t0": pose(yaw, mirror)}
    if fitted:
        e["t"] = pose(yaw, mirror)
        e["photo"] = after
    return e


def test_a_fitted_rival_is_scored_fitted_even_when_its_start_scored_higher():
    chosen = entry(0, 0.52, 0.68)
    turned = entry(270, 0.65, 0.47)               # wins only before fitting
    mirrored = entry(0, 0.60, 0.58, mirror=True)
    score, e = align.runner_up([chosen, turned, mirrored], chosen, chosen["t"])
    assert e is mirrored and score == 0.58


def test_an_unfitted_rival_keeps_its_start_score():
    chosen = entry(0, 0.52, 0.68)
    start_only = entry(90, 0.61, fitted=False)
    mirrored = entry(0, 0.60, 0.58, mirror=True)
    score, e = align.runner_up([chosen, start_only, mirrored], chosen, chosen["t"])
    assert e is start_only and score == 0.61


def test_a_fitted_rival_with_no_fitted_colour_falls_back_to_its_start():
    chosen = entry(0, 0.52, 0.68)
    unseen = entry(180, 0.63, None)
    score, e = align.runner_up([chosen, unseen], chosen, chosen["t"])
    assert e is unseen and score == 0.63


def test_poses_that_converge_on_the_chosen_one_are_not_rivals():
    chosen = entry(0, 0.52, 0.68)
    near = entry(330, 0.66, 0.67)
    near["t"] = pose(10)                           # its fit landed 10 degrees from the chosen pose
    assert align.runner_up([chosen, near], chosen, chosen["t"]) is None

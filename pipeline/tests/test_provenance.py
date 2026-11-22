import json

import numpy as np

import provenance
import splats


def test_split_radii():
    measured = np.zeros((1, 3))
    marble = np.array([[0.1, 0, 0], [0.15, 0, 0], [0.3, 0, 0], [0.5, 0, 0], [3.0, 0, 0]])
    d, overlap, imagined = provenance.split(measured, marble)
    assert overlap.tolist() == [False, True, True, False, False]
    assert imagined.tolist() == [False, False, False, True, True]


def test_run_writes_untouched_marble_rows(aligned):
    work = aligned["work"]
    c = provenance.run(work, "synthworld")
    assert c["covered"] + c["overlap"] + c["imagined"] == c["marble"]
    assert c["imagined"] > 0 and c["covered"] > c["imagined"]
    # the synthetic overlap band lies past the door plane, where the seal turns all of it to ink
    assert c["overlap"] + c["sealed"]["overlapPastPlane"] > 0
    src = splats.read(work / "marble" / "marble_synthworld.ply")["vertex"].data
    out = splats.read(work / "provenance" / "synthworld" / "imagined.ply")["vertex"].data
    assert out.dtype == src.dtype
    assert np.isin(out["x"], src["x"]).all()
    a = json.loads((work / "align" / "synthworld" / "align.json").read_text())
    world = splats.apply(np.array(a["world_from_marble"]), np.stack([out["x"], out["y"], out["z"]], 1).astype(float))
    assert np.percentile(world[:, 0], 5) > 1.9  # the invented hallway lies beyond the door wall


DOOR = {"door": {"centre": [2.0, 0.0, 0.0], "outward": [1.0, 0.0, 0.0], "width_tape_m": 0.72,
                 "top": [[2.0, 2.0, -0.36], [2.0, 2.0, 0.36]]}}


def test_the_doorway_past_the_plane_is_sealed():
    measured = np.array([[1.5, 1.0, 0.0],     # a room wall
                         [2.05, 0.01, 0.0],   # fog on the threshold past the frame: trimmed
                         [2.05, 1.0, 0.37]])  # a jamb's lining past the plane: kept
    marble = np.array([[2.30, 0.01, 0.0],     # the hallway floor 0.25 m from that fog: overlap before, ink now
                       [2.06, 0.01, 0.0],     # right on the fog: covered before, ink now
                       [2.06, 1.0, 0.37],     # the jamb's twin: still covered
                       [1.52, 1.0, 0.0]])     # the room wall's twin: still covered
    d, overlap, imagined, seal = provenance.sealed_split(measured, marble, DOOR)
    assert seal["measuredTrimmed"] == 1 and seal["marbleSealed"] == 2
    assert imagined.tolist() == [True, True, False, False]
    assert overlap.tolist() == [False, False, False, False]
    d0, overlap0, imagined0 = provenance.split(measured, marble)
    assert overlap0[0] and not imagined0[1]  # what the old split made of the same points


def test_run_counts_the_seal(aligned):
    c = provenance.run(aligned["work"], "synthworld")
    assert c["covered"] + c["overlap"] + c["imagined"] == c["marble"]
    assert set(c["sealed"]) >= {"measuredTrimmed", "marbleSealed"}


def test_past_the_plane_nothing_is_half_and_half():
    measured = np.array([[2.05, 1.0, 0.37]])            # the jamb lining, kept
    marble = np.array([[2.30, 1.0, 0.45],                # the hallway wall beside the jamb, 0.26 m off: ink, not overlap
                       [2.06, 1.0, 0.37],                # the jamb's twin: covered, so the photographed jamb shows
                       [1.80, 1.0, 0.37]])               # room side, 0.26 m off: still overlap
    d, overlap, imagined, seal = provenance.sealed_split(measured, marble, DOOR)
    assert imagined.tolist() == [True, False, False]
    assert overlap.tolist() == [False, False, True]
    assert seal["marbleSealed"] == 0 and seal["overlapPastPlane"] == 1

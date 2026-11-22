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
    assert c["imagined"] > 0 and c["overlap"] > 0 and c["covered"] > c["imagined"]
    src = splats.read(work / "marble" / "marble_synthworld.ply")["vertex"].data
    out = splats.read(work / "provenance" / "synthworld" / "imagined.ply")["vertex"].data
    assert out.dtype == src.dtype
    assert np.isin(out["x"], src["x"]).all()
    a = json.loads((work / "align" / "synthworld" / "align.json").read_text())
    world = splats.apply(np.array(a["world_from_marble"]), np.stack([out["x"], out["y"], out["z"]], 1).astype(float))
    assert np.percentile(world[:, 0], 5) > 1.9  # the invented hallway lies beyond the door wall

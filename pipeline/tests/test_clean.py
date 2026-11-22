import json

import numpy as np
import pytest

import clean
import scale
import splats


def scaled(synthetic):
    work, notes = synthetic["work"], synthetic["notes"]
    assert scale.main(["--work", str(work), "--notes", str(notes)]) == 0
    return work, notes, json.loads((work / "scale.json").read_text())


def test_proposed_box_holds_the_room_and_the_doorway(synthetic):
    _, _, s = scaled(synthetic)
    x0, x1, y0, y1, z0, z1 = clean.propose(s)
    assert x0 < -2.0 and z0 < -1.6 and z1 > 1.6
    assert x1 >= 2.0 + 1.5
    assert y0 == -0.05 and y1 > 2.5


def test_box_line_round_trip():
    line = clean.box_line([-2.8, 3.1, -0.05, 3.2, -2.4, 2.4])
    assert line == "- Cleaning box: -2.80 3.10 -0.05 3.20 -2.40 2.40"
    assert clean.read_box("x\n" + line + "\n") == [-2.8, 3.1, -0.05, 3.2, -2.4, 2.4]
    with pytest.raises(ValueError, match="six numbers"):
        clean.read_box("- Cleaning box:\n")


def test_apply_drops_outside_and_under_the_floor(synthetic):
    work, notes, s = scaled(synthetic)
    m = np.array(s["world_from_colmap"])
    raw = splats.read(work / "splat" / "splat_raw.ply")
    world = splats.apply(m, splats.centres(raw))
    box = [-2.5, 2.4, -0.05, 3.0, -2.0, 2.0]
    kept, total = clean.apply(work / "splat" / "splat_raw.ply", work / "splat" / "measured.ply", box, m)
    expect = clean.inside(box, world).sum()
    assert kept == expect < total
    out = splats.read(work / "splat" / "measured.ply")
    assert out["vertex"].data.dtype == raw["vertex"].data.dtype
    under = clean.inside([-9, 9, -9, 9, -9, 9], np.array([[0.0, -0.06, 0.0], [0.0, -0.04, 0.0]]))
    assert under.tolist() == [False, True]


def test_cli_apply_and_adopt(synthetic):
    work, notes, s = scaled(synthetic)
    notes.write_text(notes.read_text().replace("- Cleaning box:", clean.box_line(clean.propose(s))))
    assert clean.main(["--work", str(work), "--notes", str(notes), "apply"]) == 0
    ply = splats.read(work / "splat" / "measured.ply")
    keep = np.arange(len(ply["vertex"].data)) % 2 == 0
    splats.write_subset(ply, keep, work / "supersplat.ply")
    assert clean.main(["--work", str(work), "--notes", str(notes), "adopt", str(work / "supersplat.ply")]) == 0
    assert splats.count(work / "splat" / "measured.ply") == keep.sum()


def test_adopt_refuses_a_moved_export(synthetic):
    work, notes, s = scaled(synthetic)
    notes.write_text(notes.read_text().replace("- Cleaning box:", clean.box_line(clean.propose(s))))
    clean.main(["--work", str(work), "--notes", str(notes), "apply"])
    ply = splats.read(work / "splat" / "measured.ply")
    data = ply["vertex"].data.copy()
    data["y"] = -data["y"]
    from plyfile import PlyData, PlyElement
    PlyData([PlyElement.describe(data, "vertex")]).write(str(work / "moved.ply"))
    with pytest.raises(ValueError, match="not a subset"):
        clean.check_subset(work / "moved.ply", work / "splat" / "measured_auto.ply")


def test_the_box_reaches_walls_behind_furniture_far_from_the_cameras():
    # the passes walked a small loop in the middle of a 6 m x 5 m room
    s = {"room_cameras_xz": [[-0.5, -0.4], [0.5, 0.4]], "wall_band_xz": [[-2.9, -2.4], [2.9, 2.4]],
         "camera_heights_m": {"head": 1.6, "hip": 0.9},
         "door": {"a": [3.0, 0.0, -0.45], "b": [3.0, 0.0, 0.45], "centre": [3.0, 0.0, 0.0], "outward": [1.0, 0.0, 0.0]}}
    x0, x1, y0, y1, z0, z1 = clean.propose(s)
    assert x0 <= -2.9 - clean.WALL_MARGIN_M + 1e-9 and z0 <= -2.4 - clean.WALL_MARGIN_M + 1e-9
    assert z1 >= 2.4 + clean.WALL_MARGIN_M - 1e-9 and x1 >= 3.0 + clean.BEYOND_DOOR_M


def test_the_proposed_box_keeps_the_whole_room_and_is_drawn(synthetic):
    work, notes, s = scaled(synthetic)
    assert clean.main(["--work", str(work), "--notes", str(notes), "propose"]) == 0
    assert (work / "clean" / "box.png").stat().st_size > 10_000
    box = clean.propose(s)
    world = splats.apply(np.array(s["world_from_colmap"]), splats.centres(splats.read(work / "splat" / "splat_raw.ply", quiet=True)))
    room = (world[:, 0] <= 2.0) & (np.abs(world[:, 2]) <= 1.6)
    assert clean.inside(box, world[room]).mean() > 0.999


def test_every_tree_query_in_the_pipeline_uses_every_core():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    slow = {p.name for p in root.glob("*.py") for line in p.read_text().splitlines()
            if re.search(r"\.query\(", line) and "workers=-1" not in line}
    # the picks (door_points, doorway) are queries of two or four points
    assert slow <= {"door_points.py", "doorway.py"}, slow

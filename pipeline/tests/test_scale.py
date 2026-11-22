import json

import numpy as np
import pytest

import scale
import splats
import synth_world


def run(synthetic):
    work, notes = synthetic["work"], synthetic["notes"]
    assert scale.main(["--work", str(work), "--notes", str(notes)]) == 0
    return json.loads((work / "scale.json").read_text())


def test_scale_recovers_the_door_width_to_half_a_percent(synthetic):
    r = run(synthetic)
    assert r["metres_per_unit"] == pytest.approx(synth_world.S_COLMAP, rel=0.005)
    d = r["door"]
    assert np.linalg.norm(np.array(d["a"]) - np.array(d["b"])) == pytest.approx(0.9, rel=0.005)
    assert d["route"] == "clicks" and d["width_check_m"] == pytest.approx(0.902)


def test_world_frame_matches_the_room(synthetic):
    r = run(synthetic)
    m = np.array(r["world_from_colmap"])
    truth = synth_world.world_from_colmap()
    corners = np.array([[x, y, z] for x in (-2, 2) for y in (0, 2.5) for z in (-1.6, 1.6)])
    moved = splats.apply(m, splats.apply(splats.invert(truth), corners))
    assert np.abs(moved - corners).max() < 0.01


def test_floor_heights_start_and_walkable(synthetic):
    r = run(synthetic)
    assert r["camera_heights_m"]["head"] == pytest.approx(1.6, abs=0.01)
    assert r["camera_heights_m"]["hip"] == pytest.approx(0.9, abs=0.01)
    assert r["start"]["position"] == pytest.approx([0, 1.6, 0], abs=0.01)
    assert r["start"]["yawDeg"] == pytest.approx(-90, abs=0.5)
    assert r["door"]["outward"] == pytest.approx([1, 0, 0], abs=0.01)
    poly = np.array(r["walkable_measured"][0])
    assert poly[:, 0].min() < -1.2 and poly[:, 0].max() > 1.2


def test_missing_tape_width_is_an_error(synthetic):
    synthetic["notes"].write_text(synthetic["notes"].read_text().replace("**Door frame inside width (tape), in metres:**", "**gone**"))
    with pytest.raises(ValueError, match="tape width"):
        run(synthetic)


def test_long_axis_of_a_turned_rectangle():
    rng = np.random.default_rng(0)
    pts = rng.random((4000, 2)) * [4.0, 2.0]
    a = np.radians(25)
    turned = pts @ np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
    ang = scale.long_axis(turned)
    axis = np.array([np.cos(ang), np.sin(ang)])
    assert abs(axis @ [np.cos(a), np.sin(a)]) == pytest.approx(1, abs=0.01)


def test_check_length_is_measured_in_the_scaled_model(synthetic):
    r = run(synthetic)
    c = r["check_length"]
    assert c["what"] == "desk top, front edge" and c["tape_m"] == pytest.approx(1.1)
    assert abs(c["error_pct"]) < 0.5


def test_no_check_clicks_means_no_check(synthetic):
    text = synthetic["notes"].read_text()
    synthetic["notes"].write_text("\n".join(ln for ln in text.splitlines() if not ln.startswith("- Door click C")
                                            and not ln.startswith("- Door click D")) + "\n")
    assert run(synthetic)["check_length"] is None


def test_the_committed_notes_template_parses_once_filled_in():
    from conftest import TEMPLATE

    text = TEMPLATE.read_text()
    text = text.replace("- **Door frame inside width (tape), in metres:**", "- **Door frame inside width (tape), in metres:** 0.812")
    text = text.replace("- Door frame inside width, second tape (cross-check), in metres:",
                        "- Door frame inside width, second tape (cross-check), in metres: 0.815")
    text = text.replace("- Check length (what it is, and its length in metres):",
                        "- Check length (what it is, and its length in metres): desk top, front edge, 1.10")
    assert scale.TAPE_RE.search(text).group(1) == "0.812"
    assert scale.TAPE2_RE.search(text).group(1) == "0.815"
    m = scale.CHECK_RE.search(text)
    assert (m.group(1), m.group(2)) == ("desk top, front edge", "1.10")
    assert scale.TAPE_RE.search(TEMPLATE.read_text()) is None


# ---- real size, refused evidence, and the floor that is not the floor ----

def test_plane_fit_at_real_size_stays_small_and_quick():
    import time
    import tracemalloc
    rng = np.random.default_rng(0)
    n = 1_500_000
    pts = np.c_[rng.uniform(-3, 3, n), 0.01 * rng.standard_normal(n), rng.uniform(-2, 2, n)] + [0.0, 1.5, 0.0]
    tracemalloc.start()
    t = time.time()
    normal, d = scale.fit_plane(pts)
    took = time.time() - t
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert abs(normal[1]) == pytest.approx(1, abs=1e-4) and abs(d) == pytest.approx(1.5, abs=1e-3)
    assert peak < 200e6, f"{peak / 1e6:.0f} MB"  # a full SVD's U alone would be n x n
    assert took < 5


@pytest.mark.slow
def test_ransac_floor_at_real_size():
    import time
    import tracemalloc
    rng = np.random.default_rng(0)
    n = 1_500_000
    pts = np.c_[rng.uniform(-3, 3, n), 0.01 * rng.standard_normal(n), rng.uniform(-2, 2, n)]
    tracemalloc.start()
    t = time.time()
    normal, d, inl = scale.ransac_plane(pts, 0.02, np.random.default_rng(1))
    took, peak = time.time() - t, tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert abs(normal[1]) == pytest.approx(1, abs=1e-3) and inl.mean() > 0.9
    assert peak < 400e6 and took < 120, (peak, took)


def glossy(synthetic, frac):
    """The reviewer's glossy floor: the ceiling (and half the walls) reflected under the floor."""
    from colmap_model import read_model
    work = synthetic["work"]
    model = read_model(work / "colmap" / "sparse_txt" / "0")
    frames = json.loads((work / "frames.json").read_text())["frames"]
    c = splats.centres(splats.read(work / "splat" / "splat_raw.ply", quiet=True))
    truth = synth_world.world_from_colmap()
    wc = splats.apply(truth, c)
    rng = np.random.default_rng(0)
    ceil = wc[wc[:, 1] > 2.45]
    refl = ceil[rng.choice(len(ceil), int(frac * len(ceil)), replace=False)] * [1, -1, 1]
    walls = wc[(wc[:, 1] > 0.05) & (wc[:, 1] < 2.45)]
    rw = walls[rng.choice(len(walls), int(frac * len(walls) * 0.5), replace=False)] * [1, -1, 1]
    allw = np.vstack([wc, refl, rw])
    return model, splats.apply(splats.invert(truth), allw), frames, synthetic["notes"].read_text()


@pytest.mark.parametrize("frac", [0.3, 0.6, 1.0])
def test_a_glossy_floor_does_not_move_the_floor(synthetic, frac):
    model, centres, frames, notes = glossy(synthetic, frac)
    r = scale.solve(model, centres, frames, notes)
    assert r["camera_heights_m"]["head"] == pytest.approx(1.6, abs=0.03)
    assert r["camera_heights_m"]["hip"] == pytest.approx(0.9, abs=0.03)
    assert abs(r["door"]["a"][1]) < 0.03
    assert all(c["pass"] for c in r["evidence"]["checks"]), r["evidence"]["checks"]


def sparse_floor_and_desk(synthetic, keep_floor=0.03):
    """The real room on 21 Nov: the cut views look level or up and the carpet is dark, so few splats sit on the
    floor, while a desk top is a dense level plane 0.75 m up."""
    model, _, frames, notes = solve_args(synthetic)
    c = splats.centres(splats.read(synthetic["work"] / "splat" / "splat_raw.ply", quiet=True))
    truth = synth_world.world_from_colmap()
    wc = splats.apply(truth, c)
    rng = np.random.default_rng(0)
    floor = wc[:, 1] < 0.05
    keep = ~floor | (rng.random(len(wc)) < keep_floor)
    n_desk = int(floor.sum() * 0.6)
    desk = np.c_[rng.uniform(-1.8, 0.5, n_desk), 0.75 + 0.005 * rng.standard_normal(n_desk), rng.uniform(-1.6, -0.6, n_desk)]
    allw = np.vstack([wc[keep], desk])
    return model, splats.apply(splats.invert(truth), allw), frames, notes


def test_a_floor_the_splat_barely_shows_is_set_level_through_the_door_corners(synthetic):
    model, centres, frames, notes = sparse_floor_and_desk(synthetic)
    r = scale.solve(model, centres, frames, notes)
    assert r["floor"]["tilt_from_camera_up_deg"] < 1.0
    assert r["camera_heights_m"]["head"] == pytest.approx(1.6, abs=0.03)
    assert r["camera_heights_m"]["hip"] == pytest.approx(0.9, abs=0.03)
    assert abs(r["door"]["a"][1]) < 0.03
    assert failed(r) == []


def test_a_floor_tilted_away_from_the_cameras_up_is_refused():
    ev = scale.scale_evidence({}, {}, {}, None, 0.9, None, tilt_deg=scale.MAX_FLOOR_TILT_DEG + 1)
    tilt = [c for c in ev["checks"] if c["name"] == "floor tilt from the cameras' up"]
    assert tilt and not tilt[0]["pass"]
    ev = scale.scale_evidence({}, {}, {}, None, 0.9, None, tilt_deg=0.4)
    assert [c["pass"] for c in ev["checks"] if c["name"] == "floor tilt from the cameras' up"] == [True]


def failed(r):
    return [c["name"] for c in r["evidence"]["checks"] if not c["pass"]]


def test_clean_clicks_pass_every_check(synthetic):
    r = run(synthetic)
    assert failed(r) == [] and r["evidence"]["warnings"] == []
    names = [c["name"] for c in r["evidence"]["checks"]]
    for want in ("corner A reprojection RMS", "corner A ray angle", "corner A height above the floor",
                 "head pass camera height", "hip pass camera height", "check length error"):
        assert want in names


def notes_with(synthetic, old, new):
    synthetic["notes"].write_text(synthetic["notes"].read_text().replace(old, new))


def test_scattered_clicks_are_refused_with_a_reason_and_no_scale_json(synthetic, capsys):
    from colmap_model import read_model
    work = synthetic["work"]
    (work / "scale.json").write_text("{}")  # a stale one from an earlier run must not survive a refusal
    model = read_model(work / "colmap" / "sparse_txt" / "0")
    text = synthetic["notes"].read_text()
    keep = [ln for ln in text.splitlines() if not ln.startswith("- Door click")]
    synthetic["notes"].write_text("\n".join(keep + synth_world.door_click_lines(model, jitter=12.0)) + "\n")
    assert scale.main(["--work", str(work), "--notes", str(synthetic["notes"])]) == 1
    out = capsys.readouterr().out
    assert "reprojection RMS" in out and "re-click" in out
    assert not (work / "scale.json").exists()


def test_accept_records_the_override(synthetic):
    from colmap_model import read_model
    work = synthetic["work"]
    model = read_model(work / "colmap" / "sparse_txt" / "0")
    text = synthetic["notes"].read_text()
    keep = [ln for ln in text.splitlines() if not ln.startswith("- Door click")]
    synthetic["notes"].write_text("\n".join(keep + synth_world.door_click_lines(model, jitter=12.0)) + "\n")
    assert scale.main(["--work", str(work), "--notes", str(synthetic["notes"]), "--accept", "checked the corners by eye"]) == 0
    r = json.loads((work / "scale.json").read_text())
    assert r["evidence"]["accepted"] == "checked the corners by eye" and failed(r)


def test_a_check_length_that_disagrees_is_refused(synthetic):
    notes_with(synthetic, "desk top, front edge, 1.100", "desk top, front edge, 1.150")
    r = scale.solve(*solve_args(synthetic))
    assert "check length error" in failed(r)


def test_two_tapes_far_apart_warn_but_do_not_refuse(synthetic):
    notes_with(synthetic, "second tape (cross-check), in metres: 0.902", "second tape (cross-check), in metres: 0.912")
    r = scale.solve(*solve_args(synthetic))
    assert failed(r) == [] and any("12 mm" in w for w in r["evidence"]["warnings"])


def test_a_corner_clicked_up_the_jamb_is_refused(synthetic):
    from colmap_model import read_model
    work = synthetic["work"]
    model = read_model(work / "colmap" / "sparse_txt" / "0")
    lift = {"A": np.array([2.0, 0.15, -0.45])}  # 15 cm up the left jamb, in every view
    lines = []
    for ln in synthetic["notes"].read_text().splitlines():
        if ln.startswith("- Door click A "):
            name = ln.split()[4].rstrip(":")
            u, v = synth_world.project(model, name, lift["A"])
            ln = f"- Door click A {name}: {u:.2f} {v:.2f}"
        lines.append(ln)
    synthetic["notes"].write_text("\n".join(lines) + "\n")
    r = scale.solve(*solve_args(synthetic))
    assert "corner A height above the floor" in failed(r)


def solve_args(synthetic):
    from colmap_model import read_model
    work = synthetic["work"]
    model = read_model(work / "colmap" / "sparse_txt" / "0")
    frames = json.loads((work / "frames.json").read_text())["frames"]
    c = splats.centres(splats.read(work / "splat" / "splat_raw.ply", quiet=True))
    return model, c, frames, synthetic["notes"].read_text()


def test_wall_band_extent_is_recorded_for_the_crop_box(synthetic):
    r = run(synthetic)
    (x0, z0), (x1, z1) = r["wall_band_xz"]
    assert x0 < -1.8 and x1 > 1.8 and z0 < -1.4 and z1 > 1.4

import numpy as np
import pytest

import door_points
import synth_world
from colmap_model import read_model


def model_for(tmp_path):
    return synth_world.write_colmap(tmp_path / "model", tmp_path / "work")


def test_triangulated_corners_give_the_door_width(tmp_path):
    model = model_for(tmp_path)
    notes = "\n".join(synth_world.door_click_lines(model, jitter=0.5))
    r = door_points.from_clicks(model, notes)
    a, b = np.array(r["A"]["colmap"]), np.array(r["B"]["colmap"])
    width = np.linalg.norm(a - b) * synth_world.S_COLMAP
    assert width == pytest.approx(synth_world.DOOR_WIDTH, rel=0.005)
    assert r["A"]["views"] == 3 and 0 < r["A"]["rms_px"] < 2


def test_one_view_is_not_enough(tmp_path):
    model = model_for(tmp_path)
    lines = synth_world.door_click_lines(model)
    with pytest.raises(ValueError, match="at least two views"):
        door_points.from_clicks(model, "\n".join([lines[0], lines[3], lines[4]]))


def test_no_clicks_returns_none(tmp_path):
    assert door_points.from_clicks(model_for(tmp_path), "nothing here") is None


def test_splat_picks_found_in_a_flipped_frame(tmp_path):
    rng = np.random.default_rng(0)
    centres = rng.random((2000, 3))
    a, b = centres[10], centres[20]
    shown = np.diag([1.0, -1.0, -1.0])  # as a viewer that turns y-down files upright would show them
    pa, pb = shown @ a, shown @ b
    line = (f"- Door points picked in the splat (two 3D points): {pa[0]} {pa[1]} {pa[2]} ; {pb[0]} {pb[1]} {pb[2]}")
    r = door_points.from_splat_picks(line, centres, unit_hint=1.0)
    assert r["route"] == "splat picks (half-turn about x)"
    assert r["A"]["colmap"] == pytest.approx(a.tolist())


def test_splat_picks_off_the_splat_are_refused():
    centres = np.random.default_rng(1).random((500, 3))
    line = "- Door points picked in the splat (two 3D points): 9 9 9 ; 8 8 8"
    with pytest.raises(ValueError, match="do not sit on the splat"):
        door_points.from_splat_picks(line, centres, unit_hint=1.0)


def test_page_lists_the_pano_first(tmp_path):
    model = model_for(tmp_path)
    page = door_points.write_page(model, tmp_path / "work")
    html = page.read_text()
    assert html.index("5pano_0000") < html.index("1raised_")
    assert "../images/" in html and "Door click" in html
    assert door_points.candidate_views(model)[0][0] == "rig/y000p00/5pano_0000.jpg"


def test_check_length_ends_are_triangulated_when_clicked(tmp_path):
    model = model_for(tmp_path)
    r = door_points.from_clicks(model, "\n".join(synth_world.door_click_lines(model, jitter=0.3)))
    c, d = np.array(r["C"]["colmap"]), np.array(r["D"]["colmap"])
    assert np.linalg.norm(c - d) * synth_world.S_COLMAP == pytest.approx(synth_world.CHECK_LENGTH, rel=0.005)
    lines = synth_world.door_click_lines(model, check=False)
    assert "C" not in door_points.from_clicks(model, "\n".join(lines))


def test_the_model_is_found_through_the_report_whatever_the_working_directory(tmp_path, monkeypatch):
    synth_world.write_colmap(tmp_path / "work" / "colmap" / "sparse_txt" / "0", tmp_path / "work")
    monkeypatch.chdir(tmp_path)
    assert door_points.main(["--work", "work", "--notes", "NOTES.md", "page"]) == 0
    assert (tmp_path / "work" / "door" / "pick.html").exists()


def two_camera_model(baseline_m):
    """Two cameras looking along +z at a point 3 m away, baseline_m apart."""
    from colmap_model import Camera, Img, Model
    imgs = {}
    for i, x in enumerate((0.0, baseline_m), 1):
        imgs[i] = Img(i, [1.0, 0, 0, 0], [-x, 0.0, 0.0], 1, f"rig/y000p00/v{i}.jpg", [])
    return Model({1: Camera(1, "PINHOLE", 1000, 1000, [500.0, 500.0, 500.0, 500.0])}, imgs, {})


def test_ray_angle_is_reported_and_a_short_baseline_is_flagged():
    point = np.array([0.1, 0.0, 3.0])
    for baseline, flagged in ((0.1, True), (1.0, False)):
        model = two_camera_model(baseline)
        clicks = []
        for name, x in (("rig/y000p00/v1.jpg", 0.0), ("rig/y000p00/v2.jpg", baseline)):
            p = point - [x, 0, 0]
            clicks.append((name, 500 * p[0] / p[2] + 500, 500 * p[1] / p[2] + 500))
        x, rms = door_points.triangulate(model, clicks)
        angle = door_points.ray_angle_deg(model, clicks, x)
        assert angle == pytest.approx(np.degrees(np.arctan2(baseline, 3.0)), abs=0.3)
        problems = door_points.problems({"A": {"views": 2, "rms_px": rms, "ray_angle_deg": angle}})
        assert bool(problems) == flagged


def test_clicked_points_carry_their_ray_angle(tmp_path):
    model = model_for(tmp_path)
    r = door_points.from_clicks(model, "\n".join(synth_world.door_click_lines(model, jitter=0.3)))
    assert r["A"]["ray_angle_deg"] > door_points.MIN_RAY_ANGLE_DEG
    assert door_points.problems(r) == []


def test_solve_exits_3_without_clicks_and_1_on_bad_ones(tmp_path):
    model = model_for(tmp_path)
    notes = tmp_path / "NOTES.md"
    notes.write_text("nothing\n")
    args = ["--work", str(tmp_path / "work"), "--notes", str(notes), "solve"]
    synth_world.write_colmap(tmp_path / "work" / "colmap" / "sparse_txt" / "0", tmp_path / "work")
    assert door_points.main(args) == door_points.NO_CLICKS
    notes.write_text("\n".join(synth_world.door_click_lines(model, jitter=15.0)) + "\n")
    assert door_points.main(args) == 1
    assert door_points.main(args + ["--accept", "looked at the clicks"]) == 0
    notes.write_text("\n".join(synth_world.door_click_lines(model, jitter=0.2)) + "\n")
    assert door_points.main(args) == 0


def test_top_corners_of_the_frame_can_be_clicked(tmp_path):
    model = model_for(tmp_path)
    tops = {"E": np.array([2.0, 2.0, -0.45]), "F": np.array([2.0, 2.0, 0.45])}
    views = synth_world.views_seeing(model, tops)
    lines = [f"- Door click {k} {n}: {u:.2f} {v:.2f}" for k, p in tops.items() for n in views
             for u, v in [synth_world.project(model, n, p)]]
    r = door_points.from_clicks(model, "\n".join(synth_world.door_click_lines(model) + lines))
    e = np.array(r["E"]["colmap"])
    assert splats_apply(e) == pytest.approx(tops["E"], abs=0.01)


def splats_apply(p):
    import splats
    return splats.apply(synth_world.world_from_colmap(), p[None])[0]

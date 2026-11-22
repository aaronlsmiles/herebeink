import json

import colmap_report
import views
from conftest import tiny_work

HEAD = [v for v in views.kept_views(views.DEFAULT_DROP["head"])]


def rig_names() -> list[str]:
    """Every rig image tiny_work cuts: two head frames and one key frame on the head views, the pano on all eight."""
    names = [f"rig/{v.name}/{f}.jpg" for f in ("2head_0000", "2head_0001", "4key_0000") for v in HEAD]
    return names + [f"rig/{v.name}/5pano_0000.jpg" for v in views.VIEWS]


def obs_by_pitch(level: int, raised: int, **extra) -> dict[str, int]:
    out = {n: (level if "p00/" in n else raised) for n in rig_names()}
    out.update(extra)
    return out


def test_full_model_passes(tmp_path):
    work = tiny_work(tmp_path)
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["pass"] is True, r["reasons"]
    assert r["images_expected"] == 5 + 5 + 5 + 8 + 1
    assert r["groups"]["key"]["registered"] == 5
    assert r["pano"] == {"views": 8, "in_model": 8, "seeing_points": 8, "ok": True}
    assert r["mean_reprojection_error_px"] == 0.5
    assert r["share_registered"] == 1.0 and r["room_images_expected"] == 18 and r["warnings"] == []
    assert r["model_dir"] == "colmap/sparse_txt/0"


def test_too_few_placed_spheres_fails_with_the_fallbacks(tmp_path):
    # Four of the five head views of one sphere are missing: one view cannot pin a sphere (call 57).
    work = tiny_work(tmp_path, omit={"rig/y000p00/2head_0000.jpg", "rig/y090p00/2head_0000.jpg",
                                     "rig/y270p00/2head_0000.jpg", "rig/y045p40/2head_0000.jpg"})
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["pass"] is False
    assert r["spheres"] == {"expected": 3, "placed": 2, "share": 0.6667}
    assert "spheres" in r["reasons"][0]
    assert r["fallbacks"][0].startswith("1. denser sampling")


def test_images_in_the_model_with_few_points_do_not_count(tmp_path):
    weak = {f"rig/y045p40/{f}.jpg": 2 for f in ("2head_0000", "2head_0001", "4key_0000", "5pano_0000")}
    weak.update({f"rig/y315p40/{f}.jpg": 2 for f in ("2head_0000", "2head_0001", "4key_0000", "5pano_0000")})
    work = tiny_work(tmp_path, obs=weak)
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["groups"]["head"]["in_model"] == 10 and r["groups"]["head"]["registered"] == 6
    # The two pitched folders are low together, which is what a plain ceiling does: not a rotation fault,
    # and the room share is what fails it.
    assert r["weak_views"] == []
    # Call 57: blank surfaces no longer fail the run while every sphere still has two views seeing points;
    # the per-image share is kept as a warning.
    assert r["pass"] is True, r["reasons"]
    assert r["spheres"]["placed"] == 3
    assert any("see 15 or more points" in w for w in r["warnings"])


def test_a_sphere_pinned_by_one_view_is_not_placed(tmp_path):
    weak = {f"rig/{v.name}/2head_0000.jpg": 3 for v in HEAD if v.name != "y000p00"}
    work = tiny_work(tmp_path, obs=weak)
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["spheres"] == {"expected": 3, "placed": 2, "share": 0.6667}
    assert r["pass"] is False


def test_plain_ceilings_that_see_few_points_pass(tmp_path):
    work = tiny_work(tmp_path, obs=obs_by_pitch(level=200, raised=30))
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["pass"] is True, r["reasons"]
    assert r["weak_views"] == [] and r["pitch_groups"]["ratio"] == 0.15


def test_one_level_view_far_below_the_best_level_view_is_weak(tmp_path):
    obs = obs_by_pitch(level=200, raised=30, **{f"rig/y090p00/{f}.jpg": 1 for f in
                                                 ("2head_0000", "2head_0001", "4key_0000", "5pano_0000")})
    work = tiny_work(tmp_path, obs=obs)
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["weak_views"] == ["y090p00"] and r["pass"] is False
    assert any("same pitch" in x and "check the rig rotations" in x for x in r["reasons"])


def test_a_pitch_compared_only_with_its_own_pitch(tmp_path):
    obs = obs_by_pitch(level=2000, raised=300, **{f"rig/y315p40/{f}.jpg": 20 for f in
                                                   ("2head_0000", "2head_0001", "4key_0000", "5pano_0000")})
    work = tiny_work(tmp_path, obs=obs)
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["weak_views"] == ["y315p40"]


def test_pitched_views_all_near_zero_fail_on_the_group_rule(tmp_path):
    work = tiny_work(tmp_path, obs=obs_by_pitch(level=200, raised=2))
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["weak_views"] == [] and r["pass"] is False
    assert any("pitch-40" in x and "5 %" in x for x in r["reasons"])


def test_mirrored_yaw_sign_fails_the_report(tmp_path):
    # With the yaw sign mirrored, only the views at yaw 0 and 180 look the right way; the rest see almost
    # nothing, as the synthetic negative control did (under 8 % of the best view).
    wrong = {n: 3 for n in rig_names() if "y090p00" in n or "y270p00" in n or "p40/" in n}
    work = tiny_work(tmp_path, obs=obs_by_pitch(level=200, raised=200, **wrong))
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["pass"] is False
    assert {"y090p00", "y270p00"} <= set(r["weak_views"])
    assert any("check the rig rotations" in x for x in r["reasons"])


def test_the_answer_key_and_phone_are_reported_apart_and_never_fail_the_run(tmp_path):
    key = {f"rig/{v.name}/4key_0000.jpg": 2 for v in HEAD}
    work = tiny_work(tmp_path, obs={**obs_by_pitch(level=200, raised=200, **key), "phone/800x600_f25/IMG_0000.jpg": 2})
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["pass"] is True and r["share_registered"] == 1.0
    assert r["groups"]["key"]["share"] == 0.0 and r["groups"]["phone"]["share"] == 0.0
    text = " | ".join(r["warnings"])
    assert "answer key" in text and "under 50 %" in text and "Part 2" in text
    assert "phone" in text and "PHONE=0 FROM=mapper" in text
    assert r["fallbacks"] == []


def test_a_middling_answer_key_warns_without_the_part_2_statement(tmp_path):
    key = {f"rig/{v.name}/4key_0000.jpg": 2 for v in HEAD[:2]}
    work = tiny_work(tmp_path, obs=obs_by_pitch(level=200, raised=200, **key))
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["pass"] is True and r["groups"]["key"]["share"] == 0.6
    assert any("answer key" in w for w in r["warnings"]) and not any("under 50 %" in w for w in r["warnings"])


def test_failed_run_with_a_low_phone_share_puts_the_phoneless_remap_first(tmp_path):
    work = tiny_work(tmp_path, obs={**obs_by_pitch(level=200, raised=200), "phone/800x600_f25/IMG_0000.jpg": 2},
                     omit={"rig/y000p00/2head_0000.jpg", "rig/y090p00/2head_0000.jpg", "rig/y270p00/2head_0000.jpg",
                           "rig/y045p40/2head_0000.jpg"})
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["pass"] is False
    assert "PHONE=0 FROM=mapper" in r["fallbacks"][0] and r["fallbacks"][0].startswith("1.")
    assert r["fallbacks"][1].startswith("2. denser sampling")


def test_model_dir_is_stored_relative_to_work_and_the_export_runs_from_anywhere(tmp_path, monkeypatch):
    import export_training_set as ets
    work = tiny_work(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert colmap_report.main(["--work", "work", "report"]) == 0
    assert json.loads((work / "colmap_report.json").read_text())["model_dir"] == "colmap/sparse_txt/0"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert ets.main(["--work", "../work", "--out", "../work/train"]) == 0
    assert (work / "train/sparse/0/images.bin").exists()


def test_missing_pano_view_fails(tmp_path):
    work = tiny_work(tmp_path, omit={"rig/y180p00/5pano_0000.jpg"})
    r = colmap_report.report(work / "colmap/sparse_txt", work)
    assert r["pano"]["ok"] is False and r["pass"] is False


def test_cli_writes_json_and_exit_code(tmp_path):
    work = tiny_work(tmp_path)
    assert colmap_report.main(["--work", str(work), "report"]) == 0
    assert json.loads((work / "colmap_report.json").read_text())["pass"] is True

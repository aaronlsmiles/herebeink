import json
import subprocess

import numpy as np
import pytest
from PIL import Image, ImageFilter

import cut_views
import ingest_check
import views
from conftest import make_vfr_video


def fake_ingest(durations: dict[str, float], fps: float = 30.0) -> dict:
    videos = {p: {"present": True, "duration_s": d, "fps": fps, "frames": int(d * fps)} for p, d in durations.items()}
    return {"videos": videos, "pano": {"present": True}}


def test_sample_times_are_centred_in_each_interval():
    assert cut_views.sample_times(10.0, 2.5) == [1.25, 3.75, 6.25, 8.75]
    assert cut_views.sample_times(1.0, 5.0) == [2.5]


def test_plan_shares_and_answer_key_rate():
    plan = cut_views.build_plan(fake_ingest({"raised": 120, "head": 150, "hip": 120, "key": 150}))
    p = plan["passes"]
    assert p["head"]["interval_s"] == pytest.approx(3.75)
    assert p["raised"]["interval_s"] == pytest.approx(4.0)
    assert p["key"]["interval_s"] == p["head"]["interval_s"]
    assert len(p["head"]["times_s"]) == 40 and len(p["raised"]["times_s"]) == 30 and len(p["hip"]["times_s"]) == 30
    assert p["key"]["answer_key"] is True and p["head"]["answer_key"] is False
    assert p["head"]["drop"] == ["180@0", "135@40", "225@40"] and p["raised"]["drop"] == []
    summary = cut_views.plan_summary(plan)
    # raised 30 x 8, head 40 x 5, hip 30 x 5, key 40 x 5, pano 8
    assert "total 798 cube images at 1440 x 1440" in summary


def test_plan_drop_override_and_missing_pass():
    plan = cut_views.build_plan(fake_ingest({"raised": 60, "head": 60, "hip": 60}), drops={"head": (), "raised": ("180@0",)})
    assert plan["passes"]["head"]["drop"] == [] and plan["passes"]["raised"]["drop"] == ["180@0"]
    assert "key" not in plan["passes"]
    with pytest.raises(ValueError, match="hip"):
        cut_views.build_plan(fake_ingest({"raised": 60, "head": 60}))


def test_yaw_offset_is_stored_per_pass():
    plan = cut_views.build_plan(fake_ingest({"raised": 60, "head": 60, "hip": 60}), yaw_offsets={"head": 180.0})
    assert plan["passes"]["head"]["yaw_offset"] == 180.0 and plan["passes"]["hip"]["yaw_offset"] == 0
    assert plan["pano"]["yaw_offset"] == 0
    assert "yaw offset 180.0" in cut_views.plan_summary(plan)
    assert cut_views.parse_yaw_offset_arg("head=180") == ("head", 180.0)
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        cut_views.parse_yaw_offset_arg("head=left")


def test_cli_drop_parsing():
    assert cut_views.parse_drop_arg("hip=none") == ("hip", ())
    assert cut_views.parse_drop_arg("head=180@0,135@40") == ("head", ("180@0", "135@40"))
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        cut_views.parse_drop_arg("kitchen=180@0")
    with pytest.raises(argparse.ArgumentTypeError):
        cut_views.parse_drop_arg("head=0@0")


def test_frame_names_sort_in_capture_order():
    names = [cut_views.frame_name(p, k) for p in ("raised", "head", "hip", "key") for k in (0, 7, 31)] + [cut_views.frame_name("pano", 0)]
    assert names == sorted(names)
    assert cut_views.frame_name("head", 7) == "2head_0007"


def test_laplacian_prefers_sharp():
    rng = np.random.default_rng(0)
    sharp = Image.fromarray(rng.integers(0, 255, (120, 240), dtype=np.uint8))
    blurred = sharp.filter(ImageFilter.GaussianBlur(3))
    assert cut_views.laplacian_variance(np.asarray(sharp)) > 10 * cut_views.laplacian_variance(np.asarray(blurred))


def test_choose_frames_takes_the_sharpest_and_never_repeats():
    scores = {i: 1.0 for i in range(20)}
    scores[7] = 9.0
    chosen = cut_views.choose_frames([1.2, 1.3], fps=5, n_frames=20, window=0.4, scores=scores)
    assert chosen[0] == (0, 7, 9.0)
    assert chosen[1][1] != 7
    assert cut_views.choose_frames([1.2], fps=5, n_frames=20, window=0.4, scores=None) == [(0, 6, None)]


def grey_video(path, levels, fps=5, size=(256, 128)):
    frames = path.parent / "frames"
    frames.mkdir(exist_ok=True)
    for i, g in enumerate(levels):
        Image.new("L", size, int(g)).save(frames / f"{i:04d}.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", str(frames / "%04d.png"),
                    "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv444p", str(path)], check=True)
    return path


def test_cut_frames_takes_exactly_the_selected_frames(tmp_path):
    video = grey_video(tmp_path / "grey.mp4", [20 * i for i in range(12)])
    keep = views.kept_views(())
    cut_views.cut_frames(video, [2, 5, 9], ["a", "b", "c"], keep, 64, tmp_path / "images")
    for name, level in (("a", 40), ("b", 100), ("c", 180)):
        for v in keep:
            px = np.asarray(Image.open(tmp_path / "images/rig" / v.name / f"{name}.jpg").convert("L"), dtype=float)
            assert abs(px.mean() - level) < 4, (name, v.name, px.mean())


def test_score_frames_finds_the_sharp_frame(tmp_path):
    rng = np.random.default_rng(1)
    base = Image.fromarray(rng.integers(0, 255, (256, 512), dtype=np.uint8))
    frames = tmp_path / "frames"
    frames.mkdir()
    for i in range(10):
        (base if i == 7 else base.filter(ImageFilter.GaussianBlur(4))).save(frames / f"{i:04d}.png")
    video = tmp_path / "blur.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "5", "-i", str(frames / "%04d.png"),
                    "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(video)], check=True)
    scores = cut_views.score_frames(video, set(range(10)))
    assert max(scores, key=scores.get) == 7
    chosen = cut_views.choose_frames([1.2], fps=5, n_frames=10, window=0.3, scores=scores)
    assert chosen[0][1] == 7


def test_score_frames_indexes_by_real_frame_on_variable_frame_rate_input(tmp_path):
    video = make_vfr_video(tmp_path / "vfr.mp4", sharp_index=9)
    scores = cut_views.score_frames(video, set(range(40)))
    assert len(scores) == 12
    assert max(scores, key=scores.get) == 9


def test_cut_end_to_end_on_the_fixture(capture, work):
    ingest_check.run(capture, work)
    plan = cut_views.build_plan(json.loads((work / "ingest.json").read_text()), positions=10, view_size=64)
    record = cut_views.cut(plan, capture, work)
    rig = work / "images/rig"
    assert sorted(p.name for p in rig.iterdir()) == sorted(v.name for v in views.VIEWS)
    head = [f for f in record["frames"] if f["pass"] == "head"]
    assert len(head) == len(plan["passes"]["head"]["times_s"])
    for f in record["frames"]:
        for token in f["views"]:
            assert (rig / views.VIEW_BY_TOKEN[token].name / f"{f['name']}.jpg").exists()
    assert not (rig / "y180p00" / f"{head[0]['name']}.jpg").exists()
    assert (rig / "y180p00" / "5pano_0000.jpg").exists()
    assert all(f["answer_key"] == (f["pass"] == "key") for f in record["frames"])
    assert json.loads((work / "rig_config.json").read_text()) == views.rig_config()
    with Image.open(rig / "y000p00" / f"{head[0]['name']}.jpg") as im:
        assert im.size == (64, 64)


def test_preview_sheet_has_all_eight_views(capture, work):
    ingest_check.run(capture, work)
    plan = cut_views.build_plan(json.loads((work / "ingest.json").read_text()), positions=10, view_size=64)
    paths = cut_views.preview(plan, capture, work, size=64)
    assert [p.name for p in paths] == ["pass-raised.jpg", "pass-head.jpg", "pass-hip.jpg", "pass-key.jpg"]
    with Image.open(paths[1]) as im:
        assert im.size == (8 * 64, 6 * (64 + 22))


def plan_cli(work, *argv):
    return cut_views.main(["--work", str(work), "plan", *argv])


def written_plan(work):
    return json.loads((work / "cut_plan.json").read_text())


def test_replanning_keeps_the_operator_drops_and_yaw_offsets(tmp_path, capsys):
    work = tmp_path / "work"
    work.mkdir()
    (work / "ingest.json").write_text(json.dumps(fake_ingest({"raised": 120, "head": 150, "hip": 120})))
    assert plan_cli(work, "--drop", "head=180@0", "--drop", "hip=none", "--yaw-offset", "head=180") == 0
    capsys.readouterr()
    assert plan_cli(work, "--positions", "150") == 0
    out = capsys.readouterr().out
    plan = written_plan(work)
    assert plan["positions"] == 150
    assert plan["passes"]["head"]["drop"] == ["180@0"] and plan["passes"]["hip"]["drop"] == []
    assert plan["passes"]["head"]["yaw_offset"] == 180.0
    carried = [ln for ln in out.splitlines() if ln.startswith("carried over")]
    assert len(carried) == 1 and "head" in carried[0] and "yaw" in carried[0] and "--reset-drops" in carried[0]


def test_a_new_argument_beats_the_carried_value(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "ingest.json").write_text(json.dumps(fake_ingest({"raised": 120, "head": 150, "hip": 120})))
    plan_cli(work, "--drop", "head=none", "--yaw-offset", "head=90")
    plan_cli(work, "--drop", "head=180@0", "--yaw-offset", "head=270")
    plan = written_plan(work)
    assert plan["passes"]["head"]["drop"] == ["180@0"] and plan["passes"]["head"]["yaw_offset"] == 270.0


def test_reset_drops_returns_to_the_defaults_on_purpose(tmp_path, capsys):
    work = tmp_path / "work"
    work.mkdir()
    (work / "ingest.json").write_text(json.dumps(fake_ingest({"raised": 120, "head": 150, "hip": 120})))
    plan_cli(work, "--drop", "head=none", "--yaw-offset", "head=90")
    capsys.readouterr()
    plan_cli(work, "--reset-drops")
    plan = written_plan(work)
    assert plan["passes"]["head"]["drop"] == ["180@0", "135@40", "225@40"]
    assert plan["passes"]["head"]["yaw_offset"] == 0
    assert "reset" in capsys.readouterr().out


def test_a_first_plan_carries_nothing(tmp_path, capsys):
    work = tmp_path / "work"
    work.mkdir()
    (work / "ingest.json").write_text(json.dumps(fake_ingest({"raised": 120, "head": 150, "hip": 120})))
    plan_cli(work)
    assert "carried over" not in capsys.readouterr().out
    assert written_plan(work)["passes"]["head"]["drop"] == ["180@0", "135@40", "225@40"]


def planned(capture, work, **kw):
    ingest_check.run(capture, work)
    return cut_views.build_plan(json.loads((work / "ingest.json").read_text()), positions=10, view_size=64, **kw)


def test_a_failed_cut_leaves_no_stale_frames_json(capture, work):
    plan = planned(capture, work)
    cut_views.cut(plan, capture, work)
    assert (work / "frames.json").exists() and (work / "rig_config.json").exists()
    (capture / "stitched/pass-hip.mp4").unlink()
    with pytest.raises(Exception):
        cut_views.cut(plan, capture, work)
    assert not (work / "frames.json").exists() and not (work / "rig_config.json").exists()


def test_cut_writes_a_seeded_spot_check_of_images_that_were_cut(capture, work):
    plan = planned(capture, work)
    record = cut_views.cut(plan, capture, work)
    sheet = work / "preview" / "cut-check.jpg"
    assert sheet.exists()
    first = sheet.read_bytes()
    picks = cut_views.pick_check_images(work, record, 24)
    assert len(picks) == 24
    assert len({(f, t) for f, t, _ in picks}) == 24
    for frame, token, path in picks:
        assert path.exists() and token in next(f for f in record["frames"] if f["name"] == frame)["views"]
    assert picks == cut_views.pick_check_images(work, record, 24)
    cut_views.cut(plan, capture, work)
    assert sheet.read_bytes() == first
    with Image.open(sheet) as im:
        assert im.size == (cut_views.CHECK_COLS * cut_views.CHECK_TILE,
                           4 * (cut_views.CHECK_TILE + cut_views.CHECK_LABEL_H))


def test_spot_check_takes_everything_when_fewer_images_were_cut(tmp_path):
    work = tmp_path / "work"
    (work / "images/rig/y000p00").mkdir(parents=True)
    Image.new("RGB", (64, 64)).save(work / "images/rig/y000p00/2head_0000.jpg")
    record = {"frames": [{"name": "2head_0000", "views": ["0@0", "90@0"]}]}
    picks = cut_views.pick_check_images(work, record, 24)
    assert [(f, t) for f, t, _ in picks] == [("2head_0000", "0@0")]


def test_a_stale_masked_copy_stops_the_cut_with_a_message(capture, work, capsys):
    import os
    plan = planned(capture, work)
    (work / "cut_plan.json").write_text(json.dumps(plan))
    masked = capture / "stitched/pass-head.masked.mp4"
    masked.write_bytes((capture / "stitched/pass-head.mp4").read_bytes())
    old = os.stat(capture / "stitched/pass-head.mp4").st_mtime - 100
    os.utime(masked, (old, old))
    assert cut_views.main(["--capture", str(capture), "--work", str(work), "cut"]) == 1
    assert "older than pass-head.mp4" in capsys.readouterr().out

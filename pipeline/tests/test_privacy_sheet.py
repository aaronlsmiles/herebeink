import hashlib
import subprocess

import numpy as np
from PIL import Image

import ingest_check
import privacy_sheet


def frame_at(video, t, tmp_path):
    out = tmp_path / f"frame_{t}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1", str(out)], check=True)
    return np.asarray(Image.open(out).convert("L"), dtype=float)


def test_sheets_cover_every_pass_the_pano_and_the_phone(capture, work):
    ingest_check.run(capture, work)
    sheets = privacy_sheet.make_sheets(capture, work)
    out = work / "privacy"
    # 25 s at one frame a second, 20 tiles a sheet: two sheets a pass
    for name in ("raised", "head", "hip", "key"):
        assert (out / f"pass-{name}-01.jpg").exists() and (out / f"pass-{name}-02.jpg").exists()
        assert not (out / f"pass-{name}-03.jpg").exists()
    assert (out / "pano.jpg").exists()
    assert (out / "phone-01.jpg").exists()
    index = (out / "INDEX.md").read_text()
    assert "### pass-head-02.jpg" in index and "### pano.jpg" in index and "### phone-01.jpg" in index
    assert index.count("- [ ] no people") == sum(len(v) for v in sheets.values())


def test_sheet_tiles_are_labelled_and_sized(capture, work):
    privacy_sheet.make_sheets(capture, work)
    with Image.open(work / "privacy/pass-head-01.jpg") as im:
        assert im.size == (4 * 640, 5 * (320 + 26))


def test_wrap_boxes_splits_at_the_seam():
    assert privacy_sheet.wrap_boxes([(5700, 10, 100, 20)], 5760) == [(5700, 10, 60, 20), (0, 10, 40, 20)]
    assert privacy_sheet.wrap_boxes([(-50, 10, 20, 20)], 5760) == [(5710, 10, 20, 20)]


def test_mask_blacks_out_only_the_time_range_and_keeps_the_export(capture, work, tmp_path):
    original = capture / "stitched/pass-head.mp4"
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    dest = privacy_sheet.mask_video(capture, "head", 2.0, 4.0, [(40, 30, 60, 40)])
    assert dest.name == "pass-head.masked.mp4"
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    inside = frame_at(dest, 3.0, tmp_path)
    outside = frame_at(dest, 8.0, tmp_path)
    assert inside[32:68, 42:98].mean() < 20
    assert outside[32:68, 42:98].mean() > 40


def test_second_mask_builds_on_the_first(capture, work, tmp_path):
    privacy_sheet.mask_video(capture, "head", 2.0, 4.0, [(40, 30, 60, 40)])
    dest = privacy_sheet.mask_video(capture, "head", 10.0, 12.0, [(150, 60, 50, 40)])
    assert frame_at(dest, 3.0, tmp_path)[32:68, 42:98].mean() < 20
    assert frame_at(dest, 11.0, tmp_path)[62:98, 152:198].mean() < 20


def test_mask_pano_writes_a_copy(capture):
    dest = privacy_sheet.mask_pano(capture, [(500, 100, 30, 40)])
    with Image.open(dest) as im:
        px = np.asarray(im.convert("L"), dtype=float)
    assert px[110:130, 0:10].mean() < 10 and px[110:130, 503:512].mean() < 10
    with Image.open(capture / "stitched/pano.jpg") as im:
        assert np.asarray(im.convert("L"))[120, 505] > 50


def test_cli_rejects_a_pass_mask_without_times(capture):
    import pytest
    with pytest.raises(SystemExit):
        privacy_sheet.main(["--capture", str(capture), "mask", "--pass", "head", "--box", "1,1,5,5"])


def test_the_mask_window_is_padded_by_a_second_either_side(capture, work, tmp_path):
    dest = privacy_sheet.mask_video(capture, "head", 10.0, 12.0, [(40, 30, 60, 40)])
    for t in (9.2, 12.8):
        assert frame_at(dest, t, tmp_path)[32:68, 42:98].mean() < 20, t
    for t in (7.0, 14.5):
        assert frame_at(dest, t, tmp_path)[32:68, 42:98].mean() > 40, t


def test_the_padded_window_is_clamped_to_the_clip():
    assert privacy_sheet.padded_window(0.2, 1.0, 25.0) == (0.0, 2.0)
    assert privacy_sheet.padded_window(24.0, 25.5, 25.0) == (23.0, 25.0)
    assert privacy_sheet.padded_window(10.0, 12.0, 25.0) == (9.0, 13.0)


def test_the_cli_prints_the_padded_window(capture, capsys):
    assert privacy_sheet.main(["--capture", str(capture), "mask", "--pass", "head", "--start", "10", "--end", "12",
                               "--box", "40,30,60,40"]) == 0
    assert "9.0 to 13.0 s" in capsys.readouterr().out


def test_the_docs_say_the_window_is_padded(capture, work):
    assert "one second" in privacy_sheet.__doc__
    privacy_sheet.make_sheets(capture, work)
    index = " ".join((work / "privacy/INDEX.md").read_text().split())
    assert "pads the time window by one second" in index
    assert "Clean for upload: yes" in index


def test_every_pano_still_present_gets_a_sheet(capture, work):
    for stem in ("pano-auto", "pano-hdr"):
        Image.new("RGB", (512, 256), (120, 90, 60)).save(capture / f"stitched/{stem}.jpg")
    sheets = privacy_sheet.make_sheets(capture, work)
    out = work / "privacy"
    for stem in ("pano", "pano-auto", "pano-hdr"):
        assert (out / f"{stem}.jpg").exists()
    index = (out / "INDEX.md").read_text()
    assert "### pano-auto.jpg" in index and "### pano-hdr.jpg" in index
    assert sum(1 for k in sheets if k.startswith("pano")) == 3


def test_a_pano_with_a_masked_copy_gets_its_masked_sheet(capture, work):
    Image.new("RGB", (512, 256), (120, 90, 60)).save(capture / "stitched/pano-auto.jpg")
    privacy_sheet.mask_pano(capture, [(10, 10, 50, 50)], "pano-auto")
    sheets = privacy_sheet.make_sheets(capture, work)
    assert any("pano-auto.masked.jpg" in k for k in sheets)


def test_the_cli_masks_the_auto_exposure_pano(capture):
    Image.new("RGB", (512, 256), (120, 90, 60)).save(capture / "stitched/pano-auto.jpg")
    assert privacy_sheet.main(["--capture", str(capture), "mask", "--pano-auto", "--box", "1,1,5,5"]) == 0
    assert (capture / "stitched/pano-auto.masked.jpg").exists()

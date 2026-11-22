import json

from PIL import Image

import ingest_check
from conftest import TEMPLATE, fill_notes, make_jpeg, make_vfr_video, make_video


def test_template_line_is_what_the_parser_reads():
    assert "- **Door frame inside width (tape), in metres:**" in TEMPLATE.read_text()
    assert "Clean for upload: NOT YET" in TEMPLATE.read_text()


def test_complete_capture_passes_with_size_warnings(capture, work):
    result, rep = ingest_check.run(capture, work)
    assert rep.errors == []
    assert result["ok"] is True
    assert result["videos"]["head"]["width"] == 256 and result["videos"]["head"]["fps"] == 5.0
    assert any("expected 5760 x 2880" in w for w in rep.warnings)
    assert result["notes"]["door_width_m"] == 0.812
    assert result["notes"]["clean_for_upload"] == "NOT YET"
    saved = json.loads((work / "ingest.json").read_text())
    assert saved["ok"] is True


def test_phone_stills_converted_and_grouped(capture, work):
    result, rep = ingest_check.run(capture, work)
    groups = result["phone"]["groups"]
    assert groups == {"400x300_f24": 1, "300x400_f24": 1}
    assert (work / "images/phone/400x300_f24/IMG_0001.jpg").exists()
    assert (work / "images/phone/300x400_f24/IMG_0002.jpg").exists()
    assert "clip.MOV" in result["phone"]["skipped"]


def test_missing_room_pass_is_an_error(capture, work):
    (capture / "stitched/pass-head.mp4").unlink()
    result, rep = ingest_check.run(capture, work)
    assert any("pass-head.mp4 is missing" in e for e in rep.errors)
    assert result["ok"] is False
    assert ingest_check.main(["--capture", str(capture), "--work", str(work)]) == 1


def test_missing_key_pass_hdr_and_phone_are_warnings(capture, work):
    (capture / "stitched/pass-key.mp4").unlink()
    for p in (capture / "raw/phone").iterdir():
        p.unlink()
    result, rep = ingest_check.run(capture, work)
    assert rep.errors == []
    assert any("pass-key.mp4 is missing" in w for w in rep.warnings)
    assert any("pano-hdr.jpg is missing" in w for w in rep.warnings)
    assert any("no phone stills" in w for w in rep.warnings)


def test_pano_not_two_to_one_is_an_error(capture, work):
    Image.new("RGB", (512, 300)).save(capture / "stitched/pano.jpg")
    _, rep = ingest_check.run(capture, work)
    assert any("pano.jpg is 512 x 300, not exactly 2:1" in e for e in rep.errors)


def test_video_not_two_to_one_is_an_error(capture, work):
    make_video(capture / "stitched/pass-hip.mp4", width=256, height=256)
    _, rep = ingest_check.run(capture, work)
    assert any("pass-hip.mp4 is 256 x 256, not 2:1" in e for e in rep.errors)


def test_short_room_pass_is_an_error_short_key_a_warning(capture, work):
    make_video(capture / "stitched/pass-raised.mp4", seconds=5)
    make_video(capture / "stitched/pass-key.mp4", seconds=5)
    _, rep = ingest_check.run(capture, work)
    assert any("pass-raised.mp4 lasts 5 s: too short" in e for e in rep.errors)
    assert any("pass-key.mp4 lasts 5 s: too short" in w for w in rep.warnings)


def test_door_width_missing_or_implausible(capture, work):
    (capture / "NOTES.md").write_text(fill_notes(TEMPLATE.read_text(), door=None))
    _, rep = ingest_check.run(capture, work)
    assert any("door width is not in NOTES.md" in e for e in rep.errors)
    (capture / "NOTES.md").write_text(fill_notes(TEMPLATE.read_text(), door="81.2"))
    _, rep = ingest_check.run(capture, work)
    assert any("is it in metres" in e for e in rep.errors)


def test_door_width_accepts_unit_and_cross_check(capture, work):
    text = fill_notes(TEMPLATE.read_text(), door="0.812 m", clean="yes")
    text += "\n- Door frame inside width, second tape (cross-check), in metres: 0.820\n"
    (capture / "NOTES.md").write_text(text)
    result, rep = ingest_check.run(capture, work)
    assert result["notes"]["door_width_m"] == 0.812
    assert result["notes"]["door_width_check_m"] == 0.82
    assert result["notes"]["clean_for_upload"] == "yes"
    assert any("differ by more than 5 mm" in w for w in rep.warnings)


def test_variable_frame_rate_is_a_warning(capture, work):
    make_vfr_video(capture / "stitched/pass-key.mp4", sharp_index=3)
    result, rep = ingest_check.run(capture, work)
    assert any("pass-key.mp4" in w and "variable frame rate" in w for w in rep.warnings)
    assert not any("pass-head.mp4" in w and "variable frame rate" in w for w in rep.warnings)
    assert result["videos"]["key"]["avg_fps"] != result["videos"]["key"]["r_fps"]


def test_pano_auto_is_optional_and_checked_for_two_to_one(capture, work):
    _, rep = ingest_check.run(capture, work)
    assert any("pano-auto.jpg is missing" in w for w in rep.warnings) and rep.errors == []
    Image.new("RGB", (512, 300)).save(capture / "stitched/pano-auto.jpg")
    result, rep = ingest_check.run(capture, work)
    assert any("pano-auto.jpg is 512 x 300, not exactly 2:1" in e for e in rep.errors)
    Image.new("RGB", (512, 256)).save(capture / "stitched/pano-auto.jpg")
    result, rep = ingest_check.run(capture, work)
    assert rep.errors == [] and result["pano_auto"]["present"] is True


def test_whitespace_in_phone_names_is_replaced_and_nothing_collides(capture, work):
    phone = capture / "raw" / "phone"
    for name in ("IMG_1234 2.JPG", "IMG_1234.JPG", "IMG_1234_2.JPG", "IMG 7.JPG"):
        make_jpeg(phone / name)
    result, rep = ingest_check.run(capture, work)
    names = sorted(p.name for p in (work / "images/phone").rglob("*.jpg"))
    assert not any(" " in n for n in names), names
    assert names.count("IMG_7.jpg") == 1 and "IMG_1234.jpg" in names
    assert len({n for n in names if n.startswith("IMG_1234")}) == 3
    assert result["phone"]["count"] == len(names) == 2 + 4
    assert result["phone"]["renamed"] == {"IMG 7.JPG": "IMG_7.jpg", "IMG_1234 2.JPG": "IMG_1234_2_2.jpg"}
    assert "IMG_1234_2.jpg" in names


def test_a_heic_and_jpeg_of_the_same_stem_are_still_a_duplicate(capture, work):
    make_jpeg(capture / "raw/phone/IMG_0002.JPG")
    result, rep = ingest_check.run(capture, work)
    assert any("same name as another" in w for w in rep.warnings)

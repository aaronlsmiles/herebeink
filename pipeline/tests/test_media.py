import os

import pytest

import media


def touch(path, age_s=0):
    path.write_bytes(b"x")
    if age_s:
        t = path.stat().st_mtime - age_s
        os.utime(path, (t, t))
    return path


def test_the_masked_copy_is_read_when_it_is_newer(tmp_path):
    touch(tmp_path / "pass-head.mp4", 50)
    touch(tmp_path / "pass-head.masked.mp4")
    assert media.stitched_video(tmp_path, "head").name == "pass-head.masked.mp4"
    touch(tmp_path / "pano.jpg", 50)
    touch(tmp_path / "pano.masked.jpg")
    assert media.stitched_pano(tmp_path).name == "pano.masked.jpg"


def test_no_masked_copy_reads_the_export(tmp_path):
    touch(tmp_path / "pano-auto.jpg")
    assert media.stitched_pano(tmp_path, "pano-auto").name == "pano-auto.jpg"


def test_a_masked_copy_older_than_its_source_is_refused(tmp_path):
    touch(tmp_path / "pass-head.masked.mp4", 50)
    touch(tmp_path / "pass-head.mp4")
    with pytest.raises(media.MediaError, match="older than pass-head.mp4"):
        media.stitched_video(tmp_path, "head")


def test_choose_source_refuses_the_original_beside_its_masked_copy(tmp_path):
    touch(tmp_path / "pano.jpg", 50)
    touch(tmp_path / "pano.masked.jpg")
    with pytest.raises(media.MediaError, match="pano.masked.jpg"):
        media.choose_source(tmp_path / "pano.jpg")
    assert media.choose_source(tmp_path / "pano.masked.jpg").name == "pano.masked.jpg"
    touch(tmp_path / "other.jpg")
    assert media.choose_source(tmp_path / "other.jpg").name == "other.jpg"

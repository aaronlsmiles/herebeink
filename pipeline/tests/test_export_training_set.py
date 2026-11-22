import json

from PIL import Image

import colmap_report
import export_training_set as ets
from colmap_model import read_model
from conftest import tiny_work


def prepared(tmp_path):
    work = tiny_work(tmp_path)
    assert colmap_report.main(["--work", str(work), "report"]) == 0
    return work


def test_flat_names():
    assert ets.flat_name("rig/y090p00/2head_0007.jpg") == "y090p00__2head_0007.jpg"
    assert ets.flat_name("phone/800x600_f25/IMG_1.jpg") == "phone__800x600_f25__IMG_1.jpg"


def test_export_leaves_out_the_answer_key_and_phone(tmp_path):
    work = prepared(tmp_path)
    m = ets.export(work, work / "train")
    assert m["cube_images"] == 5 + 5 + 8 and m["phone_images"] == 0
    assert m["answer_key_images_left_out"] == 5
    files = sorted(p.name for p in (work / "train/images").iterdir())
    assert len(files) == 18 and not any("4key" in f for f in files) and "y000p00__5pano_0000.jpg" in files
    model = read_model(work / "train/sparse/0")
    assert list(model.cameras) == [1] and model.cameras[1].model == "PINHOLE"
    assert {im.camera_id for im in model.images.values()} == {1}
    assert {im.name for im in model.images.values()} == set(files)
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        assert (work / "train/sparse/0" / name).exists()
    assert not (work / "train/sparse/0/rigs.bin").exists()


def test_points_seen_only_from_the_answer_key_are_dropped(tmp_path):
    work = prepared(tmp_path)
    m = ets.export(work, work / "train")
    # each point is seen by one image and the pano's front view: the key sphere's 5 images and the
    # phone still (left out by default) take 20 points each down to a single observation
    assert m["points_dropped"] == (5 + 1) * 20
    model = read_model(work / "train/sparse/0")
    kept_ids = set(model.images)
    for p in model.points.values():
        assert len(p.track) >= 2 and all(i in kept_ids for i, _ in p.track)
    for im in model.images.values():
        assert all(pid == -1 or pid in model.points for _, _, pid in im.points2d)


def test_no_pano_leaves_the_still_out(tmp_path):
    work = prepared(tmp_path)
    m = ets.export(work, work / "train", with_pano=False)
    assert m["cube_images"] == 5 + 5
    assert not any("5pano" in p.name for p in (work / "train/images").iterdir())


def test_subset_for_the_dry_run(tmp_path):
    work = prepared(tmp_path)
    m = ets.export(work, work / "train_dry", subset=6)
    assert m["cube_images"] == 6
    assert len(list((work / "train_dry/images").iterdir())) == 6


def test_refuses_a_failed_reconstruction(tmp_path):
    work = prepared(tmp_path)
    r = json.loads((work / "colmap_report.json").read_text())
    r["pass"] = False
    (work / "colmap_report.json").write_text(json.dumps(r))
    assert ets.main(["--work", str(work)]) == 1


def test_images_are_copied_unchanged(tmp_path):
    work = prepared(tmp_path)
    ets.export(work, work / "train")
    a = Image.open(work / "images/rig/y090p00/2head_0001.jpg").tobytes()
    b = Image.open(work / "train/images/y090p00__2head_0001.jpg").tobytes()
    assert a == b

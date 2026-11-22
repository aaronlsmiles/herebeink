"""The whole chain on a synthetic room: ingest, cut, COLMAP with the rig, the report, the export.

Slow (about four minutes): run with `uv run pytest -m slow`. It exists to find a wrong flag or a wrong
convention tonight rather than tomorrow, and it checks the recovered sphere positions against the
positions the room was rendered from.
"""
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import numpy as np
import pytest

import cut_views
import export_training_set
import ingest_check
import synth_capture
import views
from colmap_model import read_model

pytestmark = pytest.mark.slow
PIPELINE = Path(__file__).resolve().parents[1]


def run_colmap(work: Path, **env) -> subprocess.CompletedProcess:
    return subprocess.run(["./colmap.sh"], cwd=PIPELINE, env={**os.environ, "WORK": str(work), **env},
                          capture_output=True, text=True)


@pytest.fixture(scope="module")
def smoke(tmp_path_factory):
    root = tmp_path_factory.mktemp("smoke")
    capture, work = root / "capture", root / "work"
    truth = synth_capture.make_capture(capture)
    assert ingest_check.main(["--capture", str(capture), "--work", str(work)]) == 0
    assert cut_views.main(["--capture", str(capture), "--work", str(work), "plan", "--positions", "30", "--view-size", "256"]) == 0
    assert cut_views.main(["--capture", str(capture), "--work", str(work), "cut"]) == 0
    proc = run_colmap(work)
    return {"root": root, "capture": capture, "work": work, "truth": truth, "proc": proc}


def test_colmap_sh_runs_and_passes(smoke):
    proc = smoke["proc"]
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert "db-check: PASS" in proc.stdout
    assert "PASS: one model" in proc.stdout


def test_a_plain_rerun_does_not_wipe_the_finished_model(smoke):
    proc = run_colmap(smoke["work"])
    assert proc.returncode == 2 and "FROM=report" in proc.stderr
    assert (smoke["work"] / "colmap/sparse/0/images.bin").exists()
    again = run_colmap(smoke["work"], FROM="report")
    assert again.returncode == 0 and "PASS: one model" in again.stdout


def test_the_mapper_left_snapshots(smoke):
    assert any((smoke["work"] / "colmap/snapshots").iterdir())


def test_database_holds_the_rig_the_cameras_and_every_image(smoke):
    work = smoke["work"]
    frames = json.loads((work / "frames.json").read_text())["frames"]
    n_rig_images = sum(len(f["views"]) for f in frames)
    con = sqlite3.connect(work / "colmap/database.db")
    one = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    assert one("select count(*) from images") == n_rig_images + 6
    assert one("select count(*) from cameras") == 8 + 1
    assert one("select count(*) from rigs") == 2  # the eight-view rig, and the phone camera's own
    assert one("select count(*) from frames") == len(frames) + 6
    assert one("select max(c) from (select count(*) c from frame_data group by frame_id)") == 8
    assert one("select min(c) from (select count(*) c from frame_data join frames using(frame_id) "
               "where rig_id = (select rig_id from rig_sensors group by rig_id having count(*) = 7) group by frame_id)") == 5


def test_report_numbers(smoke):
    r = json.loads((smoke["work"] / "colmap_report.json").read_text())
    assert r["pass"] is True and r["models"] == 1
    assert r["share_registered"] > 0.95
    assert r["weak_views"] == []
    assert r["pano"]["ok"] is True and r["pano"]["seeing_points"] == 8
    assert r["mean_reprojection_error_px"] < 1.5


def test_cube_cameras_kept_their_exact_intrinsics(smoke):
    work = smoke["work"]
    model = read_model(work / json.loads((work / "colmap_report.json").read_text())["model_dir"])
    for im in model.images.values():
        if im.name.startswith("rig/"):
            assert model.cameras[im.camera_id].params == [128.0, 128.0, 128.0, 128.0]


def test_sphere_positions_match_the_render_after_a_similarity_fit(smoke):
    work = smoke["work"]
    model = read_model(work / json.loads((work / "colmap_report.json").read_text())["model_dir"])
    frames = {f["name"]: f for f in json.loads((work / "frames.json").read_text())["frames"]}
    est, true = [], []
    for im in model.images.values():
        if not im.name.startswith(f"rig/{views.REF_VIEW.name}/"):
            continue
        f = frames[Path(im.name).stem]
        key = "pano" if f["pass"] == "pano" else f"{f['pass']}_{int(f['time_s'] // synth_capture.HOLD_S)}"
        w, x, y, z = im.qvec
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                      [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                      [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
        est.append(-R.T @ np.array(im.tvec))
        true.append(smoke["truth"][key])
    A, B = np.array(est), np.array(true)
    a0, b0 = A - A.mean(0), B - B.mean(0)
    U, S, Vt = np.linalg.svd(b0.T @ a0)
    D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
    s = (S * np.diag(D)).sum() / (a0 ** 2).sum()
    err = np.linalg.norm(s * (U @ D @ Vt @ a0.T).T - b0, axis=1)
    assert len(err) >= 40
    assert np.median(err) < 0.02 and err.max() < 0.05, f"median {np.median(err):.3f} m, max {err.max():.3f} m"


def test_training_export_reads_back_in_colmap(smoke):
    work = smoke["work"]
    m = export_training_set.export(work, work / "train")
    frames = json.loads((work / "frames.json").read_text())["frames"]
    assert m["cube_images"] == sum(len(f["views"]) for f in frames if not f["answer_key"])
    assert m["answer_key_images_left_out"] == sum(len(f["views"]) for f in frames if f["answer_key"])
    out = subprocess.run(["colmap", "model_analyzer", "--path", str(work / "train/sparse/0"), "--log_target", "stderr"],
                         capture_output=True, text=True)
    assert out.returncode == 0 and "Cameras: 1" in out.stderr
    dry = export_training_set.export(work, work / "train_dry", subset=20)
    assert dry["cube_images"] == 20


def test_fallback_matching_without_a_vocab_tree(smoke):
    work2 = smoke["root"] / "work-no-vocab"
    shutil.copytree(smoke["work"], work2, ignore=shutil.ignore_patterns("colmap", "train*"))
    proc = run_colmap(work2, VOCAB="none")
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert "no cached vocab tree" in proc.stdout and "PASS: one model" in proc.stdout

"""colmap.sh's own behaviour, with a stand-in `colmap` that records its arguments (the real run is the slow smoke test)."""
import json
import os
import sqlite3
import stat
import subprocess
from pathlib import Path

import pytest

PIPELINE = Path(__file__).resolve().parents[1]


@pytest.fixture
def rig(tmp_path):
    work = tmp_path / "work"
    (work / "images" / "rig" / "y000p00").mkdir(parents=True)
    (work / "images" / "rig" / "y000p00" / "2head_0000.jpg").write_bytes(b"x")
    (work / "frames.json").write_text(json.dumps({"view_size": 64, "focal_px": 40.0, "frames": []}))
    (work / "rig_config.json").write_text("[]")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "colmap"
    fake.write_text(f'#!/bin/sh\necho "$@" >> "{tmp_path}/colmap-calls.txt"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return {"work": work, "calls": tmp_path / "colmap-calls.txt", "path": f"{bin_dir}:{os.environ['PATH']}"}


def run(rig, **env):
    return subprocess.run(["./colmap.sh"], cwd=PIPELINE, capture_output=True, text=True,
                          env={**os.environ, "WORK": str(rig["work"]), "PATH": rig["path"], "VOCAB": "none", **env})


def calls(rig):
    return rig["calls"].read_text().splitlines() if rig["calls"].exists() else []


def test_a_plain_rerun_refuses_to_wipe_a_finished_model(rig):
    model = rig["work"] / "colmap" / "sparse" / "0"
    model.mkdir(parents=True)
    (model / "images.bin").write_bytes(b"model")
    proc = run(rig)
    assert proc.returncode == 2
    assert "FROM=report" in proc.stderr and "FRESH=1" in proc.stderr
    assert (model / "images.bin").read_bytes() == b"model" and calls(rig) == []


def test_fresh_overrides_the_refusal(rig):
    model = rig["work"] / "colmap" / "sparse" / "0"
    model.mkdir(parents=True)
    (model / "images.bin").write_bytes(b"model")
    run(rig, FRESH="1")
    assert not (model / "images.bin").exists()
    assert calls(rig) and calls(rig)[0].startswith("feature_extractor")


def test_an_empty_sparse_folder_has_nothing_to_protect(rig):
    (rig["work"] / "colmap" / "sparse").mkdir(parents=True)
    run(rig)
    assert calls(rig)


def test_the_camera_comes_from_frames_json(rig):
    run(rig)
    first = calls(rig)[0]
    assert "--ImageReader.camera_params 40.0,40.0,32.0,32.0" in first


def test_the_mapper_writes_snapshots_while_it_runs(rig):
    out = rig["work"] / "colmap"
    out.mkdir()
    con = sqlite3.connect(out / "database.db")
    con.execute("create table images (name text, camera_id integer)")
    con.commit()
    con.close()
    run(rig, FROM="mapper")
    mapper = next(c for c in calls(rig) if c.startswith("mapper"))
    assert "--Mapper.snapshot_path" in mapper and "--Mapper.snapshot_frames_freq" in mapper


def test_the_run_goes_through_caffeinate_so_the_mac_cannot_sleep_mid_run(rig, tmp_path):
    fake = Path(rig["path"].split(":")[0]) / "caffeinate"
    fake.write_text(f'#!/bin/sh\necho "caffeinate $1" >> "{tmp_path}/caffeinate-calls.txt"\nshift\nexec "$@"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    run(rig)
    assert (tmp_path / "caffeinate-calls.txt").read_text().splitlines() == ["caffeinate -i"]
    assert calls(rig)[0].startswith("feature_extractor")

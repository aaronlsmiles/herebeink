"""The viewer fixture, built from scratch and loaded by Spark in headless Chromium (slow: about 5 minutes)."""
import json
import subprocess
from pathlib import Path

import pytest

import make_fixture
import schema_check

pytestmark = pytest.mark.slow
PIPELINE = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("fixture") / "fixture"
    make_fixture.build(out, log=lambda *_: None)
    return out


def test_fixture_is_small_complete_and_valid(fixture_dir):
    names = sorted(p.name for p in fixture_dir.iterdir())
    assert names == ["README.md", "coastline.json", "imagined.spz", "measured-preview.spz", "measured.spz",
                     "overlap.spz", "plan.png", "scene.json"]
    assert sum(p.stat().st_size for p in fixture_dir.iterdir()) < 5_000_000
    scene = json.loads((fixture_dir / "scene.json").read_text())
    schema_check.check(scene, "scene.schema.json")
    assert scene["alignment"]["gateAPass"] and scene["counts"]["imagined"] > 10_000
    assert scene["coastline"]["stretches"] >= 1


def test_spark_loads_every_file_with_its_matrix(fixture_dir, tmp_path):
    shot = tmp_path / "start.png"
    proc = subprocess.run(["node", str(PIPELINE / "spz" / "check_load.mjs"), str(fixture_dir), str(shot)],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    scene = json.loads((fixture_dir / "scene.json").read_text())
    assert result["errors"] == []
    for key in ("measured", "overlap", "imagined", "measuredPreview"):
        assert result["counts"][key] == scene["splats"][key]["splats"]
    assert shot.stat().st_size > 50_000


def spark(scene_dir, shot):
    proc = subprocess.run(["node", str(PIPELINE / "spz" / "check_load.mjs"), str(scene_dir), str(shot), "640", "360"],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def grey(path):
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(path).convert("L"), float)


def test_a_mirrored_marble_exports_proper_matrices_and_renders_the_same(tmp_path):
    """Raw +x left: Gate A picks the mirrored start, export bakes the mirror into the files, and Spark draws the
    same picture as from the unmirrored world. The control is the review's: the same files drawn through a
    matrix with a negative determinant, which put the hallway inside the room."""
    import numpy as np

    import splats
    import spz
    plain, mirrored = tmp_path / "plain", tmp_path / "mirrored"
    make_fixture.build(plain, log=lambda *_: None, density_measured=1000, density_marble=700)
    make_fixture.build(mirrored, log=lambda *_: None, density_measured=1000, density_marble=700, marble_mirrored=True,
                       root=tmp_path / "day")
    scene = json.loads((mirrored / "scene.json").read_text())
    assert scene["alignment"]["mirrorBaked"] and scene["alignment"]["gateAPass"]
    for f in scene["splats"].values():
        m = np.array(f["matrix"]).reshape(4, 4).T
        assert splats.similarity_problem(m) is None

    control = tmp_path / "control"
    import shutil
    shutil.copytree(mirrored, control)
    work = tmp_path / "day" / "pipeline" / "work"
    a = json.loads((work / "align" / make_fixture.WORLD_ID / "align.json").read_text())
    for key, name in (("overlap", "overlap"), ("imagined", "imagined")):
        spz.transcode([(work / "provenance" / make_fixture.WORLD_ID / f"{name}.ply", control / f"{name}.spz")])
        scene_c = json.loads((control / "scene.json").read_text())
        scene_c["splats"][key]["matrix"] = splats.column_major(np.array(a["world_from_marble"]))
        (control / "scene.json").write_text(json.dumps(scene_c))
    assert np.linalg.det(np.array(a["world_from_marble"])[:3, :3]) < 0

    shots = {}
    for name, folder in (("plain", plain), ("mirrored", mirrored), ("control", control)):
        r = spark(folder, tmp_path / f"{name}.png")
        assert r["errors"] == []
        shots[name] = grey(tmp_path / f"{name}.png")
    same = np.abs(shots["mirrored"] - shots["plain"]).mean()
    wrong = np.abs(shots["control"] - shots["plain"]).mean()
    print(f"mean grey difference: baked mirror {same:.2f}, unbaked control {wrong:.2f}")
    assert same < 2.0 and wrong > 4 * same

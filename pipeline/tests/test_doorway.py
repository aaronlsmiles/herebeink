"""The kill rule's second stage: a Marble world made at the threshold, aligned on the door frame."""
import json
import shutil

import numpy as np
import pytest

import align
import doorway
import scale
import splats
import synth_world
from colmap_model import read_model


@pytest.fixture
def doorway_day(synthetic):
    work, notes = synthetic["work"], synthetic["notes"]
    model = read_model(work / "colmap" / "sparse_txt" / "0")
    text = notes.read_text()
    keep = [ln for ln in text.splitlines() if not ln.startswith("- Door click")]
    picks = synth_world.write_doorway_world(work, "dw", 500)
    notes.write_text("\n".join(keep + synth_world.door_click_lines(model, top=True) + [picks]) + "\n")
    assert scale.main(["--work", str(work), "--notes", str(notes)]) == 0
    shutil.copy2(work / "splat" / "splat_raw.ply", work / "splat" / "measured.ply")
    return work, notes


def test_umeyama_recovers_a_similarity_and_says_when_it_needs_a_mirror():
    rng = np.random.default_rng(0)
    src = rng.normal(size=(6, 3))
    from scipy.spatial.transform import Rotation
    true = splats.sim3(1.7, Rotation.from_euler("xyz", [10, 50, -20], degrees=True).as_matrix(), [1, 2, 3])
    t = doorway.umeyama(src, splats.apply(true, src))
    assert t == pytest.approx(true, abs=1e-9)
    mirrored = true @ np.diag([-1.0, 1, 1, 1])
    t = doorway.umeyama(src, splats.apply(mirrored, src), reflect=True)
    assert t == pytest.approx(mirrored, abs=1e-9)


def test_the_doorway_world_is_aligned_on_the_frame(doorway_day):
    work, notes = doorway_day
    assert json.loads((work / "scale.json").read_text())["door"]["top"][0][1] == pytest.approx(2.0, abs=0.01)
    assert align.main(["--work", str(work), "--world", "dw", "--mode", "doorway", "--notes", str(notes)]) == 0
    r = json.loads((work / "align" / "dw" / "align.json").read_text())
    truth = synth_world.world_from_doorway_true()
    pts = np.array([[x, y, z] for x in (1.0, 3.0) for y in (0.0, 2.4) for z in (-0.5, 0.5)])
    err = np.linalg.norm(splats.apply(np.array(r["world_from_marble"]), splats.apply(splats.invert(truth), pts)) - pts, axis=1)
    assert err.max() < 0.02, err
    assert r["mode"] == "doorway" and r["gateA"]["pass"] and r["gateA"]["cornerFit"]["rmsM"] < 0.02
    assert "turned" in r["picks"]["shownAs"] or "half-turn" in r["picks"]["shownAs"]


def test_picks_off_the_splat_are_refused(doorway_day):
    work, notes = doorway_day
    text = notes.read_text().splitlines()
    notes.write_text("\n".join(ln if not ln.startswith("- Doorway corners") else
                               "- Doorway corners in the Marble world (A B E F, four 3D points): 9 9 9 ; 8 8 8 ; 7 7 7 ; 6 6 6"
                               for ln in text) + "\n")
    with pytest.raises(ValueError, match="do not sit on"):
        align.main(["--work", str(work), "--world", "dw", "--mode", "doorway", "--notes", str(notes)])


def test_the_frame_must_have_its_top_corners(synthetic):
    work, notes = synthetic["work"], synthetic["notes"]
    assert scale.main(["--work", str(work), "--notes", str(notes)]) == 0
    shutil.copy2(work / "splat" / "splat_raw.ply", work / "splat" / "measured.ply")
    synth_world.write_doorway_world(work, "dw", 300)
    with pytest.raises(ValueError, match="E and F"):
        align.main(["--work", str(work), "--world", "dw", "--mode", "doorway", "--notes", str(notes)])

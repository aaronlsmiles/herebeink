"""run_part2.sh's own flow: which stage stops where, and that the fallbacks are reachable."""
import json
import os
import subprocess
from pathlib import Path

import numpy as np

import splats
import synth_world

PIPELINE = Path(__file__).resolve().parents[1]


def stage(synthetic, name, *extra):
    env = dict(os.environ, WORK=str(synthetic["work"]), NOTES=str(synthetic["notes"]))
    return subprocess.run(["bash", "run_part2.sh", "synthworld", name, *extra], cwd=PIPELINE, capture_output=True,
                          text=True, env=env, timeout=300)


def test_scale_falls_back_to_the_supersplat_picks_when_nothing_was_clicked(synthetic):
    text = synthetic["notes"].read_text()
    c = splats.centres(splats.read(synthetic["work"] / "splat" / "splat_raw.ply", quiet=True))
    world = splats.apply(synth_world.world_from_colmap(), c)
    floor = world[:, 1] < 0.005
    picks = []
    for corner in synth_world.door_corners_world().values():
        i = np.argmin(np.linalg.norm(world[floor] - corner, axis=1))
        picks.append(c[floor][i])
    line = ("- Door points picked in the splat (two 3D points): "
            + " ; ".join(" ".join(f"{v:.5f}" for v in p) for p in picks))
    keep = [ln for ln in text.splitlines() if not ln.startswith("- Door click")]
    synthetic["notes"].write_text("\n".join(ln if not ln.startswith("- Door points picked") else line for ln in keep) + "\n")
    proc = stage(synthetic, "scale")
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-1500:]
    assert "trying the SuperSplat picks" in proc.stdout
    s = json.loads((synthetic["work"] / "scale.json").read_text())
    assert s["door"]["route"].startswith("splat picks")
    assert "box.png" in proc.stdout and (synthetic["work"] / "clean" / "box.png").exists()


def test_scale_stops_on_bad_clicks_and_goes_on_with_accept(synthetic):
    from colmap_model import read_model
    model = read_model(synthetic["work"] / "colmap" / "sparse_txt" / "0")
    text = synthetic["notes"].read_text()
    keep = [ln for ln in text.splitlines() if not ln.startswith("- Door click")]
    synthetic["notes"].write_text("\n".join(keep + synth_world.door_click_lines(model, jitter=12.0)) + "\n")
    proc = stage(synthetic, "scale")
    assert proc.returncode != 0 and "REFUSED" in proc.stdout
    assert not (synthetic["work"] / "scale.json").exists()
    proc = stage(synthetic, "scale", "--accept", "clicked again by eye, still scattered: going on to see")
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-1500:]
    assert json.loads((synthetic["work"] / "scale.json").read_text())["evidence"]["accepted"].startswith("clicked again")

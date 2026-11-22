"""The door-click page in a real browser (headless Chromium through web/'s Playwright, in a subprocess)."""
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

import door_points
import synth_world

HERE = Path(__file__).resolve().parent


def test_the_page_switches_views_and_its_lines_parse(tmp_path):
    work = tmp_path / "work"
    model = synth_world.write_colmap(work / "colmap" / "sparse_txt" / "0", work)
    first, more = door_points.candidate_views(model)
    ramp = np.tile(np.linspace(40, 220, synth_world.VIEW, dtype=np.uint8), (synth_world.VIEW, 1))
    for name in first + more:
        (work / "images" / name).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(ramp).save(work / "images" / name, quality=70)
    page = door_points.write_page(model, work)
    proc = subprocess.run(["node", str(HERE / "door_page_check.mjs"), str(page)], capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr[-2000:]
    r = json.loads(proc.stdout.strip().splitlines()[-1])
    assert r["errors"] == []
    assert r["first"] == first[0] and r["second"] == first[1] and r["third"] == more[0]
    assert r["hover"] == "100.0 200.0"
    assert r["nFirst"] == len(first) and r["nMore"] == len(more) and r["moreHidden"] and r["moreShown"]
    assert r["marks"] == 2  # both clicks in the second view are marked on it
    found = door_points.CLICK_RE.findall(r["out"])
    assert len(found) == 4 and len(r["out"].splitlines()) == 4
    got = {(lab, name): (float(u), float(v)) for lab, name, u, v in found}
    assert got == {("A", first[0]): (100.0, 200.0), ("B", first[0]): (300.0, 210.0),
                   ("B", first[1]): (310.0, 640.0), ("A", first[1]): (120.0, 600.0)}

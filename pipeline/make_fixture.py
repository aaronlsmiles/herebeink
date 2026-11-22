"""The viewer's fixture: a synthetic room and invented hallway, run through the real part 2 pipeline.

    uv run python make_fixture.py                 # -> ../web/public/fixture/ (about 2.5 MB, about 4 minutes)
    uv run python make_fixture.py --out DIR

It writes synth_world's scene into a temporary folder laid out as on the day, then runs door clicks
(made by projecting the true corners), scale.py, clean.py, align.py, provenance.py, coastline.py and
export.py on it, exactly as run_part2.sh does on real data, and copies the export. Seeds and the
timestamp are fixed, so a rerun gives the same files unless the code changed.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import align
import clean
import coastline
import export
import provenance
import scale
import synth_world

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "fixture"
DENSITY_MEASURED = 2500
DENSITY_MARBLE = 1500
WORLD_ID = "fixture"
STAMP = datetime(2026, 11, 19, tzinfo=timezone.utc)
README = """# Viewer fixture (synthetic)

Made by `pipeline/make_fixture.py`, not from any capture: a 4 m x 3.2 m box room (the "measured" splat)
and a Marble-like world of it with an invented sage-green hallway beyond the door, run through the real
alignment, provenance, coastline and export code. Every file has the shape the live scene will have;
`scene.json` follows `pipeline/schema/scene.schema.json`. Regenerate with `uv run python make_fixture.py`
in `pipeline/`.
"""


def build(out: Path, log=print, density_measured: float = DENSITY_MEASURED, density_marble: float = DENSITY_MARBLE,
          marble_mirrored: bool = False, root: Path | None = None) -> dict:
    """Build the fixture into out; root keeps the day's work folder (a temporary one otherwise)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = root or Path(tmp)
        info = synth_world.write_scene(root, density_measured, density_marble, world_id=WORLD_ID,
                                       marble_mirrored=marble_mirrored)
        work, notes = info["work"], info["notes"]
        args = ["--work", str(work), "--notes", str(notes)]
        steps = [("scale", lambda: scale.main(args))]
        for name, step in steps:
            if step() != 0:
                raise RuntimeError(f"{name} failed")
        box = clean.propose(json.loads((work / "scale.json").read_text()))
        notes.write_text(notes.read_text().replace("- Cleaning box:", clean.box_line(box)))
        for name, step in (("clean", lambda: clean.main(args + ["apply"])),
                           ("align", lambda: align.main(["--work", str(work), "--world", WORLD_ID])),
                           ("provenance", lambda: provenance.main(["--work", str(work), "--world", WORLD_ID])),
                           ("coastline", lambda: coastline.main(["--work", str(work), "--world", WORLD_ID]))):
            log(f"-- {name}")
            if step() != 0:
                raise RuntimeError(f"{name} failed")
        scene = export.export(work, WORLD_ID, work / "export" / "v1", "fixture/", None, now=STAMP)
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(work / "export" / "v1", out)
        shutil.copy2(work / "coastline.png", out / "plan.png")
    (out / "README.md").write_text(README)
    return scene


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    build(args.out)
    total = sum(p.stat().st_size for p in args.out.iterdir())
    print(f"fixture written: {args.out} ({total / 1e6:.2f} MB, {len(list(args.out.iterdir()))} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

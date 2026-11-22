"""Tag every Marble splat by its distance to the measured world: covered, overlap or imagined.

    uv run python provenance.py --world WORLD_ID [--measured-min-opacity 0.2]
                                                     # -> work/provenance/<id>/overlap.ply, imagined.ply, counts.json

d = the distance from a Marble centre (aligned, world frame) to the nearest measured centre.
Covered (d < 0.15 m) is dropped: the photograph already shows it. Overlap (0.15 m to 0.50 m) is drawn
half and half. Imagined (0.50 m and beyond) is the ink. The files keep Marble's own frame and every
attribute; the viewer places them with align.json's matrix.

The doorway past the door plane is sealed (door_edge.py): measured splats there are left out of the
distances, and every Marble splat there is imagined, whatever its distance, so the ink meets the frame.
Past the plane beside the opening, nothing is overlap either: Marble's twin of the jamb stays covered
(the photographed jamb shows), and the rest is ink.

--measured-min-opacity (off by default) leaves measured splats fainter than the floor out of the
distances, for when fog trained beyond the doorway would mark Marble's hallway "covered". It is for the
split and the coastline only; the frozen residual (align.py) always uses every measured splat.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

import door_edge
import splats

COVERED_M = 0.15
OVERLAP_M = 0.50


def split(measured_world: np.ndarray, marble_world: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    d, _ = cKDTree(measured_world).query(marble_world, workers=-1)
    return d, (d >= COVERED_M) & (d < OVERLAP_M), d >= OVERLAP_M


def sealed_split(measured_world: np.ndarray, marble_world: np.ndarray, scale: dict):
    """split() with the doorway sealed: (d, overlap, imagined, counts of what the seal changed)."""
    keep = ~door_edge.sealed(measured_world, scale)
    seal = door_edge.sealed(marble_world, scale)
    d, overlap, imagined = split(measured_world[keep], marble_world)
    # Past the plane nothing is half and half: what is not the frame's own twin (covered) is ink.
    past = door_edge.past_plane(marble_world, scale) & overlap & ~seal
    return d, overlap & ~seal & ~past, imagined | seal | past, {
        "measuredTrimmed": int((~keep).sum()), "marbleSealed": int(seal.sum()), "overlapPastPlane": int(past.sum())}


def opaque(opacity: np.ndarray, floor: float | None) -> np.ndarray:
    """Which measured splats count as measured for the split and the coastline (all, unless a floor is set)."""
    return np.ones(len(opacity), bool) if floor is None else opacity >= floor


def measured_world(work: Path, scale: dict, min_opacity: float | None = None) -> np.ndarray:
    ply = splats.read(work / "splat" / "measured.ply")
    world = splats.apply(np.array(scale["world_from_colmap"]), splats.centres(ply))
    if min_opacity is None:
        return world
    keep = opaque(splats.opacity(ply), min_opacity)
    print(f"measured splats at opacity {min_opacity} or more: {keep.sum()} of {len(keep)}")
    return world[keep]


def run(work: Path, world_id: str, min_opacity: float | None = None) -> dict:
    scale = json.loads((work / "scale.json").read_text())
    align = json.loads((work / "align" / world_id / "align.json").read_text())
    measured = measured_world(work, scale, min_opacity)
    marble = splats.read(work / "marble" / f"marble_{world_id}.ply")
    world = splats.apply(np.array(align["world_from_marble"]), splats.centres(marble))
    d, overlap, imagined, seal = sealed_split(measured, world, scale)
    out = work / "provenance" / world_id
    n_overlap = splats.write_subset(marble, overlap, out / "overlap.ply")
    n_imagined = splats.write_subset(marble, imagined, out / "imagined.ply")
    counts = {"marble": int(len(d)), "covered": int(len(d) - n_overlap - n_imagined), "overlap": n_overlap,
              "imagined": n_imagined, "measured": int(len(measured)) - seal["measuredTrimmed"],
              "radiiM": {"covered": COVERED_M, "overlap": OVERLAP_M}, "sealed": seal}
    if min_opacity is not None:
        counts["measuredMinOpacity"] = min_opacity
    (out / "counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--world", required=True)
    ap.add_argument("--measured-min-opacity", type=float, default=None,
                    help="leave fainter measured splats out (fog beyond the doorway); off by default, never in the residual")
    args = ap.parse_args(argv)
    c = run(args.work, args.world, args.measured_min_opacity)
    share = lambda k: 100 * c[k] / c["marble"]  # noqa: E731
    print(f"Marble splats: {c['marble']}; covered (dropped) {c['covered']} ({share('covered'):.1f} %), "
          f"overlap {c['overlap']} ({share('overlap'):.1f} %), imagined {c['imagined']} ({share('imagined'):.1f} %)")
    print(f"measured splats: {c['measured']}; radii {COVERED_M} m and {OVERLAP_M} m")
    print(f"doorway sealed: {c['sealed']['measuredTrimmed']} measured splats trimmed past the door plane, "
          f"{c['sealed']['marbleSealed']} Marble splats there drawn as imagined, "
          f"{c['sealed']['overlapPastPlane']} overlap splats beside it moved to imagined")
    print(f"written: {args.work / 'provenance' / args.world}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

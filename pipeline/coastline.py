"""Where the measured floor ends and Marble's carries on: work/coastline.json, work/floor.json, a plan view.

    uv run python coastline.py --world WORLD_ID [--measured-min-opacity 0.2]

On a 10 cm floor grid in the world frame: a cell is covered when a measured centre lies in it between
5 cm below the floor and 0.5 m above it (the floor and what stands on it). The covered mask is closed
(3 x 3), its holes are filled (a dark rug or a patch the splat missed is still measured floor, and would
otherwise come out as a ring of coastline mid-room), and its outline is traced with marching squares.
A piece of outline is coastline only where Marble's floor carries on beyond it for at least the overlap
radius (0.5 m), the outline is not on the edge of both worlds together, and no measured wall stands on it
(centres 0.3 to 1.5 m up within a cell): a Marble wall set a little further out leaves a thin strip of
Marble floor nobody could walk on to, and a garden Marble imagines through a window lies behind a wall.
Only solid measured splats (opacity 0.2 or more, when opacities are given) count as a wall: a trained splat
is mostly near-transparent haze in the air it saw, which marks the floor as measured but stands nowhere.
A stretch that passes runs on along the outline, past the wall tolerance, until a wall or the end of
Marble's floor stops it, so a narrow doorway's line reaches from jamb to jamb.
Each stretch is smoothed with two rounds of Chaikin; stretches under 0.5 m are dropped.

The walkable floor for the viewer is the head pass's path dilated by 0.5 m plus Marble's floor, holes
filled, kept to the part joined to the path and to within 3 m of the measured floor.

--measured-min-opacity (off by default) leaves measured splats fainter than the floor out of the covered
mask, for when fog beyond the doorway would otherwise mark the hallway as measured. It never touches the
frozen residual, which align.py computes over every splat.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

import grid2d
import plots
import splats
from provenance import COVERED_M, OVERLAP_M, measured_world, opaque  # noqa: F401

GRID_M = 0.10
FLOOR_BAND_M = 0.5
# the fitted floor is only flat to a few millimetres, so the band reaches the under-floor cut clean.py makes
MEASURED_FLOOR_BAND_M = (-0.05, FLOOR_BAND_M)
MARBLE_FLOOR_BAND_M = (-0.1, FLOOR_BAND_M)
# The narrowest standard internal door leaf is 610 mm, so a gap anyone could walk through is never under
# about 0.55 m; a shorter stretch is a notch from a defect, and the smoothing trims a little off each end.
MIN_STRETCH_M = 0.5
CARRY_ON_M = OVERLAP_M
# Marble's world goes on to the edge of what it generated, far past anything worth walking to; the walk is
# kept within this of the measured floor, which covers the invented hallway and the film's path through it.
WALK_BEYOND_MEASURED_M = 3.0
# Marble's walls never sit exactly on the measured ones, so a stretch along a wall can look as if Marble's
# floor carried on past it by a cell or two; a stretch counts only where Marble's floor goes on for more
WALL_TOLERANCE_CELLS = 2
# A trained splat (MCMC above all) is mostly near-transparent haze filling the air the cameras saw; only a
# splat this solid draws a surface, so only these stand as walls.
SOLID_OPACITY = 0.2
WALK_DILATE_M = 0.5
PX_PER_M = 100


def floor_band(world: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return world[(world[:, 1] >= lo) & (world[:, 1] <= hi)][:, [0, 2]]


def carries_on(m: np.ndarray, covered: np.ndarray, marble_floor: np.ndarray, cells: int) -> bool:
    """From an outline point (row, col at half cells), does Marble's floor go on outwards for `cells` cells?"""
    nz, nx = covered.shape
    block = [(int(np.floor(m[0])), int(np.floor(m[1]))), (int(np.floor(m[0])), int(np.ceil(m[1]))),
             (int(np.ceil(m[0])), int(np.floor(m[1]))), (int(np.ceil(m[0])), int(np.ceil(m[1])))]
    if not all(0 <= r < nz and 0 <= c < nx for r, c in block):
        return False
    inside = np.array([rc for rc in block if covered[rc]], float)
    outside = np.array([rc for rc in block if not covered[rc]], float)
    if not len(inside) or not len(outside):
        return False
    normal = outside.mean(axis=0) - inside.mean(axis=0)
    normal /= np.linalg.norm(normal)
    for k in range(1, cells + 1):
        r, c = np.round(m + normal * k).astype(int)
        if not (0 <= r < nz and 0 <= c < nx and marble_floor[r, c]):
            return False
    return True


def grow(segs: np.ndarray, keep: np.ndarray, clear: np.ndarray) -> np.ndarray:
    """Run each kept stretch on along the outline over clear segments (no wall, Marble's floor carries on) that
    the wall tolerance alone ruled out: without it a 0.72 m doorway loses 20 cm at each jamb and drops under
    the shortest stretch."""
    def key(p):
        return int(round(float(p[0]) * 4)), int(round(float(p[1]) * 4))

    ends: dict[tuple[int, int], list[int]] = {}
    for i, (a, b) in enumerate(segs):
        for p in (a, b):
            ends.setdefault(key(p), []).append(i)
    keep = keep.copy()
    frontier = list(np.flatnonzero(keep))
    while frontier:
        for p in segs[frontier.pop()]:
            for j in ends[key(p)]:
                if clear[j] and not keep[j]:
                    keep[j] = True
                    frontier.append(j)
    return keep


def trace(measured_world: np.ndarray, marble_world: np.ndarray, walk_path_xz: np.ndarray,
          measured_opacity: np.ndarray | None = None) -> dict:
    meas = floor_band(measured_world, *MEASURED_FLOOR_BAND_M)
    marb = floor_band(marble_world, *MARBLE_FLOOR_BAND_M)
    both = np.vstack([np.percentile(np.vstack([meas, marb]), q, axis=0) for q in (0.1, 99.9)])
    grid = grid2d.Grid.around(both, GRID_M)
    covered = ndimage.binary_fill_holes(grid2d.close(grid.occupancy(meas)))
    marble_floor = grid.occupancy(marb)
    union = grid2d.close(covered | marble_floor)
    core = ndimage.binary_erosion(union, structure=np.ones((3, 3)), iterations=WALL_TOLERANCE_CELLS, border_value=0)
    marble_closed = grid2d.close(marble_floor)
    cells = int(np.ceil(CARRY_ON_M / GRID_M))
    solid = measured_world if measured_opacity is None else measured_world[measured_opacity >= SOLID_OPACITY]
    wall = grid.occupancy(plots.band(solid)[:, [0, 2]])

    segs = grid2d.contour_segments(covered)
    keep, clear = [], []
    for a, b in segs:
        m = (a + b) / 2
        block = [(int(np.floor(m[0])), int(np.floor(m[1]))), (int(np.ceil(m[0])), int(np.ceil(m[1]))),
                 (int(np.floor(m[0])), int(np.ceil(m[1]))), (int(np.ceil(m[0])), int(np.floor(m[1])))]
        ok = all(0 <= r < grid.nz and 0 <= c < grid.nx and not wall[r, c] for r, c in block) and carries_on(
            m, covered, marble_closed, cells)
        clear.append(ok)
        keep.append(ok and all(core[r, c] for r, c in block))
    if len(segs):
        keep = grow(segs, np.array(keep, bool), np.array(clear, bool))
    lines = []
    for pts, closed in grid2d.link(segs[np.array(keep, bool)] if len(segs) else segs):
        xz = grid2d.chaikin(grid.to_world(pts), closed)
        length = float(np.linalg.norm(np.diff(xz, axis=0), axis=1).sum())
        if length >= MIN_STRETCH_M:
            lines.append((xz, closed, length))

    path = grid.disks(walk_path_xz, WALK_DILATE_M)
    walk = ndimage.binary_fill_holes(grid2d.close(path | marble_floor))
    walk &= ndimage.distance_transform_edt(~covered) * GRID_M <= WALK_BEYOND_MEASURED_M
    parts, _ = ndimage.label(walk)
    joined = np.setdiff1d(np.unique(parts[path & walk]), [0])
    walk = np.isin(parts, joined)
    return {"grid": grid, "covered": covered, "marble_floor": marble_floor, "lines": lines,
            "walkable": grid2d.polygons(grid, walk)}


def plan_size(grid: grid2d.Grid) -> tuple[int, int]:
    return max(900, int(grid.nx * GRID_M * PX_PER_M) + 20), int(grid.nz * GRID_M * PX_PER_M) + 100


def plan_panel(grid: grid2d.Grid, width: int) -> plots.Panel:
    w, h = plan_size(grid)
    return plots.Panel((10, 40, w - 10, h - 60), (grid.x0, grid.z0), (grid.x0 + grid.nx * GRID_M, grid.z0 + grid.nz * GRID_M), top=True)


def plan_view(path: Path, grid: grid2d.Grid, measured_world: np.ndarray, overlap_world: np.ndarray,
              imagined_world: np.ndarray, lines: list, door: dict | None = None, pano=None) -> Path:
    """The plan from above (x right, z down the page), walls and furniture 0.3 to 1.5 m up, and the coastline."""
    w, h = plan_size(grid)
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    panel = plan_panel(grid, w)
    for pts, colour in ((imagined_world, (120, 150, 120)), (overlap_world, (180, 160, 110)), (measured_world, (90, 90, 90))):
        if len(pts):
            panel.points(draw, plots.thin(plots.band(pts), 60000)[:, [0, 2]], colour)
    for xz, closed, _ in lines:
        p = [tuple(q) for q in panel.px(xz)]
        draw.line(p + ([p[0]] if closed else []), fill=(10, 10, 10), width=4)
    font = ImageFont.load_default(size=16)
    if door is not None:
        start = np.asarray(pano)[[0, 2]] if pano is not None else np.zeros(2)
        panel.arrow(draw, start, np.asarray(door["centre"])[[0, 2]], "door", font)
    panel.axes(draw, font)
    draw.text((10, 10), "plan view from above: x right, z down the page; 0.3 to 1.5 m above the floor", fill=(0, 0, 0), font=font)
    draw.text((10, h - 40), "measured grey, overlap tan, imagined green, coastline black; 1 m = "
              f"{PX_PER_M} px", fill=(0, 0, 0), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def run(work: Path, world_id: str, min_opacity: float | None = None) -> dict:
    scale = json.loads((work / "scale.json").read_text())
    align = json.loads((work / "align" / world_id / "align.json").read_text())
    w_from_c, w_from_m = np.array(scale["world_from_colmap"]), np.array(align["world_from_marble"])
    ply = splats.read(work / "splat" / "measured.ply")
    op = splats.opacity(ply)
    keep = opaque(op, min_opacity)
    if min_opacity is not None:
        print(f"measured splats at opacity {min_opacity} or more: {keep.sum()} of {len(keep)}")
    measured, measured_op = splats.apply(w_from_c, splats.centres(ply))[keep], op[keep]
    marble = splats.apply(w_from_m, splats.centres(splats.read(work / "marble" / f"marble_{world_id}.ply")))
    r = trace(measured, marble, np.array(scale["walk_path_xz"]), measured_opacity=measured_op)
    g = r["grid"]
    coast = {"schemaVersion": 1, "units": "m", "frame": "world: floor y = 0, +y up",
             "gridM": GRID_M, "floorBandM": FLOOR_BAND_M, "radiiM": {"covered": COVERED_M, "overlap": OVERLAP_M},
             "gridOrigin": [g.x0, g.z0], "gridShape": [g.nz, g.nx],
             "polylines": [{"closed": closed, "points": [[round(float(x), 4), round(float(z), 4)] for x, z in xz]}
                           for xz, closed, _ in r["lines"]],
             "lengthM": round(sum(length for *_, length in r["lines"]), 3)}
    (work / "coastline.json").write_text(json.dumps(coast, indent=1, allow_nan=False) + "\n")
    (work / "floor.json").write_text(json.dumps({"walkable": r["walkable"], "dilationM": WALK_DILATE_M}, indent=1,
                                                allow_nan=False) + "\n")
    prov = work / "provenance" / world_id
    sheet = plan_view(work / "coastline.png", g, measured[measured_op >= SOLID_OPACITY],
                      splats.apply(w_from_m, splats.centres(splats.read(prov / "overlap.ply"))),
                      splats.apply(w_from_m, splats.centres(splats.read(prov / "imagined.ply"))), r["lines"],
                      scale["door"], scale.get("pano"))
    return {"coastline": coast, "walkable": len(r["walkable"]), "plan": str(sheet)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--world", required=True)
    ap.add_argument("--measured-min-opacity", type=float, default=None,
                    help="leave fainter measured splats out of the covered mask (fog beyond the doorway); off by default")
    args = ap.parse_args(argv)
    r = run(args.work, args.world, args.measured_min_opacity)
    c = r["coastline"]
    print(f"coastline: {len(c['polylines'])} stretch(es), {c['lengthM']:.2f} m in all, on a {c['gridM'] * 100:.0f} cm grid")
    print(f"walkable outlines: {r['walkable']}; plan view: {r['plan']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

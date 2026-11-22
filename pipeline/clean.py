"""The scripted half of cleaning the trained splat: a box crop and the under-floor cut -> work/splat/measured.ply.

    uv run python clean.py propose             # prints the NOTES.md line for a box round the room and the doorway,
                                               # and draws it over the raw splat: work/clean/box.png
    uv run python clean.py apply               # crops splat_raw.ply to that box -> measured.ply
    uv run python clean.py adopt FILE.ply      # takes a SuperSplat export as measured.ply, after checking it

The box is in world metres (scale.py's frame) on the template's line, six numbers, min then max per axis:

    - Cleaning box: -2.80 3.10 -0.05 3.20 -2.40 2.40

The proposed box is the union of the cameras' extent plus 1 m and the walls' extent (the 2nd to 98th
percentile of centres 0.3 to 2.0 m up, which scale.py records) plus 0.3 m, and 1.5 m beyond the doorway:
the cameras alone miss walls behind a bed or a wardrobe when the passes kept to the middle of the room.
Look at box.png before pasting the line.

Splats are kept or dropped whole; their attributes and frame never change. Anything more than 5 cm
under the floor goes whatever the box says. SuperSplat is for the floaters a box cannot reach: open
measured.ply there, delete them, export as uncompressed PLY without moving the model, and adopt the
export, which must be a subset of measured.ply, splat for splat; the auto crop stays as measured_auto.ply.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial import cKDTree

import plots
import splats

BOX_RE = re.compile(r"^- Cleaning box:[ \t]*" + r"[ \t]+".join([r"([-0-9.]+)"] * 6) + r"[ \t]*$", re.M)
UNDER_FLOOR_M = 0.05
ROOM_MARGIN_M = 1.0
BEYOND_DOOR_M = 1.5
CEILING_MARGIN_M = 1.2
WALL_MARGIN_M = 0.3  # the 2-98 % extent sits just inside the walls


def propose(scale: dict) -> list[float]:
    cams = np.array(scale["room_cameras_xz"])
    lo, hi = cams.min(axis=0) - ROOM_MARGIN_M, cams.max(axis=0) + ROOM_MARGIN_M
    if scale.get("wall_band_xz"):
        band = np.array(scale["wall_band_xz"])
        lo, hi = np.minimum(lo, band[0] - WALL_MARGIN_M), np.maximum(hi, band[1] + WALL_MARGIN_M)
    door = scale["door"]
    centre, out = np.array(door["centre"]), np.array(door["outward"])
    half = abs(np.array(door["a"]) - np.array(door["b"]))[[0, 2]] / 2 + 0.5
    far = centre[[0, 2]] + out[[0, 2]] * BEYOND_DOOR_M
    lo = np.minimum(lo, np.minimum(far - half, centre[[0, 2]] - half))
    hi = np.maximum(hi, np.maximum(far + half, centre[[0, 2]] + half))
    top = max(scale["camera_heights_m"].values()) + CEILING_MARGIN_M
    return [round(float(v), 2) for v in (lo[0], hi[0], -UNDER_FLOOR_M, top, lo[1], hi[1])]


def draw_box(path: Path, world: np.ndarray, box: list[float], scale: dict) -> Path:
    """The proposed box from above over the raw splat, for a person to check before it is used."""
    x0, x1, _, _, z0, z1 = box
    pts = plots.thin(world, 120000)
    lo = np.minimum(np.percentile(pts[:, [0, 2]], 0.5, axis=0), [x0, z0]) - 0.5
    hi = np.maximum(np.percentile(pts[:, [0, 2]], 99.5, axis=0), [x1, z1]) + 0.5
    img = Image.new("RGB", (1000, 860), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=16)
    panel = plots.Panel((10, 40, 990, 820), lo, hi, top=True)
    panel.points(draw, pts[(pts[:, 1] > 0.05) & (pts[:, 1] < 2.0)][:, [0, 2]], (150, 150, 150))
    panel.points(draw, plots.band(pts)[:, [0, 2]], (40, 40, 40))
    (u0, v0), (u1, v1) = panel.px(np.array([[x0, z0], [x1, z1]]))
    draw.rectangle((u0, v0, u1, v1), outline=(200, 30, 30), width=3)
    for x, z in scale.get("room_cameras_xz", []):
        u, v = panel.px(np.array([[x, z]]))[0]
        draw.ellipse((u - 3, v - 3, u + 3, v + 3), fill=(30, 90, 200))
    panel.arrow(draw, np.array(scale["pano"])[[0, 2]] if "pano" in scale else np.zeros(2),
                np.array(scale["door"]["centre"])[[0, 2]], "door", font)
    panel.axes(draw, font)
    draw.text((10, 10), "proposed cleaning box (red) from above: raw splat 5 cm to 2 m up grey, 0.3 to 1.5 m dark, cameras blue",
              fill=(0, 0, 0), font=font)
    draw.text((10, 830), "Every wall must lie inside the red box; widen the line in NOTES.md if one does not.",
              fill=(0, 0, 0), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def box_line(box: list[float]) -> str:
    return "- Cleaning box: " + " ".join(f"{v:.2f}" for v in box)


def read_box(notes: str) -> list[float]:
    m = BOX_RE.search(notes)
    if not m:
        raise ValueError("no '- Cleaning box:' line with six numbers in NOTES.md; run clean.py propose")
    return [float(v) for v in m.groups()]


def inside(box: list[float], world: np.ndarray) -> np.ndarray:
    x0, x1, y0, y1, z0, z1 = box
    y0 = max(y0, -UNDER_FLOOR_M)
    return ((world[:, 0] >= x0) & (world[:, 0] <= x1) & (world[:, 1] >= y0) & (world[:, 1] <= y1)
            & (world[:, 2] >= z0) & (world[:, 2] <= z1))


def apply(src: Path, dest: Path, box: list[float], world_from_colmap: np.ndarray) -> tuple[int, int]:
    ply = splats.read(src)
    keep = inside(box, splats.apply(world_from_colmap, splats.centres(ply)))
    kept = splats.write_subset(ply, keep, dest)
    return kept, len(keep)


def check_subset(candidate: Path, reference: Path, tol: float = 1e-4) -> tuple[int, float]:
    """A SuperSplat export must keep its splats exactly where measured.ply had them."""
    ref = splats.centres(splats.read(reference))
    cand = splats.read(candidate)
    names = cand["vertex"].data.dtype.names
    for need in ("x", "y", "z", "opacity", "scale_0", "rot_0", "f_dc_0"):
        if need not in names:
            raise ValueError(f"{candidate.name} has no '{need}': export from SuperSplat as uncompressed PLY")
    d, _ = cKDTree(ref).query(splats.centres(cand), workers=-1)
    scale = np.ptp(ref, axis=0).max()
    if d.max() > tol * scale:
        raise ValueError(f"{candidate.name} is not a subset of {reference.name} (a splat moved by {d.max():.4g} units): "
                         "was the model moved or rotated in SuperSplat? Export again without moving it")
    return len(d), float(d.max())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--notes", type=Path, default=Path("../capture/NOTES.md"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("propose")
    sub.add_parser("apply")
    ad = sub.add_parser("adopt")
    ad.add_argument("ply", type=Path)
    args = ap.parse_args(argv)
    scale = json.loads((args.work / "scale.json").read_text())
    splat_dir = args.work / "splat"
    if args.cmd == "propose":
        box = propose(scale)
        world = splats.apply(np.array(scale["world_from_colmap"]), splats.centres(splats.read(splat_dir / "splat_raw.ply")))
        pic = draw_box(args.work / "clean" / "box.png", world, box, scale)
        print(f"look at {pic}: every wall must be inside the red box. Then paste into capture/NOTES.md under 'Later' "
              "(edit it if the room needs more or less):")
        print(box_line(box))
        return 0
    if args.cmd == "apply":
        box = read_box(args.notes.read_text())
        kept, total = apply(splat_dir / "splat_raw.ply", splat_dir / "measured.ply", box, np.array(scale["world_from_colmap"]))
        shutil.copy2(splat_dir / "measured.ply", splat_dir / "measured_auto.ply")
        print(f"measured.ply: kept {kept} of {total} splats ({total - kept} outside the box or under the floor)")
        return 0
    n, worst = check_subset(args.ply, splat_dir / "measured_auto.ply")
    shutil.copy2(args.ply, splat_dir / "measured.ply")
    print(f"adopted {args.ply.name}: {n} splats, all where measured_auto.ply had them (worst {worst:.2g} units)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

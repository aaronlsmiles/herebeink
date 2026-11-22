"""The nested flat-view sets for Part 2's evidence ladder, cut from the pano still Marble got in Part 1.

    uv run python ladder_views.py cut      # work/ladder/views/az<AAA>.png and manifest.json
    uv run python ladder_views.py sheet    # work/ladder/views/contact.jpg, to look at before any upload

Eight pinhole views at pano yaw d + 45 deg * k, where d is the yaw, in the pano image's own convention
(views.py's: positive turns right), of the door seen from the pano camera. A view's azimuth is its angle
from d, positive to the right, which is what Marble's quickstart calls 0 front, 90 right, 180 back,
270 left. The rungs are nested: R1 is the door alone and R8 is all eight.

d comes from the Part 1 outputs: the COLMAP pose of the rig's pano reference view (the pano pass was
cut from pano.masked.jpg; pano-auto.masked.jpg is the same stand position and stitch, and a circular
cross-correlation of the two shows no yaw shift) and scale.json's door corners in the measured world.

The manifest is what Task 1.1's upload guard binds to: it names the source and each view by SHA-256 and
holds `views_clean`, which stays null until a person has looked at contact.jpg and writes a dated yes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial.transform import Rotation

import views

ROOT = Path(__file__).resolve().parent.parent
SOURCE_REL = "capture/stitched/pano-auto.masked.jpg"
SIDECAR_REL = "pipeline/work/marble/pano-auto_2560.json"
LADDER_REL = "pipeline/work/ladder/views"

H_FOV_DEG = 66.0
SIZE = (1024, 768)
# Square pixels: the vertical field of view follows from the horizontal one and the aspect.
V_FOV_DEG = float(np.degrees(2 * np.arctan(np.tan(np.radians(H_FOV_DEG / 2)) * SIZE[1] / SIZE[0])))
STEP_DEG = 45
AZIMUTHS = tuple(range(0, 360, STEP_DEG))
RUNGS = {"R1": (0,), "R2": (0, 180), "R4": (0, 90, 180, 270), "R8": AZIMUTHS}

SHEET_TILE = (512, 384)
SHEET_LABEL_H = 44
SHEET_COLS = 4


class LadderError(Exception):
    pass


def view_file_name(azimuth: int) -> str:
    return f"az{azimuth:03d}.png"


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- the source ----

def check_source(root: Path) -> tuple[Path, str, str]:
    """The still must be byte-for-byte the one prepare-pano made Marble's pano from."""
    src = root / SOURCE_REL
    side = root / SIDECAR_REL
    if not src.is_file():
        raise LadderError(f"{SOURCE_REL} not found")
    if not side.is_file():
        raise LadderError(f"the Marble sidecar {SIDECAR_REL} is missing, so the source cannot be checked")
    want = json.loads(side.read_text()).get("source_sha256")
    got = _sha256(src)
    if got != want:
        raise LadderError(f"{SOURCE_REL} (sha256 {got[:8]}...) is not the still the sidecar names "
                          f"({str(want)[:8]}...): the views would not be what Marble's pano was cut from")
    return src, got, want


# ---- where the door is ----

def rig_direction(point_world, world_from_colmap, cam_from_model, centre_colmap) -> np.ndarray:
    """Unit direction, in the pano rig frame (x right, y down, z forward), from the camera centre to a
    point in the measured world frame."""
    m = np.asarray(world_from_colmap, float)
    p = np.linalg.solve(m[:3, :3], np.asarray(point_world, float) - m[:3, 3])
    v = np.asarray(cam_from_model, float) @ (p - np.asarray(centre_colmap, float))
    return v / np.linalg.norm(v)


def lon_lat(v) -> tuple[float, float]:
    """Rig-frame direction -> (yaw, pitch) in degrees, the equirect's own: lon from +z towards +x, lat up."""
    v = np.asarray(v, float)
    return float(np.degrees(np.arctan2(v[0], v[2]))), float(np.degrees(np.arcsin(np.clip(-v[1], -1, 1))))


def door_direction(scale: dict, world_from_colmap, cam_from_model, centre_colmap) -> dict:
    d = scale["door"]
    corners = [d["a"], d["b"], d["top"][1], d["top"][0]]
    centre = np.mean([d["a"], d["b"], d["top"][0], d["top"][1]], axis=0)

    def ll(pt):
        lon, lat = lon_lat(rig_direction(pt, world_from_colmap, cam_from_model, centre_colmap))
        return {"lon": round(lon, 4), "lat": round(lat, 4)}

    c = ll(centre)
    return {"yaw_deg": c["lon"], "pitch_deg": c["lat"], "centre": c, "corners": [ll(p) for p in corners],
            "from": "scale.json door corners (mean of the four) seen from the COLMAP pose of "
                    "rig/y000p00/5pano_0000.jpg"}


def door_from_work(work: Path) -> dict:
    from answer_key import centre_of
    from colmap_model import read_model

    scale = json.loads((work / "scale.json").read_text())
    model = read_model(work / "colmap" / "sparse_txt" / "0")
    img = next((i for i in model.images.values() if i.name == "rig/y000p00/5pano_0000.jpg"), None)
    if img is None:
        raise LadderError("the COLMAP model has no rig/y000p00/5pano_0000.jpg: the pano's pose is unknown")
    r = Rotation.from_quat(img.qvec, scalar_first=True).as_matrix()
    return door_direction(scale, np.array(scale["world_from_colmap"], float), r, centre_of(img))


# ---- the cut ----

def project(lon_lat_deg: dict, yaw: float, pitch: float = 0.0) -> tuple[float, float] | None:
    """Where a pano direction lands in the view cut at (yaw, pitch), in pixels, or None if outside it."""
    lon, lat = np.radians(lon_lat_deg["lon"]), np.radians(lon_lat_deg["lat"])
    d = np.array([np.cos(lat) * np.sin(lon), -np.sin(lat), np.cos(lat) * np.cos(lon)])
    p = (Rotation.from_euler("x", -pitch, degrees=True) * Rotation.from_euler("y", -yaw, degrees=True)).as_matrix() @ d
    if p[2] <= 1e-9:
        return None
    w, h = SIZE
    fx = (w / 2) / np.tan(np.radians(H_FOV_DEG / 2))
    fy = (h / 2) / np.tan(np.radians(V_FOV_DEG / 2))
    return float(fx * p[0] / p[2] + w / 2), float(fy * p[1] / p[2] + h / 2)


def cut_view(source: Path, out: Path, yaw: float) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    flt = views.v360_flat_filter(yaw, 0, H_FOV_DEG, V_FOV_DEG, *SIZE)
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-vf", flt, "-frames:v", "1",
                        "-map_metadata", "-1", str(out)], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise LadderError(f"ffmpeg failed on {source.name}: {e.stderr.strip()}") from None


def cut(root: Path = ROOT, work: Path | None = None, door: dict | None = None) -> dict:
    work = work or root / "pipeline" / "work"
    source, digest, sidecar_digest = check_source(root)
    door = door or door_from_work(work)
    d = float(door["yaw_deg"])
    out_dir = work / "ladder" / "views"
    rel_dir = out_dir.relative_to(root).as_posix()
    entries = []
    for az in AZIMUTHS:
        yaw = views.wrap_yaw(d + az)
        f = out_dir / view_file_name(az)
        cut_view(source, f, yaw)
        entries.append({"azimuth": az, "file": f"{rel_dir}/{f.name}", "sha256": _sha256(f),
                        "pano_yaw_deg": round(float(yaw), 4)})
    by_az = {e["azimuth"]: e["file"] for e in entries}
    manifest = {
        "source": SOURCE_REL, "source_sha256": digest, "sidecar": SIDECAR_REL, "sidecar_source_sha256": sidecar_digest,
        "d_yaw_deg": round(d, 4), "door": door,
        "fov_deg": {"h": H_FOV_DEG, "v": round(V_FOV_DEG, 4)}, "size": list(SIZE), "pitch_deg": 0,
        "azimuth_convention": "degrees from d, positive to the right: 0 front (the door), 90 right, 180 back, 270 left",
        "views": entries,
        "rungs": {name: [by_az[a] for a in azs] for name, azs in RUNGS.items()},
        "views_clean": None,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify_manifest(path: Path, root: Path = ROOT) -> dict:
    """Every file the manifest names must still hash to what it recorded, source included."""
    manifest = json.loads(Path(path).read_text())
    src = root / manifest["source"]
    if not src.is_file() or _sha256(src) != manifest["source_sha256"]:
        raise LadderError("the source still has changed since the views were cut")
    for v in manifest["views"]:
        f = root / v["file"]
        if not f.is_file() or _sha256(f) != v["sha256"]:
            raise LadderError(f"{Path(v['file']).stem} has changed since the manifest was written")
    return manifest


# ---- the sheet ----

def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def make_sheet(root: Path = ROOT) -> Path:
    manifest_path = root / LADDER_REL / "manifest.json"
    manifest = verify_manifest(manifest_path, root)
    tw, th = SHEET_TILE
    rows = (len(manifest["views"]) + SHEET_COLS - 1) // SHEET_COLS
    sheet = Image.new("RGB", (SHEET_COLS * tw, rows * (th + SHEET_LABEL_H)), (40, 40, 40))
    door = manifest["door"]
    sx = tw / SIZE[0]
    for i, v in enumerate(manifest["views"]):
        x0, y0 = (i % SHEET_COLS) * tw, (i // SHEET_COLS) * (th + SHEET_LABEL_H)
        tile = Image.open(root / v["file"]).convert("RGB").resize((tw, th), Image.LANCZOS)
        draw = ImageDraw.Draw(tile)
        if v["azimuth"] == 0:
            pts = [project(c, v["pano_yaw_deg"]) for c in door["corners"]]
            if all(pts):
                draw.polygon([(x * sx, y * sx) for x, y in pts], outline=(255, 40, 40), width=2)
            c = project(door["centre"], v["pano_yaw_deg"])
            if c:
                cx, cy = c[0] * sx, c[1] * sx
                draw.line([(cx - 14, cy), (cx + 14, cy)], fill=(255, 40, 40), width=2)
                draw.line([(cx, cy - 14), (cx, cy + 14)], fill=(255, 40, 40), width=2)
            mid = tw / 2
            draw.line([(mid, 0), (mid, 10)], fill=(255, 255, 0), width=2)
        sheet.paste(tile, (x0, y0 + SHEET_LABEL_H))
        rungs = ", ".join(n for n, f in manifest["rungs"].items() if v["file"] in f)
        label = ImageDraw.Draw(sheet)
        label.text((x0 + 6, y0 + 2), f"az{v['azimuth']:03d}  (pano yaw {v['pano_yaw_deg']:.1f})", fill="white", font=_font(18))
        label.text((x0 + 6, y0 + 23), rungs, fill=(255, 210, 90), font=_font(16))
    out = root / LADDER_REL / "contact.jpg"
    sheet.save(out, quality=92)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["cut", "sheet"])
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    try:
        if a.command == "cut":
            m = cut(a.root)
            print(f"d = {m['d_yaw_deg']:.3f} deg (door centre pitch {m['door']['pitch_deg']:.2f} deg)")
            print(f"cut {len(m['views'])} views to {LADDER_REL}/; manifest.json written, views_clean is null")
        else:
            print(make_sheet(a.root))
    except LadderError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

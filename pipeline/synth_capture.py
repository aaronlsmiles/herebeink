"""A fake capture folder from a textured box room, for the COLMAP smoke test and for rehearsing the runbook.

    uv run python synth_capture.py /tmp/rehearsal/capture

It writes what the real capture day writes (four stitched passes, the pano still, phone stills,
NOTES.md filled in), small: equirect frames of 1024 x 512, each position held for two seconds, so a
pass lasts about 24 s. The room is 4 m x 3.2 m x 2.5 m with two blocks in it; every face has its own
seeded texture, so SIFT has something to find and nothing repeats along a wall.
World frame: x right, y down (the floor is y = 0), z forward, metres.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from views import direction_from_equirect

ROOM_MIN = np.array([-2.0, -2.5, -1.6])
ROOM_MAX = np.array([2.0, 0.0, 1.6])
BLOCKS = ((np.array([1.0, -0.8, 0.6]), np.array([1.7, 0.0, 1.4])),
          (np.array([-1.8, -1.2, -1.4]), np.array([-1.2, 0.0, -0.9])))
TEX = 256
TILE_M = 4.0
EQ_W, EQ_H = 1024, 512
HOLD_S = 2.0
FPS = 2
PASS_SPEC = {"raised": (12, 2.0, 0.0), "head": (12, 1.6, 0.4), "hip": (12, 0.9, 0.8), "key": (10, 1.6, 1.2)}
PHONE_SIZE, PHONE_F = (800, 600), 560.0
TEMPLATE = Path(__file__).resolve().parent.parent / "capture" / "NOTES.template.md"


def _texture(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.zeros((TEX, TEX, 3))
    for cells in (4, 8, 16, 32):
        img += np.kron(rng.random((cells, cells, 3)), np.ones((TEX // cells, TEX // cells, 1))) / 4
    return (img * 255).clip(0, 255).astype(np.uint8)


_TEXTURES = [_texture(s) for s in range(6 * (1 + len(BLOCKS)))]


def render_rays(origin: np.ndarray, dirs: np.ndarray) -> np.ndarray:
    shape = dirs.shape[:-1]
    d = dirs.reshape(-1, 3)
    best_t = np.full(len(d), np.inf)
    face = np.zeros(len(d), int)
    uv = np.zeros((len(d), 2))
    boxes = ((ROOM_MIN, ROOM_MAX),) + BLOCKS
    with np.errstate(divide="ignore", invalid="ignore"):
        for b, (lo, hi) in enumerate(boxes):
            for axis in range(3):
                o1, o2 = [a for a in range(3) if a != axis]
                for side, plane in enumerate((lo[axis], hi[axis])):
                    t = (plane - origin[axis]) / d[:, axis]
                    p = origin + t[:, None] * d
                    hit = (t > 1e-6) & (p[:, o1] >= lo[o1]) & (p[:, o1] <= hi[o1]) & (p[:, o2] >= lo[o2]) & (p[:, o2] <= hi[o2])
                    better = hit & (t < best_t)
                    best_t[better] = t[better]
                    face[better] = b * 6 + axis * 2 + side
                    uv[better] = p[better][:, [o1, o2]] / TILE_M
    out = np.zeros((len(d), 3), np.uint8)
    for f in np.unique(face):
        sel = face == f
        ij = (np.mod(uv[sel], 1.0) * TEX).astype(int) % TEX
        out[sel] = _TEXTURES[f][ij[:, 1], ij[:, 0]]
    return out.reshape(*shape, 3)


def _yaw(deg: float) -> np.ndarray:
    a = np.radians(deg)
    return np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])


def render_equirect(origin: np.ndarray, body_yaw_deg: float, width: int = EQ_W, height: int = EQ_H) -> np.ndarray:
    v, u = np.mgrid[0:height, 0:width]
    d_rig = direction_from_equirect(u + 0.5, v + 0.5, width, height)
    return render_rays(origin, d_rig @ _yaw(body_yaw_deg).T)


def render_pinhole(origin: np.ndarray, yaw_deg: float, size=PHONE_SIZE, f: float = PHONE_F) -> np.ndarray:
    w, h = size
    v, u = np.mgrid[0:h, 0:w]
    d = np.stack([(u + 0.5 - w / 2) / f, (v + 0.5 - h / 2) / f, np.ones((h, w))], -1)
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    return render_rays(origin, d @ _yaw(yaw_deg).T)


def loop(n: int, height_m: float, phase: float, radius=(1.0, 0.7)) -> list[tuple[np.ndarray, float]]:
    """Poses round an ellipse; the camera body turns to face the way it walks, as a handheld stick does."""
    out = []
    for i in range(n):
        a = phase + 2 * np.pi * i / n
        out.append((np.array([radius[0] * np.cos(a), -height_m, radius[1] * np.sin(a)]), float(np.degrees(a)) + 90.0))
    return out


def write_pass(path: Path, poses) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for k, (o, yaw) in enumerate(poses):
            Image.fromarray(render_equirect(o, yaw)).save(Path(tmp) / f"{k:04d}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(1 / HOLD_S), "-i", str(Path(tmp) / "%04d.png"),
                        "-r", str(FPS), "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(path)], check=True)


def make_capture(root: Path) -> dict:
    stitched = root / "stitched"
    phone = root / "raw" / "phone"
    stitched.mkdir(parents=True, exist_ok=True)
    phone.mkdir(parents=True, exist_ok=True)
    truth: dict[str, list[float]] = {}
    for name, (n, h, phase) in PASS_SPEC.items():
        poses = loop(n, h, phase)
        write_pass(stitched / f"pass-{name}.mp4", poses)
        truth.update({f"{name}_{k}": o.tolist() for k, (o, _) in enumerate(poses)})
    pano_origin = np.array([0.1, -1.6, 0.05])
    Image.fromarray(render_equirect(pano_origin, 20.0, 2 * EQ_W, 2 * EQ_H)).save(stitched / "pano.jpg", quality=95)
    truth["pano"] = pano_origin.tolist()
    for k, (o, yaw) in enumerate(loop(6, 1.3, 0.3, radius=(0.6, 0.4))):
        exif = Image.Exif()
        exif[0x010F] = "Synthetic"
        exif.get_ifd(0x8769)[0xA405] = round(PHONE_F / PHONE_SIZE[0] * 36)
        Image.fromarray(render_pinhole(o, yaw + 60)).save(phone / f"IMG_{k:04d}.jpg", quality=95, exif=exif.tobytes())
    notes = TEMPLATE.read_text().replace("- **Door frame inside width (tape), in metres:**",
                                         "- **Door frame inside width (tape), in metres:** 0.812")
    (root / "NOTES.md").write_text(notes)
    (root / "truth.json").write_text(json.dumps(truth, indent=1))
    return truth


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture", type=Path)
    args = ap.parse_args(argv)
    make_capture(args.capture)
    print(f"synthetic capture written: {args.capture}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

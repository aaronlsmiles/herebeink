import socket
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFilter

TEMPLATE = Path(__file__).resolve().parents[2] / "capture" / "NOTES.template.md"


def make_video(path: Path, width: int = 256, height: int = 128, fps: int = 5, seconds: float = 25) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size={width}x{height}:rate={fps}:duration={seconds}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def make_vfr_video(path, sharp_index, n=12, size=(512, 256)):
    """n frames, the first six at 5 fps, then a 3 s stall and six more: ffmpeg's default for rawvideo
    (constant rate) duplicates frames across the stall, so decoded index and real index part company."""
    rng = np.random.default_rng(1)
    base = Image.fromarray(rng.integers(0, 255, (size[1], size[0]), dtype=np.uint8))
    frames = path.parent / "vfr-frames"
    frames.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (base if i == sharp_index else base.filter(ImageFilter.GaussianBlur(4))).save(frames / f"{i:04d}.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "5", "-i", str(frames / "%04d.png"),
                    "-vf", "setpts='if(lt(N,6),N/5,(N-6)/5+3)/TB'", "-fps_mode", "vfr", "-c:v", "libx264",
                    "-crf", "10", "-pix_fmt", "yuv420p", "-video_track_timescale", "1000", str(path)], check=True)
    return path


def make_jpeg(path: Path, size=(400, 300), focal35: int | None = 24) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(len(path.name))
    img = Image.fromarray(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8))
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    if focal35:
        exif.get_ifd(0x8769)[0xA405] = focal35
    img.save(path, quality=90, exif=exif.tobytes())
    return path


def fill_notes(text: str, door: str | None = "0.812", clean: str = "NOT YET") -> str:
    if door is not None:
        text = text.replace("- **Door frame inside width (tape), in metres:**",
                            f"- **Door frame inside width (tape), in metres:** {door}")
    return text.replace("Clean for upload: NOT YET", f"Clean for upload: {clean}")


@pytest.fixture
def capture(tmp_path) -> Path:
    """A small but complete capture folder: four passes, the pano, one HEIC and one JPEG phone still."""
    cap = tmp_path / "capture"
    stitched = cap / "stitched"
    for name in ("raised", "head", "hip", "key"):
        make_video(stitched / f"pass-{name}.mp4")
    Image.new("RGB", (512, 256), (90, 90, 90)).save(stitched / "pano.jpg")
    phone = cap / "raw" / "phone"
    make_jpeg(phone / "IMG_0001.JPG")
    src = make_jpeg(tmp_path / "heic-src.jpg", size=(300, 400))
    subprocess.run(["sips", "-s", "format", "heic", str(src), "--out", str(phone / "IMG_0002.HEIC")],
                   check=True, capture_output=True)
    (phone / "clip.MOV").write_bytes(b"not a still")
    (cap / "NOTES.md").write_text(fill_notes(TEMPLATE.read_text()))
    return cap


@pytest.fixture
def work(tmp_path) -> Path:
    w = tmp_path / "work"
    w.mkdir()
    return w


def tiny_work(root: Path, obs: dict[str, int] | None = None, omit: set[str] | None = None) -> Path:
    """work/ with frames.json, images and a COLMAP text model whose observation counts are set by hand.

    Frames: two head spheres (5 views), one key sphere (5 views, answer key), the pano (8 views); one
    phone still. Every image sees `obs[name]` points (default 20); each point is also seen by the
    pano's front view, the witness, so tracks have two entries.
    """
    import json

    from colmap_model import Camera, Img, Model, Point, write_model
    import views

    obs = obs or {}
    omit = omit or set()
    head = [v.token for v in views.kept_views(views.DEFAULT_DROP["head"])]
    frames = [
        {"name": "2head_0000", "pass": "head", "sample": 0, "views": head, "answer_key": False},
        {"name": "2head_0001", "pass": "head", "sample": 1, "views": head, "answer_key": False},
        {"name": "4key_0000", "pass": "key", "sample": 0, "views": head, "answer_key": True},
        {"name": "5pano_0000", "pass": "pano", "sample": 0, "views": [v.token for v in views.VIEWS], "answer_key": False},
    ]
    work = root / "work"
    (work / "images").mkdir(parents=True, exist_ok=True)
    (work / "frames.json").write_text(json.dumps({"version": 1, "view_size": 64, "focal_px": 32.0, "frames": frames}))
    names = [f"rig/{views.VIEW_BY_TOKEN[t].name}/{f['name']}.jpg" for f in frames for t in f["views"]]
    names.append("phone/800x600_f25/IMG_0000.jpg")
    for n in names:
        p = work / "images" / n
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 64) if n.startswith("rig/") else (80, 60), (len(n) % 255, 80, 120)).save(p)
    cameras = {i + 1: Camera(i + 1, "PINHOLE", 64, 64, [32.0, 32.0, 32.0, 32.0]) for i in range(8)}
    cameras[9] = Camera(9, "OPENCV", 80, 60, [70.0, 70.0, 40.0, 30.0, 0.01, 0.0, 0.0, 0.0])
    cam_of = {v.name: i + 1 for i, v in enumerate(views.VIEWS)}
    witness_name = "rig/y000p00/5pano_0000.jpg"
    present = [n for n in names if n not in omit]
    ids = {n: i + 1 for i, n in enumerate(present)}
    images = {ids[n]: Img(ids[n], [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, float(i)], cam_of.get(n.split("/")[1], 9), n, [])
              for i, n in enumerate(present)}
    points = {}
    witness = images[ids[witness_name]]
    pid = 1
    for n in present:
        if n == witness_name:
            continue
        im = images[ids[n]]
        for _ in range(obs.get(n, 20)):
            im.points2d.append((1.5, 2.5, pid))
            witness.points2d.append((3.5, 4.5, pid))
            points[pid] = Point(pid, [0.0, 0.0, 1.0], [10, 20, 30], 0.5,
                                [(im.id, len(im.points2d) - 1), (witness.id, len(witness.points2d) - 1)])
            pid += 1
        im.points2d.append((9.0, 9.0, -1))
    model_dir = work / "colmap" / "sparse_txt" / "0"
    write_model(Model(cameras, images, points), model_dir)
    return work


class NetworkBlocked(AssertionError):
    """Raised by the socket guard; deliberately not an OSError, so requests cannot wrap or retry it."""


@pytest.fixture(autouse=True)
def network_guard(monkeypatch):
    """No test may open a socket. A guard hit that a code path swallowed still fails the test at teardown."""
    attempts: list[tuple] = []

    def blocked(*args, **kwargs):
        attempts.append(args[1:] if args else ())
        raise NetworkBlocked("a test tried to reach the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    yield attempts
    assert not attempts, f"network attempted during the test: {attempts}"


@pytest.fixture
def synthetic(tmp_path) -> dict:
    """A sparse synthetic day: COLMAP model, trained splat, Marble export and NOTES with door clicks."""
    import synth_world

    return synth_world.write_scene(tmp_path, density_measured=400, density_marble=300)


@pytest.fixture
def aligned(synthetic) -> dict:
    """The synthetic day after scale.py, with measured.ply and an align.json that holds the true transform."""
    import json
    import shutil

    import align
    import scale
    import splats
    import synth_world

    work, notes = synthetic["work"], synthetic["notes"]
    assert scale.main(["--work", str(work), "--notes", str(notes)]) == 0
    shutil.copy2(work / "splat" / "splat_raw.ply", work / "splat" / "measured.ply")
    s = json.loads((work / "scale.json").read_text())
    t = synth_world.world_from_marble_true()
    from scipy.spatial import cKDTree
    measured = splats.apply(np.array(s["world_from_colmap"]), splats.centres(splats.read(work / "splat" / "measured.ply")))
    marble_raw = splats.centres(splats.read(work / "marble" / "marble_synthworld.ply"))
    res = align.residual(t, marble_raw, cKDTree(measured))
    out = work / "align" / "synthworld"
    out.mkdir(parents=True)
    (out / "align.json").write_text(json.dumps({"world_from_marble": t.tolist(), "residual": res, "model": "marble-1.1",
                                                "gateA": {"thresholdCm": 10.0, "pass": True}, "note": align.NOTE}))
    return synthetic

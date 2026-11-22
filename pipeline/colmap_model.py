"""Read and write COLMAP's text model (cameras.txt, images.txt, points3D.txt).

COLMAP 4 also writes rigs.txt and frames.txt; they are not read here. What is written here is the
three-file layout every splat trainer reads; COLMAP 4.2.1 reads it back too (it makes one trivial
rig per camera).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Camera:
    id: int
    model: str
    width: int
    height: int
    params: list[float]


@dataclass
class Img:
    id: int
    qvec: list[float]
    tvec: list[float]
    camera_id: int
    name: str
    points2d: list[tuple[float, float, int]] = field(default_factory=list)

    @property
    def n_obs(self) -> int:
        return sum(1 for _, _, pid in self.points2d if pid != -1)


@dataclass
class Point:
    id: int
    xyz: list[float]
    rgb: list[int]
    error: float
    track: list[tuple[int, int]]


@dataclass
class Model:
    cameras: dict[int, Camera]
    images: dict[int, Img]
    points: dict[int, Point]

    def mean_reprojection_error(self) -> float:
        n = sum(len(p.track) for p in self.points.values())
        return sum(p.error * len(p.track) for p in self.points.values()) / n if n else float("nan")


def _data_lines(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if not line.startswith("#")]


def read_model(folder: Path) -> Model:
    cameras = {}
    for line in _data_lines(folder / "cameras.txt"):
        if not line.strip():
            continue
        f = line.split()
        cameras[int(f[0])] = Camera(int(f[0]), f[1], int(f[2]), int(f[3]), [float(x) for x in f[4:]])
    images = {}
    lines = _data_lines(folder / "images.txt")
    # two lines an image; the second is empty when the image has no 2D points
    for head, pts in zip(lines[0::2], lines[1::2]):
        f = head.split()
        p = pts.split()
        points2d = [(float(p[i]), float(p[i + 1]), int(p[i + 2])) for i in range(0, len(p), 3)]
        img = Img(int(f[0]), [float(x) for x in f[1:5]], [float(x) for x in f[5:8]], int(f[8]), " ".join(f[9:]), points2d)
        images[img.id] = img
    points = {}
    for line in _data_lines(folder / "points3D.txt"):
        if not line.strip():
            continue
        f = line.split()
        track = [(int(f[i]), int(f[i + 1])) for i in range(8, len(f), 2)]
        points[int(f[0])] = Point(int(f[0]), [float(x) for x in f[1:4]], [int(x) for x in f[4:7]], float(f[7]), track)
    return Model(cameras, images, points)


def write_model(model: Model, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    cam_lines = ["# Camera list with one line of data per camera:",
                 "#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]",
                 f"# Number of cameras: {len(model.cameras)}"]
    for c in sorted(model.cameras.values(), key=lambda c: c.id):
        cam_lines.append(" ".join([str(c.id), c.model, str(c.width), str(c.height)] + [repr(float(x)) for x in c.params]))
    (folder / "cameras.txt").write_text("\n".join(cam_lines) + "\n")

    img_lines = ["# Image list with two lines of data per image:",
                 "#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME",
                 "#   POINTS2D[] as (X, Y, POINT3D_ID)",
                 f"# Number of images: {len(model.images)}"]
    for im in sorted(model.images.values(), key=lambda i: i.id):
        img_lines.append(" ".join([str(im.id)] + [repr(float(x)) for x in im.qvec + im.tvec] + [str(im.camera_id), im.name]))
        img_lines.append(" ".join(f"{x!r} {y!r} {pid}" for x, y, pid in im.points2d))
    (folder / "images.txt").write_text("\n".join(img_lines) + "\n")

    pt_lines = ["# 3D point list with one line of data per point:",
                "#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[] as (IMAGE_ID, POINT2D_IDX)",
                f"# Number of points: {len(model.points)}"]
    for p in sorted(model.points.values(), key=lambda p: p.id):
        pt_lines.append(" ".join([str(p.id)] + [repr(float(x)) for x in p.xyz] + [str(int(c)) for c in p.rgb]
                                 + [repr(float(p.error))] + [f"{i} {j}" for i, j in p.track]))
    (folder / "points3D.txt").write_text("\n".join(pt_lines) + "\n")

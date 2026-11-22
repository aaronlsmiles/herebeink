"""Write the laptop's training set: work/train/images/ and work/train/sparse/0/, in the plain COLMAP layout.

    uv run python export_training_set.py                        # -> work/train/
    uv run python export_training_set.py --subset 20 --out work/train_dry   # the 20-image dry run
    uv run python export_training_set.py --with-phone --out work/train_phone   # second run, phone stills undistorted
    uv run python export_training_set.py --no-pano                  # if the pano's colours do not match the passes

What goes in: every cut view of the room passes and the pano (--no-pano leaves the pano out: the still
may be shot on auto exposure, unlike the passes). What stays out: the answer-key pass (it
was in COLMAP only so Part 2 can score against it), and any 3D point left with fewer than two
observations once those frames are gone, so nothing seen only beyond the room seeds the splat.

Why one flat folder and one camera: every cube view is the same 1440 x 1440 PINHOLE camera, but
COLMAP holds it as eight (one per rig folder). Loaders differ on several cameras and on sub-folders and
LichtFeld's behaviour is unconfirmed, so the export writes a single camera and plain file names
(<view>__<frame>.jpg). The rig itself is dropped: trainers read poses per image.

Why the phone stills are out by default: they are a different camera (OPENCV, with distortion, which
not every trainer reads), shot on the phone's own exposure and white balance, so they pull colours
away from the 360 passes. --with-phone writes a separate set with them undistorted to PINHOLE by
COLMAP's image_undistorter, for a second run if the first lacks detail.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from colmap_model import Camera, Img, Model, read_model, write_model

CUBE_CAMERA_ID = 1
PHONE_CAMERA_OFFSET = 100


def flat_name(name: str) -> str:
    """'rig/y090p00/2head_0007.jpg' -> 'y090p00__2head_0007.jpg'; 'phone/4032x3024_f24/IMG_1.jpg' -> 'phone__4032x3024_f24__IMG_1.jpg'."""
    parts = name.split("/")
    return "__".join(parts[1:]) if parts[0] == "rig" else "__".join(parts)


def training_frames(work: Path, with_pano: bool = True) -> tuple[set[str], set[str]]:
    """Frame names to keep and frame names of the answer key."""
    frames = json.loads((work / "frames.json").read_text())["frames"]
    keep = {f["name"] for f in frames if not f["answer_key"] and (with_pano or f["pass"] != "pano")}
    key = {f["name"] for f in frames if f["answer_key"]}
    return keep, key


def cube_camera(model: Model) -> Camera:
    cams = {im.camera_id for im in model.images.values() if im.name.startswith("rig/")}
    params = {tuple(np.round(model.cameras[c].params, 6)) for c in cams}
    sizes = {(model.cameras[c].width, model.cameras[c].height, model.cameras[c].model) for c in cams}
    if len(params) != 1 or len(sizes) != 1:
        raise ValueError(f"the cube views do not share one camera: {sizes}, {params}")
    w, h, kind = sizes.pop()
    if kind != "PINHOLE":
        raise ValueError(f"the cube camera should be PINHOLE, found {kind}")
    return Camera(CUBE_CAMERA_ID, "PINHOLE", w, h, list(params.pop()))


def select(model: Model, keep_frames: set[str], subset: int | None) -> list[Img]:
    imgs = [im for im in model.images.values()
            if im.name.startswith("rig/") and Path(im.name).stem in keep_frames]
    imgs.sort(key=lambda im: im.name)
    if subset:
        idx = np.linspace(0, len(imgs) - 1, min(subset, len(imgs))).round().astype(int)
        imgs = [imgs[i] for i in sorted(set(idx))]
    return imgs


def build(model: Model, images: list[Img], cameras: dict[int, Camera]) -> tuple[Model, dict]:
    """A model holding only these images, their points, and tracks trimmed to them."""
    kept_ids = {im.id for im in images}
    points = {}
    dropped = 0
    for p in model.points.values():
        track = [(i, j) for i, j in p.track if i in kept_ids]
        if len(track) >= 2:
            points[p.id] = type(p)(p.id, p.xyz, p.rgb, p.error, track)
        else:
            dropped += 1
    out_imgs = {}
    for im in images:
        pts = [(x, y, pid if pid in points else -1) for x, y, pid in im.points2d]
        out_imgs[im.id] = Img(im.id, im.qvec, im.tvec, im.camera_id, flat_name(im.name), pts)
    return Model(cameras, out_imgs, points), {"points_kept": len(points), "points_dropped": dropped}


def to_binary(txt_dir: Path) -> None:
    """Add cameras.bin, images.bin and points3D.bin beside the text files (COLMAP's own writer)."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["colmap", "model_converter", "--input_path", str(txt_dir), "--output_path", tmp,
                        "--output_type", "BIN", "--log_target", "stderr"], check=True, capture_output=True)
        for name in ("cameras.bin", "images.bin", "points3D.bin"):
            shutil.copy2(Path(tmp) / name, txt_dir / name)


def undistorted_phone(work: Path, model_dir: Path) -> tuple[list[Img], dict[int, Camera], Path]:
    """Run image_undistorter on the whole model; return the phone images and their PINHOLE cameras."""
    und = work / "undistorted"
    if und.exists():
        shutil.rmtree(und)
    subprocess.run(["colmap", "image_undistorter", "--image_path", str(work / "images"), "--input_path", str(model_dir),
                    "--output_path", str(und), "--output_type", "COLMAP", "--log_target", "stderr"],
                   check=True, capture_output=True)
    txt = und / "sparse_txt"
    txt.mkdir()
    subprocess.run(["colmap", "model_converter", "--input_path", str(und / "sparse"), "--output_path", str(txt),
                    "--output_type", "TXT", "--log_target", "stderr"], check=True, capture_output=True)
    m = read_model(txt)
    imgs = [im for im in m.images.values() if im.name.startswith("phone/")]
    cams = {}
    for im in imgs:
        c = m.cameras[im.camera_id]
        new_id = PHONE_CAMERA_OFFSET + c.id
        cams[new_id] = Camera(new_id, c.model, c.width, c.height, c.params)
        im.camera_id = new_id
    return imgs, cams, und / "images"


def export(work: Path, out: Path, subset: int | None = None, with_phone: bool = False, with_pano: bool = True) -> dict:
    report = json.loads((work / "colmap_report.json").read_text())
    txt_dir = work / report["model_dir"]
    bin_dir = txt_dir.parent.parent / "sparse" / txt_dir.name
    model = read_model(txt_dir)
    keep_frames, key_frames = training_frames(work, with_pano)
    cam = cube_camera(model)
    cube = select(model, keep_frames, subset)
    for im in cube:
        im.camera_id = CUBE_CAMERA_ID
    cameras = {CUBE_CAMERA_ID: cam}
    sources = {im.id: work / "images" / im.name for im in cube}
    phone: list[Img] = []
    if with_phone:
        phone, phone_cams, und_images = undistorted_phone(work, bin_dir)
        cameras.update(phone_cams)
        sources.update({im.id: und_images / im.name for im in phone})
    trimmed, counts = build(model, cube + phone, cameras)

    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    for im in cube + phone:
        shutil.copy2(sources[im.id], out / "images" / flat_name(im.name))
    sparse = out / "sparse" / "0"
    write_model(trimmed, sparse)
    to_binary(sparse)
    key_in_model = sum(1 for im in model.images.values() if im.name.startswith("rig/") and Path(im.name).stem in key_frames)
    manifest = {"images": len(trimmed.images), "cube_images": len(cube), "phone_images": len(phone),
                "answer_key_images_left_out": key_in_model, "camera": {"model": cam.model, "width": cam.width,
                "height": cam.height, "params": cam.params}, **counts, "source_model": report["model_dir"]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--out", type=Path, default=None, help="default work/train")
    ap.add_argument("--subset", type=int, default=None, help="keep this many evenly spaced cube views (the dry run)")
    ap.add_argument("--with-phone", action="store_true")
    ap.add_argument("--no-pano", action="store_true", help="leave the pano still's eight views out")
    args = ap.parse_args(argv)
    report = json.loads((args.work / "colmap_report.json").read_text())
    if not report.get("pass"):
        print("colmap_report.json says FAIL: fix the reconstruction before exporting (see its fallbacks)")
        return 1
    m = export(args.work, args.out or args.work / "train", args.subset, args.with_phone, with_pano=not args.no_pano)
    print(f"{m['images']} images ({m['cube_images']} cube, {m['phone_images']} phone), "
          f"{m['answer_key_images_left_out']} answer-key images left out, "
          f"{m['points_kept']} points kept, {m['points_dropped']} dropped -> {args.out or args.work / 'train'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

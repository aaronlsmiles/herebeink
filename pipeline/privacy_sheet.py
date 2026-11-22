"""Contact sheets for the privacy pass (Task 1.3), and black boxes for anything that must not travel.

    uv run python privacy_sheet.py sheets                 # -> work/privacy/*.jpg and work/privacy/INDEX.md
    uv run python privacy_sheet.py mask --pass head --start 12 --end 15.5 --box 4100,1300,300,220
    uv run python privacy_sheet.py mask --pano --box 900,1400,500,300      # also --pano-auto, --pano-hdr

The tool only makes the sheets; a model reads them and a person confirms. A mask never touches the export:
it writes pass-<name>.masked.mp4 (or pano.masked.jpg) beside it, and every later step reads the masked
copy when one exists. Box coordinates are pixels of the full equirect frame (x, y, width, height);
a box running off the right edge wraps round to the left, as the sphere does.

A pass mask widens the --start/--end window by one second each side (clamped to the clip) and prints
the window it used: the sheets show one frame a second, so something seen on a sheet was on screen for
up to a second either side of that frame. Every pano still present gets a sheet, since any of them may
be the one sent to Marble.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

import views
from media import PANO_STEMS, PASSES, MediaError, stitched_pano, stitched_video

TILE_W, TILE_H, LABEL_H = 640, 320, 26
COLS, ROWS = 4, 5
PANO_W = 2400
VIEW_TILE = 600
THUMB = 400
MASK_PAD_S = 1.0
CHECKLIST = ("people", "screens showing content", "documents or letters", "addresses or house numbers",
             "photographs of people", "logos or brand names")


def _font(size: int = 20) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _labelled(img: Image.Image, label: str, w: int, h: int) -> Image.Image:
    tile = Image.new("RGB", (w, h + LABEL_H), "white")
    tile.paste(img.convert("RGB").resize((w, h)) if img.size != (w, h) else img.convert("RGB"), (0, LABEL_H))
    ImageDraw.Draw(tile).text((6, 3), label, fill="black", font=_font())
    return tile


def _grid(tiles: list[Image.Image], cols: int) -> Image.Image:
    w, h = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (40, 40, 40))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * w, (i // cols) * h))
    return sheet


def pass_sheets(video: Path, name: str, out: Path) -> list[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps=1,scale={TILE_W}:{TILE_H}",
                        "-q:v", "4", str(Path(tmp) / "%05d.jpg")], check=True)
        frames = sorted(Path(tmp).glob("*.jpg"))
        tiles = []
        for i, f in enumerate(frames):
            with Image.open(f) as im:
                tiles.append(_labelled(im, f"{name}  {i // 60:02d}:{i % 60:02d}", TILE_W, TILE_H))
    paths = []
    per = COLS * ROWS
    for k in range(0, len(tiles), per):
        p = out / f"pass-{name}-{k // per + 1:02d}.jpg"
        _grid(tiles[k:k + per], COLS).save(p, quality=88)
        paths.append(p)
    return paths


def pano_sheet(pano: Path, out_path: Path) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        labels = "".join(f"[s{i}]" for i in range(len(views.VIEWS)))
        graph = f"[0:v]split={len(views.VIEWS)}{labels};" + ";".join(
            f"[s{i}]{views.v360_filter(v, VIEW_TILE)}[o{i}]" for i, v in enumerate(views.VIEWS))
        cmd = ["ffmpeg", "-v", "error", "-i", str(pano), "-filter_complex", graph]
        for i, v in enumerate(views.VIEWS):
            cmd += ["-map", f"[o{i}]", "-frames:v", "1", "-q:v", "3", str(Path(tmp) / f"{v.name}.jpg")]
        subprocess.run(cmd, check=True)
        tiles = []
        for v in views.VIEWS:
            with Image.open(Path(tmp) / f"{v.name}.jpg") as im:
                tiles.append(_labelled(im, f"view {v.token}", VIEW_TILE, VIEW_TILE))
    with Image.open(pano) as im:
        full = _labelled(im, f"{pano.name}  (full frame)", PANO_W, PANO_W // 2)
    grid = _grid(tiles, 4)
    sheet = Image.new("RGB", (PANO_W, full.height + grid.height), "white")
    sheet.paste(full, (0, 0))
    sheet.paste(grid.resize((PANO_W, grid.height * PANO_W // grid.width)), (0, full.height))
    sheet.save(out_path, quality=90)
    return out_path


def phone_sheets(phone_dir: Path, out: Path) -> list[Path]:
    stills = sorted(phone_dir.rglob("*.jpg")) if phone_dir.exists() else []
    tiles = []
    for p in stills:
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((THUMB, THUMB))
            canvas = Image.new("RGB", (THUMB, THUMB), (40, 40, 40))
            canvas.paste(im, ((THUMB - im.width) // 2, (THUMB - im.height) // 2))
            tiles.append(_labelled(canvas, p.name, THUMB, THUMB))
    paths = []
    for k in range(0, len(tiles), 16):
        path = out / f"phone-{k // 16 + 1:02d}.jpg"
        _grid(tiles[k:k + 16], 4).save(path, quality=88)
        paths.append(path)
    return paths


def write_index(out: Path, sheets: dict[str, list[Path]]) -> Path:
    lines = ["# Privacy pass: contact sheets", "",
             "Read every sheet for the six things below. Tick a box only when the sheet is clear of it.",
             "Write findings in capture/NOTES.md under 'Privacy pass'. Change its line 'Clean for upload: NOT YET' to",
             "exactly 'Clean for upload: yes' only when every sheet is clear or masked: marble.py reads that whole line.",
             "Mask with `privacy_sheet.py mask`, then run `privacy_sheet.py sheets` again. A pass mask pads the time",
             f"window by one second each side ({MASK_PAD_S:g} s, clamped to the clip), because the sheets show one frame a",
             "second; the command prints the window it used.",
             "A phone still with a problem is moved to capture/raw/phone-excluded/ and ingest_check.py run again.", ""]
    for group, paths in sheets.items():
        lines += [f"## {group}", ""]
        for p in paths:
            lines.append(f"### {p.name}")
            lines += [f"- [ ] no {item}" for item in CHECKLIST]
            lines.append("")
    path = out / "INDEX.md"
    path.write_text("\n".join(lines))
    return path


def make_sheets(capture: Path, work: Path) -> dict[str, list[Path]]:
    out = work / "privacy"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    stitched = capture / "stitched"
    sheets: dict[str, list[Path]] = {}
    for name in PASSES:
        video = stitched_video(stitched, name)
        if video.exists():
            sheets[f"pass {name} ({video.name}, one frame a second)"] = pass_sheets(video, name, out)
    for stem in PANO_STEMS:
        pano = stitched_pano(stitched, stem)
        if pano.exists():
            sheets[f"{stem} ({pano.name}, full frame and the eight cut views)"] = [pano_sheet(pano, out / f"{stem}.jpg")]
    phone = phone_sheets(work / "images" / "phone", out)
    if phone:
        sheets["phone stills (converted copies in work/images/phone)"] = phone
    write_index(out, sheets)
    return sheets


def parse_box(text: str) -> tuple[int, int, int, int]:
    parts = [int(round(float(p))) for p in text.split(",")]
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise argparse.ArgumentTypeError("a box is x,y,width,height in pixels, width and height above zero")
    return parts[0], parts[1], parts[2], parts[3]


def wrap_boxes(boxes: list[tuple[int, int, int, int]], width: int) -> list[tuple[int, int, int, int]]:
    out = []
    for x, y, w, h in boxes:
        x %= width
        if x + w <= width:
            out.append((x, y, w, h))
        else:
            out.append((x, y, width - x, h))
            out.append((0, y, x + w - width, h))
    return out


def drawbox_filter(boxes: list[tuple[int, int, int, int]], start: float, end: float) -> str:
    return ",".join(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=black:t=fill:enable='between(t,{start},{end})'"
                    for x, y, w, h in boxes)


def padded_window(start: float, end: float, duration: float, pad: float = MASK_PAD_S) -> tuple[float, float]:
    return max(0.0, start - pad), min(duration, end + pad)


def mask_video(capture: Path, name: str, start: float, end: float, boxes: list[tuple[int, int, int, int]]) -> Path:
    stitched = capture / "stitched"
    src = stitched_video(stitched, name)
    if not src.exists():
        raise FileNotFoundError(src)
    width, duration = (float(x) for x in subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width:format=duration",
         "-of", "csv=p=0:s=,", str(src)], check=True, capture_output=True, text=True).stdout.strip().replace("\n", ",").split(","))
    start, end = padded_window(start, end, duration)
    print(f"mask window {start:.1f} to {end:.1f} s (the requested times padded by {MASK_PAD_S:g} s each side, clamped to the clip)")
    width = int(width)
    dest = stitched / f"pass-{name}.masked.mp4"
    tmp = stitched / f"pass-{name}.masking.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                    drawbox_filter(wrap_boxes(boxes, width), start, end),
                    "-c:v", "libx264", "-crf", "14", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-fps_mode", "passthrough", "-an", str(tmp)], check=True)
    tmp.replace(dest)
    return dest


def mask_pano(capture: Path, boxes: list[tuple[int, int, int, int]], stem: str = "pano") -> Path:
    stitched = capture / "stitched"
    src = stitched_pano(stitched, stem)
    with Image.open(src) as im:
        im = im.convert("RGB")
        draw = ImageDraw.Draw(im)
        for x, y, w, h in wrap_boxes(boxes, im.width):
            draw.rectangle([x, y, x + w - 1, y + h - 1], fill="black")
        dest = stitched / f"{stem}.masked.jpg"
        im.save(dest, quality=95)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capture", type=Path, default=Path("../capture"))
    ap.add_argument("--work", type=Path, default=Path("work"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sheets", help="make the contact sheets and INDEX.md")
    m = sub.add_parser("mask", help="black out boxes on a pass (a time range) or on the pano still")
    target = m.add_mutually_exclusive_group(required=True)
    target.add_argument("--pass", dest="pass_name", choices=PASSES)
    target.add_argument("--pano", action="store_true")
    target.add_argument("--pano-auto", action="store_true")
    target.add_argument("--pano-hdr", action="store_true")
    m.add_argument("--start", type=float, help="seconds (passes only)")
    m.add_argument("--end", type=float, help="seconds (passes only)")
    m.add_argument("--box", type=parse_box, action="append", required=True, help="x,y,width,height in pixels")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "sheets":
            sheets = make_sheets(args.capture, args.work)
            n = sum(len(v) for v in sheets.values())
            print(f"{n} sheets in {args.work / 'privacy'}; read them from {args.work / 'privacy' / 'INDEX.md'}")
            return 0
        if args.pass_name:
            if args.start is None or args.end is None or args.end <= args.start:
                ap.error("--start and --end (seconds, end after start) are needed to mask a pass")
            dest = mask_video(args.capture, args.pass_name, args.start, args.end, args.box)
        else:
            stem = "pano-hdr" if args.pano_hdr else "pano-auto" if args.pano_auto else "pano"
            dest = mask_pano(args.capture, args.box, stem)
    except MediaError as exc:
        print(f"ERROR  {exc}")
        return 1
    print(f"masked copy written: {dest} (the export is untouched; run 'sheets' again to check)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

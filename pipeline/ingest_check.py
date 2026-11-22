"""Check the capture folder the moment the footage lands, and say plainly what is missing or wrong.

Also converts the phone stills (HEIC to JPEG with sips, JPEG copied) into work/images/phone/<group>/,
one group per stored pixel size and 35 mm focal length, so COLMAP gives each group one camera.

    uv run python ingest_check.py                       # ../capture -> work/ingest.json
    uv run python ingest_check.py --capture DIR --work DIR

Exit code 1 when a required input is missing or unusable; warnings never fail the run.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from media import PASSES, ROOM_PASSES, focal_35mm, image_size, probe_video

EXPECTED_VIDEO = (5760, 2880)
EXPECTED_PANO = {(11968, 5984), (5952, 2976)}
VIDEO_CODECS = {"h264", "hevc", "prores"}
PHONE_SUFFIXES = {".heic", ".heif", ".jpg", ".jpeg"}
MIN_PASS_S, SHORT_PASS_S, LONG_PASS_S = 20.0, 60.0, 360.0
DOOR_RANGE_M = (0.5, 1.5)

# The template's own line, with the number written after it on the same line.
DOOR_RE = re.compile(
    r"^- \*\*Door frame inside width \(tape\), in metres:\*\*[ \t]*([0-9]*\.?[0-9]+)[ \t]*m?[ \t]*$", re.M)
DOOR_CHECK_RE = re.compile(
    r"^- Door frame inside width, second tape \(cross-check\), in metres:[ \t]*([0-9]*\.?[0-9]+)[ \t]*m?[ \t]*$", re.M)
CLEAN_RE = re.compile(r"^Clean for upload:[ \t]*(.*?)[ \t]*$", re.M)


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.ok: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def good(self, msg: str) -> None:
        self.ok.append(msg)


def check_video(path: Path, name: str, required: bool, rep: Report) -> dict:
    info: dict = {"file": path.name, "present": path.exists()}
    if not path.exists():
        hint = f"export the {name} pass from Insta360 Studio as 360 equirectangular, 5760 x 2880, FlowState off"
        (rep.error if required else rep.warn)(f"{path.name} is missing: {hint}")
        return info
    try:
        info.update(probe_video(path))
    except (subprocess.CalledProcessError, ValueError, KeyError) as exc:
        rep.error(f"{path.name} cannot be read as a video ({exc})")
        return info
    w, h = info["width"], info["height"]
    if w != 2 * h:
        rep.error(f"{path.name} is {w} x {h}, not 2:1: it is not an equirectangular export")
        return info
    if (w, h) != EXPECTED_VIDEO:
        rep.warn(f"{path.name} is {w} x {h}; expected 5760 x 2880 (the cut still works, views will be softer)")
    if abs(info["fps"] - 30) > 0.1 and abs(info["fps"] - 29.97) > 0.05:
        rep.warn(f"{path.name} runs at {info['fps']} fps; expected 30 (the cut uses the real rate)")
    if info["avg_fps"] and info["r_fps"] and abs(info["avg_fps"] - info["r_fps"]) > 0.005 * info["r_fps"]:
        rep.warn(f"{path.name} has a variable frame rate (average {info['avg_fps']}, nominal {info['r_fps']} fps): "
                 "the cut follows frame order, so check the sheets, or export it again at a constant rate")
    if info["duration_s"] < MIN_PASS_S:
        (rep.error if required else rep.warn)(
            f"{path.name} lasts {info['duration_s']:.0f} s: too short for a pass (at least {MIN_PASS_S:.0f} s)")
    elif not SHORT_PASS_S <= info["duration_s"] <= LONG_PASS_S:
        rep.warn(f"{path.name} lasts {info['duration_s']:.0f} s; the protocol expects two to three minutes")
    if info["codec"] not in VIDEO_CODECS:
        rep.warn(f"{path.name} uses codec {info['codec']}; expected H.264 or H.265")
    rep.good(f"{path.name}: {w} x {h}, {info['fps']} fps, {info['duration_s']:.0f} s, {info['codec']}")
    return info


def check_pano(path: Path, required: bool, rep: Report) -> dict:
    info: dict = {"file": path.name, "present": path.exists()}
    if not path.exists():
        hint = "export the 360 still from Insta360 Studio as a JPG (72 MP, 11968 x 5984)"
        (rep.error if required else rep.warn)(f"{path.name} is missing: {hint}")
        return info
    try:
        w, h = image_size(path)
    except OSError as exc:
        rep.error(f"{path.name} cannot be opened as an image ({exc})")
        return info
    info.update({"width": w, "height": h})
    if w != 2 * h:
        rep.error(f"{path.name} is {w} x {h}, not exactly 2:1: it is not an equirectangular still")
        return info
    if (w, h) not in EXPECTED_PANO:
        rep.warn(f"{path.name} is {w} x {h}; expected 11968 x 5984 or 5952 x 2976")
    rep.good(f"{path.name}: {w} x {h}")
    return info


def safe_stem(stem: str) -> str:
    """COLMAP's text formats split on spaces, so a name like 'IMG_1234 2' cannot go through as it is."""
    return re.sub(r"\s+", "_", stem.strip())


def convert_phone(raw_dir: Path, out_dir: Path, rep: Report) -> dict:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    files = [p for p in raw_dir.glob("*") if p.is_file() and not p.name.startswith(".")] if raw_dir.exists() else []
    # Names that need no change are placed first, so a renamed file works around them and never the reverse.
    files.sort(key=lambda p: (p.stem != safe_stem(p.stem), p.name))
    if not files:
        rep.warn(f"no phone stills in {raw_dir.name}/ (optional: they add detail views)")
        return {"count": 0, "groups": {}, "skipped": [], "renamed": {}}
    groups: dict[str, int] = {}
    skipped: list[str] = []
    seen: dict[str, str] = {}
    renamed: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for src in files:
            suffix = src.suffix.lower()
            if suffix not in PHONE_SUFFIXES:
                skipped.append(src.name)
                continue
            stem = safe_stem(src.stem)
            if stem in seen and seen[stem] == src.stem:
                rep.warn(f"phone still {src.name} has the same name as another; skipped")
                skipped.append(src.name)
                continue
            n = 1
            while stem in seen:
                n += 1
                stem = f"{safe_stem(src.stem)}_{n}"
            seen[stem] = src.stem
            if stem != src.stem:
                renamed[src.name] = f"{stem}.jpg"
            jpeg = Path(tmp) / f"{stem}.jpg"
            if suffix in (".heic", ".heif"):
                # sips keeps the EXIF focal length; it exits 0 even when it fails, so check the file
                subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "95", str(src), "--out", str(jpeg)],
                               check=False, capture_output=True)
                if not jpeg.exists():
                    rep.warn(f"phone still {src.name} could not be converted to JPEG; skipped")
                    skipped.append(src.name)
                    continue
            else:
                shutil.copy2(src, jpeg)
            w, h = image_size(jpeg)
            f35 = focal_35mm(jpeg)
            group = f"{w}x{h}" + (f"_f{f35}" if f35 else "")
            dest = out_dir / group / jpeg.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(jpeg), dest)
            groups[group] = groups.get(group, 0) + 1
    if skipped:
        rep.warn(f"{len(skipped)} file(s) in {raw_dir.name}/ skipped (not HEIC or JPEG, or duplicate): {', '.join(skipped[:5])}")
    count = sum(groups.values())
    rep.good(f"phone stills: {count} converted into {len(groups)} camera group(s): "
             + ", ".join(f"{g} ({n})" for g, n in sorted(groups.items())))
    if renamed:
        rep.warn(f"{len(renamed)} phone still(s) renamed because their names had spaces or clashed: "
                 + ", ".join(f"{a} -> {b}" for a, b in list(renamed.items())[:5]))
    return {"count": count, "groups": groups, "skipped": skipped, "renamed": renamed}


def read_notes(path: Path, rep: Report) -> dict:
    info: dict = {"present": path.exists(), "door_width_m": None, "door_width_check_m": None, "clean_for_upload": None}
    if not path.exists():
        rep.error("capture/NOTES.md is missing")
        return info
    text = path.read_text(encoding="utf-8")
    m = DOOR_RE.search(text)
    if not m:
        rep.error("the door width is not in NOTES.md: write it in metres after "
                  "'- **Door frame inside width (tape), in metres:**', for example 0.812")
    else:
        width = float(m.group(1))
        info["door_width_m"] = width
        if not DOOR_RANGE_M[0] <= width <= DOOR_RANGE_M[1]:
            rep.error(f"the door width reads {width} m; a door is 0.5 to 1.5 m: is it in metres?")
        else:
            rep.good(f"door width: {width:.3f} m")
    c = DOOR_CHECK_RE.search(text)
    if c:
        info["door_width_check_m"] = float(c.group(1))
        if info["door_width_m"] is not None and abs(info["door_width_check_m"] - info["door_width_m"]) > 0.005:
            rep.warn(f"the two door measurements differ by more than 5 mm "
                     f"({info['door_width_m']} and {info['door_width_check_m']} m): measure again")
    k = CLEAN_RE.search(text)
    info["clean_for_upload"] = k.group(1) if k else None
    state = info["clean_for_upload"] or "(line missing)"
    rep.good(f"clean for upload: {state} (the privacy pass sets this; no upload until it reads yes)")
    return info


def run(capture: Path, work: Path) -> tuple[dict, Report]:
    rep = Report()
    stitched = capture / "stitched"
    result = {
        "videos": {p: check_video(stitched / f"pass-{p}.mp4", p, p in ROOM_PASSES, rep) for p in PASSES},
        "pano": check_pano(stitched / "pano.jpg", True, rep),
        "pano_auto": check_pano(stitched / "pano-auto.jpg", False, rep),
        "pano_hdr": check_pano(stitched / "pano-hdr.jpg", False, rep),
        "phone": convert_phone(capture / "raw" / "phone", work / "images" / "phone", rep),
        "notes": read_notes(capture / "NOTES.md", rep),
    }
    result.update({"errors": rep.errors, "warnings": rep.warnings, "ok": not rep.errors})
    work.mkdir(parents=True, exist_ok=True)
    (work / "ingest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result, rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capture", type=Path, default=Path("../capture"))
    ap.add_argument("--work", type=Path, default=Path("work"))
    args = ap.parse_args(argv)
    _, rep = run(args.capture, args.work)
    for line in rep.ok:
        print(f"ok     {line}")
    for line in rep.warnings:
        print(f"WARN   {line}")
    for line in rep.errors:
        print(f"ERROR  {line}")
    print("ingest: " + ("FAIL, fix the errors above and run again" if rep.errors else "PASS") + f"  ({args.work / 'ingest.json'})")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())

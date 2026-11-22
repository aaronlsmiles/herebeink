"""Cut the stitched passes and the pano still into the eight pinhole views COLMAP reads as one rig.

    uv run python cut_views.py plan                       # work/ingest.json -> work/cut_plan.json
    uv run python cut_views.py plan --drop head=180@0,135@40 --drop hip=none --positions 120
    uv run python cut_views.py plan --yaw-offset head=180      # the operator showed up at yaw 0
    uv run python cut_views.py plan --positions 150            # drops and yaw offsets already in
                                                               # cut_plan.json carry over; --reset-drops clears them
    uv run python cut_views.py preview                    # work/preview/pass-<name>.jpg: check the drops
    uv run python cut_views.py cut                        # -> work/images/rig/<view>/<frame>.jpg,
                                                          #    work/frames.json, work/rig_config.json,
                                                          #    work/preview/cut-check.jpg (24 cut images to look at)

Layout for COLMAP's rig: one folder per view under images/rig/, the same file name for every view of
one sphere, and names that sort in capture order: <n><pass>_<k>.jpg with n = 1 raised, 2 head, 3 hip,
4 key, 5 pano. Frames of the key pass go through COLMAP with the rest (so Part 2 can score against them)
and are marked answer_key in frames.json so the training export leaves them out.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import views
from media import PASSES, MediaError, stitched_pano, stitched_video

PASS_ORDER = {name: i for i, name in enumerate(PASSES, 1)}
PANO_ORDER = 5
SHARES = {"head": 0.4, "raised": 0.3, "hip": 0.3}
DEFAULT_POSITIONS = 100
BLUR_WINDOW_S = 0.25
SCORE_WIDTH = 960
JPEG_Q = 2  # ffmpeg's mjpeg scale, about quality 95
PREVIEW_SIZE = 320
PREVIEW_TIMES = 6
CHECK_COUNT, CHECK_COLS, CHECK_TILE, CHECK_LABEL_H, CHECK_SEED = 24, 6, 240, 20, 50


def frame_name(pass_name: str, k: int) -> str:
    order = PANO_ORDER if pass_name == "pano" else PASS_ORDER[pass_name]
    return f"{order}{pass_name}_{k:04d}"


def sample_times(duration: float, interval: float) -> list[float]:
    n = max(1, int(duration // interval))
    return [round((k + 0.5) * interval, 4) for k in range(n)]


def build_plan(ingest: dict, positions: int = DEFAULT_POSITIONS, drops: dict[str, tuple[str, ...]] | None = None,
               window: float = BLUR_WINDOW_S, view_size: int = views.VIEW_SIZE,
               yaw_offsets: dict[str, float] | None = None) -> dict:
    drops = {**views.DEFAULT_DROP, **(drops or {})}
    yaw_offsets = yaw_offsets or {}
    videos = {p: v for p, v in ingest["videos"].items() if v.get("present") and v.get("duration_s")}
    missing = [p for p in SHARES if p not in videos]
    if missing:
        raise ValueError(f"cannot plan without the room passes: {', '.join(missing)} missing from ingest.json")
    intervals = {p: videos[p]["duration_s"] / (positions * SHARES[p]) for p in SHARES}
    if "key" in videos:
        # the answer key is sampled as densely in space as the head pass, which it most resembles
        intervals["key"] = intervals["head"]
    passes = {}
    for p in PASSES:
        if p not in videos:
            continue
        v = videos[p]
        passes[p] = {
            "fps": v["fps"], "duration_s": v["duration_s"], "frames": v["frames"],
            "interval_s": round(intervals[p], 4), "times_s": sample_times(v["duration_s"], intervals[p]),
            "drop": list(drops[p]), "yaw_offset": yaw_offsets.get(p, 0), "answer_key": p == "key",
        }
    pano_present = ingest.get("pano", {}).get("present", False)
    return {"version": 1, "view_size": view_size, "positions": positions, "window_s": window,
            "passes": passes,
            "pano": {"present": pano_present, "drop": list(drops["pano"]), "yaw_offset": yaw_offsets.get("pano", 0)}}


def plan_summary(plan: dict) -> str:
    lines, total = [], 0
    for p, info in plan["passes"].items():
        n_views = len(views.kept_views(tuple(info["drop"])))
        n = len(info["times_s"]) * n_views
        total += n
        tag = "  (answer key: COLMAP only, never trained on)" if info["answer_key"] else ""
        lines.append(f"{p:7s} {info['duration_s']:6.1f} s  every {info['interval_s']:5.2f} s  "
                     f"{len(info['times_s']):3d} spheres x {n_views} views = {n:4d} images  "
                     f"drop: {', '.join(info['drop']) or 'none'}"
                     + (f"  yaw offset {info['yaw_offset']}" if info["yaw_offset"] else "") + tag)
    if plan["pano"]["present"]:
        n = len(views.kept_views(tuple(plan["pano"]["drop"])))
        total += n
        lines.append(f"pano    one still                    1 sphere  x {n} views = {n:4d} images")
    lines.append(f"total {total} cube images at {plan['view_size']} x {plan['view_size']}")
    return "\n".join(lines)


def laplacian_variance(gray: np.ndarray) -> float:
    g = gray.astype(np.float32)
    lap = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    return float(lap.var())


def score_frames(video: Path, wanted: set[int]) -> dict[int, float]:
    """Sharpness of the wanted frames, by decoding the pass once at a small size."""
    w, h = SCORE_WIDTH, SCORE_WIDTH // 2
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"scale={w}:{h},format=gray",
                             "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    scores: dict[int, float] = {}
    size = w * h
    i = 0
    assert proc.stdout is not None
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        if i in wanted:
            scores[i] = laplacian_variance(np.frombuffer(buf, np.uint8).reshape(h, w))
        i += 1
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg could not decode {video.name}")
    return scores


def candidate_frames(t: float, fps: float, window: float, n_frames: int) -> list[int]:
    lo = max(0, round((t - window) * fps))
    hi = min(n_frames - 1, round((t + window) * fps))
    centre = min(n_frames - 1, max(0, round(t * fps)))
    return list(range(lo, hi + 1)) if window > 0 else [centre]


def choose_frames(times: list[float], fps: float, n_frames: int, window: float,
                  scores: dict[int, float] | None) -> list[tuple[int, int, float | None]]:
    """(sample number, frame index, sharpness) per sample; the sharpest frame in each window wins."""
    chosen, used = [], set()
    for k, t in enumerate(times):
        cands = [c for c in candidate_frames(t, fps, window if scores else 0, n_frames) if c not in used]
        if not cands:
            continue
        best = max(cands, key=lambda c: scores.get(c, -1.0)) if scores else cands[0]
        used.add(best)
        chosen.append((k, best, scores.get(best) if scores else None))
    return chosen


def cut_frames(source: Path, frame_indices: list[int] | None, out_names: list[str], keep: tuple[views.View, ...],
               size: int, images: Path, quality: int = JPEG_Q, yaw_offset: float = 0) -> None:
    """One decode of the source; one select, one split, one v360 per kept view."""
    with tempfile.TemporaryDirectory() as tmp:
        labels = "".join(f"[s{j}]" for j in range(len(keep)))
        head = "[0:v]"
        if frame_indices is not None:
            head += "select='" + "+".join(f"eq(n\\,{i})" for i in frame_indices) + "',"
        graph = head + f"split={len(keep)}{labels};" + ";".join(
            f"[s{j}]{views.v360_filter(v, size, yaw_offset)}[o{j}]" for j, v in enumerate(keep))
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(source), "-filter_complex", graph]
        for j, v in enumerate(keep):
            (Path(tmp) / v.name).mkdir()
            cmd += ["-map", f"[o{j}]", "-fps_mode", "passthrough", "-q:v", str(quality),
                    str(Path(tmp) / v.name / "%05d.jpg")]
        subprocess.run(cmd, check=True)
        for v in keep:
            outs = sorted((Path(tmp) / v.name).glob("*.jpg"))
            if len(outs) != len(out_names):
                raise RuntimeError(f"{source.name}: expected {len(out_names)} frames for {v.name}, ffmpeg wrote {len(outs)}")
            dest = images / "rig" / v.name
            dest.mkdir(parents=True, exist_ok=True)
            for src, name in zip(outs, out_names):
                shutil.move(str(src), dest / f"{name}.jpg")


def cut(plan: dict, capture: Path, work: Path, blur: bool = True) -> dict:
    stitched = capture / "stitched"
    images = work / "images"
    if (images / "rig").exists():
        shutil.rmtree(images / "rig")
    # A half-finished cut must not leave the last run's frames.json describing images that are gone.
    for stale in ("frames.json", "rig_config.json"):
        (work / stale).unlink(missing_ok=True)
    size = plan["view_size"]
    frames: list[dict] = []
    for p, info in plan["passes"].items():
        source = stitched_video(stitched, p)
        keep = views.kept_views(tuple(info["drop"]))
        times = info["times_s"]
        wanted = {c for t in times for c in candidate_frames(t, info["fps"], plan["window_s"], info["frames"])}
        scores = score_frames(source, wanted) if blur and plan["window_s"] > 0 else None
        chosen = choose_frames(times, info["fps"], info["frames"], plan["window_s"], scores)
        indices = sorted(i for _, i, _ in chosen)
        by_index = {i: (k, s) for k, i, s in chosen}
        names = [frame_name(p, by_index[i][0]) for i in indices]
        cut_frames(source, indices, names, keep, size, images, yaw_offset=info.get("yaw_offset", 0))
        for i, name in zip(indices, names):
            k, s = by_index[i]
            frames.append({"name": name, "pass": p, "sample": k, "time_s": round(i / info["fps"], 4),
                           "frame_index": i, "sharpness": s, "views": [v.token for v in keep],
                           "answer_key": info["answer_key"], "source": source.name})
        print(f"{p}: {len(names)} spheres x {len(keep)} views from {source.name}")
    if plan["pano"]["present"]:
        pano = stitched_pano(stitched)
        keep = views.kept_views(tuple(plan["pano"]["drop"]))
        name = frame_name("pano", 0)
        cut_frames(pano, None, [name], keep, size, images, yaw_offset=plan["pano"].get("yaw_offset", 0))
        frames.append({"name": name, "pass": "pano", "sample": 0, "time_s": None, "frame_index": None,
                       "sharpness": None, "views": [v.token for v in keep], "answer_key": False, "source": pano.name})
        print(f"pano: 1 sphere x {len(keep)} views from {pano.name}")
    record = {"version": 1, "view_size": size, "focal_px": views.focal(size), "frames": frames}
    (work / "frames.json").write_text(json.dumps(record, indent=2) + "\n")
    (work / "rig_config.json").write_text(json.dumps(views.rig_config(), indent=2) + "\n")
    print(f"spot check: {cut_check_sheet(work, record)}")
    return record


def pick_check_images(work: Path, record: dict, count: int = CHECK_COUNT, seed: int = CHECK_SEED) -> list[tuple[str, str, Path]]:
    """A seeded sample of (frame, view token, file) over the images that are on disk."""
    cut = [(f["name"], t, work / "images" / "rig" / views.VIEW_BY_TOKEN[t].name / f"{f['name']}.jpg")
           for f in record["frames"] for t in f["views"]]
    cut = sorted(c for c in cut if c[2].exists())
    return sorted(random.Random(seed).sample(cut, min(count, len(cut))))


def cut_check_sheet(work: Path, record: dict, count: int = CHECK_COUNT) -> Path:
    """Task 1.5's spot check, on the very files that will be trained on: look for people, blur, wrong views."""
    picks = pick_check_images(work, record, count)
    rows = max(1, (len(picks) + CHECK_COLS - 1) // CHECK_COLS)
    sheet = Image.new("RGB", (CHECK_COLS * CHECK_TILE, rows * (CHECK_TILE + CHECK_LABEL_H)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=14)
    for i, (frame, token, path) in enumerate(picks):
        x, y = (i % CHECK_COLS) * CHECK_TILE, (i // CHECK_COLS) * (CHECK_TILE + CHECK_LABEL_H)
        draw.text((x + 4, y + 2), f"{frame} {token}", fill="black", font=font)
        with Image.open(path) as im:
            sheet.paste(im.convert("RGB").resize((CHECK_TILE, CHECK_TILE)), (x, y + CHECK_LABEL_H))
    out = work / "preview" / "cut-check.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    return out


def preview(plan: dict, capture: Path, work: Path, size: int = PREVIEW_SIZE) -> list[Path]:
    """All eight views at six moments of each pass on one sheet; dropped views crossed out in red."""
    out_dir = work / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=16)
    label_h = 22
    paths = []
    for p, info in plan["passes"].items():
        source = stitched_video(capture / "stitched", p)
        drop = set(info["drop"])
        sheet = Image.new("RGB", (len(views.VIEWS) * size, PREVIEW_TIMES * (size + label_h)), "white")
        for row in range(PREVIEW_TIMES):
            t = info["duration_s"] * (row + 0.5) / PREVIEW_TIMES
            with tempfile.TemporaryDirectory() as tmp:
                labels = "".join(f"[s{j}]" for j in range(len(views.VIEWS)))
                graph = f"[0:v]split={len(views.VIEWS)}{labels};" + ";".join(
                    f"[s{j}]{views.v360_filter(v, size, info.get('yaw_offset', 0))}[o{j}]" for j, v in enumerate(views.VIEWS))
                cmd = ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(source), "-filter_complex", graph]
                for j, v in enumerate(views.VIEWS):
                    cmd += ["-map", f"[o{j}]", "-frames:v", "1", "-q:v", "4", str(Path(tmp) / f"{v.name}.jpg")]
                subprocess.run(cmd, check=True)
                for col, v in enumerate(views.VIEWS):
                    x, y = col * size, row * (size + label_h)
                    with Image.open(Path(tmp) / f"{v.name}.jpg") as im:
                        sheet.paste(im.convert("RGB"), (x, y + label_h))
                    draw = ImageDraw.Draw(sheet)
                    dropped = v.token in drop
                    draw.text((x + 4, y + 2), f"{p} {t:5.1f}s  {v.token}" + ("  DROP" if dropped else ""),
                              fill="red" if dropped else "black", font=font)
                    if dropped:
                        draw.rectangle([x, y + label_h, x + size - 1, y + label_h + size - 1], outline="red", width=4)
                        draw.line([x, y + label_h, x + size, y + label_h + size], fill="red", width=3)
        path = out_dir / f"pass-{p}.jpg"
        sheet.save(path, quality=88)
        paths.append(path)
    return paths


def carried_settings(plan: dict) -> tuple[dict[str, tuple[str, ...]], dict[str, float]]:
    """The operator's drops and yaw offsets from an earlier plan, per pass and for the pano."""
    drops = {p: tuple(info["drop"]) for p, info in plan["passes"].items()}
    drops["pano"] = tuple(plan["pano"]["drop"])
    yaws = {p: info.get("yaw_offset", 0) for p, info in plan["passes"].items()}
    yaws["pano"] = plan["pano"].get("yaw_offset", 0)
    return drops, yaws


def describe_edits(drops: dict[str, tuple[str, ...]], yaws: dict[str, float]) -> list[str]:
    bits = [f"{p} drop {', '.join(d) or 'none'}" for p, d in drops.items() if d != views.DEFAULT_DROP[p]]
    bits += [f"{p} yaw offset {y:g}" for p, y in yaws.items() if y]
    return bits


def parse_drop_arg(text: str) -> tuple[str, tuple[str, ...]]:
    name, sep, rest = text.partition("=")
    if not sep or name not in views.DEFAULT_DROP:
        raise argparse.ArgumentTypeError(f"--drop takes PASS=VIEWS, PASS one of {', '.join(views.DEFAULT_DROP)}")
    try:
        return name, views.parse_drop(rest)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_yaw_offset_arg(text: str) -> tuple[str, float]:
    name, sep, rest = text.partition("=")
    if not sep or name not in views.DEFAULT_DROP:
        raise argparse.ArgumentTypeError(f"--yaw-offset takes PASS=DEGREES, PASS one of {', '.join(views.DEFAULT_DROP)}")
    try:
        return name, float(rest)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"'{rest}' is not a number of degrees") from exc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capture", type=Path, default=Path("../capture"))
    ap.add_argument("--work", type=Path, default=Path("work"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan", help="write work/cut_plan.json from work/ingest.json")
    pl.add_argument("--positions", type=int, default=DEFAULT_POSITIONS, help="sphere positions over the three room passes")
    pl.add_argument("--drop", type=parse_drop_arg, action="append", default=[], help="PASS=VIEWS, e.g. head=180@0,135@40")
    pl.add_argument("--window", type=float, default=BLUR_WINDOW_S, help="seconds either side to look for a sharper frame")
    pl.add_argument("--view-size", type=int, default=views.VIEW_SIZE)
    pl.add_argument("--yaw-offset", type=parse_yaw_offset_arg, action="append", default=[],
                    help="PASS=DEGREES: turn all eight views of a pass, e.g. head=180 if the operator sits at yaw 0")
    pl.add_argument("--reset-drops", action="store_true",
                    help="ignore the drops and yaw offsets in an existing cut_plan.json and start from the defaults")
    sub.add_parser("preview", help="sheet per pass with all eight views at six moments")
    c = sub.add_parser("cut", help="cut every planned view")
    c.add_argument("--no-blur", action="store_true", help="take the frame nearest each sample time")
    args = ap.parse_args(argv)

    plan_path = args.work / "cut_plan.json"
    if args.cmd == "plan":
        ingest = json.loads((args.work / "ingest.json").read_text())
        drops: dict[str, tuple[str, ...]] = {}
        yaws: dict[str, float] = {}
        if args.reset_drops:
            print("reset: drops and yaw offsets are back to the defaults")
        elif plan_path.exists():
            # A re-plan (for a different --positions, say) must not silently undo what the operator set.
            try:
                drops, yaws = carried_settings(json.loads(plan_path.read_text()))
                kept = describe_edits({p: d for p, d in drops.items() if p not in dict(args.drop)},
                                      {p: y for p, y in yaws.items() if p not in dict(args.yaw_offset)})
                print(f"carried over from {plan_path.name}: {'; '.join(kept) or 'nothing (all defaults)'} "
                      "(--reset-drops to start again)")
            except (ValueError, KeyError):
                print(f"{plan_path.name} could not be read, so nothing is carried over")
        drops.update(dict(args.drop))
        yaws.update(dict(args.yaw_offset))
        plan = build_plan(ingest, args.positions, drops, args.window, args.view_size, yaws)
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        print(plan_summary(plan))
        print(f"plan written: {plan_path}")
        return 0
    plan = json.loads(plan_path.read_text())
    try:
        if args.cmd == "preview":
            for path in preview(plan, args.capture, args.work):
                print(f"preview: {path}")
            return 0
        record = cut(plan, args.capture, args.work, blur=not args.no_blur)
    except MediaError as exc:
        print(f"ERROR  {exc}")
        return 1
    n = sum(len(f["views"]) for f in record["frames"])
    print(f"{n} images in {args.work / 'images' / 'rig'}; frames.json and rig_config.json written")
    return 0


if __name__ == "__main__":
    sys.exit(main())

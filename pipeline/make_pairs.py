"""Image-pair lists for COLMAP's matches_importer, for when retrieval is unavailable or a pass fails.

    uv run python make_pairs.py anchors > work/colmap/pairs-anchors.txt   # links the passes without a vocab tree
    uv run python make_pairs.py pass head > work/pairs-head.txt          # every pair inside one pass

Sequential matching only links neighbours in time, so on its own it never ties one pass to another.
The anchors list does: every third sphere of each pass is matched, all views against all views, with
the anchors of every other pass and with the pano; the phone stills are matched with each other and
with the head pass's anchors.
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import views


def image_names(frame: dict) -> list[str]:
    return [f"rig/{views.VIEW_BY_TOKEN[t].name}/{frame['name']}.jpg" for t in frame["views"]]


def _pairs_between(a: list[str], b: list[str]) -> set[tuple[str, str]]:
    return {tuple(sorted((x, y))) for x in a for y in b if x != y}


def anchor_pairs(frames: list[dict], phone: list[str], every: int = 3) -> list[tuple[str, str]]:
    groups: dict[str, list[str]] = {}
    for f in frames:
        if f["pass"] == "pano" or f["sample"] % every == 0:
            groups.setdefault(f["pass"], []).extend(image_names(f))
    pairs: set[tuple[str, str]] = set()
    for g1, g2 in combinations(sorted(groups), 2):
        pairs |= _pairs_between(groups[g1], groups[g2])
    pairs |= {tuple(sorted(p)) for p in combinations(phone, 2)}
    pairs |= _pairs_between(phone, groups.get("head", []))
    return sorted(pairs)


def pass_pairs(frames: list[dict], name: str) -> list[tuple[str, str]]:
    imgs = [n for f in frames if f["pass"] == name for n in image_names(f)]
    if not imgs:
        raise ValueError(f"no frames for pass '{name}' in frames.json")
    return sorted(tuple(sorted(p)) for p in combinations(imgs, 2))


def phone_names(images: Path) -> list[str]:
    root = images / "phone"
    return sorted(str(p.relative_to(images)) for p in root.rglob("*.jpg")) if root.exists() else []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=Path("work"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("anchors")
    a.add_argument("--every", type=int, default=3)
    a.add_argument("--no-phone", action="store_true")
    p = sub.add_parser("pass")
    p.add_argument("name", choices=["raised", "head", "hip", "key"])
    args = ap.parse_args(argv)
    frames = json.loads((args.work / "frames.json").read_text())["frames"]
    if args.cmd == "anchors":
        phone = [] if args.no_phone else phone_names(args.work / "images")
        pairs = anchor_pairs(frames, phone, args.every)
    else:
        pairs = pass_pairs(frames, args.name)
    sys.stdout.write("".join(f"{x} {y}\n" for x, y in pairs))
    print(f"{len(pairs)} pairs", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

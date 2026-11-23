"""The files the page loads: work/export/v1/ (SPZ splats, coastline.json, scene.json) and the MEDIA.md rows.

    uv run python export.py --world WORLD_ID [--out work/export/v1] [--prefix herebeink/v1/]
                            [--allow-failed-gate "REASON"]

- measured.spz from measured.ply, less what lies in the sealed doorway past the door plane (door_edge.py); measured-preview.spz from 40,000 of its splats drawn with probability
  in proportion to opacity (the preview is what loads first, so it spends its splats on solid surfaces);
  measured-phone.spz the same way from 300,000, which phones load in place of the full file (only when the
  room has more splats than that; a smaller room's phone file would be the full one again);
  overlap.spz and imagined.spz from provenance.py's files. Every file stays in its own frame; scene.json
  gives each a matrix into the world frame (see splats.py for why).
- sha256 and byte size of every file into scene.json, MEDIA.md and media_manifest.json (which
  upload_media.py reads). scene.json is checked against schema/scene.schema.json before it is written.
- Every matrix must be a proper similarity. A mirrored alignment (Marble's raw axes left-handed against
  the world's) is baked into the Marble files instead (splats.mirror_x), because three.js decomposes a
  mirrored matrix into a negative scale and Spark then draws the world wrongly.
- Hand edits live in work/overrides.json (filmPath, light, start) and are merged into scene.json on every
  export. A re-export removes only the files the previous export wrote (listed beside the folder in
  <out>.files.json), so anything else in the folder stays.
- Gate A must have passed; --allow-failed-gate "reason" exports anyway and records the reason in scene.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

import door_edge
import schema_check
import spz
import splats

PREVIEW_SPLATS = 40_000
# An iPhone 15 Pro holding all 1.2 M splats of the real room ran 42-56 ms a frame whatever the pixel ratio or
# the splats drawn, and often never finished loading; its cost follows the splats loaded, so phones get fewer.
PHONE_SPLATS = 300_000
CREDIT = "The imagined half was generated with Marble by World Labs, through its World API."
MEASURED_SOURCE = ("Gaussian splat trained with LichtFeld Studio on views cut from three 360-degree video passes, "
                   "posed with COLMAP")
TYPES = {".spz": "application/octet-stream", ".json": "application/json"}
LIGHT_TILT_DEG = 35.0
OVERRIDE_KEYS = ("filmPath", "light", "start")
# SPZ stores positions as 24-bit fixed point with 12 fractional bits in the file's own units, so it clamps at
# +-2048; the margin keeps clear of the last bits.
SPZ_MAX_UNITS = 2000.0
SCHEMA_MINOR = 2


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def preview(measured: Path, dest: Path, n: int = PREVIEW_SPLATS, seed: int = 0) -> int:
    ply = splats.read(measured)
    op = splats.opacity(ply)
    k = min(n, len(op))
    pick = np.random.default_rng(seed).choice(len(op), k, replace=False, p=op / op.sum())
    return splats.write_subset(ply, np.sort(pick), dest)


def yaw_towards(d: np.ndarray) -> float:
    """Yaw in degrees about +y, 0 looking along -z (three.js's camera default, Euler order YXZ)."""
    return float(np.degrees(np.arctan2(-d[0], -d[2])))


# How far past the door the film turns round: the full distance when nothing is in the way, otherwise the clearance
# short of the first Marble splat within the corridor about its walk line at eye height, never under the minimum.
FILM_PAST_M = 1.2
FILM_CLEARANCE_M = 0.25
FILM_MIN_PAST_M = 0.4
FILM_CORRIDOR_M = 0.2


def turn_distance(centre: np.ndarray, out: np.ndarray, eye: float, marble_centres: np.ndarray) -> float:
    rel = np.asarray(marble_centres, float).reshape(-1, 3) - np.array([centre[0], eye, centre[2]])
    along = rel @ out
    aside = np.linalg.norm(rel - np.outer(along, out), axis=1)
    hits = along[(along > 0) & (aside < FILM_CORRIDOR_M)]
    if not len(hits):
        return FILM_PAST_M
    return float(np.clip(hits.min() - FILM_CLEARANCE_M, FILM_MIN_PAST_M, FILM_PAST_M))


def film_path(start: dict, door: dict, eye: float, marble_centres: np.ndarray) -> list[dict]:
    """The film walks to the door, through it and turns round, short of the first Marble splat on its walk line:
    a turn inside the splats looks back at blank paper."""
    centre, out = np.array(door["centre"]), np.array(door["outward"])
    before = centre - 0.8 * out
    past = centre + turn_distance(centre, out, eye, marble_centres) * out
    ahead = yaw_towards(out)
    back = yaw_towards(-out)
    at = lambda p: [round(float(p[0]), 3), eye, round(float(p[2]), 3)]  # noqa: E731
    return [
        {"t": 0.0, "position": start["position"], "yawDeg": start["yawDeg"], "pitchDeg": 0.0},
        {"t": 4.0, "position": at(before), "yawDeg": round(ahead, 3), "pitchDeg": -8.0},
        {"t": 8.0, "position": at(past), "yawDeg": round(ahead, 3), "pitchDeg": -8.0},
        {"t": 11.0, "position": at(past), "yawDeg": round(back, 3), "pitchDeg": 0.0},
        {"t": 15.0, "position": at(before), "yawDeg": round(back, 3), "pitchDeg": 0.0},
    ]


def light_direction(door: dict) -> list[float]:
    """Light comes in through the doorway and down, unless the room has a window (then set it by hand)."""
    inward = -np.array(door["outward"], float)
    a = np.radians(LIGHT_TILT_DEG)
    d = np.cos(a) * inward + np.sin(a) * np.array([0.0, -1.0, 0.0])
    return [round(float(x), 6) for x in d / np.linalg.norm(d)]


def splat_entry(path: Path, ply_count: int, provenance: float, matrix: np.ndarray) -> dict:
    h = spz.header(path)
    if h["splats"] != ply_count:
        raise ValueError(f"{path.name} holds {h['splats']} splats, its PLY {ply_count}")
    return {"url": path.name, "sha256": sha256(path), "bytes": path.stat().st_size, "splats": h["splats"],
            "shDegree": h["shDegree"], "provenance": provenance, "matrix": splats.column_major(matrix)}


def alignment_block(align: dict, res: dict, mirrored: bool, allow_failed_gate: str | None) -> dict:
    gate = align["gateA"]
    block = {"medianCm": res["medianCm"], "p90Cm": res["p90Cm"], "icpSet": res["icpSet"],
             "gateAPass": bool(gate["pass"]), "note": align["note"], "mirrorBaked": mirrored}
    if align.get("mode"):
        block["mode"] = align["mode"]
    if align.get("hypothesis"):
        block["hypothesis"] = align["hypothesis"]
    for key in ("gravity", "photometric", "icpShare", "metricRatio"):
        if key in gate:
            block[key] = gate[key]
    if gate.get("acceptedByEye"):
        block["acceptedByEye"] = gate["acceptedByEye"]
    if allow_failed_gate:
        block["failedGateAllowed"] = allow_failed_gate
    return block


def update_media_md(media_md: Path, rows: list[tuple[str, str, int]], day: str) -> None:
    text = media_md.read_text() if media_md.exists() else (
        "# Media\n\n| Object | sha256 | Bytes | Date |\n|---|---|---|---|\n")
    lines = text.rstrip("\n").split("\n")
    keys = {r[0] for r in rows}
    lines = [ln for ln in lines if not (ln.startswith("| ") and ln.split("|")[1].strip() in keys)]
    lines += [f"| {key} | {sha} | {size} | {day} |" for key, sha, size in rows]
    media_md.write_text("\n".join(lines) + "\n")


def read_overrides(work: Path) -> dict:
    path = work / "overrides.json"
    if not path.exists():
        return {}
    o = json.loads(path.read_text())
    unknown = set(o) - set(OVERRIDE_KEYS)
    if unknown:
        raise ValueError(f"overrides.json: unknown key(s) {sorted(unknown)}; it takes {', '.join(OVERRIDE_KEYS)}")
    return o


def check_spz_range(path: Path) -> None:
    c = splats.centres(splats.read(path, quiet=True))
    worst = float(np.abs(c).max()) if len(c) else 0.0
    if worst > SPZ_MAX_UNITS:
        raise ValueError(f"{path.name} has a coordinate of {worst:.0f} in its own units; SPZ clamps positions at +-2048. "
                         "Rescale the file (divide x, y, z and the log scales' exponent by a factor k, so add -ln k to "
                         "scale_0..2) and multiply the matrix's scale by k")


def previous_outputs(out: Path) -> Path:
    return out.parent / f"{out.name}.files.json"


def clear_previous(out: Path) -> None:
    record = previous_outputs(out)
    if record.exists():
        for name in json.loads(record.read_text())["files"]:
            (out / name).unlink(missing_ok=True)
    out.mkdir(parents=True, exist_ok=True)


def export(work: Path, world_id: str, out: Path, prefix: str, media_md: Path | None, now: datetime | None = None,
           allow_failed_gate: str | None = None, phone_splats: int = PHONE_SPLATS) -> dict:
    now = now or datetime.now(timezone.utc)
    scale = json.loads((work / "scale.json").read_text())
    align = json.loads((work / "align" / world_id / "align.json").read_text())
    floor = json.loads((work / "floor.json").read_text())
    counts = json.loads((work / "provenance" / world_id / "counts.json").read_text())
    world = json.loads((work / "marble" / f"{world_id}.json").read_text())
    overrides = read_overrides(work)
    gate = align["gateA"]
    if not gate["pass"] and not allow_failed_gate:
        raise ValueError("Gate A failed (" + "; ".join(gate.get("reasons") or ["see align.json"]) + "); nothing exported. "
                         "The kill rule's next stage, or export.py --allow-failed-gate \"reason\" to export anyway")
    w_from_c, w_from_m = np.array(scale["world_from_colmap"]), np.array(align["world_from_marble"])
    mirrored = splats.parity(w_from_m) < 0
    if mirrored:
        w_from_m = w_from_m @ np.diag([-1.0, 1.0, 1.0, 1.0])
    for name, m in (("world_from_colmap", w_from_c), ("world_from_marble", w_from_m)):
        problem = splats.similarity_problem(m)
        if problem:
            raise ValueError(f"{name} {problem}; the viewer can only place a file with a similarity")
    prov = work / "provenance" / world_id

    clear_previous(out)
    staging = out.parent / f"{out.name}-ply"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    measured_ply = splats.read(work / "splat" / "measured.ply", quiet=True)
    trimmed = door_edge.sealed(splats.apply(w_from_c, splats.centres(measured_ply)), scale)
    splats.write_subset(measured_ply, ~trimmed, staging / "measured.ply")
    n_preview = preview(staging / "measured.ply", staging / "measured-preview.ply")
    sources = {"measured": staging / "measured.ply", "measured-preview": staging / "measured-preview.ply",
               "overlap": prov / "overlap.ply", "imagined": prov / "imagined.ply"}
    n_phone = None
    if splats.count(sources["measured"]) > phone_splats:
        n_phone = preview(sources["measured"], staging / "measured-phone.ply", n=phone_splats, seed=1)
        sources["measured-phone"] = staging / "measured-phone.ply"
    if mirrored:
        for name in ("overlap", "imagined"):
            ply = splats.read(sources[name], quiet=True)
            splats.write_subset(ply, np.ones(len(ply["vertex"].data), bool), staging / f"{name}.ply",
                                rows=splats.mirror_x(ply["vertex"].data))
            sources[name] = staging / f"{name}.ply"
    for src in sources.values():
        check_spz_range(src)
    spz.transcode([(src, out / f"{name}.spz") for name, src in sources.items()])
    n = {name: splats.count(src) for name, src in sources.items()}

    shutil.copy2(work / "coastline.json", out / "coastline.json")
    coast = json.loads((out / "coastline.json").read_text())
    schema_check.check(coast, "coastline.schema.json")
    door = scale["door"]
    res = align["residual"]
    marble_world = np.concatenate([splats.apply(np.array(align["world_from_marble"]), splats.centres(splats.read(prov / f"{k}.ply", quiet=True)))
                                   for k in ("overlap", "imagined")])
    scene = {
        "schemaVersion": 1,
        "schemaMinor": SCHEMA_MINOR,
        "generatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "units": "m",
        "frame": {"up": [0.0, 1.0, 0.0], "floorY": 0.0, "longAxis": [1.0, 0.0, 0.0]},
        "splats": {
            "measured": splat_entry(out / "measured.spz", n["measured"], 0, w_from_c),
            "measuredPreview": splat_entry(out / "measured-preview.spz", n["measured-preview"], 0, w_from_c),
            "overlap": splat_entry(out / "overlap.spz", n["overlap"], 0.5, w_from_m),
            "imagined": splat_entry(out / "imagined.spz", n["imagined"], 1, w_from_m),
        },
        "radiiM": dict(counts["radiiM"]),
        "floor": {"normal": [0.0, 1.0, 0.0], "y": 0.0},
        "walkable": {"polygons": floor["walkable"], "dilationM": floor["dilationM"]},
        "eyeHeightM": scale["eye_height_m"],
        "start": scale["start"],
        "door": {"centre": [round(float(x), 4) for x in door["centre"]],
                 "widthM": round(float(np.linalg.norm(np.array(door["a"]) - np.array(door["b"]))), 4),
                 "outward": [round(float(x), 6) for x in door["outward"]]},
        "filmPath": film_path(scale["start"], door, scale["eye_height_m"], marble_world),
        "light": {"direction": light_direction(door)},
        "coastline": {"url": "coastline.json", "sha256": sha256(out / "coastline.json"),
                      "bytes": (out / "coastline.json").stat().st_size, "stretches": len(coast["polylines"]),
                      "lengthM": coast["lengthM"]},
        "counts": {"measured": n["measured"], "measuredPreview": n_preview, "marble": counts["marble"],
                   "covered": counts["covered"], "overlap": counts["overlap"], "imagined": counts["imagined"]},
        "alignment": alignment_block(align, res, mirrored, allow_failed_gate),
        "sources": {"measured": MEASURED_SOURCE,
                    "imagined": {"provider": "World Labs", "model": str(world.get("model") or align.get("model") or "marble"),
                                 "worldId": world_id}},
        "credit": CREDIT,
    }
    if n_phone is not None:
        scene["splats"]["measuredPhone"] = splat_entry(out / "measured-phone.spz", n["measured-phone"], 0, w_from_c)
        scene["counts"]["measuredPhone"] = n_phone
    if scale.get("evidence"):
        scene["scaleEvidence"] = scale["evidence"]
    scene.update(overrides)
    schema_check.check(scene, "scene.schema.json")
    (out / "scene.json").write_text(json.dumps(scene, indent=1, allow_nan=False) + "\n")
    written = sorted([f"{name}.spz" for name in sources] + ["coastline.json", "scene.json"])
    previous_outputs(out).write_text(json.dumps({"files": written}, indent=1) + "\n")

    items = []
    for p in (out / name for name in written):
        items.append({"key": prefix + p.name, "path": p.name, "bytes": p.stat().st_size, "sha256": sha256(p),
                      "content_type": TYPES[p.suffix]})
    (out.parent / "media_manifest.json").write_text(json.dumps({"prefix": prefix, "root": out.name, "items": items}, indent=1) + "\n")
    if media_md is not None:
        update_media_md(media_md, [(i["key"], i["sha256"], i["bytes"]) for i in items], now.date().isoformat())
    return scene


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--world", required=True)
    ap.add_argument("--out", type=Path, default=None, help="default work/export/v1")
    ap.add_argument("--prefix", default="herebeink/v1/")
    ap.add_argument("--media-md", type=Path, default=Path("../MEDIA.md"))
    ap.add_argument("--no-media-md", action="store_true")
    ap.add_argument("--allow-failed-gate", default=None, metavar="REASON",
                    help="export although Gate A failed (the kill rule's side-by-side stage); recorded in scene.json")
    args = ap.parse_args(argv)
    out = args.out or args.work / "export" / "v1"
    try:
        scene = export(args.work, args.world, out, args.prefix, None if args.no_media_md else args.media_md,
                       allow_failed_gate=args.allow_failed_gate)
    except ValueError as e:
        print(f"export refused: {e}", file=sys.stderr)
        return 1
    total = 0
    for name, entry in scene["splats"].items():
        total += entry["bytes"]
        print(f"{entry['url']:22s} {entry['splats']:9d} splats  {entry['bytes'] / 1e6:7.2f} MB  SH {entry['shDegree']}  {entry['sha256'][:12]}")
    c = scene["counts"]
    print(f"total {total / 1e6:.2f} MB; Marble {c['marble']} = covered {c['covered']} + overlap {c['overlap']} + imagined {c['imagined']}")
    print(f"coastline {scene['coastline']['stretches']} stretch(es), {scene['coastline']['lengthM']:.2f} m; "
          f"alignment median {scene['alignment']['medianCm']:.2f} cm")
    print(f"written: {out}/ (scene.json checked against the schema), {out.parent / 'media_manifest.json'}"
          + ("" if args.no_media_md else f", rows in {args.media_md}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

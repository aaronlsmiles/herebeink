"""The ladder's files for the page: per placed rung, Marble's splats split into seen, imagined and wrong (SPZ,
each in Marble's own frame with its matrix), lighter phone files, the map's seen floor and coastline, and one
ladder.json for the viewer (web/src/ladder contract, pipeline/schema/ladder.schema.json).

    uv run python ladder_export.py          # after ladder.py: writes work/export/ladder/ and its media manifest

ladder.json carries only coverage numbers (what each rung was shown, how much of its world is imagined, and
how far the scan agrees with itself); right, wrong and completeness stay in work/ladder/ (stance A).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

import coastline
import export
import grid2d
import ladder
import ladder_views as lv
import schema_check
import spz
import splats
import visibility as vis

WORK = ladder.WORK
PHONE_SPLATS = 300_000
FILES = ("seen", "imagined", "wrong")
PROVENANCE = {"seen": 0, "imagined": 1, "wrong": 1}
LABELS = {"R1": "1 photo", "R2": "2 photos", "R4": "4 photos", "R4b": "4 photos (second seed)", "R8": "8 photos",
          "R4r": "4 photos, reconstruction mode", "P": "the 360 still"}
PHOTOS = {"R1": 1, "R2": 2, "R4": 4, "R4b": 4, "R8": 8, "R4r": 4, "P": 0}
MODES = {"R1": "flat", "R2": "flat", "R4": "flat", "R4b": "flat", "R8": "reconstruction", "R4r": "reconstruction", "P": "pano"}
STEPS = ["R1", "R2", "R4", "R8", "P"]
PREFIX = "herebeink/v3/ladder/"


def phone_pick(classes: np.ndarray, n: int = PHONE_SPLATS, seed: int = 3) -> np.ndarray:
    """A seeded random share of every class in proportion, n in all; Marble writes splats in no spatial order."""
    if len(classes) <= n:
        return np.ones(len(classes), bool)
    keep = np.zeros(len(classes), bool)
    keep[np.random.default_rng(seed).choice(len(classes), n, replace=False)] = True
    return keep


def rung_map(xyz: np.ndarray, op: np.ndarray, classes: np.ndarray, c_world: np.ndarray) -> dict:
    """Seen floor and where it ends with Marble's imagined floor carrying on, as Part 1's coastline traces it."""
    solid = op >= coastline.SOLID_OPACITY
    seen, imag = xyz[solid & (classes == ladder.SEEN)], xyz[solid & (classes != ladder.SEEN)]
    if len(coastline.floor_band(seen, *coastline.MEASURED_FLOOR_BAND_M)) < 10:
        return {"seenFloor": [], "coastline": []}
    tr = coastline.trace(seen, imag, np.array([c_world[[0, 2]]]))
    return {"seenFloor": grid2d.polygons(tr["grid"], tr["covered"]),
            "coastline": [[[round(float(x), 4), round(float(z), 4)] for x, z in xz] for xz, _, _ in tr["lines"]]}


def write_rung(work: Path, rung: str, r: dict, ctx: dict, out_root: Path | None = None) -> None:
    out = (out_root or work / "export" / "ladder") / rung
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    staging = out.parent / f"{rung}-ply"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    ply, t, k = r["_ply"], np.array(r["_t"]), r["_classes"]
    rows = ply["vertex"].data
    if splats.parity(t) < 0:
        t = t @ np.diag([-1.0, 1.0, 1.0, 1.0])
        rows = splats.mirror_x(rows)
    phone = phone_pick(k)
    jobs, counts = [], {}
    for i, name in enumerate(FILES):
        for suffix, keep in (("", k == i), ("-phone", (k == i) & phone)):
            p = staging / f"{name}{suffix}.ply"
            counts[name + suffix] = splats.write_subset(ply, keep, p, rows=rows)
            export.check_spz_range(p)
            jobs.append((p, out / f"{name}{suffix}.spz"))
    spz.transcode(jobs)
    entries = {}
    for suffix, key in (("", "splats"), ("-phone", "splatsPhone")):
        entries[key] = {name: {**export.splat_entry(out / f"{name}{suffix}.spz", counts[name + suffix], PROVENANCE[name], t),
                               "url": f"{rung}/{name}{suffix}.spz"} for name in FILES}
    doc = {**entries, "map": rung_map(r["_xyz"], r["_op"], k, ctx["pose"].c_world)}
    (out / "files.json").write_text(json.dumps(doc, indent=1) + "\n")
    shutil.rmtree(staging)


def frustums(pose: vis.Pose, manifest: dict, rung: str) -> list[dict]:
    if rung == "P":
        return []
    fov = manifest.get("fov_deg") or {}
    h, v = float(fov.get("h", lv.H_FOV_DEG)), float(fov.get("v", lv.V_FOV_DEG))
    out = []
    for yaw in vis.rung_yaws(manifest, ladder.manifest_rung(rung)):
        f = vis.world_dirs(pose, (Rotation.from_euler("y", yaw, degrees=True).as_matrix() @ np.array([0, 0, 1.0]))[None])[0]
        up = vis.world_dirs(pose, np.array([[0.0, -1.0, 0.0]]))[0]
        out.append({"forward": [round(float(x), 6) for x in f], "up": [round(float(x), 6) for x in up],
                    "hFovDeg": h, "vFovDeg": round(v, 4)})
    return out


def build(work: Path, out: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    scores = json.loads((work / "ladder" / "scores.json").read_text())["rungs"]
    shown = json.loads((work / "ladder" / "visibility.json").read_text())["rungs"]
    manifest = json.loads((work / "ladder" / "views" / "manifest.json").read_text())
    pose = vis.pose_from_work(work)
    rungs = []
    for rung, world_id in ladder.worlds().items():
        s = scores.get(rung)
        if s is None:
            continue
        vr = shown[ladder.manifest_rung(rung)]
        world = json.loads((work / "marble" / f"{world_id}.json").read_text())
        e = {"id": rung, "label": LABELS[rung], "photos": PHOTOS[rung], "mode": MODES[rung], "placed": bool(s["placed"]),
             "shown": vr["shareOfDirections"], "seenShareOfKey": vr["seenShareOfKey"],
             "imagined": s["byTau"][str(ladder.TAU_M)]["imagined"] if s["placed"] else None,
             "keyAgreement": {"within15": s["keyAgreesWithColmap"]["0.15"].get("withinTau") if s["placed"] else None,
                              "within30": s["keyAgreesWithColmap"]["0.3"].get("withinTau") if s["placed"] else None},
             "frustums": frustums(pose, manifest, rung), "worldId": world_id, "model": str(world.get("model") or "marble")}
        files = out / rung / "files.json"
        if s["placed"] and files.exists():
            e.update(json.loads(files.read_text()))
        rungs.append(e)
    doc = {"schemaVersion": 1, "units": "m", "generatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "camera": {"c": [round(float(x), 4) for x in pose.c_world]},
           "steps": [r for r in STEPS if any(e["id"] == r for e in rungs)], "rungs": rungs, "credit": export.CREDIT}
    schema_check.check(doc, "ladder.schema.json")
    (out / "ladder.json").write_text(json.dumps(doc, indent=1, allow_nan=False) + "\n")
    items = []
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.suffix in (".spz", ".json") and p.name != "files.json":
            rel = p.relative_to(out).as_posix()
            items.append({"key": PREFIX + rel, "path": rel, "bytes": p.stat().st_size, "sha256": export.sha256(p),
                          "content_type": export.TYPES[p.suffix]})
    (out.parent / "ladder_media_manifest.json").write_text(json.dumps({"prefix": PREFIX, "root": out.name, "items": items}, indent=1) + "\n")
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=WORK)
    a = ap.parse_args(argv)
    doc = build(a.work, a.work / "export" / "ladder")
    for e in doc["rungs"]:
        print(f"{e['id']:4s} shown {e['shown']:.3f}, imagined {e['imagined'] if e['imagined'] is None else round(e['imagined'], 3)}, "
              f"files {'yes' if 'splats' in e else 'no'}")
    print(f"written: {a.work / 'export' / 'ladder' / 'ladder.json'} and ladder_media_manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

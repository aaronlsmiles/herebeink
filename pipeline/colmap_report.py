"""Check the COLMAP database before matching, and judge the reconstruction after mapping.

    uv run python colmap_report.py db-check            # after rig_configurator: rigs, frames, cameras as planned?
    uv run python colmap_report.py report              # after mapper: -> work/colmap_report.json, PASS or FAIL

An image counts as registered only when it sits in the model AND carries at least MIN_OBS triangulated
points. With a rig, COLMAP places every image of a frame once the frame is placed, so a view whose rig
rotation is wrong still shows as "registered" while seeing almost no points; the per-view check below
is what catches that.

The run passes on spheres, not images (call 57, 20 Nov 2026): a sphere is placed when at least
SOLID_VIEWS of its views are registered. A view of a blank white wall or ceiling sees too few points to
register however well its sphere is placed, so a per-image share measures the room's bare surfaces
rather than the camera track; it is still reported, as a warning.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import sys
from pathlib import Path

import views
from colmap_model import Model, read_model

MIN_OBS = 15
ACCEPT_SHARE = 0.90
KEY_WARN_SHARE = 0.50
PANO_MIN_VIEWS = 4
SOLID_VIEWS = 2
ROOM_GROUPS = ("raised", "head", "hip", "pano")
# Wrong rotations on the synthetic negative control scored under 8 % of the best view's points. Plain
# ceilings in real rooms are expected to score low, but not that low: 10 % against the best view of the
# same pitch catches the former without failing the latter, and a pitch-40 group at under 5 % of the
# level group is a whole row of views looking the wrong way.
SAME_PITCH_MIN = 0.10
PITCH_GROUP_MIN = 0.05
PHONE_REMAP = "PHONE=0 FROM=mapper ./colmap.sh"
FALLBACKS = (
    "denser sampling: cut_views.py plan --positions 150 (keeps your drops and yaw offsets), cut again, ./colmap.sh",
    "exhaustive matching on the failing pass: make_pairs.py pass <name> > work/pairs-<name>.txt, "
    "then EXTRA_PAIRS=work/pairs-<name>.txt FROM=match_extra ./colmap.sh",
    f"phone stills dropped: {PHONE_REMAP}",
    "the pano placed by hand from its views (Part 2's alignment starts from it); log it in LOG.md",
)


def pct(x: float) -> str:
    return f"{x * 100:.0f} %"


def fallbacks(phone_low: bool) -> list[str]:
    """Numbered fallbacks; the phone-less remap leads when the phone stills are what registered badly."""
    order = list(FALLBACKS)
    if phone_low:
        order.insert(0, order.pop(2))
    return [f"{i}. {text}" for i, text in enumerate(order, 1)]


def expected_images(work: Path) -> dict[str, str]:
    """Image name -> group (pass name, 'pano' or 'phone') for everything cut or converted."""
    frames = json.loads((work / "frames.json").read_text())["frames"]
    out = {}
    for f in frames:
        for t in f["views"]:
            out[f"rig/{views.VIEW_BY_TOKEN[t].name}/{f['name']}.jpg"] = f["pass"]
    phone = work / "images" / "phone"
    if phone.exists():
        for p in sorted(phone.rglob("*.jpg")):
            out[str(p.relative_to(work / "images"))] = "phone"
    return out


def db_check(database: Path, work: Path, phone: bool = True) -> list[str]:
    frames = json.loads((work / "frames.json").read_text())["frames"]
    expected = expected_images(work)
    if not phone:
        expected = {k: v for k, v in expected.items() if v != "phone"}
    con = sqlite3.connect(database)
    q = lambda sql: con.execute(sql).fetchall()  # noqa: E731
    problems = []
    names = {r[0] for r in q("select name from images")}
    if names != set(expected):
        problems.append(f"database holds {len(names)} images, {len(expected)} expected "
                        f"({len(set(expected) - names)} missing, {len(names - set(expected))} unexpected)")
    rig_rows = q("select rig_id, count(*) from rig_sensors group by rig_id")
    big = [r for r, n in rig_rows if n == len(views.VIEWS) - 1]  # rig_sensors lists the non-reference cameras
    if len(big) != 1:
        problems.append(f"expected one rig of {len(views.VIEWS)} cameras, found sensor counts {[n for _, n in rig_rows]}")
    else:
        n_frames = q(f"select count(*) from frames where rig_id = {big[0]}")[0][0]
        if n_frames != len(frames):
            problems.append(f"the rig has {n_frames} frames, frames.json lists {len(frames)}")
    n_cams = q("select count(distinct camera_id) from images where name like 'rig/%'")[0][0]
    if n_cams != len(views.VIEWS):
        problems.append(f"the cube views use {n_cams} cameras, expected {len(views.VIEWS)} (one per view folder)")
    params = {r[0] for r in q("select params from cameras where camera_id in "
                              "(select distinct camera_id from images where name like 'rig/%')")}
    if len(params) != 1:
        problems.append("the cube cameras do not share one set of intrinsics")
    con.close()
    return problems


def load_models(model_root: Path) -> list[tuple[Path, Model]]:
    out = []
    for d in sorted(p for p in model_root.iterdir() if p.is_dir() and (p / "images.txt").exists()):
        out.append((d, read_model(d)))
    return out


def report(model_root: Path, work: Path, phone: bool = True) -> dict:
    expected = expected_images(work)
    if not phone:
        expected = {k: v for k, v in expected.items() if v != "phone"}
    models = load_models(model_root)
    if not models:
        return {"pass": False, "reason": "COLMAP produced no model", "models": 0, "fallbacks": fallbacks(False)}
    best_dir, model = max(models, key=lambda m: len(m[1].images))
    by_name = {im.name: im for im in model.images.values()}

    groups: dict[str, dict] = {}
    for name, group in expected.items():
        g = groups.setdefault(group, {"expected": 0, "in_model": 0, "registered": 0})
        g["expected"] += 1
        im = by_name.get(name)
        if im is not None:
            g["in_model"] += 1
            g["registered"] += im.n_obs >= MIN_OBS
    for g in groups.values():
        g["share"] = round(g["registered"] / g["expected"], 4) if g["expected"] else 0.0

    per_view = {}
    for v in views.VIEWS:
        obs = [im.n_obs for im in model.images.values() if im.name.startswith(f"rig/{v.name}/")]
        per_view[v.name] = {"images": len(obs), "median_obs": statistics.median(obs) if obs else 0, "pitch": v.pitch}
    judged = {n: pv for n, pv in per_view.items() if pv["images"] >= 3}
    weak_views = []
    for pitch in sorted({pv["pitch"] for pv in judged.values()}):
        same = {n: pv["median_obs"] for n, pv in judged.items() if pv["pitch"] == pitch}
        best = max(same.values())
        weak_views += [n for n, m in same.items() if best and m < SAME_PITCH_MIN * best]
    level = [pv["median_obs"] for pv in judged.values() if pv["pitch"] == 0]
    raised = [pv["median_obs"] for pv in judged.values() if pv["pitch"] != 0]
    pitch_groups = {"level_median": statistics.median(level) if level else None,
                    "pitched_median": statistics.median(raised) if raised else None, "ratio": None}
    if level and raised and pitch_groups["level_median"]:
        pitch_groups["ratio"] = round(pitch_groups["pitched_median"] / pitch_groups["level_median"], 4)
    pitched_low = pitch_groups["ratio"] is not None and pitch_groups["ratio"] < PITCH_GROUP_MIN

    pano_names = [n for n, g in expected.items() if g == "pano"]
    pano_in = [n for n in pano_names if n in by_name]
    pano_reg = [n for n in pano_in if by_name[n].n_obs >= MIN_OBS]
    pano_ok = bool(pano_names) and len(pano_in) == len(pano_names) and len(pano_reg) >= min(PANO_MIN_VIEWS, len(pano_names))

    frames = json.loads((work / "frames.json").read_text())["frames"]
    room_frames = [f for f in frames if f["pass"] in ROOM_GROUPS]
    placed = 0
    for f in room_frames:
        names = [f"rig/{views.VIEW_BY_TOKEN[t].name}/{f['name']}.jpg" for t in f["views"]]
        good = sum(1 for n in names if n in by_name and by_name[n].n_obs >= MIN_OBS)
        placed += good >= min(SOLID_VIEWS, len(names))
    sphere_share = placed / len(room_frames) if room_frames else 0.0
    spheres = {"expected": len(room_frames), "placed": placed, "share": round(sphere_share, 4)}

    total = sum(g["expected"] for g in groups.values())
    registered = sum(g["registered"] for g in groups.values())
    room = [g for name, g in groups.items() if name in ROOM_GROUPS]
    room_expected = sum(g["expected"] for g in room)
    room_registered = sum(g["registered"] for g in room)
    share = room_registered / room_expected if room_expected else 0.0

    reasons = []
    if sphere_share <= ACCEPT_SHARE:
        reasons.append(f"only {placed} of {len(room_frames)} room spheres ({sphere_share:.1%}; passes raised, head, hip, "
                       f"and the pano) have {SOLID_VIEWS} or more views seeing {MIN_OBS}+ points "
                       f"(need over {pct(ACCEPT_SHARE)})")
    if not pano_ok:
        reasons.append(f"the pano is not in the model with at least {PANO_MIN_VIEWS} views seeing points "
                       f"({len(pano_in)} of {len(pano_names)} in the model, {len(pano_reg)} seeing points)")
    if weak_views:
        reasons.append(f"views {', '.join(weak_views)} see under {pct(SAME_PITCH_MIN)} of the points the best view at the "
                       "same pitch sees: check the rig rotations (tests/test_rig_convention.py) before anything else")
    if pitched_low:
        reasons.append(f"the pitch-40 views see only {pitch_groups['ratio']:.1%} of the points the level views see "
                       f"(at least {pct(PITCH_GROUP_MIN)} expected, even under a plain ceiling): "
                       "check the rig rotations (tests/test_rig_convention.py) before anything else")

    warnings = []
    if share <= ACCEPT_SHARE:
        warnings.append(f"{share:.1%} of the room images see {MIN_OBS} or more points (blank walls and ceilings see "
                        "few); the spheres decide the run (call 57)")
    key, phone_group = groups.get("key"), groups.get("phone")
    if key and key["share"] < ACCEPT_SHARE:
        warnings.append(f"answer key pass: {key['share']:.1%} of its images registered (below {pct(ACCEPT_SHARE)}); "
                        "it does not fail the run")
        if key["share"] < KEY_WARN_SHARE:
            warnings.append(f"answer key under {pct(KEY_WARN_SHARE)} registered ({key['share']:.1%}): Part 2 scores against "
                            "this pass, so it cannot be scored properly until more of it registers")
    phone_low = bool(phone_group and phone_group["share"] < ACCEPT_SHARE)
    if phone_low:
        warnings.append(f"phone stills: {phone_group['share']:.1%} registered (below {pct(ACCEPT_SHARE)}); "
                        f"to map without them: {PHONE_REMAP}")
    return {
        "pass": not reasons, "reasons": reasons, "warnings": warnings,
        # Relative to work/, so the export finds it from any directory.
        "model_dir": Path(os.path.relpath(best_dir.resolve(), work.resolve())).as_posix(), "models": len(models),
        "other_model_sizes": sorted((len(m.images) for d, m in models if d != best_dir), reverse=True),
        "images_expected": total, "images_registered": registered,
        "room_images_expected": room_expected, "room_images_registered": room_registered,
        "share_registered": round(share, 4), "spheres": spheres,
        "min_obs": MIN_OBS, "groups": groups, "per_view": per_view, "weak_views": weak_views,
        "pitch_groups": pitch_groups,
        "pano": {"views": len(pano_names), "in_model": len(pano_in), "seeing_points": len(pano_reg), "ok": pano_ok},
        "mean_reprojection_error_px": round(model.mean_reprojection_error(), 4), "points": len(model.points),
        "fallbacks": [] if not reasons else fallbacks(phone_low),
    }


def print_report(r: dict) -> None:
    if r.get("models", 0) == 0:
        print("FAIL: COLMAP produced no model")
        return
    print(f"models: {r['models']} (largest used: {r['model_dir']}; others: {r['other_model_sizes'] or 'none'})")
    print(f"{'group':8s} {'expected':>8s} {'in model':>9s} {'registered':>11s} {'share':>7s}")
    for name, g in r["groups"].items():
        print(f"{name:8s} {g['expected']:8d} {g['in_model']:9d} {g['registered']:11d} {g['share']:7.1%}")
    print("median points seen per view: " + ", ".join(f"{n} {pv['median_obs']:.0f}" for n, pv in r["per_view"].items()))
    p = r["pano"]
    print(f"pano: {p['in_model']} of {p['views']} views in the model, {p['seeing_points']} seeing points")
    print(f"mean reprojection error: {r['mean_reprojection_error_px']:.3f} px over {r['points']} points")
    print(f"room images (raised, head, hip, pano) registered with at least {r['min_obs']} points: "
          f"{r['room_images_registered']} of {r['room_images_expected']} = {r['share_registered']:.1%}")
    sp = r["spheres"]
    print(f"room spheres placed ({SOLID_VIEWS}+ views seeing {r['min_obs']}+ points): "
          f"{sp['placed']} of {sp['expected']} = {sp['share']:.1%}")
    for w in r["warnings"]:
        print(f"WARN: {w}")
    if r["pass"]:
        print(f"PASS: one model, over {pct(ACCEPT_SHARE)} of the room spheres placed, the pano in it")
    else:
        print("FAIL: " + "; ".join(r["reasons"]))
        print("fallbacks, in order (log each attempt in LOG.md):")
        for f in r["fallbacks"]:
            print(f"  {f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--no-phone", action="store_true", help="the run left the phone stills out")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("db-check")
    sub.add_parser("report")
    args = ap.parse_args(argv)
    if args.cmd == "db-check":
        problems = db_check(args.work / "colmap" / "database.db", args.work, phone=not args.no_phone)
        for p in problems:
            print(f"ERROR  {p}")
        print("db-check: " + ("FAIL" if problems else "PASS"))
        return 1 if problems else 0
    r = report(args.work / "colmap" / "sparse_txt", args.work, phone=not args.no_phone)
    (args.work / "colmap_report.json").write_text(json.dumps(r, indent=2) + "\n")
    print_report(r)
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

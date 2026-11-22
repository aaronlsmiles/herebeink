"""Archive Marble worlds before World Labs ends the service: world JSON, pano, thumbnail, collider
mesh and the free full_res PLY export, into work/marble/archive/<world_id>/.

Only free calls are made (GET a world, the splat PLY export, plain downloads of URLs the API
returned). The mesh export, which costs credits, is never requested. Nothing here prints or saves a
signed URL: saved JSON has its query strings stripped.
"""

import argparse
import json
import sys
from pathlib import Path

import marble
from marble import ID_RE, Refusal, strip_queries

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".glb"}


def world_ids(marble_dir):
    """Ids of the worlds whose JSON sits in work/marble: <uuid>.json, nothing else."""
    ids = []
    for p in sorted(Path(marble_dir).glob("*.json")):
        if ID_RE.match(p.stem) and p.stem.count("-") == 4:
            ids.append(p.stem)
    return ids


def _ext(url, default):
    ext = Path(marble.strip_query(url)).suffix.lower()
    return ext if ext in ALLOWED_EXT else default


def asset_files(world):
    """(file name, url) for each asset the world response carries; absent or null ones are skipped."""
    assets = world.get("assets") or {}
    wanted = [
        ("pano", (assets.get("imagery") or {}).get("pano_url"), ".png"),
        ("thumbnail", assets.get("thumbnail_url"), ".jpg"),
        ("collider", (assets.get("mesh") or {}).get("collider_mesh_url"), ".glb"),
    ]
    return [(name + _ext(url, default), url) for name, url, default in wanted if url]


def _world_body(body):
    return body.get("world", body) if isinstance(body, dict) else {}


def archive_world(world_id, key, out_root, log=print):
    """Returns {file: size or error text}. One failed file never stops the rest."""
    if not ID_RE.match(world_id):
        raise Refusal("world id has an unexpected shape")
    dest = Path(out_root) / world_id
    dest.mkdir(parents=True, exist_ok=True)
    result = {}
    world = _world_body(marble._api("GET", f"/marble/v1/worlds/{world_id}", key).json())
    (dest / "world.json").write_text(json.dumps(strip_queries(world), indent=2, sort_keys=True) + "\n")
    result["world.json"] = (dest / "world.json").stat().st_size

    for name, url in asset_files(world):
        try:
            marble._download(url, dest / name)
            result[name] = (dest / name).stat().st_size
        except Refusal as e:
            result[name] = f"FAILED: {e}"

    try:
        body = {"asset_type": "splats", "format": "ply", "resolution": "full_res"}
        r = marble._api("POST", f"/marble/v1/worlds/{world_id}:export", key, json=body)
        url = marble.export_url(r.json())
        if not url:
            raise Refusal("export response had no download url")
        marble._download(url, dest / "splats_full_res.ply")
        result["splats_full_res.ply"] = (dest / "splats_full_res.ply").stat().st_size
    except Refusal as e:
        result["splats_full_res.ply"] = f"FAILED: {e}"
    for name, v in result.items():
        log(f"  {world_id[:8]} {name}: {v}")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("world_id", nargs="*", help="default: every world with a JSON in work/marble/")
    a = ap.parse_args(argv)
    try:
        marble._need_clean()
        key = marble._need_key()
        before = marble.get_balance(key)
        ids = a.world_id or world_ids(marble.work_dir())
        out = marble.work_dir() / "archive"
        failed = 0
        for wid in ids:
            res = archive_world(wid, key, out)
            failed += sum(1 for v in res.values() if isinstance(v, str))
        after = marble.get_balance(key)
        print(f"balance before {before}, after {after}")
        if after != before:
            print("archive_worlds: BALANCE CHANGED", file=sys.stderr)
            return 3
        return 1 if failed else 0
    except Refusal as e:
        print(f"archive_worlds: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

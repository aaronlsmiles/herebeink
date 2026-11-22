# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3==1.40.0"]
# ///
"""Upload work/export/v1/ to R2 under herebeink/v1/, and check it. Not run until the go to publish is given.

    uv run upload_media.py check                       # local files against media_manifest.json; no network, no secrets
    op run --env-file=<hub>/tools/stilldrawn-r2.env.op -- uv run upload_media.py upload
    uv run upload_media.py verify --base https://media.studionephele.com/   # HEAD every key on the public host,
                                                                            # and a CORS preflight from the site

<hub> is the studio repository that holds this prototype; the env file there holds 1Password references
only. The account id, bucket and keys come from the environment that `op run` builds, and nothing here
prints them; a connection error is reported without its endpoint URL, which holds the account id.
It runs as a uv script with its own boto3 (pinned, as the studio's other R2 uploaders are),
so the pipeline's locked environment does not grow.

Objects under a version prefix are immutable (cached for a year): an existing key whose sha256 differs
stops the upload. A changed file goes out under the next prefix (export.py --prefix herebeink/v2/).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

EXPORT = Path(__file__).resolve().parent / "work" / "export"
CACHE = "public, max-age=31536000, immutable"
SITE_ORIGIN = "https://herebeink.studionephele.com"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(export: Path = EXPORT) -> tuple[Path, list[dict]]:
    m = json.loads((export / "media_manifest.json").read_text())
    root = export / m["root"]
    for i in m["items"]:
        if i["key"] != m["prefix"] + i["path"]:
            raise ValueError(f"manifest key and path disagree: {i['key']}")
    return root, m["items"]


def check_local(root: Path, items: list[dict]) -> None:
    bad = []
    for i in items:
        p = root / i["path"]
        if not p.is_file():
            bad.append(f"missing {i['path']}")
        elif p.stat().st_size != i["bytes"] or sha256_file(p) != i["sha256"]:
            bad.append(f"differs {i['path']}")
    if bad:
        raise ValueError(f"{len(bad)} file(s) differ from media_manifest.json ({bad[0]}); nothing uploaded")


def r2_client():
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto",
                        config=Config(retries={"max_attempts": 5, "mode": "standard"}))


def _absent(e: Exception) -> bool:
    return getattr(e, "response", {}).get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound")


def upload(root: Path, items: list[dict], client, bucket: str, log=print) -> dict:
    check_local(root, items)
    stats = {"uploaded": 0, "skipped": 0}
    for i in items:
        try:
            head = client.head_object(Bucket=bucket, Key=i["key"])
            if head.get("Metadata", {}).get("sha256") == i["sha256"]:
                stats["skipped"] += 1
                continue
            raise ValueError(f"{i['key']} already exists with other bytes; version prefixes are immutable, "
                             "so export under the next prefix instead")
        except ValueError:
            raise
        except Exception as e:
            if not _absent(e):
                raise
        with open(root / i["path"], "rb") as body:
            client.put_object(Bucket=bucket, Key=i["key"], Body=body, ContentType=i["content_type"],
                              CacheControl=CACHE, Metadata={"sha256": i["sha256"]})
        stats["uploaded"] += 1
        log(f"uploaded {i['key']} ({i['bytes']} bytes)")
    return stats


def redact(text: str) -> str:
    """Error text without URLs or anything shaped like an account id."""
    return re.sub(r"[0-9a-f]{32}", "<id>", re.sub(r"https?://[^\s\"']+", "<endpoint>", text))


def run_upload(root: Path, items: list[dict], make_client, bucket: str, log=print) -> int:
    try:
        log(str(upload(root, items, make_client(), bucket, log=log)))
        return 0
    except ValueError:
        raise
    except Exception as e:  # botocore's errors are not importable without boto3, and all of them may carry the URL
        log(f"upload stopped: {type(e).__name__}: {redact(str(e))} (the endpoint is left out: it holds the account id)")
        return 1


def preflight(url: str, origin: str, opener) -> str | None:
    """A browser's CORS preflight for a GET from the site; None when the answer lets the site read the file."""
    req = urllib.request.Request(url, method="OPTIONS", headers={
        "Origin": origin, "Access-Control-Request-Method": "GET", "User-Agent": "herebeink-verify"})
    try:
        with opener(req) as r:
            allow = r.headers.get("Access-Control-Allow-Origin")
    except urllib.error.HTTPError as e:
        return f"CORS preflight from {origin}: HTTP {e.code}"
    if allow not in (origin, "*"):
        return f"CORS preflight from {origin}: Access-Control-Allow-Origin is {allow!r}, so the page could not read it"
    return None


def verify_public(items: list[dict], base: str, origin: str = SITE_ORIGIN, opener=urllib.request.urlopen) -> list[str]:
    problems = []
    for i in items:
        req = urllib.request.Request(base + i["key"], method="HEAD", headers={"User-Agent": "herebeink-verify"})
        try:
            with opener(req) as r:
                if r.headers.get("Content-Length") != str(i["bytes"]):
                    problems.append(f"{i['key']}: length")
        except urllib.error.HTTPError as e:
            problems.append(f"{i['key']}: HTTP {e.code}")
    scene = next((i for i in items if i["path"] == "scene.json"), items[0] if items else None)
    if scene is not None:
        problem = preflight(base + scene["key"], origin, opener)
        if problem:
            problems.append(f"{scene['key']}: {problem}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "upload", "verify"])
    ap.add_argument("--export", type=Path, default=EXPORT)
    ap.add_argument("--base", default="https://media.studionephele.com/")
    ap.add_argument("--origin", default=SITE_ORIGIN, help="the page's origin, for the CORS preflight")
    args = ap.parse_args(argv)
    root, items = load(args.export)
    if args.cmd == "check":
        check_local(root, items)
        print(f"{len(items)} files match media_manifest.json")
        return 0
    if args.cmd == "upload":
        return run_upload(root, items, r2_client, os.environ["R2_BUCKET"])
    problems = verify_public(items, args.base, args.origin)
    print("\n".join(problems) or f"all {len(items)} keys answer with the right length")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

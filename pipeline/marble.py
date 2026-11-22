"""Guarded command-line client for World Labs' World API (Marble).

World Labs admits requests against a low-balance threshold and bills overage
after the fact, so the guards in this file are the only real spend limits.
Nothing here prints or logs the API key, request headers or signed URLs.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image

from media import MediaError, choose_source, original_of

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://api.worldlabs.ai"
KEY_ENV = "WLT_API_KEY"

CREDITS_PER_USD = 1250
# The project's frozen money rule: ask Aaron before any single call over $5.
OVER_FIVE_USD = 5.0
# Prices for a pano prompt, which carries no input surcharge; the +80 credits World Labs adds for a
# non-pano image would apply if the API ever read the pano as a plain image.
WORST_CASE = {"marble-1.0-draft": 150, "marble-1.1": 1500, "marble-1.1-plus": 3000}
MODELS = {"draft": ["marble-1.0-draft"], "world": ["marble-1.1", "marble-1.1-plus"]}
PANO_SIZE = (2560, 1280)
PANO_MAX_BYTES = 20 * 1024 * 1024
CLEAN_LINE = "Clean for upload: yes"
# One whole line, any case: a sentence that merely mentions the phrase must not open the gate.
CLEAN_RE = re.compile(r"^Clean for upload:[ \t]*yes[ \t]*$", re.I | re.M)
TERMS = "TOS 21 Jan 2026; rewrite dated 11.10.26 noted"
MAX_RETRIES = 3
POLL_START, POLL_MAX, POLL_TIMEOUT = 5.0, 30.0, 25 * 60
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class Refusal(Exception):
    """A guard stopped the call before or between requests; the message is the whole explanation."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class Interrupted(Exception):
    pass


def _http(method, url, **kw):
    return requests.request(method, url, timeout=kw.pop("timeout", 120), **kw)


def _sleep(seconds):
    time.sleep(seconds)


def strip_query(url):
    return str(url).split("?", 1)[0].split("#", 1)[0]


_URL_WITH_QUERY = re.compile(r"(https?://[^\s?#\"']*)[?#][^\s\"']*")


def strip_queries(obj):
    """The same structure with every URL's query string removed: signed URLs are credentials."""
    if isinstance(obj, str):
        return _URL_WITH_QUERY.sub(r"\1", obj)
    if isinstance(obj, dict):
        return {k: strip_queries(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_queries(v) for v in obj]
    return obj


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def work_dir():
    return ROOT / "pipeline" / "work" / "marble"


# ---- Uncertain API shapes, kept in one place each so the first real call can correct them ----

def parse_balance(body):
    # The live reply (20 Nov 2026) is {"remaining_credits": <float>}; the others are earlier guesses.
    for k in ("remaining_credits", "balance", "credits", "credit_balance", "available_credits"):
        if isinstance(body.get(k), (int, float)):
            return body[k]
    raise Refusal("balance response had no recognised credits field; stopping before any spend")


def prepare_upload_body(file_name):
    # Field names for media-assets:prepare_upload are assumed from the docs' outline.
    return {"file_name": file_name, "kind": "image", "extension": "png"}


def parse_prepare_upload(body):
    # Assumed: {media_asset: {media_asset_id}, upload_info: {upload_url, upload_method, required_headers}}.
    asset = body["media_asset"]["media_asset_id"]
    info = body["upload_info"]
    return asset, info["upload_url"], info.get("upload_method", "PUT"), info.get("required_headers") or {}


def operation_id(body):
    # The key is unconfirmed: accept the shapes the docs could plausibly mean, and None for anything else.
    if not isinstance(body, dict):
        return None
    nested = body.get("operation")
    found = body.get("operation_id") or body.get("id") or (nested.get("id") if isinstance(nested, dict) else None)
    if not found and body.get("name"):
        found = str(body["name"]).rsplit("/", 1)[-1]
    return str(found) if found else None


def world_of(op_body):
    # Assumed: the finished Operation carries the World in `response`, with `world_id` (or `id`).
    w = op_body.get("response") or {}
    wid = w.get("world_id") or w.get("id")
    if not wid or not ID_RE.match(str(wid)):
        raise Refusal("finished operation had no usable world id")
    return str(wid), w


def export_url(body):
    return (body.get("response") or body).get("url")


# ---- plumbing ----

def _need_key():
    key = os.environ.get(KEY_ENV)
    if not key:
        raise Refusal(f"{KEY_ENV} is not set; run this under `op run` with the hub's env file")
    return key


def _need_clean():
    notes = ROOT / "capture" / "NOTES.md"
    text = notes.read_text() if notes.exists() else ""
    if not CLEAN_RE.search(text):
        raise Refusal(f'capture/NOTES.md has no line reading exactly "{CLEAN_LINE}"; no World Labs call may run yet')


def _api(method, path, key, **kw):
    """One API call. Retries only 429, which is a rejection and so never double-charges."""
    headers = {"WLT-Api-Key": key}
    for attempt in range(MAX_RETRIES + 1):
        r = _http(method, BASE + path, headers=headers, **kw)
        if r.status_code == 429 and attempt < MAX_RETRIES:
            try:
                wait = min(max(float(r.headers.get("Retry-After", 5)), 1), 120)
            except ValueError:
                wait = 5
            _sleep(wait)
            continue
        break
    if r.status_code == 402:
        raise Refusal("402: the account is out of credits; a top-up needs Aaron's approval first", status=402)
    if r.status_code >= 400:
        detail = ""
        try:
            e = r.json().get("error")
            detail = f": {str(e.get('message') if isinstance(e, dict) else e)[:120]}" if e else ""
        except Exception:
            pass
        raise Refusal(f"World Labs returned {r.status_code} for {method} {path.split('?')[0]}{detail}",
                      status=r.status_code)
    return r


def _signed(method, url, **kw):
    """A call to a signed URL. A connection error would otherwise print the URL, signature and all."""
    try:
        return _http(method, url, **kw)
    except requests.RequestException as e:
        raise Refusal(f"{method} {strip_query(url)} failed ({type(e).__name__})") from None


def _download(url, dest):
    # Signed URLs carry their own authority; the API key must not travel with them.
    r = _signed("GET", url)
    if r.status_code >= 400:
        raise Refusal(f"download failed with {r.status_code}")
    dest.write_bytes(r.content)


def get_balance(key):
    return parse_balance(_api("GET", "/marble/v1/credits", key).json())


def append_spend(row):
    with open(ROOT / "spend.jsonl", "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def spend_rows():
    p = ROOT / "spend.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def append_licence_row(world_id, model, credits):
    p = ROOT / "LICENCES.md"
    lines = p.read_text().splitlines()
    try:
        i = next(n for n, ln in enumerate(lines) if ln.strip() == "### Worlds generated")
    except StopIteration:
        raise Refusal("LICENCES.md has no 'Worlds generated' section")
    j = i + 1
    while j < len(lines) and not lines[j].startswith("|"):
        j += 1
    while j < len(lines) and lines[j].startswith("|"):
        j += 1
    date = _now()[:10]
    lines.insert(j, f"| {date} | {world_id} | {model} | {credits} | {TERMS} |")
    p.write_text("\n".join(lines) + "\n")


# ---- pano ----

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sidecar_of(png):
    return Path(png).with_suffix(".json")


def check_pano(path):
    """Only a PNG that prepare-pano wrote here, unchanged since, may be sent: the privacy pass's
    masked copy and the metadata strip both happen there, so any other file skips them."""
    path = Path(path)
    if not path.exists():
        raise Refusal(f"pano not found: {path.name}")
    if path.resolve().parent != work_dir().resolve() or path.suffix.lower() != ".png":
        raise Refusal(f"{path.name} is not a PNG in work/marble/: only a file prepare-pano wrote there may be sent")
    sc = sidecar_of(path)
    if not sc.exists():
        raise Refusal(f"{path.name} has no prepare-pano sidecar: run prepare-pano on the still and send its output")
    try:
        meta = json.loads(sc.read_text())
    except ValueError:
        raise Refusal(f"the sidecar for {path.name} is unreadable: run prepare-pano again") from None
    if meta.get("png_sha256") != _sha256(path):
        raise Refusal(f"{path.name} has changed since prepare-pano wrote it: run prepare-pano again")
    with Image.open(path) as im:
        size = im.size
    if size != PANO_SIZE:
        raise Refusal(f"pano is {size[0]:,} x {size[1]:,}, not {PANO_SIZE[0]:,} x {PANO_SIZE[1]:,}")
    if path.stat().st_size > PANO_MAX_BYTES:
        raise Refusal("pano is over the 20 MB upload limit")
    source = (ROOT / str(meta.get("source", ""))).resolve()
    if source.is_file():
        try:
            choose_source(source)
        except MediaError as e:
            raise Refusal(f"{e}; run prepare-pano again") from None


def cmd_prepare_pano(args):
    src = Path(args.pano)
    if not src.exists():
        raise Refusal(f"pano not found: {src.name}")
    try:
        choose_source(src)
    except MediaError as e:
        raise Refusal(str(e)) from None
    with Image.open(src) as im:
        w, h = im.size
        if w != 2 * h:
            raise Refusal(f"pano is {w} x {h}, not exactly 2:1")
        if w < PANO_SIZE[0]:
            raise Refusal(f"pano is {w} px wide; at least {PANO_SIZE[0]:,} are needed (export the still at full size)")
        rgb = im.convert("RGB")
        if rgb.size != PANO_SIZE:
            rgb = rgb.resize(PANO_SIZE, Image.LANCZOS)
        # Rebuilt from pixels so nothing the source carried (EXIF, GPS, ICC, XMP) can follow the image.
        out = Image.frombytes("RGB", rgb.size, rgb.tobytes())
    dest = work_dir() / f"{original_of(src)[0].stem}_{PANO_SIZE[0]}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest, optimize=True)
    if dest.stat().st_size > PANO_MAX_BYTES:
        dest.unlink()
        raise Refusal("prepared pano is over the 20 MB upload limit")
    rel = Path(os.path.relpath(src.resolve(), ROOT.resolve())).as_posix()
    sidecar_of(dest).write_text(json.dumps({
        "source": rel, "source_sha256": _sha256(src), "png_sha256": _sha256(dest),
        "size": list(out.size), "time": _now()}, indent=2) + "\n")
    print(f"wrote {dest.name} at {out.size[0]} x {out.size[1]}")
    return 0


# ---- generate ----

def _upload(pano, key):
    r = _api("POST", "/marble/v1/media-assets:prepare_upload", key, json=prepare_upload_body(pano.name))
    asset, url, method, hdrs = parse_prepare_upload(r.json())
    put = _signed(method, url, data=pano.read_bytes(), headers=hdrs)
    if put.status_code >= 400:
        raise Refusal(f"upload failed with {put.status_code}")
    return {"source": "media_asset", "media_asset_id": asset}


def image_prompt(pano, key, allow_base64):
    try:
        return _upload(pano, key)
    except (Refusal, KeyError, TypeError) as e:
        if not allow_base64:
            raise Refusal(f"media-asset upload failed ({type(e).__name__}); "
                          "rerun with --allow-base64 to send the image inline") from None
        return {"source": "data_base64", "data_base64": base64.b64encode(pano.read_bytes()).decode(),
                "extension": "png"}


def guard_generate(kind, a):
    if not a.yes:
        raise Refusal("pass --yes to confirm this paid call")
    if a.max_credits is None:
        raise Refusal("pass --max-credits N; there is no default spend limit")
    if a.model not in MODELS[kind]:
        raise Refusal(f"model {a.model} is not allowed for `{kind}` (allowed: {', '.join(MODELS[kind])})")
    price = WORST_CASE[a.model]
    if price > a.max_credits:
        raise Refusal(f"worst case {price} credits exceeds --max-credits {a.max_credits}")
    if price / CREDITS_PER_USD > OVER_FIVE_USD and not a.aaron_approved_over_5:
        raise Refusal(f"worst case ${price / CREDITS_PER_USD:.2f} is over $5; "
                      "ask Aaron, then pass --aaron-approved-over-5")
    _need_clean()
    key = _need_key()
    check_pano(a.pano)
    return price, key


def cmd_generate(kind, a):
    price, key = guard_generate(kind, a)
    before = get_balance(key)
    if before - price < a.floor:
        raise Refusal(f"balance {before} minus worst case {price} would fall below the floor {a.floor}")
    pano = Path(a.pano)
    body = {
        "display_name": f"herebeink {kind}",
        "model": a.model,
        "permission": {"public": False},
        "world_prompt": {"type": "image", "is_pano": True,
                         "image_prompt": image_prompt(pano, key, a.allow_base64)},
    }
    if a.seed is not None:
        body["seed"] = a.seed
    row = {"time": _now(), "kind": kind, "model": a.model, "world_id": None, "operation_id": None,
           "credits_estimate": price, "credits_actual": None, "usd": round(price / CREDITS_PER_USD, 4),
           "balance_before": before, "balance_after": None, "purpose": a.purpose, "seed": a.seed}
    # Logged before the POST: once the request leaves, the money may be spent whatever happens next.
    append_spend({**row, "status": "requesting"})
    try:
        resp = _api("POST", "/marble/v1/worlds:generate", key, json=body)
    except Refusal as e:
        if e.status is not None and e.status < 500:
            append_spend({**row, "time": _now(), "status": "rejected"})
        else:
            print(f"marble: {_unparsed(row, [])}", file=sys.stderr)
        raise
    except BaseException:
        print(f"marble: {_unparsed(row, [])}", file=sys.stderr)
        raise
    try:
        op = resp.json()
    except Exception:
        op = None
    op_id = operation_id(op)
    if not op_id or not ID_RE.match(op_id):
        raise Refusal(_unparsed(row, sorted(op) if isinstance(op, dict) else []))
    # The call is admitted from here on, whatever happens to this process, so it is logged now.
    append_spend({**row, "time": _now(), "operation_id": op_id, "status": "admitted"})
    print(f"admitted {kind} {op_id}; polling")
    return finish(op_id, key, op)


def _unparsed(row, keys):
    """Log a generate call that may have been admitted but left no id to resume from; return what to tell the user."""
    append_spend({**row, "time": _now(), "status": "admitted-unparsed", "response_keys": keys})
    seen = f" (response keys: {', '.join(keys)})" if keys else ""
    return ("the generate call may have been admitted but gave no usable operation id" + seen
            + ": check the balance (marble.py credits) and the account's operations on platform.worldlabs.ai "
            "by hand before trying again")


NOT_FOUND_GRACE = 60.0  # seconds a just-admitted operation may 404 before polling stops


def poll(op_id, key, first=None):
    delay, waited, body = POLL_START, 0.0, first
    while True:
        if body is None or not body.get("done"):
            try:
                body = _api("GET", f"/marble/v1/operations/{op_id}", key).json()
            except Refusal as exc:
                # A fresh operation can 404 for a moment after admission (seen 20 Nov 2026). A GET
                # never charges, so wait it out; past the grace, hand over to `status` as for a timeout.
                if exc.status != 404:
                    raise
                if waited >= NOT_FOUND_GRACE:
                    raise Interrupted from exc
                body = {}
        if body.get("done"):
            return body
        if waited >= POLL_TIMEOUT:
            raise Interrupted
        _sleep(delay)
        waited += delay
        delay = min(delay * 1.5, POLL_MAX)
        body = None


def finish(op_id, key, first=None):
    try:
        body = poll(op_id, key, first if first and first.get("done") else None)
    except (KeyboardInterrupt, Interrupted):
        print(f"still running; resume with: marble.py status {op_id}", file=sys.stderr)
        return 130
    admitted = next((r for r in reversed(spend_rows())
                     if r.get("operation_id") == op_id and r["status"] == "admitted"), None)
    already = any(r.get("operation_id") == op_id and r["status"] in ("done", "failed") for r in spend_rows())
    base = dict(admitted or {"kind": None, "model": None, "credits_estimate": None, "balance_before": None,
                             "purpose": None, "seed": None, "operation_id": op_id})
    if body.get("error"):
        if not already:
            append_spend({**base, "time": _now(), "status": "failed"})
        raise Refusal("the operation failed; see spend.jsonl (no credits assumed spent until the balance says so)")
    wid, world = world_of(body)
    out = work_dir()
    out.mkdir(parents=True, exist_ok=True)
    # Signed preview URLs expire, so they are fetched in the same sitting, and only then stripped for the record.
    for res, url in ((world.get("assets") or {}).get("splats") or {}).get("spz_urls", {}).items():
        if ID_RE.match(res):
            _download(url, out / f"{wid}_{res}.spz")
    (out / f"{wid}.json").write_text(json.dumps(strip_queries(world), indent=2))
    if already:
        print(f"world {wid} saved (already logged)")
        return 0
    after = get_balance(key)
    rows = spend_rows()
    # Another call logged since would make the balance difference include its cost.
    sole = admitted is not None and rows and rows[-1] == admitted
    actual = (base["balance_before"] - after) if sole and base.get("balance_before") is not None else None
    credits = actual if actual is not None else base.get("credits_estimate")
    append_spend({**base, "time": _now(), "world_id": wid, "credits_actual": actual, "balance_after": after,
                  "usd": round(credits / CREDITS_PER_USD, 4) if credits is not None else None,
                  "status": "done"})
    append_licence_row(wid, base.get("model") or "unknown", credits)
    print(f"done: world {wid}, {credits} credits")
    return 0


def cmd_status(a):
    _need_clean()
    key = _need_key()
    if not ID_RE.match(a.operation_id):
        raise Refusal("operation id has an unexpected shape")
    return finish(a.operation_id, key)


# ---- free commands ----

def cmd_credits(a):
    _need_clean()
    print(get_balance(_need_key()))
    return 0


def cmd_export(a):
    _need_clean()
    key = _need_key()
    if not ID_RE.match(a.world_id):
        raise Refusal("world id has an unexpected shape")
    body = {"asset_type": "splats", "format": a.format, "resolution": a.resolution}
    r = _api("POST", f"/marble/v1/worlds/{a.world_id}:export", key, json=body)
    url = export_url(r.json())
    if not url:
        raise Refusal("export response had no download url")
    dest = work_dir() / f"marble_{a.world_id}.{a.format}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    _download(url, dest)
    print(f"saved {dest.name}")
    return 0


# ---- cli ----

def build_parser():
    p = argparse.ArgumentParser(prog="marble.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("credits")
    pp = sub.add_parser("prepare-pano")
    pp.add_argument("pano")
    for kind in ("draft", "world"):
        g = sub.add_parser(kind)
        g.add_argument("--pano", required=True)
        g.add_argument("--model", required=True)
        g.add_argument("--purpose", required=True)
        g.add_argument("--seed", type=int)
        g.add_argument("--yes", action="store_true")
        g.add_argument("--max-credits", type=int)
        g.add_argument("--floor", type=int, default=0)
        g.add_argument("--aaron-approved-over-5", action="store_true")
        g.add_argument("--allow-base64", action="store_true")
    ex = sub.add_parser("export")
    ex.add_argument("world_id")
    ex.add_argument("--format", choices=["ply"], required=True)
    ex.add_argument("--resolution", choices=["full_res", "500k", "150k", "100k"], required=True)
    st = sub.add_parser("status")
    st.add_argument("operation_id")
    return p


def main(argv=None):
    try:
        a = build_parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) and e.code else 2
    try:
        if a.cmd in ("draft", "world"):
            return cmd_generate(a.cmd, a)
        return {"credits": cmd_credits, "prepare-pano": cmd_prepare_pano,
                "export": cmd_export, "status": cmd_status}[a.cmd](a)
    except Refusal as e:
        print(f"marble: {e}", file=sys.stderr)
        return 2
    except requests.RequestException as e:
        req = getattr(e, "request", None)
        where = f" on {req.method} {strip_query(req.url)}" if req is not None and getattr(req, "url", None) else ""
        print(f"marble: network error ({type(e).__name__}){where}; no response was read", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("marble: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

"""Marble client tests. Every HTTP call goes through a fake; nothing touches the network."""

import hashlib
import json
import os
import sys
from urllib.parse import urlparse
from pathlib import Path

import pytest
import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import marble  # noqa: E402

KEY = "test-key-do-not-leak-123"
SIGNED = "sig=SECRETSIGNATURE"


class Resp:
    def __init__(self, status=200, body=None, headers=None, content=b""):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.content = content
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class Api:
    """Scripted World API. `balances` is consumed per credits GET; `polls` per operation GET."""

    def __init__(self, balances=(10000, 9850), polls=None, generate=None, upload_ok=True):
        self.calls = []
        self.balances = list(balances)
        self.polls = list(polls if polls is not None else [PENDING, PENDING, DONE])
        self.generate = list(generate if generate is not None else [Resp(200, {"operation_id": "op-1", "done": False})])
        self.upload_ok = upload_ok
        self.sleeps = []
        self.put_error = None
        self.download_error = None
        self.on_generate = None

    def __call__(self, method, url, **kw):
        path = urlparse(url).path
        self.calls.append((method, path, kw))
        if method == "GET" and path == "/marble/v1/credits":
            return Resp(200, {"remaining_credits": self.balances.pop(0) if len(self.balances) > 1 else self.balances[0]})
        if method == "POST" and path == "/marble/v1/media-assets:prepare_upload":
            if not self.upload_ok:
                return Resp(500, {"error": "nope"})
            return Resp(200, {"media_asset": {"media_asset_id": "ma-1"},
                              "upload_info": {"upload_url": "https://store.example/up?" + SIGNED,
                                              "upload_method": "PUT", "required_headers": {"x-h": "1"}}})
        if method == "PUT":
            if self.put_error:
                raise self.put_error
            return Resp(200)
        if method == "POST" and path == "/marble/v1/worlds:generate":
            if self.on_generate:
                self.on_generate()
            g = self.generate.pop(0) if len(self.generate) > 1 else self.generate[0]
            if isinstance(g, BaseException):
                raise g
            return g
        if method == "GET" and path.startswith("/marble/v1/operations/"):
            p = self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]
            if isinstance(p, BaseException):
                raise p
            return p
        if method == "GET" and path.startswith("/dl/"):
            if self.download_error:
                raise self.download_error
            return Resp(200, content=b"SPZ-BYTES-" + path.encode())
        if method == "POST" and path.endswith(":export"):
            return Resp(200, {"response": {"url": "https://cdn.example/dl/ply?" + SIGNED}})
        raise AssertionError(f"unexpected call {method} {path}")

    def paths(self):
        return [(m, p) for m, p, _ in self.calls]


PENDING = Resp(200, {"operation_id": "op-1", "done": False})
DONE = Resp(200, {"operation_id": "op-1", "done": True, "response": {
    "world_id": "w-1",
    "assets": {"splats": {
        "spz_urls": {"100k": "https://cdn.example/dl/100k?" + SIGNED,
                     "500k": "https://cdn.example/dl/500k?" + SIGNED,
                     "full_res": "https://cdn.example/dl/full?" + SIGNED},
        "semantics_metadata": {"metric_scale_factor": 1.7, "ground_plane_offset": 0.1}}}}})

LICENCES = """# Licences

### Worlds generated

| Date | World id | Model | Credits | Terms version |
|---|---|---|---|---|

## Third-party software

| Component |
|---|
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "capture").mkdir(parents=True)
    (root / "pipeline").mkdir()
    (root / "capture" / "NOTES.md").write_text("Clean for upload: YES\n")
    (root / "spend.jsonl").write_text("")
    (root / "LICENCES.md").write_text(LICENCES)
    monkeypatch.setattr(marble, "ROOT", root)
    monkeypatch.setenv("WLT_API_KEY", KEY)
    monkeypatch.setattr(marble, "_sleep", lambda s: None)
    source = root / "capture" / "stitched" / "pano-auto.jpg"
    source.parent.mkdir()
    Image.new("RGB", (2560, 1280), "white").save(source)
    assert marble.main(["prepare-pano", str(source)]) == 0
    api = Api()
    monkeypatch.setattr(marble, "_http", api)
    api.root, api.source = root, source
    api.pano = root / "pipeline" / "work" / "marble" / "pano-auto_2560.png"
    return api


def run(env, *argv):
    return marble.main(list(argv))


def draft_args(env, **over):
    a = {"--pano": str(env.pano), "--model": "marble-1.0-draft", "--purpose": "test",
         "--seed": "7", "--max-credits": "150"}
    a.update(over)
    out = ["draft"]
    for k, v in a.items():
        if v is not None:
            out += [k, v]
    return out + ["--yes"]


def spend_rows(env):
    return [json.loads(line) for line in (env.root / "spend.jsonl").read_text().splitlines()]


def refused(env, rc, capsys, fragment):
    assert rc != 0
    err = capsys.readouterr().err
    assert fragment in err and len(err.strip().splitlines()) == 1
    assert env.calls == []
    assert spend_rows(env) == []


# ---- guards ----

def test_refuses_without_yes(env, capsys):
    args = [a for a in draft_args(env) if a != "--yes"]
    refused(env, run(env, *args), capsys, "--yes")


def test_refuses_without_max_credits(env, capsys):
    args = draft_args(env, **{"--max-credits": None})
    refused(env, run(env, *args), capsys, "--max-credits")


def test_refuses_when_price_exceeds_max_credits(env, capsys):
    args = ["world", "--pano", str(env.pano), "--model", "marble-1.1", "--purpose", "t",
            "--max-credits", "1000", "--yes"]
    refused(env, run(env, *args), capsys, "worst case 1500")


def test_refuses_over_five_dollars_without_approval(env, capsys, monkeypatch):
    monkeypatch.setitem(marble.WORST_CASE, "marble-1.1-plus", 7000)
    args = ["world", "--pano", str(env.pano), "--model", "marble-1.1-plus", "--purpose", "t",
            "--max-credits", "7000", "--yes"]
    refused(env, run(env, *args), capsys, "$5")


def test_over_five_dollars_allowed_with_approval(env, monkeypatch):
    monkeypatch.setitem(marble.WORST_CASE, "marble-1.1-plus", 7000)
    env.balances = [20000, 13000]
    args = ["world", "--pano", str(env.pano), "--model", "marble-1.1-plus", "--purpose", "t",
            "--max-credits", "7000", "--aaron-approved-over-5", "--yes"]
    assert run(env, *args) == 0


def test_refuses_when_balance_would_fall_below_floor(env, capsys):
    env.balances = [100]
    rc = run(env, *draft_args(env))
    assert rc != 0
    assert "floor" in capsys.readouterr().err
    assert env.paths() == [("GET", "/marble/v1/credits")]
    assert spend_rows(env) == []


def test_floor_can_be_raised(env, capsys):
    env.balances = [1000]
    rc = run(env, *draft_args(env), "--floor", "900")
    assert rc != 0 and "floor" in capsys.readouterr().err
    assert ("POST", "/marble/v1/worlds:generate") not in env.paths()


def test_refuses_when_not_clean_for_upload(env, capsys):
    (env.root / "capture" / "NOTES.md").write_text("Clean for upload: NOT YET\n")
    refused(env, run(env, *draft_args(env)), capsys, "Clean for upload")


def test_notes_gate_covers_credits_and_export(env, capsys):
    (env.root / "capture" / "NOTES.md").write_text("Clean for upload: NOT YET\n")
    assert run(env, "credits") != 0
    assert run(env, "export", "w-1", "--format", "ply", "--resolution", "full_res") != 0
    assert env.calls == []


def test_refuses_without_api_key(env, capsys, monkeypatch):
    monkeypatch.delenv("WLT_API_KEY")
    rc = run(env, *draft_args(env))
    assert rc != 0
    err = capsys.readouterr().err
    assert "op run" in err and len(err.strip().splitlines()) == 1
    assert env.calls == []


def test_refuses_a_pano_that_prepare_pano_did_not_write(env, capsys, tmp_path):
    stray = env.root / "pipeline" / "work" / "marble" / "stray.png"
    Image.new("RGB", (2560, 1280), "white").save(stray)
    refused(env, run(env, *draft_args(env, **{"--pano": str(stray)})), capsys, "prepare-pano")
    outside = tmp_path / "outside.png"
    Image.new("RGB", (2560, 1280), "white").save(outside)
    refused(env, run(env, *draft_args(env, **{"--pano": str(outside)})), capsys, "work/marble")


def test_refuses_a_pano_the_wrong_size_even_with_a_sidecar(env, capsys):
    p = env.pano
    Image.new("RGB", (2000, 1000), "white").save(p)
    sc = json.loads(p.with_suffix(".json").read_text())
    sc["png_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    p.with_suffix(".json").write_text(json.dumps(sc))
    refused(env, run(env, *draft_args(env)), capsys, "2,560 x 1,280")


def test_refuses_a_pano_changed_after_prepare_pano(env, capsys):
    Image.new("RGB", (2560, 1280), "black").save(env.pano)
    refused(env, run(env, *draft_args(env)), capsys, "changed since prepare-pano")


def test_refuses_when_a_mask_appears_after_prepare_pano(env, capsys):
    masked = env.source.with_name("pano-auto.masked.jpg")
    masked.write_bytes(env.source.read_bytes())
    refused(env, run(env, *draft_args(env)), capsys, "masked")


def test_sidecar_records_source_hash_size_and_time(env):
    sc = json.loads(env.pano.with_suffix(".json").read_text())
    assert sc["source"] == "capture/stitched/pano-auto.jpg"
    assert sc["source_sha256"] == hashlib.sha256(env.source.read_bytes()).hexdigest()
    assert sc["png_sha256"] == hashlib.sha256(env.pano.read_bytes()).hexdigest()
    assert sc["size"] == [2560, 1280] and sc["time"].endswith("Z")


def test_draft_only_accepts_draft_model(env, capsys):
    refused(env, run(env, *draft_args(env, **{"--model": "marble-1.1"})), capsys, "model")


def test_world_refuses_draft_model(env, capsys):
    args = ["world", "--pano", str(env.pano), "--model", "marble-1.0-draft", "--purpose", "t",
            "--max-credits", "1500", "--yes"]
    refused(env, run(env, *args), capsys, "model")


# ---- behaviour ----

def test_happy_path_draft(env, capsys):
    assert run(env, *draft_args(env)) == 0
    paths = env.paths()
    assert paths[0] == ("GET", "/marble/v1/credits")
    order = [p for p in paths if p[1] in ("/marble/v1/media-assets:prepare_upload", "/marble/v1/worlds:generate")]
    assert [p[1] for p in order] == ["/marble/v1/media-assets:prepare_upload", "/marble/v1/worlds:generate"]
    assert sum(1 for m, p in paths if p == "/marble/v1/operations/op-1") == 3

    gen = next(kw for m, p, kw in env.calls if p == "/marble/v1/worlds:generate")
    body = gen["json"]
    assert body["model"] == "marble-1.0-draft"
    assert body["permission"] == {"public": False}
    assert body["seed"] == 7
    wp = body["world_prompt"]
    assert wp["is_pano"] is True and wp["image_prompt"]["source"] == "media_asset"
    assert "data_base64" not in json.dumps(body) and "uri" not in wp["image_prompt"]
    assert gen["headers"]["WLT-Api-Key"] == KEY

    work = env.root / "pipeline" / "work" / "marble"
    assert json.loads((work / "w-1.json").read_text())["world_id"] == "w-1"
    for res in ("100k", "500k", "full_res"):
        assert (work / f"w-1_{res}.spz").read_bytes().startswith(b"SPZ-BYTES")

    requesting, admitted, done = spend_rows(env)
    assert requesting["status"] == "requesting" and admitted["status"] == "admitted" and done["status"] == "done"
    assert done["kind"] == "draft" and done["model"] == "marble-1.0-draft"
    assert done["world_id"] == "w-1" and done["operation_id"] == "op-1"
    assert done["credits_estimate"] == 150 and done["credits_actual"] == 150
    assert done["usd"] == pytest.approx(150 / 1250)
    assert done["purpose"] == "test" and done["seed"] == 7
    assert done["time"].endswith("Z") or "+00:00" in done["time"]

    lic = (env.root / "LICENCES.md").read_text()
    row = [ln for ln in lic.splitlines() if "| w-1 |" in ln]
    assert len(row) == 1 and "marble-1.0-draft" in row[0] and "150" in row[0]
    assert "TOS 21 Jan 2026; rewrite dated 11.10.26 noted" in row[0]
    assert lic.index(row[0]) < lic.index("## Third-party")

    leak = capsys.readouterr()
    for text in (leak.out, leak.err, (env.root / "spend.jsonl").read_text(), lic):
        assert KEY not in text and "SECRETSIGNATURE" not in text


def test_spend_log_is_append_only(env):
    (env.root / "spend.jsonl").write_text('{"earlier": true}\n')
    run(env, *draft_args(env))
    lines = (env.root / "spend.jsonl").read_text().splitlines()
    assert lines[0] == '{"earlier": true}' and len(lines) == 4


def test_world_marble_11_plus(env):
    env.balances = [10000, 8500]
    args = ["world", "--pano", str(env.pano), "--model", "marble-1.1-plus", "--purpose", "w2",
            "--max-credits", "3000", "--yes"]
    assert run(env, *args) == 0
    done = spend_rows(env)[-1]
    assert done["kind"] == "world" and done["credits_estimate"] == 3000 and done["credits_actual"] == 1500


def test_rate_limit_waits_retry_after_then_succeeds(env, monkeypatch):
    sleeps = []
    monkeypatch.setattr(marble, "_sleep", sleeps.append)
    env.generate = [Resp(429, {"error": "slow"}, {"Retry-After": "17"}),
                    Resp(200, {"operation_id": "op-1", "done": False})]
    assert run(env, *draft_args(env)) == 0
    assert 17 in sleeps
    assert sum(1 for m, p in env.paths() if p == "/marble/v1/worlds:generate") == 2
    assert len(spend_rows(env)) == 3


def test_rate_limit_gives_up(env, capsys):
    env.generate = [Resp(429, {}, {"Retry-After": "1"})]
    assert run(env, *draft_args(env)) != 0
    assert "429" in capsys.readouterr().err
    assert [r["status"] for r in spend_rows(env)] == ["requesting", "rejected"]


def test_payment_required_stops_cleanly(env, capsys):
    env.generate = [Resp(402, {"error": "credits"})]
    assert run(env, *draft_args(env)) != 0
    err = capsys.readouterr().err
    assert "402" in err and "top" in err.lower()
    assert [r["status"] for r in spend_rows(env)] == ["requesting", "rejected"]
    assert not any(p.startswith("/marble/v1/operations/") for _, p in env.paths())


def test_interrupted_poll_resumes_with_status(env, capsys):
    env.polls = [PENDING, KeyboardInterrupt()]
    assert run(env, *draft_args(env)) == 130
    assert "status op-1" in capsys.readouterr().err
    rows = spend_rows(env)
    assert [r["status"] for r in rows] == ["requesting", "admitted"]

    env.polls = [DONE]
    env.balances = [9850]
    assert run(env, "status", "op-1") == 0
    rows = spend_rows(env)
    assert [r["status"] for r in rows] == ["requesting", "admitted", "done"]
    assert rows[2]["credits_actual"] == 150 and rows[2]["purpose"] == "test"
    assert (env.root / "pipeline" / "work" / "marble" / "w-1.json").exists()
    assert (env.root / "LICENCES.md").read_text().count("| w-1 |") == 1


def test_status_twice_does_not_double_log(env):
    run(env, *draft_args(env))
    env.polls = [DONE]
    assert run(env, "status", "op-1") == 0
    assert len(spend_rows(env)) == 3
    assert (env.root / "LICENCES.md").read_text().count("| w-1 |") == 1


def test_failed_operation_is_logged(env, capsys):
    env.polls = [Resp(200, {"operation_id": "op-1", "done": True, "error": {"message": "bad pano"}})]
    assert run(env, *draft_args(env)) != 0
    assert [r["status"] for r in spend_rows(env)] == ["requesting", "admitted", "failed"]
    assert (env.root / "LICENCES.md").read_text() == LICENCES


def test_base64_only_after_upload_fails_and_flag_given(env, capsys):
    env.upload_ok = False
    assert run(env, *draft_args(env)) != 0
    assert ("POST", "/marble/v1/worlds:generate") not in env.paths()
    assert "--allow-base64" in capsys.readouterr().err

    env.calls.clear()
    assert run(env, *draft_args(env), "--allow-base64") == 0
    gen = next(kw for m, p, kw in env.calls if p == "/marble/v1/worlds:generate")
    assert gen["json"]["world_prompt"]["image_prompt"]["source"] == "data_base64"
    assert gen["json"]["permission"] == {"public": False}


def test_export_ply_saves_file(env):
    assert run(env, "export", "w-1", "--format", "ply", "--resolution", "full_res") == 0
    method, path, kw = next(c for c in env.calls if c[1].endswith(":export"))
    assert path == "/marble/v1/worlds/w-1:export"
    assert kw["json"] == {"asset_type": "splats", "format": "ply", "resolution": "full_res"}
    out = env.root / "pipeline" / "work" / "marble" / "marble_w-1.ply"
    assert out.read_bytes().startswith(b"SPZ-BYTES")
    assert spend_rows(env) == []


def test_export_rejects_odd_world_id(env, capsys):
    assert run(env, "export", "../x", "--format", "ply", "--resolution", "full_res") != 0
    assert env.calls == []


def test_credits_prints_balance(env, capsys):
    assert run(env, "credits") == 0
    assert "10000" in capsys.readouterr().out


def test_prepare_pano_downsizes_without_network(env, tmp_path):
    big = env.root / "capture" / "stitched" / "pano.jpg"
    Image.new("RGB", (5760, 2880), "gray").save(big)
    env.calls.clear()
    assert run(env, "prepare-pano", str(big)) == 0
    out = env.root / "pipeline" / "work" / "marble" / "pano_2560.png"
    assert Image.open(out).size == (2560, 1280)
    assert env.calls == []


def test_prepare_pano_refuses_non_two_to_one(env, tmp_path, capsys):
    bad = tmp_path / "bad.jpg"
    Image.new("RGB", (3000, 1600), "gray").save(bad)
    assert run(env, "prepare-pano", str(bad)) != 0
    assert "2:1" in capsys.readouterr().err


def test_prepare_pano_refuses_a_source_narrower_than_the_upload(env, tmp_path, capsys):
    small = tmp_path / "small.jpg"
    Image.new("RGB", (2000, 1000), "gray").save(small)
    assert run(env, "prepare-pano", str(small)) != 0
    assert "2,560" in capsys.readouterr().err


def test_prepare_pano_strips_all_metadata(env, tmp_path):
    src = env.root / "capture" / "stitched" / "pano-hdr.jpg"
    exif = Image.Exif()
    exif[0x010F] = "MARKER-MAKE"
    exif[0x013B] = "MARKER-ARTIST"
    exif.get_ifd(0x8825)[0x0002] = (51.0, 30.0, 0.0)
    im = Image.new("RGB", (5120, 2560), "gray")
    im.save(src, exif=exif.tobytes(), icc_profile=b"\x00" * 200)
    assert b"MARKER-MAKE" in src.read_bytes()
    assert run(env, "prepare-pano", str(src)) == 0
    out = env.root / "pipeline" / "work" / "marble" / "pano-hdr_2560.png"
    raw = out.read_bytes()
    assert b"MARKER" not in raw and b"eXIf" not in raw and b"iCCP" not in raw and b"tEXt" not in raw
    with Image.open(out) as o:
        assert not o.getexif() and "exif" not in o.info and "icc_profile" not in o.info


def test_prepare_pano_refuses_a_source_that_has_a_masked_copy(env, capsys):
    stitched = env.root / "capture" / "stitched"
    Image.new("RGB", (2560, 1280), "white").save(stitched / "pano.jpg")
    Image.new("RGB", (2560, 1280), "black").save(stitched / "pano.masked.jpg")
    os.utime(stitched / "pano.masked.jpg", None)
    assert run(env, "prepare-pano", str(stitched / "pano.jpg")) == 2
    err = capsys.readouterr().err
    assert "pano.masked.jpg" in err and len(err.strip().splitlines()) == 1
    assert run(env, "prepare-pano", str(stitched / "pano.masked.jpg")) == 0
    sc = json.loads((env.root / "pipeline/work/marble/pano_2560.json").read_text())
    assert sc["source"] == "capture/stitched/pano.masked.jpg"


def test_prepare_pano_refuses_a_masked_copy_older_than_its_source(env, capsys):
    stitched = env.root / "capture" / "stitched"
    Image.new("RGB", (2560, 1280), "black").save(stitched / "pano.masked.jpg")
    Image.new("RGB", (2560, 1280), "white").save(stitched / "pano.jpg")
    old = os.stat(stitched / "pano.jpg").st_mtime - 100
    os.utime(stitched / "pano.masked.jpg", (old, old))
    assert run(env, "prepare-pano", str(stitched / "pano.masked.jpg")) == 2
    assert "older" in capsys.readouterr().err


# ---- a paid call is never unlogged ----

def statuses(env):
    return [r["status"] for r in spend_rows(env)]


def test_requesting_row_is_on_disk_before_the_post(env):
    seen = []
    env.on_generate = lambda: seen.append(spend_rows(env))
    assert run(env, *draft_args(env)) == 0
    assert len(seen) == 1 and [r["status"] for r in seen[0]] == ["requesting"]
    row = seen[0][0]
    assert row["kind"] == "draft" and row["model"] == "marble-1.0-draft" and row["credits_estimate"] == 150
    assert row["balance_before"] == 10000 and row["purpose"] == "test" and row["seed"] == 7 and row["time"]


@pytest.mark.parametrize("body", [{"id": "op-9", "done": False}, {"operation": {"id": "op-9"}, "done": False},
                                  {"name": "operations/op-9", "done": False}])
def test_operation_id_shapes_are_accepted(env, body):
    env.generate = [Resp(200, body)]
    assert run(env, *draft_args(env)) == 0
    assert statuses(env) == ["requesting", "admitted", "done"]
    assert spend_rows(env)[1]["operation_id"] == "op-9"


def test_unrecognised_200_is_logged_as_unparsed_with_key_names_only(env, capsys):
    env.generate = [Resp(200, {"ticket": "VALUE-SHOULD-NOT-APPEAR", "meta": {"k": "NESTED-VALUE"}})]
    assert run(env, *draft_args(env)) != 0
    assert statuses(env) == ["requesting", "admitted-unparsed"]
    row = spend_rows(env)[1]
    assert row["response_keys"] == ["meta", "ticket"]
    cap = capsys.readouterr()
    assert "meta, ticket" in cap.err and "balance" in cap.err and "operations" in cap.err
    for text in (cap.out, cap.err, (env.root / "spend.jsonl").read_text()):
        assert "VALUE-SHOULD-NOT-APPEAR" not in text and "NESTED-VALUE" not in text and KEY not in text
    assert not any(p.startswith("/marble/v1/operations/") for _, p in env.paths())


def test_non_json_200_is_logged_as_unparsed(env, capsys):
    env.generate = [Resp(200, None)]
    assert run(env, *draft_args(env)) != 0
    assert statuses(env) == ["requesting", "admitted-unparsed"]
    assert spend_rows(env)[1]["response_keys"] == []
    assert "balance" in capsys.readouterr().err


def test_odd_operation_id_shape_is_logged_as_unparsed(env):
    env.generate = [Resp(200, {"operation_id": "../x"})]
    assert run(env, *draft_args(env)) != 0
    assert statuses(env) == ["requesting", "admitted-unparsed"]


def test_timeout_on_the_post_is_logged_and_prints_no_query(env, capsys):
    env.generate = [requests.Timeout("read timed out: https://api.worldlabs.ai/marble/v1/worlds:generate?" + SIGNED)]
    assert run(env, *draft_args(env)) != 0
    assert statuses(env) == ["requesting", "admitted-unparsed"]
    cap = capsys.readouterr()
    assert "SECRETSIGNATURE" not in cap.err + cap.out and "Traceback" not in cap.err
    assert "balance" in cap.err


def test_ctrl_c_on_the_post_is_logged(env, capsys):
    env.generate = [KeyboardInterrupt()]
    assert run(env, *draft_args(env)) == 130
    assert statuses(env) == ["requesting", "admitted-unparsed"]
    assert "balance" in capsys.readouterr().err


def test_server_error_on_the_post_may_have_been_admitted(env):
    env.generate = [Resp(502, {"error": "bad gateway"})]
    assert run(env, *draft_args(env)) != 0
    assert statuses(env) == ["requesting", "admitted-unparsed"]


def test_client_error_on_the_post_is_a_rejection(env):
    env.generate = [Resp(400, {"error": "bad request"})]
    assert run(env, *draft_args(env)) != 0
    assert statuses(env) == ["requesting", "rejected"]


def test_network_error_outside_the_post_exits_with_one_line_and_no_query(env, capsys, monkeypatch):

    def boom(*a, **k):
        raise requests.ConnectionError("Max retries exceeded with url: /marble/v1/credits?" + SIGNED)

    monkeypatch.setattr(marble, "_http", boom)
    assert run(env, "credits") == 2
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1 and "SECRETSIGNATURE" not in err and "?" not in err


def test_credits_actual_is_null_when_another_row_came_after_the_admitted_one(env, capsys):
    env.polls = [PENDING, KeyboardInterrupt()]
    assert run(env, *draft_args(env)) == 130
    with open(env.root / "spend.jsonl", "a") as f:
        f.write(json.dumps({"status": "admitted", "operation_id": "op-other"}) + "\n")
    env.polls = [DONE]
    env.balances = [9000]
    assert run(env, "status", "op-1") == 0
    done = spend_rows(env)[-1]
    assert done["status"] == "done" and done["credits_actual"] is None
    assert done["usd"] == pytest.approx(150 / 1250)


# ---- signed URLs stay out of the terminal and out of files ----

def test_saved_world_json_has_no_query_strings(env):
    assert run(env, *draft_args(env)) == 0
    saved = (env.root / "pipeline" / "work" / "marble" / "w-1.json").read_text()
    assert "SECRETSIGNATURE" not in saved and "sig=" not in saved
    urls = json.loads(saved)["assets"]["splats"]["spz_urls"]
    assert urls["100k"] == "https://cdn.example/dl/100k"


def test_upload_connection_error_names_the_method_and_url_without_query(env, capsys):
    env.put_error = requests.ConnectionError("HTTPSConnectionPool: Max retries exceeded with url: /up?" + SIGNED)
    pano = marble.work_dir() / "pano-auto_2560.png"
    with pytest.raises(marble.Refusal) as exc:
        marble._upload(pano, KEY)
    assert "PUT https://store.example/up" in str(exc.value) and "?" not in str(exc.value)
    assert "SECRETSIGNATURE" not in repr(exc.value.__cause__)

    rc = run(env, *draft_args(env))
    err = capsys.readouterr().err
    assert rc != 0 and "SECRETSIGNATURE" not in err and "Traceback" not in err

    assert run(env, *draft_args(env), "--allow-base64") == 0


def test_download_connection_error_prints_no_query_and_no_traceback(env, capsys):
    env.download_error = requests.ConnectionError("failed: https://cdn.example/dl/100k?" + SIGNED)
    rc = run(env, *draft_args(env))
    err = capsys.readouterr().err
    assert rc == 2 and "GET https://cdn.example/dl/100k" in err
    assert "SECRETSIGNATURE" not in err and "Traceback" not in err
    assert len(err.strip().splitlines()) == 1


def test_export_download_error_prints_no_query(env, capsys):
    env.download_error = requests.ConnectionError("failed: https://cdn.example/dl/ply?" + SIGNED)
    assert run(env, "export", "w-1", "--format", "ply", "--resolution", "full_res") == 2
    err = capsys.readouterr().err
    assert "SECRETSIGNATURE" not in err and "GET https://cdn.example/dl/ply" in err


# ---- the upload gate is one exact line ----

@pytest.mark.parametrize("text", ["Clean for upload: yes\n", "Clean for upload: YES\n", "x\nclean for upload:   Yes  \ny\n"])
def test_gate_opens_on_the_exact_line(env, text):
    (env.root / "capture" / "NOTES.md").write_text(text)
    assert run(env, "credits") == 0


@pytest.mark.parametrize("text", [
    "Clean for upload: YES, apart from the hall mirror\n",
    "Clean for upload: not yet (was YES)\n",
    "- Clean for upload: yes\n",
    'Set "Clean for upload: YES" when done.\n',
    "Clean for upload:\nyes\n",
])
def test_gate_stays_shut_unless_the_whole_line_says_yes(env, text, capsys):
    (env.root / "capture" / "NOTES.md").write_text(text)
    assert run(env, "credits") == 2
    assert "Clean for upload" in capsys.readouterr().err


# ---- no network ----

def test_default_http_hits_the_socket_guard(network_guard):
    from conftest import NetworkBlocked
    # A closed local port: without the guard this would be a refused connection, not a NetworkBlocked.
    with pytest.raises(NetworkBlocked):
        marble._http("GET", "http://127.0.0.1:9/marble/v1/credits")
    assert len(network_guard) >= 1
    network_guard.clear()


def test_parse_balance_reads_the_live_reply():
    # The live /marble/v1/credits reply, seen 20 Nov 2026, is exactly {"remaining_credits": <float>}.
    assert marble.parse_balance({"remaining_credits": 13250.0}) == 13250.0


def test_poll_waits_through_a_404_just_after_admission(env):
    # Seen live 20 Nov 2026: the first GET of a fresh operation returned 404; a later one found it done.
    env.polls = [Resp(404, {"error": {"message": "not found"}}), PENDING, DONE]
    assert run(env, *draft_args(env)) == 0
    assert [r["status"] for r in spend_rows(env)] == ["requesting", "admitted", "done"]


def test_poll_gives_up_on_a_404_that_lasts(env, capsys):
    env.polls = [Resp(404, {"error": {"message": "not found"}})]
    assert run(env, *draft_args(env)) != 0
    assert "status op-1" in capsys.readouterr().err
    assert [r["status"] for r in spend_rows(env)] == ["requesting", "admitted"]

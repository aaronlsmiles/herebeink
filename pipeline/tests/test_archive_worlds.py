import json

import archive_worlds as aw
import marble

SIGNED = "https://cdn.example.test/w/pano.png?Signature=SECRET&Expires=1"


def _world():
    return {
        "world_id": "w1",
        "assets": {
            "imagery": {"pano_url": SIGNED},
            "thumbnail_url": "https://cdn.example.test/w/t.webp?X-Sig=SECRET",
            "mesh": {"collider_mesh_url": "https://cdn.example.test/w/c.glb?s=SECRET", "hq_mesh_url": None},
            "splats": {"spz_urls": {"full_res": "https://cdn.example.test/w/f.spz?s=SECRET"}},
        },
    }


def test_asset_file_names_come_from_the_url_path_not_the_query():
    names = dict(aw.asset_files(_world()))
    assert set(names) == {"pano.png", "thumbnail.webp", "collider.glb"}


def test_missing_assets_are_skipped_and_odd_extensions_get_the_default():
    w = {"assets": {"imagery": {"pano_url": "https://cdn.example.test/p.exe?x=1"}, "mesh": {"collider_mesh_url": None}}}
    assert [n for n, _ in aw.asset_files(w)] == ["pano.png"]
    assert aw.asset_files({}) == []


def test_world_ids_takes_only_uuid_named_json(tmp_path):
    for n in ["10361775-79cf-40d6-8193-a5dfa026f588.json", "pano-auto_2560.json", "x.txt"]:
        (tmp_path / n).write_text("{}")
    assert aw.world_ids(tmp_path) == ["10361775-79cf-40d6-8193-a5dfa026f588"]


def test_saved_json_has_no_query_strings_and_one_failure_does_not_stop_the_rest(tmp_path, monkeypatch):
    class R:
        def __init__(self, body):
            self._b = body

        def json(self):
            return self._b

    def fake_api(method, path, key, **kw):
        if method == "GET":
            return R(_world())
        return R({"response": {"url": "https://cdn.example.test/w/x.ply?s=SECRET"}})

    def fake_download(url, dest):
        if "t.webp" in url:
            raise marble.Refusal("download failed with 404")
        dest.write_bytes(b"data")

    monkeypatch.setattr(marble, "_api", fake_api)
    monkeypatch.setattr(marble, "_download", fake_download)
    res = aw.archive_world("w1", "k", tmp_path, log=lambda *_: None)
    saved = (tmp_path / "w1" / "world.json").read_text()
    assert "SECRET" not in saved and "Signature" not in saved
    assert json.loads(saved)["world_id"] == "w1"
    assert str(res["thumbnail.webp"]).startswith("FAILED")
    assert res["pano.png"] == 4 and res["splats_full_res.ply"] == 4
    assert not any("SECRET" in str(v) for v in res.values())


def test_the_mesh_export_is_never_requested(tmp_path, monkeypatch):
    calls = []

    class R:
        def json(self):
            return _world() if not calls or calls[-1][0] == "GET" else {"url": "https://cdn.example.test/a.ply"}

    def fake_api(method, path, key, **kw):
        calls.append((method, path, kw.get("json")))
        return R()

    monkeypatch.setattr(marble, "_api", fake_api)
    monkeypatch.setattr(marble, "_download", lambda url, dest: dest.write_bytes(b"x"))
    aw.archive_world("w1", "k", tmp_path, log=lambda *_: None)
    bodies = [c[2] for c in calls if c[2]]
    assert bodies == [{"asset_type": "splats", "format": "ply", "resolution": "full_res"}]

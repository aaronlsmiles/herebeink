import json

import pytest

import upload_media


class FakeR2:
    def __init__(self, existing=None):
        self.objects = dict(existing or {})

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            e = Exception("absent")
            e.response = {"Error": {"Code": "404"}}
            raise e
        return {"Metadata": {"sha256": self.objects[Key]}}

    def put_object(self, Bucket, Key, Body, ContentType, CacheControl, Metadata):
        assert CacheControl == upload_media.CACHE
        self.objects[Key] = Metadata["sha256"]


def manifest(tmp_path):
    root = tmp_path / "v1"
    root.mkdir()
    (root / "a.spz").write_bytes(b"abc")
    (root / "scene.json").write_text("{}")
    items = [{"key": f"herebeink/v1/{p.name}", "path": p.name, "bytes": p.stat().st_size,
              "sha256": upload_media.sha256_file(p), "content_type": "application/octet-stream"} for p in sorted(root.iterdir())]
    (tmp_path / "media_manifest.json").write_text(json.dumps({"prefix": "herebeink/v1/", "root": "v1", "items": items}))
    return upload_media.load(tmp_path)


def test_check_catches_a_changed_file(tmp_path):
    root, items = manifest(tmp_path)
    upload_media.check_local(root, items)
    (root / "a.spz").write_bytes(b"abd")
    with pytest.raises(ValueError, match="differ"):
        upload_media.check_local(root, items)


def test_upload_sends_missing_and_skips_identical(tmp_path):
    root, items = manifest(tmp_path)
    r2 = FakeR2({items[0]["key"]: items[0]["sha256"]})
    assert upload_media.upload(root, items, r2, "bucket", log=lambda *_: None) == {"uploaded": 1, "skipped": 1}


def test_upload_never_overwrites_a_published_object(tmp_path):
    root, items = manifest(tmp_path)
    r2 = FakeR2({items[0]["key"]: "0" * 64})
    with pytest.raises(ValueError, match="immutable"):
        upload_media.upload(root, items, r2, "bucket", log=lambda *_: None)


class EndpointConnectionError(Exception):
    """Shaped like botocore's: its message carries the endpoint URL, which holds the account id."""


class Unreachable(FakeR2):
    def head_object(self, Bucket, Key):
        raise EndpointConnectionError('Could not connect to the endpoint URL: '
                                      '"https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com/bucket/herebeink/v1/a.spz"')


def test_a_connection_error_is_reported_without_the_endpoint(tmp_path):
    root, items = manifest(tmp_path)
    said = []
    assert upload_media.run_upload(root, items, lambda: Unreachable(), "bucket", log=said.append) == 1
    text = " ".join(said)
    assert "EndpointConnectionError" in text and "Could not connect" in text
    assert "0123456789abcdef" not in text and "cloudflarestorage" not in text


class Answer:
    def __init__(self, headers, status=200):
        self.headers, self.status = headers, status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_verify_checks_lengths_and_a_cors_preflight_from_the_site(tmp_path):
    _, items = manifest(tmp_path)
    seen = []

    def opener(req):
        seen.append((req.get_method(), req.full_url, dict(req.header_items())))
        if req.get_method() == "OPTIONS":
            return Answer({"Access-Control-Allow-Origin": upload_media.SITE_ORIGIN})
        item = next(i for i in items if req.full_url.endswith(i["path"]))
        return Answer({"Content-Length": str(item["bytes"])})

    assert upload_media.verify_public(items, "https://media.example/", opener=opener) == []
    pre = [s for s in seen if s[0] == "OPTIONS"]
    assert pre and pre[0][2].get("Origin") == upload_media.SITE_ORIGIN

    def no_cors(req):
        if req.get_method() == "OPTIONS":
            return Answer({})
        return opener(req)

    problems = upload_media.verify_public(items, "https://media.example/", opener=no_cors)
    assert any("CORS" in p for p in problems)

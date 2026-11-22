import gzip

import numpy as np
import pytest

import splats
import spz


def test_transcode_keeps_every_splat_and_reports_the_header(tmp_path):
    rng = np.random.default_rng(0)
    n = 1234
    splats.write_splats(tmp_path / "a.ply", rng.random((n, 3)) * 3, rng.random((n, 3)), np.tile([0, 0, 1.0], (n, 1)),
                        np.tile([1.0, 0, 0], (n, 1)), size=0.01)
    spz.transcode([(tmp_path / "a.ply", tmp_path / "a.spz")])
    h = spz.header(tmp_path / "a.spz")
    assert h == {"version": 3, "splats": n, "shDegree": 0, "fractionalBits": 12, "flags": h["flags"]}


def test_not_an_spz_is_refused(tmp_path):
    (tmp_path / "x.spz").write_bytes(gzip.compress(b"\0" * 32))
    with pytest.raises(ValueError, match="not an SPZ"):
        spz.header(tmp_path / "x.spz")


def test_a_missing_ply_fails_loudly(tmp_path):
    with pytest.raises(RuntimeError, match="transcode.mjs failed"):
        spz.transcode([(tmp_path / "none.ply", tmp_path / "none.spz")])

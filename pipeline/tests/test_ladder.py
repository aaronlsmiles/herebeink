"""Part 2's scoring per direction from c (STATUS, "Part 2 criteria"): each cell of the panorama is seen,
imagined and right, imagined and wrong, empty, or unscored, by the frozen rules."""
import numpy as np
import pytest

import ladder

INF = np.inf


def grid(**cols):
    """One row of cells; each keyword a list, one value per cell."""
    n = len(next(iter(cols.values())))
    base = {"key": [2.0] * n, "in_v": [True] * n, "past": [False] * n, "marble": [2.0] * n, "frustum": [False] * n,
            "hall_ok": [False] * n, "wt": [1.0] * n}
    base.update(cols)
    return {k: np.array(v, dtype=float if k in ("key", "marble", "wt") else bool)[None, :] for k, v in base.items()}


def classes(g, tau=0.15):
    return ladder.classify(g["key"], g["in_v"], g["past"], g["marble"], g["frustum"], g["hall_ok"], tau)


def test_each_class_by_the_frozen_rules():
    g = grid(key=[2.0, 2.0, 2.0, 2.0, 2.0, INF, 2.0, 2.0, 2.0],
             in_v=[True, True, True, True, True, True, False, True, True],
             marble=[2.1, 2.1, 1.0, 1.0, INF, 2.0, 2.0, 1.0, 1.0],
             frustum=[True, False, True, False, False, False, False, False, False],
             past=[False, False, False, False, False, False, False, True, True],
             hall_ok=[False, False, False, False, False, False, False, True, False])
    c = classes(g)
    want = ["seen", "right", "wrong", "wrong", "empty", "notScanned", "outside", "wrong", "hallUnscored"]
    for name in ladder.CLASSES:
        assert c[name][0].tolist() == [w == name for w in want], name


def test_classes_partition_every_direction():
    rng = np.random.default_rng(0)
    n = 500
    g = grid(key=np.where(rng.random(n) < 0.1, INF, rng.uniform(1, 4, n)), in_v=rng.random(n) < 0.9,
             past=rng.random(n) < 0.2, marble=np.where(rng.random(n) < 0.05, INF, rng.uniform(1, 4, n)),
             frustum=rng.random(n) < 0.4, hall_ok=rng.random(n) < 0.5)
    c = classes(g)
    total = sum(c[k].astype(int) for k in ladder.CLASSES)
    assert (total == 1).all()


def test_shares_and_the_reference_line():
    # 10 scored cells: 3 in view and seen, 7 out of view: 2 right, 4 wrong, 1 empty; plus 2 not scanned
    g = grid(key=[2.0] * 10 + [INF, INF], marble=[2.0] * 3 + [2.05, 1.9] + [1.0] * 4 + [INF] + [2.0, 2.0],
             frustum=[True] * 3 + [False] * 9)
    s = ladder.shares(classes(g), g["wt"], g["frustum"])
    assert s["scored"] == pytest.approx(10 / 12)
    assert s["seen"] == pytest.approx(0.3)
    assert s["imagined"] == pytest.approx(0.6)  # right + wrong over the scored directions
    assert s["empty"] == pytest.approx(0.1)
    assert s["imaginedRight"] == pytest.approx(2 / 6)  # over the imagined directions
    assert s["completeness"] == pytest.approx(2 / 7)  # out of view, within tau of the key
    assert s["notScanned"] == pytest.approx(2 / 12)


def test_tau_moves_the_line_between_seen_and_wrong():
    g = grid(marble=[2.1, 2.1], frustum=[True, False])
    assert classes(g, tau=0.05)["wrong"][0].tolist() == [True, True]
    assert classes(g, tau=0.15)["seen"][0].tolist() == [True, False]
    assert classes(g, tau=0.15)["right"][0].tolist() == [False, True]


def test_splat_classes_follow_their_own_distance_to_the_key():
    # splats on one ray (cell 0, key at 2 m): at the key, floating in front, behind the wall (outside V)
    key = np.array([[2.0]])
    r = np.array([2.05, 1.0, 3.0, 1.0])
    cell = np.zeros(4, int)
    in_v = np.array([True, True, False, True])
    past = np.array([False, False, False, True])
    near_key_pt = np.array([False, False, False, False])
    frustum = np.array([True, True, True, True])
    k = ladder.splat_classes(key.reshape(-1), cell, r, in_v, past, near_key_pt, frustum, 0.15)
    assert k.tolist() == [ladder.SEEN, ladder.WRONG, ladder.IMAGINED, ladder.IMAGINED]


def test_kr3_noise_rule():
    # R4's seeds 0.50 and 0.56 (mean 0.53); steps |R4 - R2| = 0.13 and |R8 - R4| = 0.05: 0.06 > 0.05, within noise
    assert ladder.kr3({"R2": 0.40, "R4": 0.50, "R4b": 0.56, "R8": 0.58}) == {
        "seedGap": pytest.approx(0.06), "smallerStep": pytest.approx(0.05), "withinNoise": True}
    assert ladder.kr3({"R2": 0.30, "R4": 0.50, "R4b": 0.52, "R8": 0.70})["withinNoise"] is False
    # one neighbour missing (not placed): that step alone
    assert ladder.kr3({"R4": 0.50, "R4b": 0.52, "R8": 0.70})["smallerStep"] == pytest.approx(0.19)


def test_phone_pick_keeps_every_class_in_proportion():
    import ladder_export
    k = np.repeat([0, 1, 2], [200_000, 500_000, 300_000]).astype(np.int8)
    keep = ladder_export.phone_pick(k, n=100_000)
    assert keep.sum() == 100_000
    shares = np.bincount(k[keep], minlength=3) / 100_000
    assert shares == pytest.approx([0.2, 0.5, 0.3], abs=0.01)
    assert ladder_export.phone_pick(k[:10], n=100).all()

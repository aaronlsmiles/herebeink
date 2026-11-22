import pytest

import make_pairs


def frames():
    head = ["0@0", "90@0"]
    out = [{"name": f"2head_{k:04d}", "pass": "head", "sample": k, "views": head} for k in range(6)]
    out += [{"name": f"1raised_{k:04d}", "pass": "raised", "sample": k, "views": head} for k in range(4)]
    out += [{"name": "5pano_0000", "pass": "pano", "sample": 0, "views": ["0@0"]}]
    return out


def test_anchor_pairs_link_passes_and_never_pair_inside_one():
    pairs = make_pairs.anchor_pairs(frames(), phone=["phone/g/A.jpg", "phone/g/B.jpg"], every=3)
    group = lambda n: n.split("/")[-1].split("_")[0] if n.startswith("rig/") else "phone"  # noqa: E731
    cross = [(a, b) for a, b in pairs if "phone" not in (group(a), group(b))]
    assert cross and all(group(a) != group(b) for a, b in cross)
    # anchors: head samples 0 and 3, raised 0 and 3, the pano: (2 + 2) views each, 1 pano view
    assert len(cross) == 4 * 4 + 4 * 1 + 4 * 1
    assert ("phone/g/A.jpg", "phone/g/B.jpg") in pairs
    assert ("phone/g/A.jpg", "rig/y000p00/2head_0000.jpg") in pairs
    assert len(pairs) == len(set(pairs))


def test_pass_pairs_are_every_pair_in_the_pass():
    pairs = make_pairs.pass_pairs(frames(), "raised")
    n = 4 * 2
    assert len(pairs) == n * (n - 1) // 2
    with pytest.raises(ValueError):
        make_pairs.pass_pairs(frames(), "hip")

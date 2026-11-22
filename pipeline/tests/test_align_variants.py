"""Gate A against deliberately wrong inputs (the independent review's variants). Slow: about three minutes.

Each variant changes the Marble export (or the pano images) of one synthetic day and runs align.py. The
rule under test: Gate A never says PASS with a wrong pose. Either the right pose is found and passes, or
the gate fails and says why.
"""
import json
import shutil

import numpy as np
import pytest
from plyfile import PlyData, PlyElement
from scipy.spatial.transform import Rotation

import align
import scale
import splats
import synth_world

pytestmark = pytest.mark.slow
CORNERS = np.array([[x, y, z] for x in (-2, 2) for y in (0, 2.5) for z in (-1.6, 1.6)])
MARKER = np.array([[2.9, 0.4, 2.15]])  # the invented thing round the hallway's turn, on the +z side
FLIP = np.diag([1.0, -1, -1])
MIRROR = np.diag([-1.0, 1, 1])
RESULTS = []


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    root = tmp_path_factory.mktemp("variants")
    info = synth_world.write_scene(root, 700, 500, world_id="fx")
    work = info["work"]
    assert scale.main(["--work", str(work), "--notes", str(info["notes"])]) == 0
    shutil.copy2(work / "splat" / "splat_raw.ply", work / "splat" / "measured.ply")
    return work


def warp(p):
    q = p.copy()
    q[:, 0] = p[:, 0] * 1.04  # the room 4 % longer
    q[:, 2] = p[:, 2] + 0.08 * np.sin(p[:, 0] * 1.2)  # walls bowed by up to 8 cm
    q[:, 1] = p[:, 1] * 0.97  # the ceiling 3 % lower
    return q


def make(base, tmp_path, name, linear=None, world_fn=None, msf_mult=1.0, sh3=False, no_photos=False):
    work = tmp_path / name
    shutil.copytree(base, work, ignore=shutil.ignore_patterns("align"))
    path = work / "marble" / "marble_fx.ply"
    rows = splats.read(path, quiet=True)["vertex"].data
    raw = np.stack([rows["x"], rows["y"], rows["z"]], 1).astype(float)
    truth = synth_world.world_from_marble_true()
    if world_fn is not None:
        raw = splats.apply(splats.invert(truth), world_fn(splats.apply(truth, raw)))
    if linear is not None:
        raw = raw @ np.asarray(linear).T
    names = list(rows.dtype.names)
    if sh3:
        names = names[:9] + [f"f_rest_{i}" for i in range(45)] + names[9:]
    arr = np.zeros(len(rows), dtype=[(n, "<f4") for n in names if n not in ("nx", "ny", "nz")] if sh3 else rows.dtype)
    for n in arr.dtype.names:
        arr[n] = rows[n] if n in rows.dtype.names else np.random.default_rng(3).normal(0, 0.05, len(rows))
    arr["x"], arr["y"], arr["z"] = raw.T
    PlyData([PlyElement.describe(arr, "vertex")], text=False, byte_order="<").write(str(path))
    j = json.loads((work / "marble" / "fx.json").read_text())
    j["assets"]["splats"]["semantics_metadata"]["metric_scale_factor"] *= msf_mult
    (work / "marble" / "fx.json").write_text(json.dumps(j))
    if no_photos:
        shutil.rmtree(work / "images")
    code = align.main(["--work", str(work), "--world", "fx"])
    r = json.loads((work / "align" / "fx" / "align.json").read_text())
    assert (code == 0) == r["gateA"]["pass"]
    return r


def corner_error(r, linear):
    """Largest error at the room's corners, through the variant's own raw frame."""
    truth = synth_world.world_from_marble_true()
    raw = splats.apply(splats.invert(truth), CORNERS) @ np.asarray(linear).T
    return float(np.linalg.norm(splats.apply(np.array(r["world_from_marble"]), raw) - CORNERS, axis=1).max())


def record(name, r, err=None):
    g, h = r["gateA"], r["hypothesis"]
    RESULTS.append(f"{name:34s} {align.label((h['yawDeg'], h['mirror'], h['flip'])):26s} "
                   f"median {r['residual']['medianCm'] if r['residual']['medianCm'] is not None else '-':>6} cm  photo {g['photometric']['score']}  "
                   f"margin {g['photometric']['margin']}  {'PASS' if g['pass'] else 'FAIL'}"
                   + ("" if err is None else f"  corner error {err * 100:.1f} cm")
                   + ("" if g["pass"] else f"  ({'; '.join(g['reasons'])})"))
    print(RESULTS[-1])


def right_pose_passes(r, name, linear, mirror, flip, tol=0.03):
    err = corner_error(r, linear)
    record(name, r, err)
    assert r["gateA"]["pass"], r["gateA"]["reasons"]
    assert err < tol
    assert (r["hypothesis"]["mirror"], r["hypothesis"]["flip"]) == (mirror, flip)


@pytest.mark.parametrize("name,linear,mirror,flip", [
    ("as generated", np.eye(3), False, False),
    ("mirrored (raw +x is left)", MIRROR, True, False),
    ("turned over (exported y-up)", FLIP, False, True),
    ("mirrored and turned over", FLIP @ MIRROR, True, True),
    ("turned a further 9 degrees", Rotation.from_euler("y", 9, degrees=True).as_matrix(), False, False),
])
def test_wrong_frames_are_found_or_refused(base, tmp_path, name, linear, mirror, flip):
    right_pose_passes(make(base, tmp_path, "v", linear=linear), name, linear, mirror, flip)


@pytest.mark.parametrize("mult", [1.2 / 1.04, 0.8 / 1.04], ids=["factor 20 % high", "factor 20 % low"])
def test_a_wrong_metric_factor_is_absorbed_and_reported(base, tmp_path, mult):
    r = make(base, tmp_path, "m", msf_mult=mult)
    right_pose_passes(r, f"metric factor x {mult * 1.04:.1f}", np.eye(3), False, False)
    assert r["scale"]["ratioToMetricFactor"] == pytest.approx(1 / (mult * 1.04), rel=0.01)


def test_a_world_five_times_too_big_fails_with_the_reason(base, tmp_path):
    r = make(base, tmp_path, "big", linear=5 * np.eye(3))
    err = corner_error(r, 5 * np.eye(3))
    record("five times too big (factor unchanged)", r, err)
    assert r["gateA"]["pass"] is False or err < 0.03
    if not r["gateA"]["pass"]:
        assert r["gateA"]["reasons"]


@pytest.mark.parametrize("mirrored", [False, True], ids=["reshaped", "reshaped and mirrored"])
def test_a_reimagined_room_keeps_the_hallway_on_its_side(base, tmp_path, mirrored):
    lin = MIRROR if mirrored else np.eye(3)
    r = make(base, tmp_path, "w", world_fn=warp, linear=lin)
    truth = synth_world.world_from_marble_true()
    raw_marker = splats.apply(splats.invert(truth), warp(MARKER)) @ lin.T
    marker = splats.apply(np.array(r["world_from_marble"]), raw_marker)[0]
    record("reshaped" + (" and mirrored" if mirrored else ""), r)
    if r["gateA"]["pass"]:
        assert (r["hypothesis"]["mirror"], r["hypothesis"]["flip"]) == (mirrored, False)
        assert marker[2] > 1.5 and np.linalg.norm(marker - warp(MARKER)[0]) < 0.3, marker
    else:
        assert r["gateA"]["reasons"]


def test_sh_degree_three_marble(base, tmp_path):
    r = make(base, tmp_path, "sh", sh3=True)
    right_pose_passes(r, "SH degree 3", np.eye(3), False, False)


def test_without_the_pano_views_the_gate_fails_and_says_why(base, tmp_path):
    r = make(base, tmp_path, "np", no_photos=True)
    record("pano views missing", r)
    assert not r["gateA"]["pass"]
    assert any("photometric check not possible" in x for x in r["gateA"]["reasons"])


def test_accept_by_eye_is_recorded(base, tmp_path):
    work = tmp_path / "eye"
    shutil.copytree(base, work, ignore=shutil.ignore_patterns("align", "images"))
    assert align.main(["--work", str(work), "--world", "fx", "--accept-by-eye", "contact sheet and table read: right way round"]) == 0
    g = json.loads((work / "align" / "fx" / "align.json").read_text())["gateA"]
    assert g["pass"] and g["acceptedByEye"] == "contact sheet and table read: right way round"
    assert not g["photometric"]["pass"]


def test_zz_print_the_table():
    print("\n" + "\n".join(RESULTS))

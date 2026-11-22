import json

import numpy as np
import pytest
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

import align
import splats
import synth_world


def test_hypotheses_are_rotations_or_mirrors():
    assert align.hypothesis(0, False) == pytest.approx(np.eye(3))
    assert np.linalg.det(align.hypothesis(90, True)) == pytest.approx(-1)
    assert align.hypothesis(180, False) @ [0, 0, 1] == pytest.approx([0, 0, -1])


def test_initial_puts_marble_origin_at_the_pano_and_forward_through_the_door():
    w_from_c = synth_world.world_from_colmap()
    model = synth_world.write_colmap(*[__import__("pathlib").Path(__import__("tempfile").mkdtemp()) / p for p in ("m", "w")])
    pano_c, r_cam = align.pano_pose(model)
    t = align.initial(w_from_c, pano_c, r_cam, 2.0, align.hypothesis(0, False))
    origin, forward = splats.apply(t, np.array([[0.0, 0, 0], [0, 0, 1.0]]))
    assert origin == pytest.approx(synth_world.PANO_W, abs=1e-9)
    assert (forward - origin) == pytest.approx([2.0, 0, 0], abs=1e-9)
    assert splats.split(t)[0] == pytest.approx(2.0)


def test_residual_follows_the_frozen_definition():
    measured = np.zeros((1, 3))
    marble = np.array([[0.01, 0, 0], [0.02, 0, 0], [0.03, 0, 0], [0.5, 0, 0], [2.0, 0, 0]])
    r = align.residual(np.eye(4), marble, cKDTree(measured))
    # numpy linear percentile of 1, 2, 3, 50 cm: 3 + 0.7 * 47
    assert r == {"medianCm": 2.5, "p90Cm": pytest.approx(35.9), "icpSet": 4}


def planes(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    a, b = rng.random(n) * 3, rng.random(n) * 3
    pts = np.concatenate([np.c_[a, b, 0 * a], np.c_[a, 0 * a, b], np.c_[0 * a, a, b], np.c_[a, b, 0 * a + 2.5]])
    nrm = np.concatenate([np.tile([0, 0, 1.0], (n, 1)), np.tile([0, 1.0, 0], (n, 1)), np.tile([1.0, 0, 0], (n, 1)),
                          np.tile([0, 0, -1.0], (n, 1))])
    return pts, nrm


def test_similarity_round_recovers_scale_rotation_and_shift():
    tgt, nrm = planes()
    src, _ = planes(seed=1)
    true = splats.sim3(1.015, Rotation.from_euler("xyz", [1, -2, 1.5], degrees=True).as_matrix(), [0.03, -0.02, 0.01])
    start = splats.invert(true)
    t = align.similarity_round(start, src, tgt, nrm, dist=0.15, iters=40)
    assert splats.split(t)[0] == pytest.approx(1.0, abs=2e-3)
    assert np.abs(splats.apply(t, src) - src).max() < 0.01


def test_two_way_prefers_the_matching_shape():
    tgt, _ = planes()
    tree = cKDTree(tgt)
    same = align.two_way(np.eye(4), planes(seed=2)[0], tree, tgt)
    turned = align.two_way(splats.sim3(1, Rotation.from_euler("z", 90, degrees=True).as_matrix(), [3, 0, 0]),
                           planes(seed=2)[0], tree, tgt)
    assert same < 0.5 * turned


def test_metric_factor_is_required():
    with pytest.raises(ValueError, match="metric_scale_factor"):
        align.metric_factor({"assets": {}})
    assert align.metric_factor(synth_world.marble_json("w")) == (synth_world.MSF_REPORTED, pytest.approx(0.941, abs=1e-3))


@pytest.mark.slow
@pytest.mark.parametrize("corridor", [True, False], ids=["with the planted corridor", "room only"])
def test_marble_copy_recovered_to_a_centimetre(tmp_path, corridor):
    import shutil
    import scale
    info = synth_world.write_scene(tmp_path, 1000, 700, corridor=corridor)
    work, notes = info["work"], info["notes"]
    assert scale.main(["--work", str(work), "--notes", str(notes)]) == 0
    shutil.copy2(work / "splat" / "splat_raw.ply", work / "splat" / "measured.ply")
    assert align.main(["--work", str(work), "--world", "synthworld"]) == 0
    r = json.loads((work / "align" / "synthworld" / "align.json").read_text())
    t, truth = np.array(r["world_from_marble"]), synth_world.world_from_marble_true()
    corners = np.array([[x, y, z] for x in (-2, 3.1) for y in (0, 2.5) for z in (-1.6, 2.5)])
    err = np.linalg.norm(splats.apply(t, splats.apply(splats.invert(truth), corners)) - corners, axis=1)
    assert err.max() < 0.01, f"{err.max() * 100:.2f} cm"
    assert r["hypothesis"] == {"yawDeg": 0, "mirror": False, "flip": False, "rawDown": "+y"}
    assert r["gateA"]["pass"] and r["residual"]["medianCm"] < 3
    assert r["scale"]["ratioToMetricFactor"] == pytest.approx(1 / 1.04, abs=0.003)
    assert (work / "align" / "synthworld" / "contact.png").exists()


# ---- the hypothesis set, the gravity and photometric checks, the gate ----

def test_hypotheses_include_the_half_turn_about_x_and_say_which_raw_axis_is_down():
    hs = align.HYPOTHESES
    assert len(hs) == 48 and len(set(hs)) == 48
    assert {(m, f) for _, m, f in hs} == {(False, False), (True, False), (False, True), (True, True)}
    for yaw, mirror, flip in hs:
        h = align.hypothesis(yaw, mirror, flip)
        # the raw axis the hypothesis calls down lands on the pano camera's down (+y in OpenCV axes)
        assert h @ align.raw_down(flip) == pytest.approx([0, 1, 0], abs=1e-12)
    assert align.raw_down(True) == pytest.approx([0, -1, 0])
    assert align.hypothesis(0, False, True) == pytest.approx(np.diag([1.0, -1, -1]))


@pytest.mark.parametrize("text,expect", [("0", (0.0, False, False)), ("17.5", (17.5, False, False)),
                                         ("180,mirror", (180.0, True, False)), ("45,flip,mirror", (45.0, True, True))])
def test_start_accepts_any_yaw(text, expect):
    assert align.parse_start(text) == expect


def test_start_refuses_an_unknown_word():
    with pytest.raises(ValueError, match="sideways"):
        align.parse_start("10,sideways")


def test_gravity_angle_of_a_pose():
    t = synth_world.world_from_marble_true()  # raw +y is down
    assert align.gravity_deg(t, flip=False) == pytest.approx(0, abs=1e-6)
    assert align.gravity_deg(t, flip=True) == pytest.approx(180, abs=1e-6)
    tilted = splats.sim3(1.7, Rotation.from_euler("x", 12, degrees=True).as_matrix() @ splats.split(t)[1], [0, 0, 0])
    assert align.gravity_deg(tilted, flip=False) == pytest.approx(12, abs=1e-6)


def gate_input(**over):
    r = {"residual": {"medianCm": 2.0, "p90Cm": 40.0, "icpSet": 900}, "marbleSplats": 1000,
         "chosen": {"gravityDeg": 1.0, "rawDown": "+y"},
         "photometric": {"score": 0.9, "runnerUp": {"yawDeg": 180, "mirror": False, "flip": False, "score": 0.5}},
         "scale": {"ratioToMetricFactor": 0.96}}
    for k, v in over.items():
        r[k] = v
    return r


def test_gate_passes_only_when_every_check_holds():
    g = align.gate(gate_input())
    assert g["pass"] and g["residualPass"] and g["reasons"] == []
    assert g["gravity"]["pass"] and g["photometric"]["pass"] and g["icpShare"]["pass"] and g["metricRatio"]["pass"]


@pytest.mark.parametrize("over,reason", [
    ({"chosen": {"gravityDeg": 25.0, "rawDown": "+y"}}, "down"),
    ({"photometric": {"score": 0.6, "runnerUp": {"yawDeg": 0, "mirror": True, "flip": False, "score": 0.55}}}, "photometric"),
    ({"photometric": {"score": None, "runnerUp": None, "reason": "no pano views"}}, "no pano views"),
    ({"marbleSplats": 10000}, "share"),
    ({"scale": {"ratioToMetricFactor": 0.2}}, "metric"),
    ({"residual": {"medianCm": 12.0, "p90Cm": 40.0, "icpSet": 900}}, "residual"),
])
def test_gate_fails_with_a_reason(over, reason):
    g = align.gate(gate_input(**over))
    assert not g["pass"] and any(reason in r for r in g["reasons"]), g["reasons"]


def test_accept_by_eye_overrides_the_added_checks_but_never_the_frozen_residual():
    g = align.gate(gate_input(chosen={"gravityDeg": 25.0, "rawDown": "+y"}), accept_by_eye="looked at contact.png: right")
    assert g["pass"] and g["acceptedByEye"] == "looked at contact.png: right" and g["reasons"]
    g = align.gate(gate_input(residual={"medianCm": 12.0, "p90Cm": 40.0, "icpSet": 900}), accept_by_eye="looked")
    assert not g["pass"]


def test_residual_queries_use_every_core():
    import inspect
    assert "workers=-1" in inspect.getsource(align.residual)


def test_the_photometric_sample_is_spread_over_the_whole_file():
    pick = align.sample(1_000_000, 300_000)
    opacity = np.ones(1_000_000)
    chosen = align.photo_pick(pick, opacity, 1000)
    assert len(chosen) == 1000 and len(set(chosen)) == 1000 and set(chosen) <= set(pick)
    assert chosen.max() > 900_000 and chosen.min() < 100_000  # not the first thousand of a sorted sample
    faint = np.where(np.arange(1_000_000) % 2 == 0, 0.05, 0.9)
    assert (faint[align.photo_pick(pick, faint, 1000)] >= align.PHOTO_MIN_OPACITY).all()

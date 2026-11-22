"""A flat rung placed on what it saw: align.search with the rung's frustum as the fit mask and the origin held at c.

The world here is the measured frame itself (world_from_colmap is the identity), so c is a world point and
the pano camera faces +x: its rig axes are x right (+z in the world), y down, z forward (+x in the world).
Marble's world is the box room seen from c, turned 40 degrees about the camera's down axis, in raw
units of 1.3 m, plus junk behind the camera that only an unmasked fit would see.
"""
import numpy as np
import pytest
from PIL import Image

import align
import ladder_views
import splats
import synth_world
import visibility

C = np.array([0.5, 1.3, 0.3])
RIG_FROM_WORLD = synth_world.CAM_FACING_X.T
LO, HI = np.array([-2.0, 0.0, -1.6]), np.array([2.0, 2.5, 1.6])
MSF_TRUE = 1.3
MSF = MSF_TRUE * 1.04  # the reported factor 4 % off, as in synth_world
MARBLE_YAW = 40.0
CORNER_VIEW_YAW = 45.0  # looks into the +x, +z corner: two walls in the frame
WALL_VIEW_YAW = 0.0  # looks straight at the x = 2 wall: one flat wall fills the frame
POSE = visibility.Pose(C, RIG_FROM_WORLD)


def manifest(yaw: float) -> dict:
    f = "pipeline/work/ladder/views/az000.png"
    return {"fov_deg": {"h": ladder_views.H_FOV_DEG, "v": round(ladder_views.V_FOV_DEG, 4)}, "size": list(ladder_views.SIZE),
            "d_yaw_deg": yaw, "views": [{"azimuth": 0, "file": f, "pano_yaw_deg": yaw}], "rungs": {"R1": [f]}}


def box(density: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return synth_world.sample(synth_world.box_faces(LO, HI, "wall", inside=True), density, rng)[0]


def junk_behind(world: np.ndarray, view_yaw: float, share: float, seed: int) -> np.ndarray:
    """share x len(world) points 0.5 m in front of the walls behind the camera, on their own rays from c (so
    still outside the frustum), close enough to the room for an unmasked fit to take them in."""
    rng = np.random.default_rng(seed)
    d, r = visibility.rig_dirs(POSE, world)
    fwd = np.array([np.sin(np.radians(view_yaw)), 0.0, np.cos(np.radians(view_yaw))])
    behind = np.flatnonzero((d @ fwd < -0.3) & (r > 1.0))
    pick = rng.choice(behind, int(share * len(world)))
    return world[pick] - visibility.world_dirs(POSE, d[pick]) * 0.5


def marble_raw(view_yaw: float, origin=C, seed: int = 2) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    world = box(500, seed)
    world = world + 0.003 * rng.standard_normal(world.shape)
    junk = junk_behind(world, view_yaw, 0.3, seed + 1)
    true = splats.sim3(MSF_TRUE, RIG_FROM_WORLD.T @ align.hypothesis(MARBLE_YAW, False), origin)
    return splats.apply(splats.invert(true), np.vstack([world, junk])), world


def run(view_yaw: float, origin=C):
    measured = box(3000, 1)
    raw, world = marble_raw(view_yaw, origin)
    m = manifest(view_yaw)
    mask = align.rung_mask(POSE, m, "R1")
    r = align.search(measured, raw, np.eye(4), C, RIG_FROM_WORLD, MSF, mask_fn=mask, hold=C, log=lambda *_: None)
    in_frustum = int(visibility.in_rung(visibility.rig_dirs(POSE, world)[0], m, "R1").sum())
    return r, in_frustum, len(raw)


def test_masked_fit_recovers_the_pose_and_ignores_the_outside():
    r, in_frustum, n = run(CORNER_VIEW_YAW)
    t = np.array(r["world_from_marble"])
    assert np.linalg.norm(t[:3, 3] - C) < 1e-6
    assert r["residual"]["medianCm"] < 2.0
    # the fit set is the frustum's share of the room, none of the junk
    assert r["fitSetSplats"] == pytest.approx(in_frustum, rel=0.03) and r["fitSetSplats"] < 0.5 * n
    assert r["residual"]["icpSet"] <= r["fitSetSplats"]
    assert r["scale"]["metresPerRawUnit"] == pytest.approx(MSF_TRUE, rel=0.005)
    assert r["worldYawDeg"] == pytest.approx(MARBLE_YAW, abs=0.5)
    assert r["translationTestable"] and r["translationReleaseM"] < 0.03
    g = align.gate(r)
    assert g["translation"]["pass"] and not any("translation" in x for x in g["reasons"])


def test_release_check_flags_a_world_built_off_c():
    # 0.3 m off c, away from the x = 2 wall and towards the z = 1.6 wall. Not every 0.3 m offset shows: on two walls
    # the held fit's yaw and scale about c absorb some directions to under a centimetre (0.20 m towards
    # +x and -z left a 1.0 cm residual and a 0.015 m release), and none along the walls' shared vertical.
    off = 0.3 * np.array([-1.3, 0.0, 1.5]) / np.hypot(1.3, 1.5)
    r, _, _ = run(CORNER_VIEW_YAW, origin=C + off)
    assert r["translationTestable"] and r["translationReleaseM"] > 0.10
    assert r["translationReleaseM"] == pytest.approx(0.3, abs=0.05)
    g = align.gate(r)
    assert not g["pass"]
    assert not g["translation"]["pass"] and any("translation" in x for x in g["reasons"])
    # a person who has looked cannot overrule it: the world is not the one its inputs describe
    assert not align.gate(r, accept_by_eye="looked")["pass"]


def test_one_flat_wall_is_not_testable():
    r, _, _ = run(WALL_VIEW_YAW)
    assert r["translationTestable"] is False
    g = align.gate(r)
    assert g["translation"]["pass"] and g["translation"]["note"] == "translation not testable"


# ---- the colour check's views and the command line ----

def test_ladder_input_views_draw_where_the_cut_put_them(tmp_path):
    m = manifest(30.0)
    f = tmp_path / m["views"][0]["file"]
    f.parent.mkdir(parents=True)
    Image.new("RGB", ladder_views.SIZE, (200, 100, 50)).save(f)
    (v,) = align.ladder_input_views(m, "R1", POSE, root=tmp_path)
    assert v.image.shape == (72, 96)
    # a world point in a known pano direction lands where ladder_views.project puts that direction, scaled
    lon, lat = 30.0 + 12.0, -8.0
    d_rig = np.array([np.cos(np.radians(lat)) * np.sin(np.radians(lon)), -np.sin(np.radians(lat)),
                      np.cos(np.radians(lat)) * np.cos(np.radians(lon))])
    p = C + visibility.world_dirs(POSE, d_rig[None])[0] * 2.0
    x = splats.apply(v.cam_from_world, p[None])[0]
    uv = np.array([v.k[0, 0] * x[0] / x[2] + v.k[0, 2], v.k[1, 1] * x[1] / x[2] + v.k[1, 2]])
    want = np.array(ladder_views.project({"lon": lon, "lat": lat}, 30.0)) * 96 / ladder_views.SIZE[0]
    assert uv == pytest.approx(want, abs=1e-3)  # the manifest keeps V_FOV to 4 places


@pytest.mark.parametrize("argv,needs", [(["--fit-mask", "seen"], "--rung"), (["--rung", "R1"], "--fit-mask seen"),
                                        (["--rung", "R1", "--fit-mask", "seen", "--mode", "doorway"], "doorway")])
def test_fit_mask_seen_and_rung_go_together(argv, needs, capsys):
    with pytest.raises(SystemExit):
        align.main(["--world", "w", *argv])
    assert needs in capsys.readouterr().err



def hazy_room(seed: int = 11) -> tuple[np.ndarray, np.ndarray]:
    """Sparse walls with dense haze in front of them on the camera's rays, as the trained splat holds: the
    centres a fit would aim at, and the walls alone (what the answer-key surface finds)."""
    rng = np.random.default_rng(seed)
    walls = box(300, 1)
    d, _ = visibility.rig_dirs(POSE, walls)
    rep = np.repeat(np.arange(len(walls)), 8)
    haze = walls[rep] - visibility.world_dirs(POSE, d[rep]) * rng.uniform(0.05, 0.9, len(rep))[:, None]
    return np.vstack([walls, haze]), walls


def hazy_run(fit_target):
    measured, walls = hazy_room()
    raw, _ = marble_raw(CORNER_VIEW_YAW)
    m = manifest(CORNER_VIEW_YAW)
    mask = align.rung_mask(POSE, m, "R1")
    target = None if fit_target is None else fit_target(walls, m)
    return align.search(measured, raw, np.eye(4), C, RIG_FROM_WORLD, MSF, mask_fn=mask, hold=C, log=lambda *_: None,
                        fit_target=target)


def test_haze_pulls_a_fit_aimed_at_every_measured_centre():
    # the failure seen on R1 (hub call 95): the world shrinks and turns towards the haze, and the residual,
    # read against the same haze, still looks small
    r = hazy_run(None)
    off = r["scale"]["metresPerRawUnit"] < 0.95 * MSF_TRUE or abs(r["worldYawDeg"] - MARBLE_YAW) > 5
    assert off and r["residual"]["medianCm"] < 10


def test_a_fit_aimed_at_the_key_surface_ignores_the_haze():
    def key_in_view(walls, m):
        # the key is a rendered surface, dense where the scan's walls are sparse
        key = box(3000, 3)
        return key[visibility.in_rung(visibility.rig_dirs(POSE, key)[0], m, "R1")]
    r = hazy_run(key_in_view)
    t = np.array(r["world_from_marble"])
    assert np.linalg.norm(t[:3, 3] - C) < 1e-6
    assert r["scale"]["metresPerRawUnit"] == pytest.approx(MSF_TRUE, rel=0.01)
    assert r["worldYawDeg"] == pytest.approx(MARBLE_YAW, abs=1.0)
    assert r["fitTarget"] == "answer-key surface"
    assert r["keyResidual"]["medianCm"] < 2.0
    # the frozen residual is still read against every measured centre, haze included
    assert r["residual"]["icpSet"] > 0

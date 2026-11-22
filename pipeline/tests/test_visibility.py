"""Part 2, Task 0.5: each rung's seen region by construction and the answer-key panorama from c."""
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

import ladder_views as lv
import visibility as vis

LO, HI = np.array([-2.0, 0.0, -1.5]), np.array([2.0, 2.5, 1.5])
C = np.array([0.0, 1.25, 0.0])
# The rig frame has y down; the world has y up. A camera looking along world +z with y down:
RIG_FROM_WORLD = np.diag([-1.0, -1.0, 1.0])


def rect_share(h, v):
    a, b = np.radians(h / 2), np.radians(v / 2)
    return 4 * np.arcsin(np.sin(a) * np.sin(b)) / (4 * np.pi)


def manifest(d=0.0):
    return {"views": [{"azimuth": az, "file": f"az{az:03d}.png", "pano_yaw_deg": d + az} for az in range(0, 360, 45)],
            "rungs": {"R1": ["az000.png"], "R2": ["az000.png", "az180.png"],
                      "R4": [f"az{a:03d}.png" for a in (0, 90, 180, 270)],
                      "R8": [f"az{a:03d}.png" for a in range(0, 360, 45)]},
            "fov_deg": {"h": 66.0, "v": lv.V_FOV_DEG}}


# ---- geometry ----

def test_one_view_matches_the_rectangle_solid_angle():
    assert vis.share_by_construction(manifest(), "R1") == pytest.approx(rect_share(66.0, lv.V_FOV_DEG), abs=2e-4)


def test_nested_rungs_and_their_sizes():
    m = manifest(-10.16)
    s = {r: vis.share_by_construction(m, r) for r in ("R1", "R2", "R4", "R8")}
    assert s["R2"] == pytest.approx(2 * s["R1"], abs=2e-4)
    assert s["R4"] == pytest.approx(4 * s["R1"], abs=5e-4)
    assert s["R4"] < s["R8"] < 8 * s["R1"]  # R8's neighbours overlap
    assert vis.share_by_construction(m, "R4r") == s["R4"]
    assert vis.share_by_construction(m, "P") == pytest.approx(1.0)


def test_frustum_agrees_with_ladder_views_project():
    rng = np.random.default_rng(0)
    d = rng.normal(size=(4000, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    yaw = 34.84
    mine = vis.in_view(d, yaw)
    assert 0.03 < mine.mean() < 0.12
    for k in range(0, 4000, 7):
        lon, lat = lv.lon_lat(d[k])
        p = lv.project({"lon": lon, "lat": lat}, yaw)
        theirs = p is not None and 0 <= p[0] <= lv.SIZE[0] and 0 <= p[1] <= lv.SIZE[1]
        assert mine[k] == theirs


def test_rig_dirs_round_trip():
    rot = Rotation.from_euler("y", 30, degrees=True).as_matrix()
    pose = vis.Pose(np.array([0.0, 1.4, 0.0]), rot)
    d, r = vis.rig_dirs(pose, np.array([[0.0, 1.4, 2.0]]))
    assert r[0] == pytest.approx(2.0)
    assert d[0] == pytest.approx(rot @ np.array([0, 0, 1.0]))


def test_equirect_cells_round_trip_and_weights():
    dirs, w = vis.equirect_dirs(1.0)
    assert dirs.shape == (180, 360, 3) and w.sum() == pytest.approx(1.0)
    row, col = vis.cell_of(dirs.reshape(-1, 3), 1.0)
    assert (row == np.repeat(np.arange(180), 360)).all() and (col == np.tile(np.arange(360), 180)).all()


# ---- the answer key ----

def box_room(n=60000, seed=0, haze=0, floor=True):
    rng = np.random.default_rng(seed)
    face = rng.integers(0, 6, n)
    p = LO + (HI - LO) * rng.random((n, 3))
    axis, side = face // 2, face % 2
    p[np.arange(n), axis] = np.where(side, HI[axis], LO[axis])
    if not floor:
        p = p[~((axis == 1) & (side == 0))]
    op = np.full(len(p), 0.9)
    if haze:
        h = LO + (HI - LO) * rng.random((haze, 3))
        p, op = np.vstack([p, h]), np.r_[op, np.full(haze, 0.03)]
    return p, op, np.full(len(p), 0.02)


def truth(deg):
    dirs, w = vis.equirect_dirs(deg)
    world = dirs.reshape(-1, 3) @ RIG_FROM_WORLD  # rig -> world (orthonormal)
    return vis.box_distance(C, world, LO, HI).reshape(dirs.shape[:2]), dirs, w


def test_rendered_surface_sits_on_the_walls_and_ignores_faint_haze():
    p, op, sg = box_room(haze=200000)
    pose = vis.Pose(C, RIG_FROM_WORLD)
    d = vis.footprint_depth(pose, p, op, sg, "rendered", deg=1.0)
    t, _, w = truth(1.0)
    ok = np.isfinite(d)
    assert (w * ok).sum() > 0.95
    assert np.median(np.abs(d[ok] - t[ok])) < 0.05


def test_opaque_rule_drops_faint_splats():
    p, op, sg = box_room(n=0, haze=50000)
    pose = vis.Pose(C, RIG_FROM_WORLD)
    assert not np.isfinite(vis.footprint_depth(pose, p, op, sg, "opaque", deg=1.0)).any()


def test_opaque_rule_finds_solid_walls():
    p, op, sg = box_room()
    d = vis.footprint_depth(vis.Pose(C, RIG_FROM_WORLD), p, op, sg, "opaque", deg=1.0)
    t, _, w = truth(1.0)
    ok = np.isfinite(d)
    assert (w * ok).sum() > 0.95 and np.median(np.abs(d[ok] - t[ok])) < 0.05


def test_a_hole_in_the_scan_stays_a_hole():
    p, op, sg = box_room(floor=False)
    d = vis.footprint_depth(vis.Pose(C, RIG_FROM_WORLD), p, op, sg, "rendered", deg=1.0)
    _, dirs, _ = truth(1.0)
    down = dirs[..., 1] > 0.9  # rig y is down
    assert down.any() and not np.isfinite(d[down]).any()


def test_rendered_rule_reaches_half_opacity_by_stacking_faint_splats():
    # splats of opacity 0.1 stacked along one ray: 7 deep (1 - 0.9**7 = 0.52) is a surface, 6 deep (0.47) is not
    lat, lon = np.radians(0.5), np.radians(0.5)  # the centre of cell (89, 180) at 1 degree
    rig = np.array([np.cos(lat) * np.sin(lon), -np.sin(lat), np.cos(lat) * np.cos(lon)])
    world = rig @ RIG_FROM_WORLD
    pose = vis.Pose(C, RIG_FROM_WORLD)

    def column(n):
        p = C + np.outer(1.5 + 0.01 * np.arange(n), world)
        return p, np.full(n, 0.1), np.full(n, 1e-4)
    d7 = vis.footprint_depth(pose, *column(7), "rendered", deg=1.0)
    d6 = vis.footprint_depth(pose, *column(6), "rendered", deg=1.0)
    assert d7[89, 180] == pytest.approx(1.56, abs=1e-6)
    assert not np.isfinite(d6).any()


def test_nearer_surface_wins():
    a = np.full((2, 2), 3.0)
    b = np.array([[1.0, np.inf], [4.0, 2.0]])
    assert (vis.combine(a, b) == np.array([[1.0, 3.0], [3.0, 2.0]])).all()


def test_surface_points_unproject_onto_the_walls():
    t, dirs, w = truth(2.0)
    pose = vis.Pose(C, RIG_FROM_WORLD)
    pts, wt = vis.surface_points(pose, t)
    assert len(pts) == t.size and wt.sum() == pytest.approx(1.0)
    on_wall = np.min(np.abs(np.c_[pts - LO, pts - HI]), axis=1)
    assert on_wall.max() < 1e-6


def test_scored_volume_holds_the_room_and_the_corridor_only():
    rng = np.random.default_rng(3)
    room = LO + (HI - LO) * rng.random((5000, 3))
    door = {"centre": [2.0, 0.0, 0.0], "outward": [1.0, 0.0, 0.0]}
    key_pts = np.c_[rng.uniform(2.1, 3.0, 500), rng.uniform(0.2, 2.0, 500), rng.uniform(-0.4, 0.4, 500)]
    key_cams = np.array([[2.5, 1.0, 0.0], [1.5, 1.0, 0.0]])
    walls, _, _ = box_room()
    v = vis.ScoredVolume.build(walls, door, key_pts, key_cams)
    assert v.contains(room).mean() > 0.99
    assert v.contains(np.array([[2.6, 1.0, 0.0]])).all()          # in the corridor
    assert not v.contains(np.array([[0.0, 1.0, 3.0], [2.6, 1.0, 1.5], [0.0, 4.0, 0.0]])).any()  # behind walls, beside the corridor, above


def test_colmap_agreement_counts_cells_within_tau():
    depth = np.array([[1.0, 2.0, np.inf], [3.0, 4.0, 5.0]])
    colmap = np.array([[1.1, 2.5, 2.0], [np.inf, 4.0, 5.14]])
    w = np.full(depth.shape, 1 / 6)
    a = vis.agreement(depth, colmap, w, np.ones(depth.shape, bool), tau=0.15)
    assert a["cells"] == 4 and a["withinTau"] == pytest.approx(0.75)


def test_no_measured_splat_forms_the_key_through_the_doorway():
    p, op, sg = box_room()
    scale = {"door": {"centre": [2.0, 0.0, 0.0], "outward": [1.0, 0.0, 0.0], "width_tape_m": 0.72,
                      "top": [[2.0, 2.0, -0.36], [2.0, 2.0, 0.36]]}}
    pose = vis.Pose(C, RIG_FROM_WORLD)
    d = vis.key_depth(pose, p, op, sg, np.zeros((0, 3)), scale, "rendered", deg=1.0)
    dirs, w = vis.equirect_dirs(1.0)
    through = vis.door_edge.through_opening(C, vis.world_dirs(pose, dirs.reshape(-1, 3)), scale).reshape(d.shape)
    assert through.any() and not np.isfinite(d[through]).any()
    assert (w * np.isfinite(d))[~through].sum() / w[~through].sum() > 0.95

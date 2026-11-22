import json

import numpy as np

import coastline
import door_edge
import provenance
import schema_check
import splats
import synth_world


def worlds(corridor=True):
    m = synth_world.measured_world(600)[0]
    k = synth_world.marble_world(400, corridor=corridor)[0]
    head = np.array([c[[0, 2]] for name, (c, _) in synth_world.camera_poses().items() if "head" in name])
    return m, k, head


def test_coastline_crosses_the_hallway_where_the_survey_stopped():
    m, k, head = worlds()
    r = coastline.trace(m, k, head)
    pts = np.vstack([xz for xz, _, _ in r["lines"]])
    assert pts[:, 0].min() > 2.0, "no coastline inside the room or along its walls"
    across = pts[(pts[:, 1] > -0.3) & (pts[:, 1] < 0.3)]
    assert len(across) > 5
    assert np.abs(across[:, 0] - synth_world.STUB_END_X).max() <= coastline.GRID_M


def test_no_coastline_when_marble_adds_nothing():
    m, k, head = worlds(corridor=False)
    r = coastline.trace(m, k, head)
    assert sum(length for *_, length in r["lines"]) < 0.5


def test_walkable_reaches_into_the_invented_hallway():
    m, k, head = worlds()
    poly = np.array(coastline.trace(m, k, head)["walkable"][0])
    assert poly[:, 0].max() > 3.0 and poly[:, 0].min() < -1.5


def test_run_writes_files_that_meet_the_schema(aligned):
    work = aligned["work"]
    provenance.run(work, "synthworld")
    r = coastline.run(work, "synthworld")
    c = json.loads((work / "coastline.json").read_text())
    schema_check.check(c, "coastline.schema.json")
    assert c["gridM"] == 0.1 and c["radiiM"] == {"covered": 0.15, "overlap": 0.5}
    assert len(json.loads((work / "floor.json").read_text())["walkable"]) >= 1
    assert (work / "coastline.png").exists() and r["coastline"]["lengthM"] > 0.5


# ---- ordinary defects must not draw coastline (the review's coast.py) ----

def interior(r, margin=0.4):
    """Stretches with any point well inside the room (not near its walls or the doorway)."""
    out = []
    for xz, closed, length in r["lines"]:
        inside = (np.abs(xz[:, 0]) < 2.0 - margin) & (np.abs(xz[:, 1]) < 1.6 - margin)
        if inside.any():
            out.append((closed, round(length, 2)))
    return out


def test_a_hole_in_the_measured_floor_draws_no_ring():
    m, k, head = worlds()
    hole = (np.abs(m[:, 0] - 0.3) < 0.35) & (np.abs(m[:, 2] - 0.2) < 0.35) & (m[:, 1] < 0.5)
    r = coastline.trace(m[~hole], k, head)
    assert interior(r) == []
    assert not any(closed for _, closed, _ in r["lines"])


def test_a_marble_wall_set_back_draws_no_stretch_along_it():
    m, k, head = worlds()
    k = k.copy()
    far = k[:, 0] < -1.95
    k[far, 0] -= 0.25
    r = coastline.trace(m, k, head)
    pts = np.vstack([xz for xz, _, _ in r["lines"]]) if r["lines"] else np.zeros((0, 2))
    assert (pts[:, 0] < -1.5).sum() == 0, "a stretch along the far wall"
    assert np.abs(np.vstack([xz for xz, _, _ in r["lines"]])[:, 0] - synth_world.STUB_END_X).min() < 0.15


def test_short_stretches_are_dropped():
    m, k, head = worlds()
    r = coastline.trace(m, k, head)
    assert all(length >= coastline.MIN_STRETCH_M for *_, length in r["lines"])
    assert coastline.MIN_STRETCH_M >= 0.5


def test_the_walkable_area_is_clamped_round_the_room():
    m, k, head = worlds()
    rng = np.random.default_rng(0)
    plain = np.c_[rng.uniform(-12, 12, 40000), rng.uniform(-0.05, 0.02, 40000), rng.uniform(-12, 12, 40000)]
    r = coastline.trace(m, np.vstack([k, plain]), head)
    poly = np.vstack([np.array(p) for p in r["walkable"]])
    limit = coastline.WALK_BEYOND_MEASURED_M + 0.2
    assert poly[:, 0].max() < 2.5 + limit and poly[:, 0].min() > -2.0 - limit
    assert np.abs(poly[:, 1]).max() < 1.6 + limit


def test_fog_beyond_the_doorway_can_be_left_out_with_an_opacity_floor():
    rng = np.random.default_rng(0)
    xyz = np.c_[rng.uniform(2.5, 3.1, 3000), rng.uniform(0.0, 0.3, 3000), rng.uniform(-0.5, 0.5, 3000)]
    opacity = np.full(3000, 0.05)
    keep = coastline.opaque(opacity, None)
    assert keep.all()
    assert not coastline.opaque(opacity, 0.2).any()


def test_plan_view_is_seen_from_above_and_not_clipped(tmp_path):
    from PIL import Image
    g = coastline.grid2d.Grid(-1.0, -1.0, 0.1, 30, 20)
    # an L: a long arm along +x and a short arm along +z, both from the origin, 1 m up
    long_arm = np.c_[np.linspace(0, 1.5, 300), np.full(300, 1.0), np.zeros(300)]
    short_arm = np.c_[np.zeros(200), np.full(200, 1.0), np.linspace(0, 0.8, 200)]
    floor_only = np.c_[np.linspace(-0.8, 1.8, 300), np.zeros(300), np.full(300, -0.8)]
    path = coastline.plan_view(tmp_path / "p.png", g, np.vstack([long_arm, short_arm, floor_only]), np.zeros((0, 3)),
                               np.zeros((0, 3)), [], door=None)
    img = np.asarray(Image.open(path).convert("L"))
    panel = coastline.plan_panel(g, img.shape[1])
    dark = lambda xz: img[int(round(panel.px(np.array([xz]))[0][1])), int(round(panel.px(np.array([xz]))[0][0]))] < 160  # noqa: E731
    assert dark([1.4, 0.0]) and dark([0.0, 0.7])
    u0, v0 = panel.px(np.array([[0.0, 0.0]]))[0]
    u1, _ = panel.px(np.array([[1.4, 0.0]]))[0]
    _, v1 = panel.px(np.array([[0.0, 0.7]]))[0]
    assert u1 > u0 + 50 and v1 > v0 + 30, "+x to the right and +z down the page: the view from above"
    assert not dark([0.5, -0.8]), "the plan is sliced 0.3 to 1.5 m up, so bare floor stays out"
    assert img.shape[1] >= 900  # wide enough for its caption


def test_a_garden_seen_through_a_window_draws_no_coastline_along_the_wall():
    m, k, head = worlds()
    rng = np.random.default_rng(0)
    garden = np.c_[rng.uniform(-2, 2, 6000), rng.uniform(-0.05, 0.05, 6000), rng.uniform(-3.6, -1.65, 6000)]
    r = coastline.trace(m, np.vstack([k, garden]), head)
    pts = np.vstack([xz for xz, _, _ in r["lines"]])
    assert (pts[:, 1] < -1.4).sum() == 0, "a stretch along the window wall"
    assert np.abs(pts[:, 0] - synth_world.STUB_END_X).min() < 0.15


def narrow(points, width):
    """The hallway past the door squeezed to `width` (the synthetic one is 1 m wide), like the real 0.72 m one."""
    p = points.copy()
    hall = p[:, 0] > synth_world.DOOR_X
    p[hall, 2] *= width
    return p


def across_the_stub(r):
    pts = np.vstack([xz for xz, _, _ in r["lines"]]) if r["lines"] else np.zeros((0, 2))
    return pts[np.abs(pts[:, 0] - synth_world.STUB_END_X) <= coastline.GRID_M]


def test_a_narrow_hallway_gets_its_line_from_wall_to_wall():
    m, k, head = worlds()
    r = coastline.trace(narrow(m, 0.72), narrow(k, 0.72), head)
    across = across_the_stub(r)
    assert len(across) > 3, "no coastline across a 0.72 m hallway"
    assert np.ptp(across[:, 1]) >= 0.72 - 3 * coastline.GRID_M


def haze(m, n=40000, seed=1):
    """An MCMC splat's near-transparent haze through the measured volume: the room and the stub of hallway."""
    rng = np.random.default_rng(seed)
    room = np.c_[rng.uniform(-2.0, synth_world.DOOR_X, n), rng.uniform(0.0, 2.4, n), rng.uniform(-1.6, 1.6, n)]
    stub = np.c_[rng.uniform(synth_world.DOOR_X, synth_world.STUB_END_X, n // 6), rng.uniform(0.0, 2.4, n // 6),
                 rng.uniform(-0.5, 0.5, n // 6)]
    h = np.vstack([room, stub])
    return np.vstack([m, h]), np.r_[np.ones(len(m)), np.full(len(h), 0.01)]


def test_near_transparent_haze_is_measured_but_never_a_wall():
    m, k, head = worlds()
    mh, opacity = haze(m)
    assert len(across_the_stub(coastline.trace(mh, k, head))) == 0, "the haze should hide the line when it counts as wall"
    r = coastline.trace(mh, k, head, measured_opacity=opacity)
    across = across_the_stub(r)
    assert len(across) > 5, "the haze hid the coastline"
    pts = np.vstack([xz for xz, _, _ in r["lines"]])
    assert pts[:, 0].min() > 2.0, "no coastline inside the room or along its walls"


def test_run_hands_the_trace_each_measured_splats_opacity(aligned, monkeypatch):
    work = aligned["work"]
    provenance.run(work, "synthworld")
    seen = {}
    real = coastline.trace

    def spy(measured, marble, walk, measured_opacity=None):
        seen["n"], seen["opacity"] = len(measured), measured_opacity
        return real(measured, marble, walk, measured_opacity=measured_opacity)

    monkeypatch.setattr(coastline, "trace", spy)
    coastline.run(work, "synthworld")
    ply = splats.read(work / "splat" / "measured.ply", quiet=True)
    s = json.loads((work / "scale.json").read_text())
    outside = ~door_edge.sealed(splats.apply(np.array(s["world_from_colmap"]), splats.centres(ply)), s)
    want = splats.opacity(ply)[outside]
    assert seen["opacity"] is not None and len(seen["opacity"]) == seen["n"] == len(want)
    assert np.allclose(np.sort(seen["opacity"]), np.sort(want))

import json
from datetime import datetime, timezone

import numpy as np
import pytest

import coastline
import door_edge
import export
import provenance
import schema_check
import splats
import spz


PHONE_TEST = 10_000


@pytest.fixture
def exported(aligned, tmp_path):
    work = aligned["work"]
    provenance.run(work, "synthworld")
    coastline.run(work, "synthworld")
    media = tmp_path / "MEDIA.md"
    media.write_text("# Media\n\nIntro.\n\n| Object | sha256 | Bytes | Date |\n|---|---|---|---|\n"
                     "| herebeink/v1/measured.spz | old | 1 | 2026-01-01 |\n| other/thing | keep | 2 | 2026-01-01 |\n")
    # the synthetic room is small, so a phone budget below its size makes the phone file a real subsample
    scene = export.export(work, "synthworld", work / "export" / "v1", "herebeink/v1/", media,
                          now=datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc), phone_splats=PHONE_TEST)
    return work, scene, media


def test_files_counts_and_hashes(exported):
    work, scene, _ = exported
    out = work / "export" / "v1"
    assert sorted(p.name for p in out.iterdir()) == ["coastline.json", "imagined.spz", "measured-phone.spz",
                                                     "measured-preview.spz", "measured.spz", "overlap.spz", "scene.json"]
    for key, entry in scene["splats"].items():
        f = out / entry["url"]
        assert entry["sha256"] == export.sha256(f) and entry["bytes"] == f.stat().st_size
        assert spz.header(f)["splats"] == entry["splats"]
    s = json.loads((work / "scale.json").read_text())
    src = splats.centres(splats.read(work / "splat" / "measured.ply", quiet=True))
    kept = int((~door_edge.sealed(splats.apply(np.array(s["world_from_colmap"]), src), s)).sum())
    assert scene["splats"]["measured"]["splats"] == kept < len(src)
    assert scene["counts"]["measuredPreview"] == min(40000, scene["counts"]["measured"])
    assert [scene["splats"][k]["provenance"] for k in ("measured", "measuredPreview", "overlap", "imagined")] == [0, 0, 0.5, 1]
    schema_check.check(json.loads((out / "scene.json").read_text()), "scene.schema.json")


def test_matrices_are_the_pipeline_transforms(exported):
    work, scene, _ = exported
    s = json.loads((work / "scale.json").read_text())
    a = json.loads((work / "align" / "synthworld" / "align.json").read_text())
    m = np.array(scene["splats"]["measured"]["matrix"]).reshape(4, 4).T
    k = np.array(scene["splats"]["imagined"]["matrix"]).reshape(4, 4).T
    assert m == pytest.approx(np.array(s["world_from_colmap"]), abs=1e-8)
    assert k == pytest.approx(np.array(a["world_from_marble"]), abs=1e-8)


def test_phones_get_a_lighter_measured_file_in_the_same_frame(exported):
    work, scene, _ = exported
    phone, full = scene["splats"]["measuredPhone"], scene["splats"]["measured"]
    assert full["splats"] > PHONE_TEST
    assert phone["splats"] == PHONE_TEST == scene["counts"]["measuredPhone"]
    assert phone["url"] == "measured-phone.spz" and phone["provenance"] == 0
    assert phone["matrix"] == full["matrix"]
    assert export.PREVIEW_SPLATS < export.PHONE_SPLATS


def test_the_phone_file_is_a_fixed_opacity_weighted_subset(aligned, tmp_path):
    src = aligned["work"] / "splat" / "measured.ply"
    a, b = tmp_path / "a.ply", tmp_path / "b.ply"
    assert export.preview(src, a, n=10_000, seed=1) == 10_000
    export.preview(src, b, n=10_000, seed=1)
    full = splats.centres(splats.read(src, quiet=True))
    pa, pb = splats.centres(splats.read(a, quiet=True)), splats.centres(splats.read(b, quiet=True))
    assert np.array_equal(pa, pb), "the same seed must give the same file"
    rows = {tuple(r) for r in full.round(6)}
    assert all(tuple(r) in rows for r in pa.round(6)), "every phone splat comes from the full file"


def test_a_phone_file_out_of_step_with_the_measured_one_is_refused(exported):
    work, scene, _ = exported
    s = json.loads((work / "export" / "v1" / "scene.json").read_text())
    del s["counts"]["measuredPhone"]
    assert any("measuredPhone" in p for p in schema_check.scene_semantics(s))
    s = json.loads((work / "export" / "v1" / "scene.json").read_text())
    s["splats"]["measuredPhone"]["matrix"] = s["splats"]["overlap"]["matrix"]
    assert any("measuredPhone" in p for p in schema_check.scene_semantics(s))
    s = json.loads((work / "export" / "v1" / "scene.json").read_text())
    s["splats"]["measuredPhone"]["splats"] = s["splats"]["measured"]["splats"] + 1
    s["counts"]["measuredPhone"] = s["splats"]["measuredPhone"]["splats"]
    assert any("measuredPhone" in p for p in schema_check.scene_semantics(s))


def test_the_phone_file_is_marked_as_minor_2(exported):
    work, scene, _ = exported
    assert scene["schemaMinor"] >= 2
    assert "minor 2" in (export.Path(schema_check.__file__).parent / "schema" / "README.md").read_text().lower()


def test_a_room_no_bigger_than_the_phone_budget_gets_no_phone_file(ready):
    work = ready
    scene = export.export(work, "synthworld", work / "export" / "v1", "herebeink/v1/", None, phone_splats=10**9)
    assert "measuredPhone" not in scene["splats"] and "measuredPhone" not in scene["counts"]
    assert not (work / "export" / "v1" / "measured-phone.spz").exists()


def test_a_scene_without_a_phone_file_still_meets_the_schema(exported):
    work, scene, _ = exported
    s = json.loads((work / "export" / "v1" / "scene.json").read_text())
    del s["splats"]["measuredPhone"], s["counts"]["measuredPhone"]
    schema_check.check(s, "scene.schema.json")


def test_start_film_and_light(exported):
    _, scene, _ = exported
    assert scene["start"]["yawDeg"] == pytest.approx(-90, abs=0.5)
    path = scene["filmPath"]
    assert [p["t"] for p in path] == sorted(p["t"] for p in path)
    assert path[2]["position"][0] > scene["door"]["centre"][0] > path[1]["position"][0]
    d = np.array(scene["light"]["direction"])
    assert np.linalg.norm(d) == pytest.approx(1) and d[1] < 0 and d[0] < 0


FILM_DOOR = {"centre": [1.0, 0.0, 0.0], "outward": [1.0, 0.0, 0.0]}
FILM_START = {"position": [-1.0, 1.6, 0.0], "yawDeg": -90.0}


def turn_past_door(path):
    """How far past the door the film turns round (its third and fourth points share the turn position)."""
    assert path[2]["position"] == path[3]["position"]
    return path[2]["position"][0] - FILM_DOOR["centre"][0]


def test_with_nothing_in_the_way_the_film_turns_the_full_distance_past_the_door():
    path = export.film_path(FILM_START, FILM_DOOR, 1.6, np.zeros((0, 3)))
    assert turn_past_door(path) == pytest.approx(export.FILM_PAST_M)


def test_the_film_turns_short_of_a_marble_splat_on_its_walk_line():
    # the real room: Marble's splats begin 1.07 m past the door, so the turn falls at 0.82 m
    blocker = np.array([[1.0 + 1.07, 1.6, 0.05]])
    path = export.film_path(FILM_START, FILM_DOOR, 1.6, blocker)
    assert turn_past_door(path) == pytest.approx(1.07 - export.FILM_CLEARANCE_M, abs=1e-3)


def test_splats_off_the_walk_line_or_behind_the_door_do_not_move_the_turn():
    aside = [1.0 + 0.6, 1.6, export.FILM_CORRIDOR_M + 0.1]
    below = [1.0 + 0.6, 1.6 - export.FILM_CORRIDOR_M - 0.1, 0.0]
    behind = [1.0 - 0.3, 1.6, 0.0]
    path = export.film_path(FILM_START, FILM_DOOR, 1.6, np.array([aside, below, behind]))
    assert turn_past_door(path) == pytest.approx(export.FILM_PAST_M)


def test_the_film_never_turns_closer_than_the_minimum_past_the_door():
    path = export.film_path(FILM_START, FILM_DOOR, 1.6, np.array([[1.0 + 0.3, 1.6, 0.0]]))
    assert turn_past_door(path) == pytest.approx(export.FILM_MIN_PAST_M)


def test_the_exported_film_turns_in_open_space(exported):
    work, scene, _ = exported
    turn = np.array(scene["filmPath"][2]["position"])
    world_from_marble = np.array(json.loads((work / "align" / "synthworld" / "align.json").read_text())["world_from_marble"])
    for name in ("imagined", "overlap"):
        ply = splats.read(work / "provenance" / "synthworld" / f"{name}.ply", quiet=True)
        centres = splats.apply(world_from_marble, splats.centres(ply))
        past = (turn - np.array(scene["door"]["centre"])) @ np.array(scene["door"]["outward"])
        if past > export.FILM_MIN_PAST_M + 1e-3:
            near = np.linalg.norm(centres - turn, axis=1) < export.FILM_CLEARANCE_M - 1e-3
            assert not near.any(), f"{near.sum()} {name} splats within the clearance of the turn point"


def test_preview_prefers_opaque_splats(tmp_path):
    rng = np.random.default_rng(0)
    n = 2000
    splats.write_splats(tmp_path / "m.ply", rng.random((n, 3)), rng.random((n, 3)), np.tile([0, 0, 1.0], (n, 1)),
                        np.tile([1.0, 0, 0], (n, 1)), size=0.01)
    ply = splats.read(tmp_path / "m.ply")
    data = ply["vertex"].data
    data["opacity"][: n // 2] = -6.0
    from plyfile import PlyData, PlyElement
    PlyData([PlyElement.describe(data, "vertex")]).write(str(tmp_path / "m2.ply"))
    export.preview(tmp_path / "m2.ply", tmp_path / "p.ply", n=200)
    kept = splats.opacity(splats.read(tmp_path / "p.ply"))
    assert (kept > 0.5).mean() > 0.9


def test_media_md_rows_replaced_not_duplicated(exported):
    _, _, media = exported
    text = media.read_text()
    assert "| herebeink/v1/measured.spz | old |" not in text
    assert text.count("| herebeink/v1/measured.spz |") == 1 and "| other/thing | keep |" in text
    assert "Intro." in text and "| herebeink/v1/scene.json |" in text


def test_manifest_lists_every_file(exported):
    work, _, _ = exported
    m = json.loads((work / "export" / "media_manifest.json").read_text())
    assert m["prefix"] == "herebeink/v1/" and len(m["items"]) == 7
    assert all(i["key"] == "herebeink/v1/" + i["path"] for i in m["items"])


# ---- refusals, mirrors baked, hand edits kept ----

def do_export(work, **kw):
    return export.export(work, "synthworld", work / "export" / "v1", "herebeink/v1/", None,
                         now=datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc), **kw)


@pytest.fixture
def ready(aligned):
    work = aligned["work"]
    provenance.run(work, "synthworld")
    coastline.run(work, "synthworld")
    return work


def set_align(work, **fields):
    p = work / "align" / "synthworld" / "align.json"
    a = json.loads(p.read_text())
    a.update(fields)
    p.write_text(json.dumps(a))


def test_a_matrix_that_is_not_a_similarity_is_refused(ready):
    t = np.array(json.loads((ready / "align" / "synthworld" / "align.json").read_text())["world_from_marble"])
    t[:3, 0] *= 1.2
    set_align(ready, world_from_marble=t.tolist())
    with pytest.raises(ValueError, match="similarity"):
        do_export(ready)


def mirror_marble(work):
    """The same day with Marble's file mirrored (raw +x left) and the alignment that goes with it."""
    from plyfile import PlyData, PlyElement
    for name in ("marble/marble_synthworld.ply",):
        ply = splats.read(work / name, quiet=True)
        PlyData([PlyElement.describe(splats.mirror_x(ply["vertex"].data), "vertex")], text=False,
                byte_order="<").write(str(work / name))
    t = np.array(json.loads((work / "align" / "synthworld" / "align.json").read_text())["world_from_marble"])
    set_align(work, world_from_marble=(t @ np.diag([-1.0, 1, 1, 1])).tolist())


def test_a_mirrored_alignment_is_baked_into_the_files_and_the_matrix_stays_proper(aligned):
    work = aligned["work"]
    provenance.run(work, "synthworld")
    plain = splats.apply(np.array(json.loads((work / "align" / "synthworld" / "align.json").read_text())["world_from_marble"]),
                         splats.centres(splats.read(work / "provenance" / "synthworld" / "imagined.ply", quiet=True)))
    mirror_marble(work)
    provenance.run(work, "synthworld")
    coastline.run(work, "synthworld")
    scene = do_export(work)
    k = np.array(scene["splats"]["imagined"]["matrix"]).reshape(4, 4).T
    assert np.linalg.det(k[:3, :3]) > 0 and splats.similarity_problem(k) is None
    assert scene["alignment"]["mirrorBaked"] is True
    baked = splats.read(work / "export" / "v1-ply" / "imagined.ply", quiet=True)
    assert np.sort(splats.apply(k, splats.centres(baked)), axis=0) == pytest.approx(np.sort(plain, axis=0), abs=1e-5)


def test_a_failed_gate_is_refused_unless_allowed_with_a_reason(ready):
    set_align(ready, gateA={"thresholdCm": 10.0, "pass": False, "reasons": ["photometric score is not clearly the best"]})
    with pytest.raises(ValueError, match="Gate A failed"):
        do_export(ready)
    scene = do_export(ready, allow_failed_gate="side-by-side version, the reason goes on the page")
    assert scene["alignment"]["gateAPass"] is False
    assert scene["alignment"]["failedGateAllowed"] == "side-by-side version, the reason goes on the page"


def test_hand_edits_survive_a_re_export(ready):
    do_export(ready)
    out = ready / "export" / "v1"
    (out / "notes-by-hand.txt").write_text("keep me")
    film = [{"t": 0.0, "position": [0.0, 1.6, 0.0], "yawDeg": -90.0, "pitchDeg": 0.0},
            {"t": 6.0, "position": [2.5, 1.6, 0.0], "yawDeg": -90.0, "pitchDeg": -5.0}]
    (ready / "overrides.json").write_text(json.dumps({"filmPath": film, "light": {"direction": [0.0, -1.0, 0.0]}}))
    scene = do_export(ready)
    assert (out / "notes-by-hand.txt").read_text() == "keep me"
    assert scene["filmPath"] == film and scene["light"] == {"direction": [0.0, -1.0, 0.0]}
    m = json.loads((ready / "export" / "media_manifest.json").read_text())
    assert "notes-by-hand.txt" not in [i["path"] for i in m["items"]]


def test_an_unknown_override_is_refused(ready):
    (ready / "overrides.json").write_text(json.dumps({"filmpath": []}))
    with pytest.raises(ValueError, match="filmpath"):
        do_export(ready)


def test_coordinates_beyond_what_spz_can_hold_are_refused(ready):
    from plyfile import PlyData, PlyElement
    p = ready / "provenance" / "synthworld" / "imagined.ply"
    rows = splats.read(p, quiet=True)["vertex"].data.copy()
    rows["x"][0] = 2500.0
    PlyData([PlyElement.describe(rows, "vertex")], text=False, byte_order="<").write(str(p))
    with pytest.raises(ValueError, match="2048"):
        do_export(ready)


def test_scene_json_never_holds_nan(ready):
    set_align(ready, residual={"medianCm": float("nan"), "p90Cm": 1.0, "icpSet": 5})
    with pytest.raises(ValueError):
        do_export(ready)


def test_the_measured_files_stop_at_the_sealed_doorway(exported):
    work, scene, _ = exported
    s = json.loads((work / "scale.json").read_text())
    src = splats.read(work / "splat" / "measured.ply", quiet=True)
    world = splats.apply(np.array(s["world_from_colmap"]), splats.centres(src))
    sealed = door_edge.sealed(world, s)
    assert scene["counts"]["measured"] == len(world) - int(sealed.sum())
    shipped = splats.read(work / "export" / "v1-ply" / "measured.ply", quiet=True)
    assert not door_edge.sealed(splats.apply(np.array(s["world_from_colmap"]), splats.centres(shipped)), s).any()

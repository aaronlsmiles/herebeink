"""KR4's misread reading: under the chosen pose, which input photo each of the placed world's directions looks
like, and whether the best layout runs the photos round the circle backwards (frozen Part 2 criteria, KR4).

A painted synthetic room is drawn into four level cameras at c, 90 degrees apart, to stand in for the four
photos sent; the same room stands in for Marble's placed world. Swapping which photo was sent at 90 and at
270 is what a sign misread does to the world: the side photos land on the wrong sides."""
import dataclasses

import numpy as np
import pytest
from PIL import Image

import align
import photo
import synth_world
import visibility

POSE = visibility.Pose(synth_world.PANO_W, synth_world.CAM_FACING_X.T)
AZ = [0, 90, 180, 270]
YAW0 = 12.0


def manifest() -> dict:
    files = [f"pipeline/work/ladder/views/az{a:03d}.png" for a in AZ]
    return {"fov_deg": {"h": 66.0, "v": 51.9373}, "size": [1024, 768], "d_yaw_deg": YAW0,
            "views": [{"azimuth": a, "file": f, "pano_yaw_deg": YAW0 + a} for a, f in zip(AZ, files)],
            "rungs": {"R4": files}}


@pytest.fixture(scope="module")
def room():
    xyz, rgb, _, _ = synth_world.measured_world(4000, seed=3)
    return xyz, photo.luminance(rgb)


@pytest.fixture(scope="module")
def sent(room, tmp_path_factory):
    root = tmp_path_factory.mktemp("views")
    m = manifest()
    for v in m["views"]:
        f = root / v["file"]
        f.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1024, 768), (128, 128, 128)).save(f)
    views = align.ladder_input_views(m, "R4", POSE, root=root)
    xyz, lum = room
    return [dataclasses.replace(v, image=photo.drawn(v, xyz, lum)[0]) for v in views]


def relabel(views, order):
    """The photos as sent, each camera now holding photo order[i]'s pixels."""
    return [dataclasses.replace(v, image=views[j].image) for v, j in zip(views, order)]


def test_photos_in_the_order_sent_read_as_the_order_sent(sent, room):
    r = align.view_order(sent, AZ, *room)
    assert r["best"] == {"reflected": False, "offset": 0, "photoAt": AZ}
    assert r["reverseCyclicOrder"] is False
    assert r["bestMean"] > r["bestReflectedMean"] + 0.2


def test_side_photos_swapped_read_as_reverse_cyclic_order(sent, room):
    # the world shows at 90 what was sent at 270, and the reverse: a sign misread of the azimuths
    r = align.view_order(relabel(sent, [0, 3, 2, 1]), AZ, *room)
    assert r["best"] == {"reflected": True, "offset": 0, "photoAt": [0, 270, 180, 90]}
    assert r["reverseCyclicOrder"] is True


def test_a_turned_layout_is_not_a_reversal(sent, room):
    # every photo one place round: the yaw is off by 90 degrees, not the order (KR2's business, not a re-run)
    # (the photo sent at 90 holds what lies at 180, so the world shows it at 180: every photo turned +90)
    r = align.view_order(relabel(sent, [1, 2, 3, 0]), AZ, *room)
    assert r["best"] == {"reflected": False, "offset": 3, "photoAt": [270, 0, 90, 180]}
    assert r["reverseCyclicOrder"] is False


def test_the_score_matrix_is_camera_by_photo(sent, room):
    r = align.view_order(sent, AZ, *room)
    s = np.array(r["ncc"])
    assert s.shape == (4, 4)
    assert (np.argmax(s, axis=1) == np.arange(4)).all()


def test_needs_evenly_spaced_azimuths(sent, room):
    with pytest.raises(ValueError):
        align.view_order(sent, [0, 90, 180, 300], *room)

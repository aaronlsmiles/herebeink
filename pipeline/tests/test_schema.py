import copy
import json

import numpy as np
import pytest

import schema_check

EXAMPLE = json.loads((schema_check.SCHEMAS / "scene.example.json").read_text())


def test_schemas_use_only_checked_keywords():
    for name in ("scene.schema.json", "coastline.schema.json"):
        schema_check.load(name)


def test_unknown_keyword_is_refused(tmp_path, monkeypatch):
    (tmp_path / "x.schema.json").write_text(json.dumps({"type": "object", "oneOf": []}))
    monkeypatch.setattr(schema_check, "SCHEMAS", tmp_path)
    with pytest.raises(ValueError, match="oneOf"):
        schema_check.load("x.schema.json")


def test_documented_example_is_valid():
    schema_check.check(EXAMPLE, "scene.schema.json")


@pytest.mark.parametrize("change,message", [
    (lambda s: s.pop("start"), "missing 'start'"),
    (lambda s: s["splats"]["measured"].update(matrix=[1.0] * 15), "fewer than 16"),
    (lambda s: s["splats"]["imagined"].update(provenance=0.7), "one of"),
    (lambda s: s["splats"]["overlap"].update(sha256="xyz"), "does not match"),
    (lambda s: s.update(extra=1), "unexpected 'extra'"),
    (lambda s: s["counts"].update(measured=1.5), "must be integer"),
    (lambda s: s["start"].update(pitchDeg=120), "above 90"),
    (lambda s: s.update(schemaVersion=2), "must be 1"),
])
def test_contract_violations_are_caught(change, message):
    bad = copy.deepcopy(EXAMPLE)
    change(bad)
    with pytest.raises(ValueError, match=message):
        schema_check.check(bad, "scene.schema.json")


def _matrix(s, key="measured"):
    return s["splats"][key]["matrix"]


@pytest.mark.parametrize("change,message", [
    (lambda s: s["splats"]["measured"].update(matrix=list(np.array(_matrix(s)).reshape(4, 4).T.ravel())), "last row"),
    (lambda s: _matrix(s, "imagined").__setitem__(0, float("nan")), "finite"),
    (lambda s: s["door"].update(widthM=float("inf")), "finite"),
    (lambda s: s["splats"]["overlap"].update(matrix=list((np.array(_matrix(s, "overlap")).reshape(4, 4) @ np.diag([-1.0, 1, 1, 1])).ravel())), "determinant"),
    (lambda s: _matrix(s, "imagined").__setitem__(0, _matrix(s, "imagined")[0] * 1.3), "similarity"),
    (lambda s: s["counts"].update(covered=s["counts"]["covered"] + 1), "covered"),
    (lambda s: s["door"].update(outward=[0.0, 0.0, 0.0]), "unit"),
    (lambda s: s["light"].update(direction=[0.0, -2.0, 0.0]), "unit"),
    (lambda s: s["splats"]["imagined"].update(splats=s["splats"]["imagined"]["splats"] + 1), "imagined"),
])
def test_broken_values_the_schema_cannot_see_are_caught(change, message):
    bad = copy.deepcopy(EXAMPLE)
    change(bad)
    with pytest.raises(ValueError, match=message):
        schema_check.check(bad, "scene.schema.json")


def test_coastline_with_nan_is_caught():
    c = {"schemaVersion": 1, "units": "m", "frame": "world", "gridM": 0.1, "floorBandM": 0.5,
         "radiiM": {"covered": 0.15, "overlap": 0.5}, "gridOrigin": [0.0, 0.0], "gridShape": [3, 3],
         "polylines": [{"closed": False, "points": [[0.0, 0.0], [float("nan"), 1.0]]}], "lengthM": 1.0}
    with pytest.raises(ValueError, match="finite"):
        schema_check.check(c, "coastline.schema.json")

import copy
import json
from pathlib import Path

import numpy as np
import pytest

import make_ladder_fixture as mlf
import schema_check

FIXTURE = Path(__file__).resolve().parents[2] / "web" / "public" / "fixture-ladder" / "ladder.json"


def test_ladder_schema_uses_only_checked_keywords():
    schema_check.load("ladder.schema.json")


def test_committed_fixture_matches_the_schema():
    schema_check.check(json.loads(FIXTURE.read_text()), "ladder.schema.json")


@pytest.mark.parametrize("change,message", [
    (lambda d: d.pop("steps"), "missing 'steps'"),
    (lambda d: d["rungs"][0].pop("keyAgreement"), "missing 'keyAgreement'"),
    (lambda d: d["rungs"][0].update(id="R3"), "one of"),
    (lambda d: d["rungs"][0].update(shown=1.5), "above 1"),
    (lambda d: d["rungs"][0]["splats"]["seen"].update(provenance=0.5), "one of"),
    (lambda d: d["rungs"][0].update(extra=1), "unexpected 'extra'"),
])
def test_ladder_violations_are_caught(change, message):
    bad = copy.deepcopy(json.loads(FIXTURE.read_text()))
    change(bad)
    with pytest.raises(ValueError, match=message):
        schema_check.check(bad, "ladder.schema.json")


def test_frustums_show_the_planned_shares_of_all_directions():
    dirs = mlf.sphere(100_000)
    shares = {rid: mlf.in_any(dirs, az).mean() for rid, _, _, _, az, _, _ in mlf.RUNGS}
    # plan §3's table: 7.7 %, 15 %, 31 %, 43 % and the whole sphere
    assert shares["R1"] == pytest.approx(0.077, abs=0.003)
    assert shares["R2"] == pytest.approx(0.154, abs=0.004)
    assert shares["R4"] == pytest.approx(0.307, abs=0.005)
    assert shares["R8"] == pytest.approx(0.43, abs=0.01)
    assert shares["P"] == 1.0


def test_plan_fans_merge_round_the_circle():
    assert mlf.intervals([0]) == [(327.0, 393.0)]
    assert mlf.intervals(list(range(0, 360, 45))) is None
    full = mlf.plan(list(range(0, 360, 45)))
    assert full["coastline"] == [] and len(full["seenFloor"]) == 1
    two = mlf.plan([0, 180])
    assert len(two["seenFloor"]) == 2 and len(two["coastline"]) == 4
    assert np.allclose(two["seenFloor"][0][0], two["seenFloor"][0][-1])

# Ladder fixture (synthetic)

Made by `pipeline/make_ladder_fixture.py`, not from any capture or any Marble world: the viewer fixture's
synthetic room and Marble-like world, split per rung into seen, imagined and wrong by the rung's own
frustums. The shown shares come from the frustums; the imagined shares and the scan's agreement are made
up. R4r is written as not placed. `ladder.json` follows `pipeline/schema/ladder.schema.json`.
Regenerate with `uv run python make_ladder_fixture.py` in `pipeline/`.

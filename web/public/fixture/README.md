# Viewer fixture (synthetic)

Made by `pipeline/make_fixture.py`, not from any capture: a 4 m x 3.2 m box room (the "measured" splat)
and a Marble-like world of it with an invented sage-green hallway beyond the door, run through the real
alignment, provenance, coastline and export code. Every file has the shape the live scene will have;
`scene.json` follows `pipeline/schema/scene.schema.json`. Regenerate with `uv run python make_fixture.py`
in `pipeline/`.

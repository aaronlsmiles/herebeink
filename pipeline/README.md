# herebeink-pipeline

Python 3.12 with uv. Run `uv sync` once, then:

- `uv run pytest -q`: the fast tests (about half a minute).
- `uv run pytest -m slow -q`: the whole chain, COLMAP and Spark included, on a synthetic room, with the review's wrong-input variants (about nine minutes).

## From footage to a training set

Run from this folder. Inputs live in `../capture/` (names fixed: `stitched/pass-raised.mp4`,
`pass-head.mp4`, `pass-hip.mp4`, `pass-key.mp4`, `pano.jpg` (manual exposure, the one cut into views),
optional `pano-auto.jpg` and `pano-hdr.jpg`, `raw/phone/*`, and `NOTES.md`). Everything made here goes
to `work/`, which is not committed.

```bash
uv run python ingest_check.py                 # is everything there? phone stills -> JPEG
uv run python privacy_sheet.py sheets         # contact sheets for the privacy pass
uv run python cut_views.py plan               # how often to sample each pass, which views to drop
uv run python cut_views.py preview            # check the operator only sits in the dropped views
uv run python cut_views.py cut                # eight 90-degree views per sample, as a COLMAP rig;
                                              # look at work/preview/cut-check.jpg (24 images that were cut)
./colmap.sh                                   # features, rig, matching, mapping, report (1-2.5 h)
FROM=report ./colmap.sh                       # only print the report again (a plain re-run refuses to wipe a model)
uv run python export_training_set.py          # work/train for the laptop
uv run python export_training_set.py --subset 20 --out work/train_dry
```

Then `laptop/README.md`. To rehearse all of it on a synthetic room:
`uv run python synth_capture.py /tmp/rehearsal/capture`, and pass `--capture /tmp/rehearsal/capture
--work /tmp/rehearsal/work` to the scripts (and `WORK=/tmp/rehearsal/work` to `colmap.sh`), with
`cut_views.py plan --positions 30 --view-size 256`.

Re-running `cut_views.py plan` keeps the drops and yaw offsets already in `work/cut_plan.json`;
`--reset-drops` clears them. A privacy mask on a pass pads its time window by a second each side.

## The World Labs client

`marble.py` only ever sends a PNG that `prepare-pano` made, which strips the metadata and refuses a
still whose `.masked.jpg` twin exists unless the twin itself is named:

```bash
uv run python marble.py prepare-pano ../capture/stitched/pano-auto.masked.jpg   # or pano-auto.jpg when there is no mask
uv run python marble.py draft --pano work/marble/pano-auto_2560.png ...         # the output is named after the still
```

Every paid call writes a `requesting` row to `../spend.jsonl` before it is sent. No call of any kind
runs until `../capture/NOTES.md` has the line `Clean for upload: yes` on a line of its own.

## Part 2: from the trained splat and a Marble world to the page's files

After `work/splat/splat_raw.ply` is back from the laptop and `marble.py` has exported a world
(`work/marble/<id>.json`, `marble_<id>.ply`), run `./run_part2.sh <id> door`, then `scale`, `clean`,
`align` (Gate A) and `finish`; each stage says what to do before the next and stops where a person
must look. The output is `work/export/v1/` (SPZ files, `coastline.json`, `scene.json`); `scene.json`'s
contract is in `schema/`. SPZ files are written by Spark's own encoder, so `npm ci` must have been run
in `../web/`. `uv run python make_fixture.py` rebuilds the synthetic scene in `../web/public/fixture/`.

What each stage refuses, and how to go on:

- `scale`: door clicks whose RMS is over 3 px or whose rays meet under 5 degrees, a door corner more than
  3 cm off the floor, head or hip cameras at unbelievable heights, a check length more than 1.5 % out.
  With no clicks at all it tries the SuperSplat picks. `--accept "reason"` goes on and records the reason
  (scale.json, then scene.json's `scaleEvidence`). Then look at `work/clean/box.png` before pasting the box.
- `align`: Gate A needs the frozen residual under 10 cm and the added checks: the pose's down within
  10 degrees of the world's, the photometric score (Marble drawn into the pano's own views) clearly the
  best of every distinct pose, at least 30 % of Marble in the ICP set, and ICP's scale within 2/3 to 1.5
  of the metric factor's. It needs the pano's cut views in `work/images/rig/*/5pano_0000.jpg`.
  `--accept-by-eye "reason"` overrules the added checks (never the residual) after a person has read
  `contact.png` and the table; `--start YAW[,mirror][,flip]` forces a start.
- `doorway`: the kill rule's second stage (`align.py --mode doorway`): click E and F (the frame's top
  inside corners) on the door page as well, pick A B E F in SuperSplat on the doorway world and paste
  them on the `- Doorway corners in the Marble world (A B E F, four 3D points):` line (see `doorway.py`).
- `finish`: export refuses a failed gate (`--allow-failed-gate "reason"` for the side-by-side stage),
  a matrix that is not a proper similarity, and coordinates SPZ cannot hold. A mirrored alignment is
  baked into the Marble files. Hand edits to `filmPath`, `light` and `start` go in
  `work/overrides.json`; re-exports keep them and anything else in the folder that export did not write.
  `--measured-min-opacity` on `provenance.py` and `coastline.py` (off by default) leaves faint measured
  splats out of the split and the coastline, for fog beyond the doorway.

Every stage that reads a PLY prints its splat count, SH degree, opacity range and properties, and
refuses a compressed or unexpected PLY in words.

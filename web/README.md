# herebeink-web

Vanilla three.js with Spark (`@sparkjsdev/spark`) in Vite and TypeScript. No framework.

## Pinned (18 Nov 2026)

- three 0.187.0 (newest; Spark's peer range is `>=0.180.0`), @types/three 0.187.0
- @sparkjsdev/spark 2.4.0

## Run

```bash
tools/fetch-sample.sh   # once: downloads the sample splat into public/sample/ (gitignored)
npm install
npm run dev
npm test                # Vitest
npm run e2e             # Playwright, Chromium, 1440x900; screenshot in shots/
```

## Sample splat

`butterfly.spz` from Spark's own quick-start: https://sparkjs.dev/assets/splats/butterfly.spz.
The Spark docs state no separate licence for it; it is not committed or redistributed here, and it is a stand-in until the real capture exists.

## The viewer (`index.html`)

Loads `scene.json` (default `/fixture/scene.json`, the synthetic fixture; a production build points elsewhere with `VITE_SCENE_URL`), then the measured preview, then the overlap, imagined and full measured files. Render graph and module map: sub-plan C in the hub (`prototypes/plans/p50-here-be-ink/plans/sub-plan-c-viewer.md`).

URL parameters:

| Parameter | Effect |
|---|---|
| `scene=<url>` | another `scene.json`; file URLs in it are relative to it. A production build accepts only a URL on the page's own origin or the origin of `VITE_SCENE_URL`, and ignores any other |
| `ink=off` | the imagined half as a plain desaturate-and-contrast filter, no outlines or hatching (the switch) |
| `coast=off` | hides the floor line, the screen-space coastline and the statement's pen-line sentence (hallway test) |
| `map=1` | opens on the map (`M` or the Map button toggles it) |
| `hud=1` | median frame time over 5 s, splats, LoD, data-pass scale, and a button that copies the numbers as JSON |
| `lod=<splats>` | LoD budget (default 500k on phones and in XR, 1.5M on desktop) |
| `gscale=<0.25..1>` | data-pass scale (default one data pixel per CSS pixel) |
| `pose=x,y,z,yaw,pitch` | start somewhere else (metres, degrees; yaw 0 looks along -z) |
| `debug=shade\|depth\|normal\|flag\|edges` | diagnostic views |
| `ladder=<rung>` | opens Part 2's ladder mode on a rung (`R1`, `R2`, `R4`, `R4b`, `R8`, `R4r`, `P`); `ladder=1` on its first step. The walk's splat files are not fetched |
| `redpen=1` | with `ladder=`: the imagined splats that landed wrong drawn in red ink |

### Ladder mode (Part 2)

Opt-in: the "Ladder" tab in the top bar, or `?ladder=`. It reads `ladder.json` (contract: `pipeline/schema/ladder.schema.json`; reader: `src/ladder/contract.ts`) from `VITE_LADDER_URL`, or else `ladder/ladder.json` beside the scene (so `…/v3/scene.json` gives `…/v3/ladder/ladder.json`); with the default fixture scene it reads the synthetic fixture in `public/fixture-ladder/` (`pipeline/make_ladder_fixture.py`). A page whose ladder file is missing or fails the contract simply has no Ladder tab. Not on the hallway link (`coast=off`) or in film mode.

One rung is in memory at a time: stepping disposes the last rung's meshes before the next rung's files are fetched, and a phone loads a rung's `splatsPhone` when it has them. Seen splats draw as photograph, imagined and wrong ones in ink; the red pen sets a per-mesh flag that the shade pass turns into a red wash on the wrong file's paper and the flag pass carries (green channel) to the present pass, which draws that mesh's strokes in red. Under the publication stance the page shows coverage numbers only (shown, imagined, the scan's own check); right and wrong are colour. Module map: sub-plan E in the hub (`prototypes/plans/p50-here-be-ink/plans/sub-plan-e-ladder-mode.md`).

The old smoke page is `smoke.html`; the spike is `spike.html`.

```bash
node tools/viewer-measure.mjs all   # real GPU: screenshots and numbers into ../docs/viewer/
```

## Test hooks

`document.documentElement.dataset.ready` becomes `"1"` once every file is in and every pass has drawn three frames (in ladder mode, `dataset.ladderRung` names the rung shown and `dataset.ladderReady` names it once its files are all in); `dataset.firstSplats` holds the time of the first frame with splats. In dev builds `window.__hbi` holds `{ viewer, chrome, inkSwitch, params, ladder, setPose, setParts, frame, readFlag, hud }` (the smoke page keeps its own `{ renderer, scene, camera, spark, mesh }`).

## Spike S1 (outlines from a second Spark pass)

`spike.html` is a measurement page, not product code; its findings are in `../docs/spike-s1.md`.

```bash
npm run dev -- --port 5299
open "http://localhost:5299/spike.html?pass=final"   # pass=shade|depth|normal|flag|edges|final
node tools/spike-s1.mjs all                          # screenshots into ../docs/spike-s1/, widths, softness, cost (real GPU)
```

Other knobs: `stddev=8|4`, `orbit=1`, `hud=1` (add `gputimer=1` for timer queries, which cost frame time on Metal, and `sync=1` for synced wall times), `angle`, `elev`, `dist`, `paper=0`, `coast=0`, `dilate=brute`, `passes=0`, `post=0`, `flagpass=0`.

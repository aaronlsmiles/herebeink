# Here Be Ink

*photograph where the camera measured, ink where a model imagined*

Old mapmakers drew dragons where their knowledge ran out. This draws ink.

## What it explores

A walk-in world where what the camera measured renders photoreal and what a model imagined beyond it renders in ink: a real place captured with a 360 camera as a Gaussian splat, extended by World Labs' Marble, the two drawn differently in the browser.

## Why it matters

Generated worlds now extend real captures without a seam, and that is the problem: nobody walking through can tell measured from made. A caption won't survive a screenshot; a rendering style does.

## What it suggests

Generated worlds will carry their provenance in how they are drawn, not in a caption.

## Status

Part 1 of 2 shipped 22 Nov 2026. Part 1 builds the walk-in world from one Marble world and ships it. Part 2 adds an evidence ladder: how the border moves as the model is shown more of the room. Part 2 is not started; it gets its own plan and gate.

The success criteria and kill rules were frozen before any capture or generation; they are in [STATUS.md](STATUS.md). Findings, round by round, are in [LOG.md](LOG.md).

## How to run

- `web/`: the viewer. Vite and TypeScript on three.js with Spark. `cd web && npm ci && npm run dev` opens it on the synthetic fixture world in `web/public/fixture/`; tests, URL parameters and the rest are in [web/README.md](web/README.md).
- `pipeline/`: the offline steps (cut the 360 footage into views, reconstruct, align the Marble world to the capture, split by provenance, trace the coastline, export). Python 3.12 with uv; the runbook is [pipeline/README.md](pipeline/README.md).
- `film/`: the film's camera paths, edit list and one-command build; see [film/README.md](film/README.md).

The capture, the trained splat and the Marble world are not in this repository; the page loads them from the media host.

## Credits

- Imagined world generated with World Labs Marble (marble-1.1-plus) through the World API; re-rendered in ink by Studio Nephele. The model named here follows the world that is kept; each world is listed in [LICENCES.md](LICENCES.md).
- Spark (sparkjs.dev, by World Labs), the Gaussian splat renderer for three.js, and three.js itself.
- LichtFeld Studio, for training the splat.
- SuperSplat, for cleaning it.
- Niantic spz, for compressing it.
- Geist and Geist Mono, the typefaces.

Code: MIT ([LICENSE](LICENSE)). Everything else, and the terms of the services used: [LICENCES.md](LICENCES.md).

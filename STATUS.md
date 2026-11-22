# Here Be Ink — status
Card: P50 · Started: 18 Nov 2026 · Public slug: herebeink (cleared 18 Nov 2026)

## Criteria (frozen 18 Nov 2026)

Frozen at Gate 0, before any capture or generation, from the approved plan and Aaron's rulings (hub calls 13–36). A criterion changes only by a new call, recorded here with its number.

### Done means
1. A stranger walking it can say where the measured world ends without being told. Met by the hallway test and the ink/filter switch (below); no statistics are claimed.
2. It runs smoothly on a recent phone: the phone numbers below.
3. Film and thesis linked from the portfolio.

### Alignment
- The residual: the median nearest-neighbour distance, in cm, from Marble centres within 1 m of a measured centre (the ICP set), computed after alignment and before the provenance split.
- Pass: under 10 cm (a hand's width). Gate A reads it.
- It is reported as the quality of the fit for this room, never as a Marble accuracy score, and never beside another model's numbers (LICENCES.md).

### Phone
- Median frame time under 33 ms on Aaron's iPhone 15 Pro; the iOS version is recorded on the day of measurement.
- First splats within two seconds on 4G.
- Android is dropped, and the page says so.

### Hallway test (done line 1)
- Three people who have not seen the page walk the live page on their own phone.
- They see it with both coastlines (the floor line and the screen-space pen line) and the statement's pen-line sentence hidden (`?coast=off`). The statement's rule stays: the photograph is measured, the drawing is imagined.
- Aaron asks one question: "Where does the photograph end?" They answer first; then Aaron shows them the line.
- A walker "can say" when they name or point to the doorway, or to where the line falls, within about a step.
- Window: within 7 days of launch. All three are invited before the first answer is read.
- Their words, anonymised, go in LOG.md. No statistics are claimed; the thesis claims no measured result.
- The page also carries an ink/filter switch (`?ink=off` and a button) for every visitor. It flips the imagined half between the ink pass and a plain desaturate-and-contrast filter, and changes the imagined half's shading only.

### Kill rules
1. **Alignment (staged).** The residual (as defined above) above 10 cm after two rounds (round 2 may re-run Marble once from a re-shot still) → the doorway version (Marble from a still at the threshold, aligned on the door plane). Above 10 cm there too → the two worlds side by side, with the reason on the page. Each stage is logged in this file before the next.
2. **Ink reads as a filter.** If the design-pass critique (Gate D) says filter, one more pass on the pen rules (not the architecture). Still failing → ship with the finding stated, never with the ink pass hidden. If two of the three hallway walkers (coastlines hidden) cannot say where the photograph ends, that is stated on the page and in the thesis as the finding.
3. **Phone.** Median frame time above 33 ms on Aaron's iPhone 15 Pro after LoD tuning → the phone view drops to the preview mesh plus a still-image coastline, and the page says so. Desktop and XR keep the full world.
4. **Spend (calls 23, 29).** No hard cap. Stop and ask Aaron before every credit top-up and before any single call over $5; every call is logged in `spend.jsonl`. GPU rental stops at £6. Card worst case £25 (both parts).

### Budget
- £25 worst case for both parts (call 29). Part 1 about £8 (the Marble credits already bought; Part 1 worst case £14). Part 2 about £4–8.
- 11 days.
- Spend rule: no hard cap; ask Aaron before every top-up and before any single call over $5; every call logged in `spend.jsonl`.
- GPU rental cap: £6.

## Rounds
| # | Date | What was tried | Result | Kept? | £ |
|---|---|---|---|---|---|

## Run log
| Date | Task | From | To | Why |
|---|---|---|---|---|
| 18 Nov | Session controller | Opus 5.5 · high (kick-off) | Fable 5.2 controller | Aaron's call 36: execution runs under a Fable controller |
| 18 Nov | 0.5 Mac installs and laptop steps | Haiku 5.5 · low | Controller, then sub-plan A part 1 (Sonnet 5.5 · high) | The installs were two commands; the laptop steps belong with the training script |
| 18 Nov | 1.2 Moshpit360 check | Haiku 5.5 · low | Sonnet 5.5 · medium, with the trainer and COLMAP facts | One research pass covered both; the facts feed the pipeline |
| 18 Nov | 1.4 Sub-plan A | Opus 5.5 · high, one plan | Opus 5.5 · high, two parts, each run before it was written | The plan already splits it at Phase 3; running the code first found the rig, frame and scale errors |
| 18 Nov | 1.5, 1.6, 2.3, 3.4 code | Sonnet 5.5 · medium | Sonnet 5.5 · high | Built ahead of the capture from tested plans; a wrong merge would be silent |
| 18 Nov | Review of the capture tools and the Marble client | (none in the plan) | Opus 5.5 · high, independent | The footage is hard to repeat and the client spends money |
| 18 Nov | Sub-plan A part 2 and its code (scale to export) | at Phase 3's start | Opus 5.5 · high plan, Sonnet 5.5 · high code, built now on synthetic data | Aaron's ask: leave only the capture and the processing |
| 18 Nov | Review of part 2 | (none in the plan) | Opus 5.5 · high, independent | Gate A decides the card; it passed a mirrored world before the fixes |
| 18–19 Nov | Sub-plan C and the viewer, then touch, WebXR, film mode, deploy scripts | at Phase 4's start | Opus 5.5 · high plan and core, Sonnet 5.5 · high additions, built now on a fixture world | Same ask |
| 19 Nov | Review of the viewer and its fixes | (none in the plan) | Opus 5.5 · high review, Sonnet 5.5 · high fixes | "Ink only on the imagined part" is won or lost at the border |

## Gates
| Gate | What | Who | State |
|---|---|---|---|
| 0 | Decisions ratified, criteria and kill rules frozen in STATUS, the Marble terms read and recorded | Aaron | Passed 18 Nov |
| N | Name cleared and picked | Aaron, after the sweep | Passed 18 Nov (`herebeink`) |
| M | Marble credits bought, key stored | Aaron | Met 18 Nov |
| S1 | Spike passed: outlines at constant width from a second Spark pass | subagent, Aaron sees the screenshot | Passed 18 Nov on one condition (below); Aaron still to see `docs/spike-s1/final.png` |
| C | Capture done: the passes, the pano still, the door width, phone stills; privacy pass clean | Aaron | Met 20 Nov (below) |
| T | Trained and cleaned splat accepted (walls flat, door intact) | Aaron | Not called on its own; the trained splat went into Gate A |
| A | Alignment median under 10 cm, or the fallback stage chosen | Aaron | Passed 21 Nov (below) |
| D | Design pass: the ink reads as drawn (not a filter) | Aaron | Decided 22 Nov by kill rule 2: filter, after the one pen pass; the page and thesis state it (LOG.md, round 3). Aaron reviews it live |
| V | Verify clean at 1440 and 390, both themes, console clean | subagent | Passed 22 Nov (LOG.md, "Gate V"); three edge cases left open there |
| P | Clearance passed; push and deploy | Aaron's word | Passed 22 Nov: deployed; the repo public as one squashed commit; live on its own domain the same day (Aaron's CNAME, the certificate issued) and the case study on studionephele.com (site v1.53) |

## Gate S1 (18 Nov)
- Outlines hold 2 CSS px at device pixel ratios 1 and 2, at two distances and along an orbit (1.90 to 2.11 measured). Write-up: `docs/spike-s1.md`.
- The condition: on a MacBook Air M5 the second pass costs 3.3 ms at pixel ratio 1 and 4.0 ms at pixel ratio 2 with the data passes at half resolution; at full resolution at pixel ratio 2 it costs 7.6 ms, over the 6 ms bar. The viewer therefore draws its data passes at reduced resolution.
- Not yet known: the cost on the phone, WebXR, and how soft silhouettes are on a real room.

## Spend
- £0 spent on calls.
- About £8 of Marble credits bought (Gate M); balance 13,250 credits on 18 Nov.
- GPU rental: £0 of the £6 cap.
- £ per keeper: n/a.

## Links
- Page: https://herebeink.studionephele.com (live 22 Nov).
- Case study: https://studionephele.com/work/herebeink/ (site v1.53, 22 Nov).
- Code: https://github.com/aaronlsmiles/herebeink (MIT; one squashed public commit on the branch `public`; `main` keeps the private history, and a pre-push hook lets only `public` reach GitHub).
- Film (v1, captions only): `herebeink/film/v1/` on the media host (MEDIA.md).
- Thesis: THESIS.md. Plain words: the page with `?plain=1`.

## Built before the capture (19 Nov)
- **Pipeline:** capture check to export, run end to end on synthetic data (318 fast tests, 29 slow). Runbook: `pipeline/README.md`.
- **Viewer:** runs on the fixture world in `web/public/fixture/`. 92 unit tests; 33 browser tests in one pass (46 minutes under software rendering).
- **Reviewed independently, three times:** capture tools and the Marble client, scale to export, the viewer. All findings fixed test-first.
- **Known and open:**
  - The ink pass on a MacBook Air M5, against the 6 ms bar, at three views: 6.9, 5.5 and 5.3 ms on 18 Nov; 2.9, 4.9 and 5.9 ms on 19 Nov after the fixes. The two nights disagree by up to 4 ms at one view, so the cost is not pinned down; measure again on the real scene.
  - The background is paper, so a hole the capture missed reads as drawing. A tone for "not scanned" is a Gate D question.
  - The data passes still compute view-dependent colour they then discard. Skipping it changed the photograph in a test, so it is left on; check the real capture's `shDegree` first.
- **Not yet tested on a device (as of 19 Nov; the phone, the training script, the media upload and Marble's replies have run since, 20–21 Nov):** phone frame time (kill rule 3), the iOS tilt prompt, a headset session (`docs/viewer/xr-check.md`), the Windows training script, the media upload, Marble's real replies.

## The laptop (19 Nov)
- NVIDIA GeForce RTX 3080 Laptop GPU, 16 GB, compute capability 8.6; driver 546.01, to be updated to 570 or newer before training.
- Trainer: LichtFeld Studio, an older GPLv3 Windows build (labelled 0.4.2, nightly of 3 Feb 2026); Brush as fallback.

## Capture to the first look (19–21 Nov; hub calls 54–66)
- **Capture (Gate C, 19–20 Nov):** pano stills and three room passes plus the hallway answer-key pass on the X3; door re-taped between the clicked points (0.72 m floor, 0.715 m top, 1.96 m high); clean for upload.
- **COLMAP:** passes on the sphere rule (call 57): 141 of 149 room spheres placed, 1.15 px.
- **Training (laptop):** LichtFeld 5a92bff, 30k iterations MCMC, 1.5 M splats, 31 min, PSNR 29.51, SSIM 0.9575.
- **Marble:** two drafts and two worlds, 3,300 credits ($2.64); world 2 (1.1 Plus) is the one in use.
- **Scale and floor:** 0.30421 m per COLMAP unit, check length +0.86 %; the click spread accepted (Aaron); the floor set level through the door corners, because the splat holds almost no floor (call 59).
- **Gate A passed (Aaron):** median 2.86 cm (flattered by the MCMC haze; the pose rests on the photometric margin 0.25 and the contact sheet), gravity 2.0°, best start not mirrored.
- **The measured world ends at the door frame** (Aaron, call 62): covered 96.4 %, overlap 0.7 %, imagined 2.9 % (Marble's hallway and its turn). One 0.60 m coastline across the doorway, passed on Aaron's look (call 63).
- **Media v1** on the media host (31.9 MB, immutable); the CORS rule for the page's origin added by Aaron in the dashboard (call 64).
- **Phone (kill rule 3):** the full room misses 33 ms (42–56 ms) and often never finishes loading (call 65). The 300,000-splat phone file (8.1 MB) loads in full, but alone it still misses: 51 ms at dpr 2 with 323k drawn (call 67). **Passed after LoD tuning (22 Nov, call 67):** the cost follows splats *drawn*; with at most 200k drawn, 25 ms median and 27 ms p90 at the start view, dpr 2. Phones now draw at most 200k at pixel ratio 2, exactly as measured (`LOD_PHONE`, `PHONE_MAX_DPR`). **Media v2** (v1 plus the phone file) is on the media host, verified with CORS; v1 untouched.
- **Tilt** cannot work over the plain-http Wi-Fi server (iOS hides the orientation API on insecure pages); the label now says so. Test tilt on the https page.

## Next
1. Part 2, the evidence ladder: plan for Gate 0 in the hub (`prototypes/plans/p50-here-be-ink/plan-part-2-2026-11-22.md`). World Labs ends Marble and its API on 8 Jan 2027 and stops credit sales on 8 Dec 2026, so every paid generation must run before then.
2. Aaron, after launch: the tilt check on the https page, the hallway test (three walkers, `?coast=off`, within 7 days), his proofread (`?plain=1` too) and the real-reader test, his music for the film. The Quest 2 check moved to card P77 (hub call 69); the film keeps an empty slot for its headset shot (`film/README.md`).
3. Open from Gate V (LOG.md): with zero coastlines the copy still mentions the pen line; a failed scene fetch says "Failed to fetch"; small overlaps at 200 % text and on a phone on its side with plain words on.
4. A later version, Aaron's call: make the ink a drawing through the architecture (edges and tone from Marble's colour, or a draughtsman's light), per Gate D.

## Clearance (22 Nov, publish-clearance)
- **Page:** staged with `tools/deploy/stage.sh` (7 files, no fixture, sample, spike, smoke, source maps or splats); identifier scan clean on exactly what ships; the bundle names only the media host's `scene.json`. Copy read in `web/src/ui.ts`, `web/src/plainwords/words.ts` and the map key; the plain-words layer is off on the hallway link (`?coast=off`). Cleared.
- **Media** (`herebeink/v1/`, `v2/`): hashes match `MEDIA.md` and the local export; SPZ headers carry no names or times; `scene.json` holds a private World Labs world id (generated with `public: false`), the scale checks and Aaron's first name, nothing identifying. Cleared.
- **Privacy pass on the final splat:** the film's frames at every cut and caption change, and 17 views rendered from the published measured file round the room (walls, desk, shelves, print, window, ceiling). Curtains closed at night, screens off, box labels taped, nothing legible (no documents, post, addresses or screens); no person; the third-party print is unrecognisable at the splat's resolution (left in on Aaron's call, 20 Nov). Marble's hallway has a fuse-box-like box whose label is generated pseudo-text, illegible. Nothing needs masking.
- **Film:** no audio stream in any of the three videos (ffprobe); VTT and SRT carry the same 15 cues; claims checked against LOG and STATUS; end card credits World Labs Marble (marble-1.1-plus) in words; poster has no EXIF. Cleared.
- **Repo history:** 105 commits, all authored with the GitHub noreply address; identifier scan clean on the full `git log -p`; no home or Windows user paths with a user name. Licence added (MIT, as the sibling repos). The eleven `docs/spike-s1/` screenshots render Spark's sample butterfly, whose licence Spark does not state (LICENCES.md), so the public repo is one squashed commit without them; `docs/spike-s1.md` there says how to remake them, and the private history keeps them.

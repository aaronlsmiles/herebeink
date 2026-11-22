# Here Be Ink — log

The findings loop: one entry per round (capture, training, Marble, alignment, ink, the hallway test). No new round starts until the last round's findings are written here. Newest last.

The criteria and kill rules each round is read against are frozen in [STATUS.md](STATUS.md).

## Round 0 · 18 Nov 2026 · repo created

- The repo was created after Gate 0 and Gate N. The criteria and kill rules are frozen in STATUS.md.
- Nothing captured, trained or generated yet; no findings.

## Round 0b · 18 Nov 2026 · built before the capture

Nothing here is a finding about the room: no footage exists yet. These are findings about the method, from synthetic data.

- **Moshpit360** (Task 1.2): no release found, so the plain path is primary (stitch, cut views, COLMAP, train).
- **Spike S1:** a second Spark pass gives pen outlines at a constant 2 CSS px. Silhouettes come from the coverage contour, not from blended depth, which is undefined at a splat cloud's soft edge. A splat carries three writable channels, not four, so the provenance flag needs a pass of its own. Cost and the condition on the gate are in STATUS.
- **COLMAP with a rig:** the eight views cut from one sphere are one rig with known rotations. On a synthetic room every sphere came back within 2.3 mm (median) of where it was rendered. A wrong rotation still "registers" every image, so acceptance counts an image only when it carries 15 or more points.
- **Alignment on a synthetic Marble copy:** point-to-point ICP with scaling came out 1.1 % small (5.6 cm at the far wall); solving scale in a final point-to-plane round brought it to 0.2 cm. The frozen residual cannot tell a right fit from a half-turned one (1.5 cm against 1.6 cm), so Gate A also reads the contact sheet.
- **Spherical harmonics:** Spark shades view-dependent colour correctly under a mesh rotation and not under a baked one, so each splat file stays in its own frame with a matrix in `scene.json`.
- **Independent review** of the capture tools and the Marble client: one critical and seven important findings, all fixed test-first before any real data or paid call.

## Round 0c · 19 Nov 2026 · the viewer, before the capture

Still no footage: these are findings about the renderer, from a synthetic fixture world.

- **A sorted renderer is not a settled one.** Until Spark's level-of-detail worker answers, a far view shows the tree's coarse root: one hatched blob, identical on every run, so a determinism test alone passes it. Film frames, screenshots and a visitor's first view now wait for the cut; a file is drawn only once its cut is in, and the preview stays until then.
- **The border is where the claim is tested.** Hatching and grain were weighted by a blurred flag, so 60,767 measured pixels in one view carried faded ink, in the band the tests skipped. Weighted by the flag under each pixel, eroded by one data pixel, the count is 0, at pixel ratios 1 and 2.
- **A pixel a few percent imagined is shaded differently in ink and filter modes whatever the ink pass does**, because the imagined splats behind it are paper in one and photograph in the other. The ink-against-filter check therefore compares only pixels no imagined splat reaches.
- **In a headset the screen-space ink is off:** the imagined half shows flat paper and the floor coastline. A per-eye ink pass is not built.
- **Skipping view-dependent colour in the data passes is not safe:** the setting lives on the shared splats, and on a sample with spherical harmonics it changed 7,700 to 10,600 of 144,000 pixels of the photograph.
- **Independent review of the viewer:** no critical finding, six important ones, all fixed test-first.


## Round 1 · 19–20 Nov 2026 · the capture, Marble and COLMAP

The first real material: one sitting in a narrow room with a high ceiling and bare white walls.

- **The room is smaller than the protocol assumed.** A loop 0.6 m off every wall does not fit; the passes run near the middle and take about 1:20 each at the slow pace. Hip height puts the operator's body across nearly half the sphere, so the hip pass keeps only its three forward views; the raised pass also loses its back view (the top of the head).
- **The privacy pass found brand marks, not people.** Masked in the three stills (laptop mark and sticker, an audio unit's name round its tape); the passes left as they are, since the marks blur away at the trained splat's resolution. A lit lock screen in 15 phone stills was excluded and the desk re-shot.
- **Marble, first runs:** two drafts (150 credits each) and worlds on Marble 1.1 and 1.1 Plus (1,500 each; Plus came in at half its 3,000 worst case). 3,300 credits, $2.64. Both drafts reproduce the still's view faithfully, as they should; the test is off the still's axis, through the doorway.
- **The client met the live API and moved two guesses to facts:** the credits field is `remaining_credits`, and a just-admitted operation can answer 404 for a moment. Both fixed test-first; no call was repeated.
- **COLMAP failed the plan's per-image rule and passed on spheres.** Every run placed nearly all room views, but only about 70 % saw 15 or more points: the rest look at bare wall, ceiling and door panel. Fallbacks in order: phone stills dropped (69.9 %), denser sampling to 888 views (69.9 %), exhaustive matching inside the raised pass (74.6 %). More frames do not add texture to a white wall. With Aaron's advance go (call 57) the run now passes when over 90 % of room spheres have two or more views seeing 15+ points: 141 of 149, 94.6 %; reprojection 1.15 px; the rotation guards (same-pitch and pitch-group medians) all clear. Seen from above, the camera path draws the room's loops, the doorway and the hallway's turn; from the side, the three heights separate, and the raised pass dips where the operator ducked the door frame.
- **The phone stills mostly did not join** (14 of 62 in the first run), so the training set is cube views only: 737 images, 14,594 points.

## Round 2 · 20–21 Nov 2026 · training and the door

- **Training on the laptop worked first time.** LichtFeld Studio (tag 5a92bff) on the RTX 3080 Laptop: 30,000 iterations, MCMC, 1.5 M splats, 31 minutes; on the held-out views PSNR 29.51, SSIM 0.9575. Both Marble worlds exported as full-resolution PLY (export is free).
- **Every door click was refused:** the three views disagree by 5–12 px RMS per corner, where the check allows 3. The camera poses are not the cause: COLMAP's own points near the door reproject at 0.5–1.1 px in all three clicked views. Two explanations were tried and dropped on the numbers: the X3's stitch seam (tie-point error is flat across yaw, 1.0–1.35 px, seam included) and rolling shutter in a turning frame (the same view's tie points fit). What is left is the corners themselves: the door's edge, the carpet pile at the floor and the frame's head seen from different heights each put the "corner" on a slightly different physical point in each view.
- **The door's proportions question the 5 cm.** Aaron found the open door hides the left jamb, its visible edge 5 cm in, so the clicked span would be 0.66 m. At 0.66 m the model's door is 1.81–1.83 m tall, not the taped 1.94; at 0.71 m it is 1.95. Every pair of views agrees on the shortfall (5–12 %). So the span between the clicks reads about 0.69–0.71 m, as if the 0.71 m tape already ran to the door's edge. Asked Aaron to tape the clicked span directly (call 58).
- **The door, settled (21 Nov).** The first tape had gone to the middle of the jambs; Aaron re-taped between the clicked points: 0.72 m at the floor, 0.715 m at the top, 1.96 m high. Scale 0.30421 m per COLMAP unit; the height comes out 1.977 m (+0.86 %). The click spread was accepted on Aaron's word, with the reason recorded (call 58).
- **The checks passed a wrong floor, and only a look caught it.** The floor leaned 19.6° and put the head pass at 1.31 m. An MCMC splat is mostly near-transparent (1,857 of 1.5 M splats above 0.5 opacity), and the floor is hardly in it, so the lowest fifth of the centres was the desk top and the corner-pinned fallback swung up to it. Now every floor must stay within 5° of the cameras' up (the door jambs agree with that up to 0.5°), and when the splat shows too little floor it is set level through the door corners. Heights now 2.14 / 1.69 / 1.05 m for raised / head / hip (call 59).
- **Gate A, by the numbers (21 Nov):** Marble 1.1 Plus lines up with the measured room at a median of 2.86 cm (90th percentile 6.17 cm), the right way round by a clear margin (photometric 0.925 against 0.676), 2.0° from upright, at 1.021 × the metric scale factor. The best start was not mirrored, so Marble's raw frame is OpenCV-like, as the plan assumed. Marble's `ground_plane_offset` (1.2227) matches neither the pano's measured 1.42 m nor 1.02 m in raw units, so it stays unused (call 60).
- **Gate A passed on Aaron's look; the finish step then found nothing imagined (21 Nov).** 99.6 % of Marble counted as covered, the coastline came out empty. An MCMC splat is mostly near-transparent haze (median opacity 0.000) filling the whole cleaning box, and a nearest-centre test counts haze as measured surface. Two findings for the thesis: Marble 1.1 Plus, given a pano from the room's middle, rebuilt the room and added only about 1.1 m of hallway past the door; and the frozen alignment residual (2.86 cm) is flattered by the same haze (7.6–14.9 cm against solid splats only), so the pose's real evidence is the photometric margin (0.25) and the contact sheet (call 61).
- **The coastline found its doorway (21 Nov).** With the measured world ended at the door frame (Aaron, call 62), Marble's hallway is the imagined part: 56,323 splats, 2.9 % of the world. The coastline then needed two fixes, both test-first (call 63): haze is measured but never a wall, and a stretch that passes in a doorway runs on to the jambs, because a 0.72 m door loses 20 cm at each side to the wall tolerance and fell under the 0.5 m minimum. One stretch now crosses the doorway, 0.60 m long.
- **The first real look, on the phone (21 Nov, about 2 am).** The room is the photograph and the doorway fills with Marble's hallway in crosshatch, the pen line round it: the piece works on real data. The phone does not yet hold it: with all 1.2 M splats loaded the median frame is 42–56 ms whatever the pixel ratio or the splats drawn, while the preview set (109k) runs at 17–22 ms. The full set often never finishes loading on the phone. The cost follows what is loaded, so the next tuning step is a lighter measured file for phones; kill rule 3's fallback is already shown to run (call 65).

## 22 Nov — the phone passes on splats drawn

- Phone file (300k measured + overlap + imagined = 368,926 loaded) on the iPhone 15 Pro: loads in full, but 51 ms median at dpr 2 (323k drawn) and 99 ms at dpr 3 (331k). Fewer splats loaded did not help; the 500k budget simply drew all of them.
- `?lod=200000`, dpr 2, start view: 25 ms median, 27 p90. `?lod=150000`, dpr 2, near a wall corner: 30 ms, 36 p90. Close walls cost more (large splats fill the screen); the frozen reading is the start view.
- Finding: on this phone the frame cost follows splats drawn (about 0.15 ms per thousand above ~110k), not splats loaded. Last night's reading of call 65 was wrong.
- Phone budget set to 200k (bfb1f21). Tilt did nothing over http: iOS removes the orientation API on insecure pages; the label now says so instead of blaming the phone.
- At the phone's own pixel ratio, 3 (phone file fully loaded, 200k drawn): 37 ms median at the start view and 54 ms at a near wall, against 25 ms at ratio 2. So phones stay capped at ratio 2 (c6071e4).

## Round 3 · 22 Nov 2026 · the design pass (Gate D)

### The black blots on the door

- **What they were.** Two failures in the hatching, both on pixels the flag calls imagined, and both ending in the same place. Hatch strokes are spaced 3 cm apart on the surface; where they pack closer than a pixel, the anti-moire fade swaps them for their mean ink, and that mean, 0.84 × width ÷ spacing, ran to 1: solid black.
  - **The black band along the left jamb** is Marble's hallway wall, seen almost edge-on through the door: its depth runs from 3.6 m to 2.9 m in ten pixels, so the strokes pack below a pixel.
  - **The smear on the door leaf** is the measured wall beside the frame, which the capture left as a thin veil (coverage 0.2 to 0.5 at 1.6 m, measured splats alone). Marble's splats behind it show through, in layers at 3.1 to 4.4 m. The G-buffer blends every splat's depth by its share of the pixel, so the depth there belongs to no surface and jumps by a metre between neighbouring pixels. Strokes laid on it pack into ink, and the crease test draws a line at every jump. Not MCMC haze this time: hiding each file in turn put it on the veil and the imagined splats behind it.
- **The fix (00e4be6), at the cause, not the colour.** A packed hatch now holds the tone of the closest spacing it can draw, as a pen lays fewer strokes rather than more ink; it can no longer reach solid black (under half ink at every pixel ratio). And hatching and creases are drawn only where the splats under a pixel are one surface. The test is the second difference of inverse depth, which is zero on any plane however steeply it is seen. A pixel loses its strokes when more than about a third of a 5 × 5 grid around it is rough. A real corner is rough only along its line, a fifth of the grid, so it keeps its strokes. The veil beside the door is now blank paper under the photograph's veil, with its silhouette still drawn.
- **Cost:** the extra work runs only on imagined pixels. The screen-space ink pass alone, timed in a synchronised loop on the MacBook Air M5 at the start view: 2.56 → 2.66 ms at pixel ratio 2, 1.54 → 1.66 ms at ratio 1. A view filled with the hallway pays the whole of it, about 0.55 ms at 1440 × 900 data pixels. Phones draw a quarter of those data pixels. The phone budget is unchanged. (Timer queries read 65–85 ms on this Metal backend, as the spike found, so they were not used.)
- Before and after, start view, desktop and phone: kept with the design-pass screenshots for Gate D.

### A tone for what was never scanned

- **The problem.** The canvas behind the splats was paper, and paper is the drawing's own material. Anywhere the capture saw nothing, the page said "drawn". The floor is the big case: the splat holds almost no floor (call 59), so looking down showed a pale paper field between the measured furniture and a few overlap islands.
- **The choice: a flat mid grey, `unscanned` in `web/src/theme/tokens.ts` (#8f908c on light paper, #5c5d5a on dark), as the canvas's clear colour.** Why this one:
  - It is neither material. The photograph is never flat, and the drawing is paper with ink on it.
  - Grey is the common sign for "no data" (an unloaded map tile, an empty viewport), so it needs no legend to be read as absence. The legend still names it.
  - It is mid-tone on purpose. A light grey sits too close to this room's white walls, and a dark one reads as shadow.
  - It is the same rule everywhere: where nothing was captured and nothing imagined, the page shows the grey. That includes past the end of Marble's world and around the survey on the map, where it makes the paper hallway read as the drawn thing it is.
  - Imagined splats are still drawn as paper, so the drawing keeps its ground. Only their soft edges thin into the grey.
- One token, its CSS twin checked against it by a test. Aaron can change the value in one place.

### The page chrome

- The first screen is the survey's cartouche: the title at display size, the statement at 20 px, the plain-words invite, Walk in, and a key of how to walk with key caps. It sits on the sheet's own paper, in ink, with square corners and no rules or shadows. On touch screens the key folds into "How to walk", so more of the room shows above the card. On wide screens the card stops short of the doorway.
- The map key gains "Not scanned". Its photograph swatch is a few pixels cut from the photograph itself. On phones it moves to the foot of the sheet, clear of the controls.
- The plain-words invite is the studio's blue-pencil component, in place after the statement. It shows only when the plain-words layer offers itself (`chrome.offerPlainWords`), and never on the hallway link. The layer itself is not built yet.
- About now says the page has not yet been tried in a headset.
- Motion: opening the map by its button lays the key down (180 ms, from its anchored edge). M and closing snap. The invite's button has press feedback. Nothing else moves, and hovers are a step in tone.

### The ink judged: drawing or filter (kill rule 2)

- **Verdict: filter.** Judged at five views (the start, near the door, inside the hallway, towards its turn, and the film's look-back), each against `?ink=off`.
  - The filter view shows what Marble imagined: a corridor with a door at its end, a picture on the wall, a skirting board, floorboards. The ink draws none of it. The whole doorway is one even cross-hatch inside the imagined region's outline.
  - **Tone carries no form here.** The scene's light runs straight along the hallway, so every wall that faces the walker is equally unlit and gets the same cross-hatch. Only the floor gets single hatching. The tone thresholds cannot separate them: the walls all sit at a lit amount of about 0. The tone tests fix that rule ("cross-hatches a wall the light runs along").
  - **Outlines find almost nothing inside.** Marble's corners are soft. Its door, picture and skirting lie flat on the walls, so they exist only in its colours, which the ink replaces with paper. Lowering the crease thresholds to 8° adds scribble along the jambs and still finds no door.
  - It reads as a hatch pattern laid over a mask, which is what a filter is. It does still do the piece's job: the border between photograph and drawing is unmistakable, which is what done line 1 asks of it.
- **The one pass on the pen rules.** Hatch spacing 3 → 4 cm, so paper shows between strokes from across the room. Creases at a 1.5 % depth step and a 14° turn (were 2 % and 20°), which picks up the jamb's corner. Paper grain 0.02 → 0.04. Tone thresholds unchanged, for the reason above.
- **Judged again: still filter, though lighter and more like pen strokes.** By kill rule 2 the page ships with the finding stated and the ink pass shown, never hidden.
- **What would make it a drawing is the architecture, not the pen.**
  - Draw Marble's own structure: edges and tone taken from the imagined splats' colour, which the shade pass now throws away.
  - And/or a draughtsman's light (from over the shoulder) in place of the scene's light, which shines straight at the walker down the hallway.
  - Either is outside kill rule 2's one pass. It is Aaron's call, and Part 2 is a natural place for it.
- **Found on the way:** at the film's turn point (2.955, 1.6, 0.477, looking back), the camera stands inside imagined splats. The view is blank paper in ink and grey fog in the filter, so the film's look-back shows no room. The path's turn point wants moving back towards the door before the film is cut.

## 22 Nov — the film (task 6.2)

- **The cut.** 78.3 s in 16:9 (1920 × 1080) and 9:16 (1080 × 1920), 24 fps, captions only: burned in, and as WebVTT and SRT. No audio track until Aaron's own music. Shot list, captions and commands are in `film/README.md`; the edit list is `film/edl.json`.
- **The export's camera path looks back from inside a wall.** Its turn, (2.955, 1.6, 0.477), is 1.2 m past the door centre. Marble's hallway wall stands about 1.07 m past it at eye height (the nearest imagined splats over 30 % opaque within 30 cm of the walk line). From there the look back is one flat tone: 1 grey level between the 10th and 90th percentiles in ink, 8 in the filter.
- **Fixed for the film, not in the media.** v2 is immutable, so the film renders from the local export through a route only the dev server has (`/film-scene/`, `web/vite/film-scene.ts`). Its `scene.json` differs from the export's only in `filmPath`, one path per shot from `film/paths.json`. The walk now turns at (2.609, 1.6, 0.421), 0.85 m past the door centre, and eases back to 0.70 m; the room shows whole through the doorway.
- **For the pipeline:** `film_path()` in `export.py` should turn short of the hallway's end rather than at a fixed 1.2 m: the nearest imagined or overlap splat on the walk line at eye height, less 0.25 m, and never under 0.4 m past the door (about 0.82 m here).
- **The finding, shown.** The switch shot wipes the design pass's view near the door from ink to `?ink=off` and back. The filter shows Marble's door, picture and skirting board; the ink, one even cross-hatch. The captions say it reads as a filter, not a drawing.
- **Checks.** Every frame used is checked before the cut, for a nearly flat tone (the camera inside a wall) and for a change from the frame before more than 2.5 times the changes around it (a late splat, a level-of-detail switch). None in either aspect. A frame planted out of place mid-walk changed 3.5 times as much as its neighbours, so the bar catches one. A walk frame dumped again on a fresh server came back byte for byte the same.
- **The headset slot** is an optional segment between the look back and the map, skipped until `film/takes/headset.mp4` exists (the Quest check is P77's). One command re-cuts with it (`film/README.md`).
- £0 spent.

## 22 Nov — Gate V (verify)

- **Checked.** The real scene (v2 on the media host) through the dev server and the production build, at 1440 × 900 and at a 390 × 844 iPhone (user agent, touch, pixel ratio 3), each in light and dark. Every control in turn: Walk in, How to walk, the invite, the plain-words chapters, Next, the notes fold, Map open and closed (button and M), Imagined half ink and filter, Plain words hide and bring back, About. After each step an audit lists any control or panel that overlaps another, leaves the screen or makes the page scroll sideways. The console was clean throughout. Screenshots stay with the session, not the repo.
- **Failed, and fixed.**
  - *The first card scrolled at 1280 × 800, 1366 × 768 and 1280 × 720* (it overran by 148, 124 and 199 px). It now holds every word without scrolling at 1100 × 900, 1280 × 800, 1366 × 768 and 1280 × 720, with one tighter step in type and air where the doorway holds the card to 25 to 28 rem and a second below 760 px high. The words are untouched.
  - *On the phone the tilt switch covered the map key* (206 × 44 px of it). The switch hides while the map is open. A tilt switch has no use on a top-down survey.
  - *Phone, plain words on, bar notes open:* the column ran down to the foot, over the tilt note and switch while walking and over the key on the map. It now stops above them (upright phones) and above the key on the map (any narrow width).
  - *The map's marker was half under the key* at the start position at 1440 × 900 with plain words on. It is drawn above the key now.
  - *At 720 to 880 px wide or under 600 px high (a phone on its side, a page zoomed to 200 %) and at 200 % text on a wide screen:* the key sat over the bar's tabs, and the plain-words band and its column over each other and the tabs. The key moves to the foot below 720 px, the bar wraps clear of the key over the map, and the band keeps below the bar and clear of the column.
- **break-ui, on the page's copy.** No WebGL (Chromium with graphics off; 1440, 390 and 320 wide, 200 % text, both themes): the fallback reads whole, no overflow. A slow network (scene 4 s, each splat file 6 s late, walking in while it loads) and a scene that fails to fetch: first screen and notes readable, status lines right, the fatal card whole at 1440, 390 and 320. A `scene.json` with zero coastlines (the coastline file with no stretches, served from a local route, nothing uploaded): no console errors, no layout change; the floor line and the map's line are simply gone. A long credit line from `scene.json`: wraps, no overflow. Plain words at 320 wide, at 200 % text and at 150 %: nothing cut off, panels scroll inside themselves.
- **Left open, for Aaron's call, because they are about words or an edge case.**
  - With zero coastlines the statement, the map key's "Pen line" row and the plain-words coastline note still talk about a line that is not there. Not a case v2 has (one 0.6 m stretch); the words are the copy's.
  - A failed fetch says "The scene could not be loaded: Failed to fetch", the browser's own wording.
  - On a phone on its side with plain words on, the tilt note sits under the band. At 200 % root text on a 390-wide phone the tilt switch wraps to two lines and its note touches it.
  - With plain words open on the first screen the card scrolls (the band is long by design) and Walk in is below the fold of the card.
- **Tests.** A new `e2e/layout.spec.ts` holds the card's fit at five laptop sizes and the two phone fixes. The full browser suite (42 tests, software rendering) ran on a copy of the config at another port, because the film work held the usual one: 40 passed on the first full run that had a stable server. The other two passed on their own: the spike's 60 s wait for the first frame timed out under load, and `plain.spec.ts` line 18 (the band takes focus after the invite) fails about a quarter of the time on the page as it was before these fixes too, because the focus waits for the next animation frame and software rendering can take over a second to draw one. Page and test are both right; the test's five seconds are too tight for this machine under load. Vitest 170 passed, `tsc` clean.
- **The clean pass.** After the last fix: the matrix again at both sizes in both themes on the dev server, and the production build the same way, console clean, no overlap and nothing off the screen (the audit's two remaining lines are a link clipped by the card's own scroll and the tilt switch lying under the card on About).

## 22 Nov — live and public

- **Deployed** to the personal Vercel team's project `herebeink`; the live files hash the same as the staged build. Driven in Chromium against the real scene on the media host at 1440 (light, dark, `?plain=1`) and 390 (light; dark with `?plain=1`): console clean, no failed requests, no sideways scroll, the only outside host the media host.
- **The domain:** added to the project, but `herebeink.studionephele.com` has no DNS record yet. The CNAME is Aaron's in Cloudflare (DNS only), as for the earlier cards; the deploy token cannot edit DNS.
- **The film needed no re-cut after Gate V:** its stills were shot at 1920×1080 and 540×675, which none of Gate V's new size rules reach, and the map marker stays mid-frame, clear of the key.
- **The repo is public** as one squashed commit without the eleven butterfly screenshots (no stated licence); `docs/spike-s1.md` says how to remake them. The private history keeps them.

## 22 Nov — the door seal (media v3)

- **What Aaron saw (hub call 90):** on the live page a strip of the hallway's wood floor showed as photograph between the door frame and the inked hallway.
- **Found:** inside the doorway, past the door plane, 6,765 of Marble's overlap splats (6,687 of them on the floor) were drawn half and half in Marble's own photo-like colour, because they sat 15 to 50 cm from fog the trained splat holds past the frame; 7,881 more were covered and dropped, so that fog showed in their place. The trained splat held 11,771 splats inside the opening past the plane, 67 of them at opacity 0.2 or more: the hallway's colour seen through the doorway, not a measurement (call 62). Beside the opening, a further band of overlap splats (Marble's hallway walls just past the jambs) showed as warm slivers along both jambs.
- **The seal:** the door plane is a hard edge (`pipeline/door_edge.py`, the one definition provenance, the coastline, the export and Part 2's ladder all read). Inside the opening past the plane (2 cm inside the taped jambs, 3 cm below the head), measured splats are trimmed and every Marble splat is imagined, whatever its distance. Past the plane beside the opening nothing is half and half: Marble's twin of the jamb stays covered, so the photographed jamb shows, and the rest is ink. The frame was checked face-on and from above: the head and both jambs keep their splats; the one trimmed cluster beside the right jamb (7,131 splats, median opacity 0.000, the hallway's orange) is fog.
- **The split changed:** covered 96.1 % (1,845,628), overlap 0.03 % (657), imagined 3.8 % (73,715), against 96.4 %, 0.7 % (12,603) and 2.9 % (56,323) before; measured 1,139,845 splats (11,089 trimmed); one coastline, 0.73 m (was 0.60 m). Almost all of Part 1's overlap band lay past the door.
- **Shipped:** media v3 on the media host (v1 and v2 untouched), the page pointed at it and deployed; the live checks pass and the console is clean. The plain words now say "about four in every hundred" (3.8 %), and THESIS carries both splits. The film keeps the v2 look and was not re-cut.
- **Left:** a faint grey smudge at the foot of the left jamb, on the frame's side of the seal.

## 22 Nov — Part 2, R1: one photo

- **Frozen first:** Part 2's criteria went into STATUS (and the public branch) before any ladder world existed, with the answer key changed by Amendment 1: the trained splat is mostly haze, so the key is the splat's rendered surface from the camera point rather than its few solid splats; a plane-fitted key was built and compared under a rule written first, and came out level with it, so the rendered key stood.
- **Generated:** R1, one 66° photo facing the door, cut from the 360 still. 1,580 credits. Marble's reply does not echo the seed, so whether seeds are honoured cannot be read from it.
- **Placed?** Not yet. Inside the photo's view the fit is close (6.5 to 6.8 cm), but Marble's room is narrower than the real one and its scale came out at 0.72 of what it states. The search picked a mirrored pose that is level; the unmirrored start Part 1's world used fits the room's shape better but sits 15° off level. One near-symmetric door wall and one photo cannot tell them apart by colour (0.49 against 0.50). Gate A failed on the colour check; the placement is Aaron's call.
- **Not placed.** Aaron's look at the full contact sheets: the orange is far from the grey. Drawn again with only what lies inside the photo's view, he is right about the placement too: Marble's door wall does not land on the real one in either pose, sitting about 0.7 m nearer the camera, and both fits shrank Marble's world to 0.72 of the scale it states. The 6.5 cm residual hid this, because it is read against every measured splat and the haze fills the room in front of the walls. With one narrow view the fit chases that haze; the 360 world in Part 1 had the whole sphere to hold its scale. R1 counts as not placed (kill rule 2). The fit's target is the next thing to fix, before R4 is bought.
- **Re-placed (hub calls 96–97).** The fit was changed to aim at the answer key inside a rung's view instead of every measured splat: a synthetic room with sparse walls and dense haze reproduced the pull (a known room came back at 89 % of its size and turned 39° wrong while its fit error read 3.3 cm) and the change recovers it. It was committed, with that test, before it touched R1. R1 then lands at the start Part 1's world took, Marble's front 2.6° from the door, its seen walls a median 4 cm from the key. Against COLMAP's own points, which the fit never uses, it sits 0.41 m nearer the camera than the room, about half of that the key's own error where one photo looks; before the change it was about 1.5 m. One check, colour against the photo's mirror image, fell short (0.055 where 0.10 is needed), and Aaron placed R1 by eye on grounds written once for every later rung. R1's numbers will be read as the scan's reading, as the frozen text says.

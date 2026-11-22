# Here Be Ink: provenance you can walk through

*Thesis, 22 November 2026; Part 1 of 2. Every figure comes from this repository's [LOG.md](LOG.md) and [STATUS.md](STATUS.md). The hallway test has not run yet; the walkers' words will be added when it has.*

## What it explores

The page opens on my room as a photograph. You walk. At the doorway a pen line crosses the floor: the coastline, like the edge of charted land on an old map. Past it the world is drawn in ink: paper tone, hatched shadow, outlines that keep one width as you move. Turn round and the room is still a photograph. A map shows the survey from above, and a switch flips the drawn half between the ink and a plain grey filter.

The first screen states the rule: the photograph is what the camera measured; the drawing is what a model made up beyond it. It does not say where the line falls. Finding it is the walk.

Both halves are real data. The measured half is three slow passes of the room with a 360 camera, each at a different height. COLMAP placed the cameras, and a laptop GPU trained the result as 1.5 million Gaussian splats. The imagined half is a world that World Labs' Marble built from one 360 still taken in the middle of the room. I set the capture's scale from the door frame and aligned Marble's world to it. A Marble splat within 15 cm of a measured one counts as covered and is dropped; from 15 to 50 cm it is overlap; beyond that, imagined.

In the browser, Spark draws the measured splats as captured and the imagined ones as paper, with hatching fixed to their surfaces. A second pass renders depth, normals and a provenance flag, so pen outlines fall only where the flag says imagined. Where nothing was captured or imagined, a flat grey ("Not scanned" on the map key) stands in, so a hole in the capture cannot pass for paper.

## Why it matters

Generated worlds now extend real captures without a seam. From one still, Marble rebuilt my room closely enough that its walls, floor and ceiling coincide with mine on the alignment contact sheet. Past the door it added about 1.1 m of hallway, 3.8 % of its world, made of the same stuff as the room. Seen through the plain filter, that hallway has a door, a picture on the wall and a skirting board. Nothing in how it looks tells a visitor which part anyone saw.

A caption saying so would not survive a screenshot. A rendering style does: crop any frame of this page and the drawn part still says imagined.

That only holds if the style stops exactly at the border, so the border is where the claim is won or lost. On the real room, the design pass found the border unmistakable: the room a photograph, the doorway in crosshatch, the pen line round it.

## What it suggests

First, provenance can be carried by how a world is drawn rather than by what is written beside it. Here the border holds; the drawing does not yet. Judged at five views against the plain filter, the ink reads as a filter: one even cross-hatch over the whole doorway. Marble's door, picture and skirting lie flat on its walls, so they exist only in its colour, which the ink replaces with paper. And the scene's light runs straight down the hallway, so every wall facing the walker is equally unlit and gets the same tone. One more pass on the pen rules, all that the rules fixed before the capture allow, made it lighter, not a drawing. By those rules, the page ships with the finding stated and the ink shown. What would make it a drawing is the architecture, not the pen: edges and tone taken from Marble's own colour, or a draughtsman's light from over the shoulder.

Whether strangers find the border unaided is the hallway test's question. Three people who have not seen the page will walk it on their own phones within seven days of launch, with both lines hidden, and say where the photograph ends. If two of the three cannot, that is the finding.

Second, "measured" has to be recorded when the capture is made; it cannot be read back from the result. The trained splat is mostly haze: only 1,857 of its 1.5 million splats are more than half opaque. A distance test counts haze as surface, so the first provenance pass called 99.6 % of Marble's world covered and found no border at all. A pipeline that kept, for each splat, how solidly the cameras saw it would make the coastline a fact rather than a judgement.

Third, on a phone the cost follows the splats drawn, not the splats loaded. On an iPhone 15 Pro the full room missed the 33 ms bar; capped at 200,000 splats drawn, the start view runs at 25 ms. Close views cost more, and the phone criterion, fixed before the capture, is read at the start view.

Part 2, under way, asks what moves the line: Marble shown one photo of the room, then two, four and eight, each set cut from the same 360 still and holding the one before, and last the 360 still itself; one model against itself on one room, before World Labs ends Marble on 8 January 2027.

## Numbers

- Camera positions placed: 141 of 149; reprojection 1.15 px (LOG, round 1).
- Training: 737 images, 30,000 iterations, 1.5 M splats, 31 minutes (LOG, round 2).
- Scale: door frame taped at 1.96 m high, 1.977 m in the model (+0.86 %) (LOG, round 2).
- Alignment, the fit for this room only: median 2.86 cm; colour check (each candidate pose scored against the 360 still's own views) 0.925 against 0.676 for the next pose (LOG, round 2). Pass bar: under 10 cm (STATUS).
- Split, with the doorway sealed at the door plane (media v3, 22 Nov): covered 96.1 %, overlap 0.03 % (657 splats), imagined 3.8 % (73,715); one coastline, 0.73 m, across the doorway (LOG, 22 Nov, the door seal). Before the seal, and in the film: 96.4 %, 0.7 %, 2.9 % (56,323), 0.60 m (LOG, round 2).
- Phone, iPhone 15 Pro, pixel ratio 2: full room 42 to 56 ms; lighter file, 323,000 drawn, 51 ms; capped at 200,000 drawn, 25 ms median and 27 ms p90 at the start view, 30 ms and 36 ms near a wall at 150,000. Bar: 33 ms (LOG, round 2 and 22 Nov; STATUS).
- The border: measured pixels carrying ink in one synthetic view, 60,767 with hatching weighted by a blurred flag, 0 when weighted by the flag under each pixel (LOG, round 0c).
- Outlines: 2 CSS px, measured 1.90 to 2.11 (STATUS, Gate S1).
- Design pass: the ink judged at five views against the plain filter; verdict filter, before and after one pass on the pen rules (hatch spacing 3 to 4 cm) (LOG, round 3).
- Marble: two drafts and two worlds, 3,300 credits ($2.64) (LOG, round 1).

## One honest limitation

The line on this page is part measurement, part judgement. Because haze reads as surface, no opacity threshold placed the border on its own: I ended the measured world at the door frame, where the trained splat turns to fog. The splat holds almost no floor either, so the floor is set level through the door's corners rather than fitted. The automatic fit had leaned 19.6° onto the desk top, and every check passed it until a look caught it. The same haze flatters the alignment figure: against solid splats only, the fit is 7.6 to 14.9 cm, so the pose rests instead on the colour check and the contact sheet. Each call is logged with its reason, but they are calls.

## Credits

Imagined world generated with World Labs Marble (marble-1.1-plus) through the World API; re-rendered in ink by Studio Nephele. The ink is the page's own rendering, never drawn by hand. Spark renders the splats, LichtFeld Studio trained them and COLMAP placed the cameras.

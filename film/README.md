# The film

A 78-second walk through the page, cut in 16:9 (1920 × 1080) and 9:16 (1080 × 1920) at 24 fps. Captions carry the story: burned in, and as `herebeink.vtt` and `herebeink.srt` beside the video. **There is no audio track.** Aaron's own music goes in later (below); nothing third-party, no narration.

Frames, page shots and exports are gitignored (`film/frames/`, `film/out/`). What is committed: the camera paths (`paths.json`), the edit list (`edl.json`), the tools in `web/tools/` and `web/vite/film-scene.ts`, and `make-film.sh`.

## Shot list (16:9, without the headset clip)

| Time | Segment | Picture | Caption |
|---|---|---|---|
| 0:00 | hook | Looking down at the pen line across the threshold, tilting up into the drawn doorway | A pen line crosses the floor of a real room. / On this side a camera measured. Past it, a model imagined. |
| 0:06 | first-screen | The page's first screen (page shot) | The first screen states the rule. It doesn't say where the line falls. |
| 0:10.5 | walk | From the start pose to the door | My room, filmed in three slow passes with a 360 camera. / Where it looks like a photograph, the camera saw it. |
| 0:18.5 | step-over | Through the door and over the line | At the door frame the measuring stops. Past the line, it is ink. |
| 0:24.5 | hallway | Marble's hallway in ink | World Labs' Marble built this hallway from one 360 still. |
| 0:28 | look-back | Turning round; the room through the doorway | Turn round, and the room is still a photograph. |
| (0:39) | headset | **Empty slot**, 5–8 s, skipped until its file exists | The same walk on a Quest. |
| 0:39 | map | The map, the visitor's dot following the walk (page shots) | From above: photograph, drawing, and grey where nothing was scanned. |
| 0:46 | switch | The view near the door in ink, wiped to `?ink=off` and back (gold divider) | The same view near the door, in ink. / Now as a plain filter. / The filter shows what Marble made: a door at the end, a picture, a skirting board. / The ink keeps none of it, just one even cross-hatch. It reads as a filter, not a drawing. |
| 1:02 | suggests | The start pose, a slow step towards the doorway | Still, the border holds. A caption won't survive a screenshot; a way of drawing can. / One test, not a proof: a made-up world can carry its provenance in how it is drawn. |
| 1:12 | end | Title, URL, credits (World Labs Marble named in words) | — |

The switch is the finding from the design pass (LOG.md, round 3): the ink reads as a filter. The film shows it rather than hiding it, as kill rule 2 requires of the page.

## The camera path, and why it is not the export's

The export's `filmPath` (in `scene.json`, written by `pipeline/export.py`) turns at (2.955, 1.6, 0.477), 1.2 m past the door centre. Marble's hallway wall stands about 1.07 m past the door centre at eye height (the nearest imagined splats more than 30 % opaque within 30 cm of the walk line), so the turn is inside the wall and its look back is blank paper in ink and grey fog in the filter.

The published media (`herebeink/v2/`) are immutable, so the film does not change them. It renders from the local export, `pipeline/work/export/v2/`, served by the dev server at `/film-scene/` (`web/vite/film-scene.ts`, only when `HBI_FILM_EXPORT` is set, never in a build). Its `scene.json` is the export's with one change: `filmPath` comes from a shot in `paths.json`. Each shot is its own path:

- `walk` turns at (2.609, 1.6, 0.421), 0.85 m past the door centre on the door's axis, about 0.22 m short of the wall, then eases back to 0.70 m while looking at the room.
- `hook`, `switch` (the design pass's view near the door, rendered twice: ink and `?ink=off`) and `outro` are short paths of their own.

What the pipeline should change: `film_path()` in `export.py` places the turn at a fixed `centre + 1.2 × outward`. It should measure the hallway instead: march along `outward` from the door centre at eye height, take the nearest imagined (or overlap) splat centre within about 0.3 m of that line, and turn about 0.25 m short of it, never less than 0.4 m past the door. For this room that gives about 0.82 m. `work/overrides.json` can still carry a hand path.

## Make it

One command, from the repo root (about 35 minutes on a MacBook Air M5; the frame dumps are most of it):

```bash
film/make-film.sh                 # export folder defaults to pipeline/work/export/v2
```

It runs, for each aspect, `web/tools/film-dump.mjs` for every shot (16:9 at 1920 × 1080; the 9:16 picture at 1080 × 1350, a 4:5 window between two ink bands), the `switch` shot again with `--ink off`, then `web/tools/film-shots.mjs` for the page shots (the first screen; the map, one shot per fourth frame of the walk), then `web/tools/film-cut.mjs`.

Step by step, from `web/`:

```bash
node tools/film-dump.mjs --export pipeline/work/export/v2 --shot walk --set 16x9-walk      # one shot, one aspect
node tools/film-dump.mjs --export pipeline/work/export/v2 --shot switch --ink off --set 16x9-switch-filter
node tools/film-shots.mjs --export pipeline/work/export/v2 --aspect 16x9                   # page shots from edl.json
node tools/film-shots.mjs --export pipeline/work/export/v2 --pose 2.6,1.6,0.42,80.8,-4      # a quick look at one pose (film/frames/looks/)
node tools/film-cut.mjs                                                                      # both aspects; --aspect 16x9, --only walk,map for a draft
```

`film-dump.mjs` starts the dev server on :5299 with `HBI_FILM_EXPORT` set if nothing answers there; if a server is already up without it, the dump stops and says so. That server runs without hot reload, so an edit to the page from another session cannot restart a shot halfway. Each frame is drawn only after Spark's sort and level-of-detail cut have settled for it, so two runs give the same frames. Its other flags: `--from N --frames N` for a range (numbered as in the whole shot), `--keep`, `--sw` (software rendering, for checks only), `--timeout <minutes>`.

Before cutting, `film-cut.mjs` checks every frame it uses: a frame that is nearly one flat tone (the camera inside a wall: blank paper or fog) or whose change from the frame before is well above the changes around it (a late splat, a level-of-detail switch) stops the cut and is named. `--no-check` cuts anyway.

## Outputs (`film/out/`)

- `herebeink-16x9.mp4`, `herebeink-9x16.mp4`: H.264 at CRF 23 for the web, `+faststart`, no audio. The CRF 16 masters they are encoded from stay in `film/frames/cut/<aspect>/master.mp4` (use those for an upload to a video host, or for laying in music).
- `herebeink.vtt`, `herebeink.srt`: the captions, timed to the cut (both aspects share the timing).
- `herebeink-poster.png` and `.jpg`: 1280 × 720, the room with the drawn doorway (the last frame of the `outro` shot), no caption.
- `herebeink-loop.mp4`: 8 s, silent and uncaptioned, for the portfolio card (the walk up to the door and into the ink).
- `herebeink-contact-16x9.png`, `herebeink-contact-9x16.png`: a frame every 3 s.

## The headset slot

The edit list carries a segment `headset` between the look back and the map, marked optional: the cut skips it while `film/takes/headset.mp4` is absent. The Quest check belongs to card P77. To put the clip in:

1. Record 5–8 s of the walk in the headset and save it as `film/takes/headset.mp4` (any size; it is scaled to fill the picture and cut to 8 s; `*.mp4` is gitignored).
2. Check the caption in `edl.json` (segment `headset`) says what the clip shows.
3. Re-cut without dumping again: `cd web && node tools/film-cut.mjs`. Every later segment, the VTT and the SRT move by the clip's length.

## Music (Aaron's own, later)

The film is cut silent on purpose. To lay a track under the finished cut, normalised for the web:

```bash
ffmpeg -i film/out/herebeink-16x9.mp4 -i music.wav -map 0:v -map 1:a -c:v copy \
  -af "afade=t=out:st=76:d=2,loudnorm=I=-14:TP=-1.5:LRA=11" -c:a aac -b:a 192k -shortest -movflags +faststart film/out/herebeink-16x9-music.mp4
```

The same for the 9:16 cut. Cut points fall on segment boundaries (the table above), so a bar line can be matched by moving `dur` or a frame range in `edl.json` and re-cutting.

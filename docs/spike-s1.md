# Spike S1: pen outlines from a second Spark pass

Run 18 Nov 2026 on Spark 2.4.0, three.js 0.187.0, Chromium (Playwright 1.64.1) on a MacBook Air M5, ANGLE's Metal backend. The page is `web/spike.html`; the measurements come from `web/tools/spike-s1.mjs`; the sample is Spark's public butterfly (177,132 splats). The screenshots are not in this public copy: they render that butterfly, whose licence Spark does not state. To remake them, run `web/tools/fetch-sample.sh`, then `node tools/spike-s1.mjs shots` in `web/` with the dev server on port 5299; they land in `docs/spike-s1/`.

## Verdict

**Gate S1: passes, with one condition.** The outlines work on the direct route, read 2 CSS px at both pixel ratios and along the orbit, and fall only on the imagined half. The second pass costs 3.3 ms a frame at DPR 1 and 4.0 ms on the Air's own DPR 2 screen **when the data passes run at half resolution** (`?gscale=0.5`), under the 6 ms bar. At full DPR 2 resolution it costs 7.6 ms, which fails. The product should draw the data passes at about one CSS pixel per data pixel; the outline still measures 1.85–1.94 CSS px that way.

| | |
|---|---|
| Rung of the ladder | The direct route (rung 0): screen-space outlines from depth, normal and coverage, masked by the provenance flag. Neither fallback was needed. |
| Flag route | Option (ii) is not optional: every off-screen pass needs its own `SplatMesh` sharing the loaded `PackedSplats`, on its own three.js layer. The flag then needs a pass of its own (option (i) on top of (ii)), because a splat carries only three writable channels, not four. |
| Outline width | 1.90–1.97 CSS px at DPR 1, 2.05–2.11 CSS px at DPR 2, at two distances; 1.95–1.97 CSS px at three orbit angles. |
| Cost of the second pass | 3.3 ms at DPR 1; at DPR 2, 4.0 ms with the data passes at half resolution (pass) and 7.6 ms at full resolution (fail). Frame-throughput A/B on the Air's GPU, states interleaved; ±0.5 ms or so. |

*Screenshot `final.png`: final frame (not in the public copy).*

The left half of the butterfly is flagged measured (shade pass untouched, no outline); the right half is flagged imagined (first-cut paper dyno, pen outline). The coastline runs down the body where the flag crosses 0.5.

## What was built

Per frame, in this order (`web/src/spike/main.ts`):

1. **G-buffer pass.** A second `SparkRenderer` with a `target` (RGBA16F, `NoColorSpace`, `accumExtSplats: true`) draws a second `SplatMesh` on layer 1. Its `worldModifier` dyno writes, per splat, `rgb = (depth01, 0.5 + 0.5 n.x, 0.5 + 0.5 n.y)` in view space, with `depth01 = clamp((viewZ − near)/(far − near), 0, 1)` and `n` the shortest axis rotated by the splat's quaternion, flipped to face the camera. Alpha stays the splat's opacity, so after blending the target's alpha is coverage and `rgb / a` is the coverage-weighted mean.
2. **Flag pass.** A third `SparkRenderer` (RGBA8 target) draws a third `SplatMesh` on layer 2 whose dyno writes `rgb = flag`. For the spike the flag comes from a world-space plane inside the dyno (`x < 0` measured, `x ≥ 0` imagined); a per-mesh `provenance` uniform replaces the plane for real files.
3. **Edge detection** (`web/src/spike/outlinePass.ts`), three full-screen passes:
   - *strength*: Sobel on view depth (a step of 2 % of depth is the threshold) and on the normal (20°), only between pixels with coverage ≥ 0.5;
   - *thin*: non-maximum suppression along the gradient for creases; silhouettes and the coastline are the inside pixels of the coverage = 0.5 and flag = 0.5 contours, so each is one pixel thin;
   - *spread*: a row pass that records the horizontal distance to the nearest line pixel.
4. **Shade pass** to the canvas (the ordinary `SparkRenderer` on layer 0, with the paper dyno on the imagined half).
5. **Composite**: a column pass finishes an exact Euclidean distance `d` to the nearest line pixel, and ink alpha is `clamp((W + 1)/2 − d, 0, 1) × flag` with `W = 2 × DPR` device pixels (3 × DPR for the coastline). Summed across a straight line, the ink is `W` pixels whatever the splats underneath look like. Ink `#1c1a17` on paper `#f4efe4` (dark scheme: `#e8e2d4` on `#1c1a17`).

The paper dyno on the imagined half (three tones from a fixed light, 45° world-space hatching, cross-hatching in the darkest tone) is the brief's bonus (e), and only a first cut: the hatching is evaluated at each splat's centre, so its lines are as coarse as the splats, and it reads as a grey engraving rather than ink. It is in the screenshots so they show the imagined half as more than an outline.

Two departures from the brief, both deliberate:

- **Silhouettes come from coverage, not depth.** Blended depth is undefined where coverage falls to zero, so a depth Sobel at the edge of a splat cloud fires across the whole soft ramp. The coverage = 0.5 contour is one pixel thin and sits where the eye puts the edge. Depth and normal Sobel then only find creases and occlusion edges inside the object.
- **The coastline is a contour, not a band.** `|flag − 0.5| < 0.08` after blending gives a band whose width is the width of the blend, which depends on splat size and distance. The flag = 0.5 contour widened to 3 CSS px is constant, as the brief wants of the line.

## Debug views

`?pass=shade|depth|normal|flag|edges|final`, all at the same pose (angle 40°, elevation 20°, distance 3):

| shade | depth | normal |
|---|---|---|
| `shade.png` | `depth.png` | `normal.png` |
| **flag** | **edges** | **final** |
| `flag.png` | `edges.png` | `final.png` |

## Outline width

Measured from screenshots of the edges view (ink on paper, coastline off) by summing ink across the line horizontally (`w_h`) and vertically (`w_v`) at every crossing and taking `w = 1/√(1/w_h² + 1/w_v²)`, which holds for a straight band at any angle. Median over all crossings, interquartile range in brackets:

| Case | CSS px | Device px (IQR) | Crossings |
|---|---|---|---|
| DPR 1, distance 2 | 1.90 | 1.90 (1.74–1.99) | 544 |
| DPR 1, distance 4 | 1.96 | 1.96 (1.79–2.27) | 223 |
| DPR 2, distance 2 | 2.05 | 4.10 (3.91–4.45) | 1138 |
| DPR 2, distance 4 | 2.11 | 4.22 (3.94–5.29) | 487 |
| DPR 1, orbit 10° | 1.95 | 1.95 (1.74–2.06) | 296 |
| DPR 1, orbit 45° | 1.96 | 1.96 (1.74–2.19) | 325 |
| DPR 1, orbit 80° | 1.97 | 1.97 (1.53–3.09) | 354 |

| DPR 2, distance 2, data at half resolution | 1.85 | 3.70 (3.39–3.99) | 976 |
| DPR 2, distance 4, data at half resolution | 1.94 | 3.89 (3.46–5.10) | 376 |

The line reads 2 CSS px at both pixel ratios and both distances (halving the distance doubles the butterfly on screen), and stays there along the orbit.

The tail above the median comes from junctions and tight curves (the antennae, the wing tips), where two lines' ink overlaps. Three frames along the orbit, final view:

| 10° | 45° | 80° |
|---|---|---|
| `orbit-10.png` | `orbit-45.png` | `orbit-80.png` |

At half resolution the line comes out about 5 % thin, because bilinear stretching spreads the antialiased edge; the edge is softer than at full resolution but still reads as a pen line:

*Screenshot `final-dpr2-data-half-crop.png`: DPR 2, data passes at half resolution (not in the public copy).*

The dots inside the imagined wing are creases found in the splats' normals: single pixels where the noisy normal field crosses 20°. They are fewer at √8 than at √4. A minimum line length, or a small blur of the normals before Sobel, would remove them; on a room they may be the texture we want, so this waits for the real capture.

## How soft the silhouettes are, √8 against √4

*Screenshot `stddev-8-vs-4.png`: √8 against √4 (not in the public copy).*

Softness is the mean width, in device pixels, of the 10–90 % coverage ramp per pixel of the coverage = 0.5 contour, read from the G-buffer's alpha:

| Cut-off | Distance 1.6 | Distance 3 |
|---|---|---|
| √8 | 2.04 px | 1.36 px |
| √4 | 2.01 px | 1.26 px |

On this sample the cut-off barely matters: the butterfly's edge splats are small, so the ramp is one to two pixels at either setting, and the outline sits on the contour either way. √4 is not needed for outlines, and it makes them worse here: its noisier normals give more single-pixel creases inside the wing (right-hand panel). It may matter on a room capture, where floaters and big background splats make wider ramps; check again on the real capture before deciding. The setting must be the same on every pass, or the G-buffer's coverage stops matching the shade pass.

## Cost

### How it was measured

The number that counts is what the extra passes add to a frame. It was measured as throughput: Chromium headless on the real GPU (`--use-angle=metal`; WebGL reports `ANGLE Metal Renderer: Apple M5`) with vsync and the frame-rate cap off (`--disable-gpu-vsync --disable-frame-rate-limit`), the camera on the slow deterministic orbit (`?orbit=1`, so Spark regenerates and re-sorts every frame as it would while walking), and the mean frame time taken as window length over frames drawn. Within one page the states alternate (extra passes off; splat passes only; everything), 1.5 s each after a 0.3 s settle, eight cycles; each cost below is the median of the eight paired differences. Interleaving matters: the Air has no fan, and back-to-back runs of one configuration drifted by up to 2 ms at DPR 2.

| Canvas | Data passes | Shade only (ms/frame) | + splat passes | + edge passes | **Second pass in all** |
|---|---|---|---|---|---|
| DPR 1 | full | 1.94 | +2.95 | +0.40 | **3.31** |
| DPR 2 | full | 3.23 | +5.51 | +2.02 | **7.63** |
| DPR 2 | half (`gscale=0.5`) | 2.87 | +3.21 | +0.56 | **3.99** |
| DPR 3 | full | 5.08 | +9.61 | +4.25 | **13.92** |
| DPR 3 | half | 4.67 | +3.99 | +1.87 | **5.83** |
| DPR 3 | a third | 4.74 | +3.31 | +1.13 | **4.51** |
| DPR 1, brute dilation | full | 2.21 | +3.61 | +0.82 | 4.37 |
| DPR 2, brute dilation | full | 3.32 | +5.93 | +7.03 | 12.98 |
| DPR 3, brute dilation | full | 4.57 | +7.42 | +21.40 | 29.61 |

"Splat passes" are the G-buffer and flag renders (each with its own generate, sort and draw); "edge passes" are strength, thin, spread and the composite. The splat passes cost about what the shade pass costs, each: they rasterise the same splats at the same resolution, so their cost falls with resolution, which is why half-resolution data passes fix the budget. The flag pass on its own was within the noise of the G-buffer pass in a separate probe (a single G-buffer pass already costs most of the +3 to +5 ms), which points at per-pass overhead as much as fill.

### How far to trust it

- **Fairly, as a frame cost on this machine**: the paired differences were stable across cycles, and the DPR 1 figures agree with the earlier, cruder runs (3.2 to 4.1 ms). Expect about ±0.5 ms at DPR 1 and ±1 ms at DPR 2–3. It is a throughput number with the GPU flat out, so it includes pipeline stalls and thermal throttling; at a vsync-capped 60 Hz the same work may hide some of its cost in idle time, so this errs high.
- **Not as GPU time.** Two other clocks were tried and rejected. `EXT_disjoint_timer_query_webgl2` is exposed on ANGLE/Metal, but its numbers did not add up (the shade pass read 4.6 ms with nothing else drawn) and four queries a frame themselves added about 2.5 ms of frame time at DPR 2. Batches of 40 back-to-back passes between forced syncs (`window.__spike.bench`, kept for reference) put the G-buffer and flag passes at 0.04–0.12 ms whatever the resolution, which the throughput runs contradict; the batch probably does not exercise what a real frame does (Spark's sort and readback run asynchronously after the frame, outside any synchronous timer), so it is not used.
- **Not for the phone.** Nothing here says what an iPhone 15 Pro will do; the phone criterion needs its own measurement on the device.

### Separable against brute-force dilation

Brute force over a (2R + 1)² window costs 5 ms more than the separable pass at DPR 2 and 17 ms more at DPR 3, for an identical line. The separable pass is the default (`?dilate=brute` brings the other back for comparison).

## Spark API: the plan's facts against the installed 2.4.0

Read from `node_modules/@sparkjsdev/spark/dist/types/*.d.ts` and `dist/spark.module.js`.

| Fact in the plan | Status | What is true in 2.4.0 |
|---|---|---|
| `SparkRenderer` takes `target: { width, height, doubleBuffer?, superXY? }` | **Confirmed, with more** | `target?: { width; height; doubleBuffer?; superXY? } & THREE.RenderTargetOptions`. The defaults are `RGBAFormat`, `UnsignedByteType`, **`SRGBColorSpace`**: a data target must pass `colorSpace: THREE.NoColorSpace` and usually `type: THREE.HalfFloatType`, or the values pass through sRGB. There is no resize method; `spark.target.setSize(w, h)` works because it is a plain `WebGLRenderTarget`. |
| `renderTarget({ scene, camera })`, `readTarget()`, `renderReadTarget()` | **Confirmed** | `renderTarget(...)` returns the `WebGLRenderTarget`. `readTarget(): Promise<Uint8Array>` reads bytes only (no use for a float target) and averages `superXY` on the CPU. Not needed for outlines: the post pass samples the texture on the GPU. |
| Several SparkRenderers may exist with different render layers, sort options or dyno programs | **Confirmed, with a trap** | `renderTarget` sets `SparkRenderer.sparkOverride` and calls `renderer.render(scene, camera)`. Every `SparkRenderer` *object* in the scene that the camera can see then draws the override's splats **with its own material**. So the off-screen renderer must itself be in the scene, and it must be the only one on the camera's layers during its render, or its custom shaders are silently ignored. Layers do both jobs: `SplatAccumulator.prepareGenerate` only generates `SplatGenerator`s that are visible and pass `camera.layers.test(node.layers)`. Each renderer keeps its own accumulators, sort worker and LoD state. Dyno programs belong to meshes, not renderers. |
| `SplatMesh` has `objectModifier` and `worldModifier` dyno hooks over a Gsplat (`center`, `scales`, `quaternion`, `rgba`, `flags`, `index`) | **Confirmed, with a catch** | They are setters for `objectModifiers` / `worldModifiers` (arrays also accepted in the options). Set after construction, they do not mark the generator dirty: call `mesh.updateGenerator()`. The GLSL struct is `Gsplat { vec3 center; uint flags; vec3 scales; int index; vec4 quaternion; vec4 rgba; }`. Helpers used: `dyno.dynoBlock`, `dyno.Dyno` (GLSL `statements`), `dyno.splitGsplat`, `dyno.gsplatNormal` (shortest axis rotated), `dyno.dynoFloat`, `dyno.dynoBool`, `dyno.dynoVec3`. Spark also ships `modifiers.makeDepthColorModifier` and `modifiers.makeNormalColorModifier`, which do almost what the G-buffer dyno does. |
| An `update` callback / `updateVersion` refreshes uniforms | **Changed** | A dyno uniform (`dynoFloat(...)` etc.) is a three.js uniform read when Spark *generates*; set `.value` and it applies at the next generate. Spark only generates when the view moves (> 1 mm or > ~2.6°) or a mesh's version changes, so after changing a uniform with the camera still, call `mesh.updateVersion()`. There is also an `onFrame({ mesh, time, deltaTime })` option. |
| The view matrix reaches the dyno as a uniform updated every frame | **Confirmed, by Spark's own route** | Set `mesh.enableWorldToView = true` and use `mesh.context.worldToView` (a `SplatTransformer` with `apply(vec3)`, `applyDir(vec3)`, `applyGsplat(...)`), whose `scale`, `rotate` and `translate` dyno uniforms Spark refreshes from the camera in `frameUpdate` before each generate. A hand-made `dynoMat4` would also work but is unnecessary. `context.viewToWorld` and `viewToObject` exist too. |
| Two `SplatMesh` instances can share one `packedSplats` | **Confirmed** | `new SplatMesh({ packedSplats: other.packedSplats })`. The constructor writes `splatEncoding` onto the shared object (harmless while both use the default). Copy the source mesh's position, quaternion and scale. |
| `maxStdDev` controls the footprint cut-off (default √8) | **Confirmed** | `SparkRendererOptions.maxStdDev`, default `Math.sqrt(8)`, per renderer, not per mesh. |
| (not in the plan) four channels per splat | **Wrong** | A splat has three writable channels. `rgba.a` is opacity and drives blending. The default accumulator stores rgb as 8 bits in [0, 1]; `accumExtSplats: true` stores fp16, but the splat vertex shader clamps rgb to ≥ 0, so signed values need the `0.5 + 0.5 x` encoding. This is why the flag needs its own pass. |
| (not in the plan) Spark's fragment shader | **Trap** | When drawing into a render target Spark sets `encodeLinear` and applies `pow(rgb, 2.2)`. A data pass needs its own `fragmentShader` (the option exists; `getShaders()` is not exported, so the spike carries a 25-line copy of the kernel without the conversion). `vertexShader` can be replaced the same way. |

## What the product code should do differently

1. **Draw the G-buffer and the flag in one splat pass with two outputs.** The vertex shader already has everything for depth and normal (`viewCenter`, the view-space quaternion, the scales). A custom `vertexShader` that computes them and a fragment shader with two outputs (`WebGLRenderTarget` with `count: 2`) leave the three per-splat channels free for the flag (and anything else per splat), and remove one generate, one sort and one draw per frame. This was not tried in the spike: Spark's `target` option builds the render target itself, so MRT needs either a target swapped in after construction or a small subclass. It is the first thing to try if the cost is tight.
2. **Or drop the second and third SparkRenderers entirely.** All passes could share the shade renderer's accumulator and sort: a second `THREE.Mesh` with the shade renderer's `geometry` and `uniforms` and a G-buffer material, drawn into the target after the shade pass, with the provenance looked up from the accumulator's per-mesh index ranges (`spark.display.mapping`). That is one generate and one sort per frame for everything, and keeps LoD in step for free. It reaches further into Spark's internals, so it wants a pinned version and a test.
3. **Draw the data passes at about one data pixel per CSS pixel** (`gscale = 1 / DPR`, clamped), composite the ink at that resolution and stretch it over the canvas. That is what brings DPR 2 under budget and it is the obvious lever for the phone (DPR 3).
4. **Keep the per-pass work separable.** The brute-force dilation over a (2R + 1)² window cost twice as much at DPR 2 and three times at DPR 3; the two-pass exact distance is already in the spike and should stay.
5. **Never leave timer queries on.** On ANGLE's Metal backend each query added real frame time (about 2.5 ms for four a frame at DPR 2); measure with them only in a dedicated run.
6. **One `maxStdDev` and one LoD setting shared by every pass**, or coverage and depth stop lining up with what is on screen.
7. **Edge thresholds want the real capture.** On the butterfly almost every line is a silhouette; creases barely fire, because the sample is nearly flat. A room has walls meeting at 90° and floaters; the 2 % depth and 20° normal thresholds need checking there, and splat-normal noise may need a small blur before Sobel.

## Open risks

- **WebXR.** Two eyes double every pass, and Spark updates after rendering in XR (`preUpdate` false). The outline pass would need to run per eye on the XR framebuffer's layers, at a width in device pixels that means something in a headset. Not tried.
- **LoD with two renderers.** LoD cuts are kept per renderer and per `SplatMesh` (`lodInstances` is keyed by mesh), so the G-buffer's mesh and the shade mesh can pick different LoD cuts and the outline can drift off the shaded surface. `enableDriveLod: false` lets a renderer use LoD driven elsewhere, but only for the same mesh object. Route 2 above avoids the problem; route 1 must be tested with a paged or LoD file.
- **Memory of the targets at DPR 3.** The G-buffer (RGBA16F) plus its depth buffer, the flag (RGBA8) plus depth, strength (RGBA16F), thin (RGBA8) and spread (RGBA16F): about 40 bytes a pixel, so about 470 MB at a 1440 × 900 window at DPR 3 (4320 × 2700) and about 120 MB on an iPhone 15 Pro at full resolution (1179 × 2556), before Spark's own accumulators. Half-resolution data passes, or dropping the depth buffers of the data targets (splats do not write depth), would cut that sharply; the phone criterion may need it.
- **Sort lag between passes.** Each renderer sorts on its own schedule, so for a frame or two after a fast turn the G-buffer and the shade pass can come from slightly different sort orders. Not visible in the spike's slow orbit.
- **Thermal drift.** The MacBook Air has no fan; repeated runs of the same configuration varied by up to 2 ms at DPR 2 before the interleaved method.

## Reproduce

```bash
cd web
tools/fetch-sample.sh            # once
npm run dev -- --port 5299 &
node tools/spike-s1.mjs all      # real GPU; --sw for SwiftShader
npm run e2e                      # includes e2e/spike.spec.ts under SwiftShader
```

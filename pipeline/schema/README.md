# scene.json and coastline.json: the contract between the pipeline and the page

`export.py` writes both and checks them against `scene.schema.json` and `coastline.schema.json`
before writing (`schema_check.py`). The page reads nothing else besides the splat files.
`scene.example.json` is a real one, from the synthetic fixture, with the walkable outline thinned.

## Frame and units

World frame: metres, the floor at y = 0, +y up, the room's long axis along +x, the origin on the
floor under the pano still. three.js's own convention (right-handed, y up), so no axis swap is needed.

**Every splat file stays in its own frame.** Its `matrix` (16 numbers, column-major, the order
`THREE.Matrix4.fromArray` takes) maps file coordinates to the world: a similarity (uniform scale,
rotation, translation). Set it on the mesh, for example
`new THREE.Matrix4().fromArray(f.matrix).decompose(mesh.position, mesh.quaternion, mesh.scale)`.
Spark evaluates spherical harmonics in the mesh's frame, so view-dependent colour stays right under the
rotation (tested with Spark 2.4.0); rewriting the files into the world frame would need the SH
coefficients rotated as well, which Spark's own transcoder does not do.

Angles: `yawDeg` turns about +y, 0 looks along -z and -90 along +x; `pitchDeg` looks up when
positive. Apply them as `camera.rotation.set(pitch, yaw, 0, "YXZ")` (radians).

## Fields

| Field | What |
|---|---|
| `schemaVersion` | 1. A breaking change bumps it. |
| `schemaMinor` | Additive changes within version 1 (optional; absent means 0). 1 since 18 Nov 2026 and 2 since 21 Nov 2026: the fields marked "minor 1" and "minor 2" below. A reader of version 1 may ignore them. |
| `generatedAt` | UTC time of the export, `YYYY-MM-DDTHH:MM:SSZ`. |
| `units`, `frame` | `"m"`; the world's up, floor height and long axis (always `[0,1,0]`, `0`, `[1,0,0]`). |
| `splats.measured` | The photographed room. `provenance` 0. |
| `splats.measuredPreview` | 40,000 of the measured splats, opacity-weighted; load first, swap for `measured`. |
| `splats.measuredPhone` | Minor 2, optional: 300,000 of the measured splats, opacity-weighted, in `measured`'s frame; phones load it in place of `measured`. `provenance` 0. |
| `splats.overlap` | Marble splats 0.15 to 0.50 m from a measured one. `provenance` 0.5. |
| `splats.imagined` | Marble splats 0.50 m or more from any measured one. `provenance` 1. |
| each splat file | `url` (relative to scene.json), `sha256`, `bytes`, `splats`, `shDegree`, `provenance`, `matrix`. |
| `radiiM` | `covered` 0.15 and `overlap` 0.5: the provenance radii, for the map's legend. |
| `floor` | normal and height of the floor plane (always up and 0). |
| `walkable` | `polygons`: closed outlines on the floor, `[x, z]` pairs, largest first; `dilationM` 0.5. |
| `eyeHeightM` | 1.6. |
| `start` | where the page opens: the pano still's place at eye height, looking at the door. |
| `door` | the doorway's centre on the floor, its width and the horizontal direction out of the room. |
| `filmPath` | keyframes `{t, position, yawDeg, pitchDeg}` for the film's walk (a first draft; edited by hand). The camera is always at eye height (`floor.y + eyeHeightM`; the walk sets it), so each key's `position[1]` must be that height, to within 2 cm: the viewer refuses a path that says otherwise rather than drop its heights. |
| `light.direction` | the unit vector the light travels along (in through the doorway and down, unless set by hand). |
| `coastline` | the coastline file: `url`, `sha256`, `bytes`, `stretches`, `lengthM`. |
| `counts` | splats in each file, and Marble's total and covered (dropped) count. Minor 2 adds `measuredPhone`, present exactly when `splats.measuredPhone` is. |
| `alignment` | the Gate A residual (median and 90th percentile in cm over the ICP set), its size, pass, and the note that it is this room's fit, not a Marble accuracy score. Minor 1 adds, all optional: `mode` (`pano` or `doorway`), `mirrorBaked` (Marble's files were mirrored in x before export, so the matrix stays a proper similarity), `hypothesis` (the chosen start: `yawDeg`, `mirror`, `flip`, `rawDown`), the added checks `gravity`, `photometric`, `icpShare` and `metricRatio` (each with `pass`), `acceptedByEye` (a person's reason for overruling the added checks) and `failedGateAllowed` (the reason for exporting after a failed gate). `gateAPass` is true only when the residual and every added check pass, or a person accepted by eye. |
| `scaleEvidence` | Minor 1, optional: how the scale was checked (`scale.py`): `checks` (each `name`, `value`, `limit`, `pass`, `fix`), `warnings`, and `accepted` when a person overruled a failed check. |
| `sources` | how each half was made; for the imagined half the provider, model and world id. |
| `credit` | the line the page and the film carry for World Labs. |

Checked beyond the schema's keywords (`schema_check.py`): no NaN or infinity anywhere; every
`matrix` is a proper similarity in column-major order (last row 0 0 0 1, determinant above 0, orthogonal
columns of one length); `covered + overlap + imagined = marble` and each file's `splats` equals its count;
`door.outward`, `light.direction`, `frame.up`, `frame.longAxis` and `floor.normal` are unit vectors.

`coastline.json`: `polylines` (each `{closed, points}` with `[x, z]` points on the floor in metres),
`lengthM`, and how it was made (`gridM` 0.1, `floorBandM` 0.5, `radiiM`, `gridOrigin`, `gridShape`).

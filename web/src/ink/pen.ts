// Every pen number in one place, so the look can be tuned without touching the shaders.
export const PEN = {
  /** Outline width in CSS px, at every devicePixelRatio. */
  outlineCssPx: 2,
  /** Screen-space coastline width in CSS px. */
  coastCssPx: 3,
  /** Hatch spacing on surfaces, metres: wide enough that paper shows between strokes from across the room. */
  hatchSpacingM: 0.04,
  /** Hatch stroke width in CSS px: a fine pen, so paper shows between strokes. */
  hatchCssPx: 1.1,
  /** Below this spacing in device px the strokes would alias; they fade to their mean tone. */
  hatchMinSpacingPx: 3,
  /** Tone thresholds on dot(n, L): above the first paper, above the second hatch, else cross-hatch. */
  toneLight: 0.66,
  toneMid: 0.33,
  /** Paper grain on the imagined half: luminance noise amplitude, fixed in screen space; enough to read as a sheet's tooth. */
  grain: 0.04,
  /** Floor coastline: width, hand jitter (metres) and height above the floor. */
  floorLineWidthM: 0.006,
  floorJitterM: 0.002,
  floorLineY: 0.005,
  /** Coverage and flag are blurred by this sigma (CSS px) before contours, to drop specks and pinholes. */
  cleanCssPx: 1.5,
  /** The screen-space coastline: where the cleaned flag rises past this (measured 0, overlap 0.5). */
  coastFlagAt: 0.25,
  /**
   * A pixel is "imagined" for ink once its flag passes these: a narrow ramp above the overlap
   * ring's one half, so a stroke is drawn in full or not at all, and never faintly on the
   * measured photograph.
   */
  imaginedFlagFrom: 0.55,
  imaginedFlagTo: 0.7,
  /** Edge thresholds: a 1.5 % step in view depth, a 14° turn of the normal (Marble's corners are soft). */
  depthStep: 0.015,
  normalDeg: 14,
  /**
   * Where no single surface lies under a pixel (a thin measured veil with the imagined world
   * showing through it, or imagined splats in layers), the blended depth belongs to nothing, and
   * strokes or creases laid on it are noise. Roughness is the second difference of inverse depth
   * across `surfaceStridePx` (CSS px), relative to the centre: zero on any plane however steeply
   * it is seen. It ramps from `roughFrom` to `roughTo`.
   */
  surfaceStridePx: 2,
  roughFrom: 0.01,
  roughTo: 0.03,
  /**
   * The share of rough samples around a pixel (a 5 x 5 grid, `surfaceStepPx` CSS px apart) at
   * which hatching and creases fade out. A real corner is rough only along its line, a fifth of
   * the grid, so it keeps its strokes.
   */
  surfaceStepPx: 3,
  layeredFrom: 0.25,
  layeredTo: 0.45,
} as const;

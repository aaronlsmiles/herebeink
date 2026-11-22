export type DeviceClass = "phone" | "desktop" | "xr";

export interface DeviceInfo {
  userAgent: string;
  maxTouchPoints: number;
  devicePixelRatio: number;
  xr: boolean;
}

export interface Budget {
  deviceClass: DeviceClass;
  lodSplatCount: number;
  /** Data pixels per canvas pixel for the G-buffer, flag and edge passes. */
  dataScale: number;
  /** Canvas pixel ratio, capped: beyond 3 the extra pixels buy nothing on a splat. */
  pixelRatio: number;
}

/**
 * Spark's splat size limits, in the pixels of the renderer that draws them (its defaults, written
 * out so the shade pass and the data passes are built from one place).
 */
export const SPARK_PIXEL_RADIUS = { min: 0, max: 512 } as const;

/**
 * The same limits for a pass drawn at `dataScale` of the canvas's resolution: a splat is cut at the
 * same size on screen in every pass, whatever devicePixelRatio is.
 */
export function dataPixelRadii(dataScale: number, base: { min: number; max: number } = SPARK_PIXEL_RADIUS) {
  return { min: base.min * dataScale, max: base.max * dataScale };
}

// Measured on an iPhone 15 Pro: the frame cost follows the splats drawn, and 200k held 25 ms at the start view.
export const LOD_PHONE = 200_000;
/** A phone's own ratio is 3, but its frame time was measured at 2; ?dpr= can still ask for 3. */
export const PHONE_MAX_DPR = 2;
export const LOD_XR = 500_000;
export const LOD_DESKTOP = 1_500_000;
const MIN_SCALE = 0.25;

export function deviceClass(d: DeviceInfo): DeviceClass {
  if (d.xr) return "xr";
  // Quest browsers say "Mobile VR" or "VR"; a headset must keep the full room for its session, so it is never a phone.
  if (/OculusBrowser|Quest|\bVR\b/.test(d.userAgent)) return "desktop";
  if (/iPhone|iPod|Android|Mobile/i.test(d.userAgent)) return "phone";
  // iPadOS asks for desktop pages with a Mac user agent; touch points give it away.
  if (/Macintosh/.test(d.userAgent) && d.maxTouchPoints > 1) return "phone";
  return "desktop";
}

/**
 * Which measured file to load: a phone takes the lighter one when the scene carries it, since the full file
 * often never finishes decoding on a phone; ?measured= overrides, but only towards a file the scene has.
 */
export function measuredKeyFor(cls: DeviceClass, sceneHasPhone: boolean, choice: "phone" | "full" | null): "measured" | "measuredPhone" {
  const wantPhone = choice ? choice === "phone" : cls === "phone";
  return wantPhone && sceneHasPhone ? "measuredPhone" : "measured";
}

export function budgetFor(d: DeviceInfo, overrides: { lod: number | null; gscale: number | null; dpr?: number | null }): Budget {
  const cls = deviceClass(d);
  const ownRatio = Math.min(d.devicePixelRatio || 1, cls === "phone" ? PHONE_MAX_DPR : 3);
  const pixelRatio = Math.min(Math.max(overrides.dpr ?? ownRatio, 1), 3);
  const lodDefault = cls === "desktop" ? LOD_DESKTOP : cls === "xr" ? LOD_XR : LOD_PHONE;
  // About one data pixel per CSS pixel: the spike found the outline still reads 2 CSS px there,
  // and it is what brought DPR 2 under the 6 ms bar.
  const scaleDefault = 1 / pixelRatio;
  const scale = overrides.gscale ?? scaleDefault;
  return {
    deviceClass: cls,
    lodSplatCount: overrides.lod ?? lodDefault,
    dataScale: Math.min(1, Math.max(MIN_SCALE, scale)),
    pixelRatio,
  };
}

import { describe, expect, it } from "vitest";
import { budgetFor, dataPixelRadii, deviceClass, LOD_DESKTOP, LOD_PHONE, LOD_XR, measuredKeyFor, PHONE_MAX_DPR, SPARK_PIXEL_RADIUS } from "./device.ts";

const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1";
const MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36";
const ANDROID = "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36";
const none = { lod: null, gscale: null };

describe("deviceClass", () => {
  it("knows phones, iPads posing as Macs, desktops and XR", () => {
    expect(deviceClass({ userAgent: IPHONE, maxTouchPoints: 5, devicePixelRatio: 3, xr: false })).toBe("phone");
    expect(deviceClass({ userAgent: ANDROID, maxTouchPoints: 5, devicePixelRatio: 2.6, xr: false })).toBe("phone");
    expect(deviceClass({ userAgent: MAC, maxTouchPoints: 5, devicePixelRatio: 2, xr: false })).toBe("phone");
    expect(deviceClass({ userAgent: MAC, maxTouchPoints: 0, devicePixelRatio: 2, xr: false })).toBe("desktop");
    expect(deviceClass({ userAgent: MAC, maxTouchPoints: 0, devicePixelRatio: 1, xr: true })).toBe("xr");
  });
});

describe("budgetFor", () => {
  it("caps a phone at the 200k splats drawn that held 25 ms on an iPhone 15 Pro (P50 call 67)", () => {
    // 323k drawn gave 51 ms and 200k gave 25 ms at the start view: the cost follows splats drawn.
    expect(LOD_PHONE).toBe(200_000);
  });

  it("draws a phone at pixel ratio 2, the setting its 25 ms was measured at, with data passes at a half", () => {
    // At dpr 3 a near wall took 30 ms with only ~103k drawn: the extra pixels are fill the phone can't afford.
    const b = budgetFor({ userAgent: IPHONE, maxTouchPoints: 5, devicePixelRatio: 3, xr: false }, none);
    expect(PHONE_MAX_DPR).toBe(2);
    expect(b).toEqual({ deviceClass: "phone", lodSplatCount: LOD_PHONE, dataScale: 0.5, pixelRatio: 2 });
  });

  it("gives a desktop 1.5M splats and one data pixel per CSS pixel", () => {
    expect(budgetFor({ userAgent: MAC, maxTouchPoints: 0, devicePixelRatio: 2, xr: false }, none))
      .toEqual({ deviceClass: "desktop", lodSplatCount: LOD_DESKTOP, dataScale: 0.5, pixelRatio: 2 });
    expect(budgetFor({ userAgent: MAC, maxTouchPoints: 0, devicePixelRatio: 1, xr: false }, none).dataScale).toBe(1);
  });

  it("gives XR the phone budget", () => {
    expect(budgetFor({ userAgent: MAC, maxTouchPoints: 0, devicePixelRatio: 1, xr: true }, none).lodSplatCount).toBe(LOD_XR);
  });

  it("caps the pixel ratio at 3 (2 on a phone) and floors it at 1", () => {
    expect(budgetFor({ userAgent: MAC, maxTouchPoints: 0, devicePixelRatio: 4, xr: false }, none).pixelRatio).toBe(3);
    expect(budgetFor({ userAgent: ANDROID, maxTouchPoints: 5, devicePixelRatio: 4, xr: false }, none).pixelRatio).toBe(2);
    expect(budgetFor({ userAgent: MAC, maxTouchPoints: 0, devicePixelRatio: 0.5, xr: false }, none).pixelRatio).toBe(1);
  });

  it("lets ?lod= and ?gscale= win, with the scale clamped to 0.25..1", () => {
    const d = { userAgent: IPHONE, maxTouchPoints: 5, devicePixelRatio: 3, xr: false };
    expect(budgetFor(d, { lod: 900_000, gscale: 0.5 })).toMatchObject({ lodSplatCount: 900_000, dataScale: 0.5 });
    expect(budgetFor(d, { lod: null, gscale: 0.1 }).dataScale).toBe(0.25);
    expect(budgetFor(d, { lod: null, gscale: 4 }).dataScale).toBe(1);
  });
});

describe("budgetFor, ?dpr=", () => {
  it("renders at the asked pixel ratio, clamped to 1..3, with the data pass following it", () => {
    const d = { userAgent: IPHONE, maxTouchPoints: 5, devicePixelRatio: 3, xr: false };
    expect(budgetFor(d, { lod: null, gscale: null, dpr: 2 })).toMatchObject({ pixelRatio: 2, dataScale: 0.5 });
    expect(budgetFor(d, { lod: null, gscale: null, dpr: 5 }).pixelRatio).toBe(3);
    expect(budgetFor(d, { lod: null, gscale: null, dpr: 0.5 }).pixelRatio).toBe(1);
    expect(budgetFor(d, { lod: null, gscale: null, dpr: 3 }).pixelRatio).toBe(3);
    expect(budgetFor(d, { lod: null, gscale: null, dpr: null }).pixelRatio).toBe(2);
  });
});

describe("measuredKeyFor", () => {
  it("gives phones the lighter measured file when the scene has one, and everything else the full file", () => {
    expect(measuredKeyFor("phone", true, null)).toBe("measuredPhone");
    expect(measuredKeyFor("phone", false, null)).toBe("measured");
    expect(measuredKeyFor("desktop", true, null)).toBe("measured");
    expect(measuredKeyFor("xr", true, null)).toBe("measured");
  });

  it("never takes a headset browser for a phone, so a headset keeps the full room", () => {
    const quest2 = "Mozilla/5.0 (Linux; Android 10; Quest 2) AppleWebKit/537.36 (KHTML, like Gecko) OculusBrowser/23.0.0.6.47.522134018 SamsungBrowser/4.0 Chrome/116.0.5845.240 Mobile VR Safari/537.36";
    const quest3 = "Mozilla/5.0 (X11; Linux x86_64; Quest 3) AppleWebKit/537.36 (KHTML, like Gecko) OculusBrowser/35.2.0.4.123.556318233 Chrome/126.0.6478.122 VR Safari/537.36";
    for (const ua of [quest2, quest3]) {
      const cls = deviceClass({ userAgent: ua, maxTouchPoints: 0, devicePixelRatio: 1, xr: false });
      expect(cls).not.toBe("phone");
      expect(measuredKeyFor(cls, true, null)).toBe("measured");
    }
  });

  it("lets ?measured= choose, but never a file the scene lacks", () => {
    expect(measuredKeyFor("phone", true, "full")).toBe("measured");
    expect(measuredKeyFor("desktop", true, "phone")).toBe("measuredPhone");
    expect(measuredKeyFor("desktop", false, "phone")).toBe("measured");
  });
});

describe("dataPixelRadii", () => {
  it("is the shade pass's limits where the data passes draw at the canvas's resolution", () => {
    expect(dataPixelRadii(1)).toEqual(SPARK_PIXEL_RADIUS);
  });

  it("scales both limits with the data pass's pixels, so a splat is cut at the same size on screen in every pass", () => {
    expect(dataPixelRadii(0.5).max).toBe(SPARK_PIXEL_RADIUS.max / 2);
    expect(dataPixelRadii(1 / 3).max).toBeCloseTo(SPARK_PIXEL_RADIUS.max / 3, 9);
    expect(dataPixelRadii(0.25, { min: 4, max: 100 })).toEqual({ min: 1, max: 25 });
    // The desktop and phone budgets draw the data passes at 1 / devicePixelRatio of the canvas.
    for (const dpr of [1, 2, 3]) {
      const scale = budgetFor({ userAgent: MAC, maxTouchPoints: 0, devicePixelRatio: dpr, xr: false }, none).dataScale;
      expect(dataPixelRadii(scale).max / scale).toBeCloseTo(SPARK_PIXEL_RADIUS.max, 9);
    }
  });
});

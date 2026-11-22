import { describe, expect, it } from "vitest";
import { XR_NOTE } from "./xr.ts";

describe("the headset note in About", () => {
  it("says plainly that the page has not yet been tried in a headset", () => {
    expect(XR_NOTE).toMatch(/^Not yet tried in a headset\./);
  });
  it("keeps the caveat that the outlines are drawn on screens only", () => {
    expect(XR_NOTE).toContain("outlines are drawn on screens, not yet in the headset");
  });
});

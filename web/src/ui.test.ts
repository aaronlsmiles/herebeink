import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { FINDING } from "./ui.ts";

describe("the design pass's finding, stated on the page (kill rule 2)", () => {
  const text = FINDING.join(" ");
  it("is two to four sentences", () => {
    expect(FINDING.length).toBeGreaterThanOrEqual(2);
    expect(FINDING.length).toBeLessThanOrEqual(4);
    for (const s of FINDING) expect(s.trim()).toMatch(/^[A-Z“].*[.]$/);
    expect(text.split(/(?<=[.!?])\s+/)).toHaveLength(FINDING.length);
  });
  it("says what the visitor sees and why, without hedging or apology", () => {
    expect(text).toMatch(/reads as a filter, not a drawing/);
    expect(text).toMatch(/one even cross-hatch/);
    expect(text).toMatch(/light runs straight down the (imagined )?hallway/);
    expect(text).not.toMatch(/\b(might|may|perhaps|possibly|arguably|somewhat|seems?|sorry|unfortunately|apolog\w*|hopefully|sadly)\b/i);
  });
  it("points at the ink/filter switch by its live label", () => {
    const label = text.match(/“([^”]+)”/)![1];
    const inkswitch = readFileSync(resolve(import.meta.dirname, "inkswitch.ts"), "utf8");
    expect(inkswitch).toContain(`"${label}: ink"`);
    expect(inkswitch).toContain(`"${label}: filter"`);
  });
});

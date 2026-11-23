// Stance A, in words: a number on the ladder is a coverage number; right and wrong never come with one.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { validateLadder } from "./contract.ts";
import { CHART, LADDER, LEGEND, pct, pointTitle, READOUT, STEP_LABEL } from "./words.ts";

const ladder = validateLadder(JSON.parse(readFileSync(resolve(import.meta.dirname, "../../public/fixture-ladder/ladder.json"), "utf8")));
const JUDGING = /\b(right|wrong|correct|incorrect|accura\w*|error|mistakes?|complete\w*|landed)\b/i;

describe("ladder words", () => {
  it("writes shares as the page does", () => {
    expect(pct(0.0773)).toBe("7.7%");
    expect(pct(0.307)).toBe("31%");
    expect(pct(0)).toBe("0%");
    expect(pct(1)).toBe("100%");
  });

  it("follows the control's wording: What Marble saw: 1 photo · 2 · 4 · 8 · the 360 still", () => {
    expect(`${LADDER.heading}: ${ladder.steps.map((s) => STEP_LABEL[s]).join(" · ")}`).toBe("What Marble saw: 1 photo · 2 · 4 · 8 · the 360 still");
  });

  it("never puts a number in a sentence about right or wrong", () => {
    const withNumbers = [
      ...ladder.rungs.flatMap((r) => [pointTitle(r), READOUT.shownText(r), READOUT.imaginedText(r), READOUT.checkText(r)]),
    ];
    expect(withNumbers.filter((s) => /\d/.test(s) && JUDGING.test(s))).toEqual([]);
    const fixed = [...(Object.values(LADDER) as unknown[]).filter((v): v is string => typeof v === "string"), ...(Object.values(CHART) as unknown[]).filter((v): v is string => typeof v === "string"), CHART.notPlotted(["4 photos"]), ...Object.values(LEGEND).flat()];
    expect(fixed.filter((s) => /\d/.test(s) && JUDGING.test(s))).toEqual([]);
  });

  it("uses the ladder's own classes in its key, never Part 1's", () => {
    const key = Object.values(LEGEND).flat().join(" ");
    expect(key).toMatch(/Seen/);
    expect(key).toMatch(/Imagined and wrong/);
    expect(key).not.toMatch(/\b(covered|overlap|half and half)\b/i);
  });

  it("says when the scan has no check figure, rather than showing nothing", () => {
    const r = { ...ladder.rungs[0], keyAgreement: { within15: null, within30: null } };
    expect(READOUT.checkText(r)).toBe("not available for this view");
    expect(pointTitle(r)).not.toMatch(/agrees/);
  });
});

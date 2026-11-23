import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { chartModel, chartSvg, CHART_BOX, toX, toY } from "./chart.ts";
import { type Ladder, validateLadder } from "./contract.ts";

const ladder = (): Ladder => validateLadder(JSON.parse(readFileSync(resolve(import.meta.dirname, "../../public/fixture-ladder/ladder.json"), "utf8")));

describe("the ladder's chart", () => {
  it("plots every placed rung, both R4 seeds included, and leaves out the rung not placed", () => {
    const m = chartModel(ladder(), "R4");
    expect(m.points.map((p) => p.id).sort()).toEqual(["P", "R1", "R2", "R4", "R4b", "R8"]);
    expect(m.missing).toEqual(["R4r"]);
    expect(m.points.find((p) => p.id === "R4")!.current).toBe(true);
    expect(m.points.filter((p) => p.current)).toHaveLength(1);
  });

  it("puts each point at (shown, imagined)", () => {
    const l = ladder();
    const m = chartModel(l, null);
    for (const r of l.rungs.filter((r) => r.placed)) {
      const p = m.points.find((q) => q.id === r.id)!;
      expect(p.px).toBeCloseTo(toX(r.shown));
      expect(p.py).toBeCloseTo(toY(r.imagined!));
    }
  });

  it("draws the floor through (shown, 1 − seen share of the key), left to right, one point per x", () => {
    const l = ladder();
    const m = chartModel(l, null);
    const xs = [...new Set(l.rungs.map((r) => r.shown))].sort((a, b) => a - b);
    expect(m.floor.map(([x]) => x)).toEqual(xs.map(toX));
    const r1 = l.rungs.find((r) => r.id === "R1")!;
    expect(m.floor[0][1]).toBeCloseTo(toY(1 - r1.seenShareOfKey));
  });

  it("marks reconstruction mode and footnotes the two rungs that rest on the scan's least certain part", () => {
    const m = chartModel(ladder(), null);
    expect(m.points.filter((p) => p.reconstruction).map((p) => p.id)).toEqual(["R8"]);
    expect(m.points.filter((p) => p.footnote).map((p) => p.id).sort()).toEqual(["R1", "R2"]);
    expect(chartSvg(m)).toMatch(/>1\*<\/text>/);
  });

  it("keeps labels apart and inside the sheet", () => {
    const m = chartModel(ladder(), null);
    const r4 = m.points.find((p) => p.id === "R4")!, r4b = m.points.find((p) => p.id === "R4b")!;
    expect(r4.anchor !== r4b.anchor || Math.abs(r4.ly - r4b.ly) >= 10).toBe(true);
    const p = m.points.find((q) => q.id === "P")!;
    expect(p.anchor).toBe("end");
    for (const q of m.points) expect(q.lx).toBeLessThanOrEqual(CHART_BOX.width);
  });

  it("says no right or wrong figure anywhere: titles and labels carry coverage only", () => {
    const svg = chartSvg(chartModel(ladder(), "R1"));
    expect(svg).not.toMatch(/\b(right|wrong|correct|accura\w*|error|complete\w*)\b/i);
    expect(svg).toMatch(/shown 7\.7%, imagined/);
    expect(svg).toMatch(/agrees with itself in 31% of this view/);
  });
});

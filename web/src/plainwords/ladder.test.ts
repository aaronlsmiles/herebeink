import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";
import { LADDER_NOTES } from "./ladder.ts";

const here = (rel: string) => readFileSync(resolve(import.meta.dirname, rel), "utf8");
const STORY = Object.values(LADDER_NOTES).flat();
const unquoted = (s: string) => s.replace(/"[^"]*"/g, "");
const quoted = (s: string) => [...s.matchAll(/"([^"]+)"/g)].map((m) => m[1]);

describe("the ladder in plain words", () => {
  test("no digits, and no figure at all (the thesis has no Part 2 numbers to source yet)", () => {
    expect(STORY.flatMap((s) => s.match(/\d/g) ?? [])).toEqual([]);
    const NUMBER_WORDS = /\b(one|two|three|four|five|six|seven|eight|nine|ten|twenty|hundred|thousand|million|dozen|twice|half|metres?|centimetres?|percent|per cent)\b/gi;
    expect(STORY.flatMap((s) => unquoted(s).match(NUMBER_WORDS) ?? [])).toEqual([]);
  });

  test("never a share of right or wrong: those are colour only (the publication stance)", () => {
    const SHARE = /\b(most|many|few|some|all|none|every|much|more|less|fewer)\b[^.]*\b(right|wrong)\b|\b(right|wrong)\b[^.]*\b(most|many|few|share|part of|amount)\b/i;
    expect(STORY.filter((s) => SHARE.test(unquoted(s)) && !/teacher/.test(s))).toEqual([]);
  });

  test("field words appear only inside quotes", () => {
    const JARGON = /\b(splats?|gaussian|colmap|provenance|coastlines?|render\w*|align\w*|frustums?|models?|generat\w*|imagined|reconstruct\w*|seeds?|directions?|scored|percent)\b|[%±§]/i;
    expect(STORY.filter((s) => JARGON.test(unquoted(s)))).toEqual([]);
  });

  const syllables = (w: string) => {
    const s = w.toLowerCase().replace(/[^a-z]/g, "");
    if (!s) return 0;
    if (s.length <= 3) return 1;
    const t = s.replace(/(?:[^laeiouy]es|ed|[^laeiouy]e)$/, "").replace(/^y/, "");
    return Math.max(1, (t.match(/[aeiouy]{1,2}/g) ?? []).length);
  };
  const sentences = STORY.flatMap((p) => p.split(/(?<=[.!?])\s+/)).map((s) => s.split(/\s+/).filter((w) => /[a-z0-9]/i.test(w)));
  const words = sentences.flat();
  const grade = 0.39 * (words.length / sentences.length) + 11.8 * (words.reduce((n, w) => n + syllables(w), 0) / words.length) - 15.59;
  test(`reads at grade 6 or below (Flesch–Kincaid ${grade.toFixed(1)}), no sentence over 25 words`, () => {
    expect(grade).toBeLessThanOrEqual(6);
    expect(sentences.filter((s) => s.length > 25).map((s) => s.join(" "))).toEqual([]);
  });

  test("every quoted label is the ladder's live label", () => {
    const live = here("../ladder/words.ts");
    const labels = [...new Set(STORY.flatMap(quoted))];
    expect(labels.length).toBeGreaterThan(0);
    expect(labels.filter((l) => !live.includes(`"${l}"`))).toEqual([]);
  });

  test("every note is placed exactly once", () => {
    const placed = here("../ladder/panel.ts") + here("./layer.ts");
    const counts = Object.keys(LADDER_NOTES).map((id) => [id, placed.split(`ladderNote("${id}"`).length - 1]);
    expect(counts.filter(([, n]) => n !== 1)).toEqual([]);
  });
});

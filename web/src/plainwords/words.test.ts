// The plain-words checks (the studio's method): every figure has a source in THESIS.md, field words only inside
// quotes, a reading level a 12-year-old manages, quoted labels that are the page's live labels, and the shared
// wording on the controls.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";
import { PLAIN_INVITE } from "../ui.ts";
import { CHAPTERS, chapterLabel, NOTES, UI } from "./words.ts";

const here = (rel: string) => readFileSync(resolve(import.meta.dirname, rel), "utf8");
const thesis = here("../../../THESIS.md");

const STORY = [...CHAPTERS.flatMap((c) => c.text), ...Object.values(NOTES).flat()];
const EVERYTHING = [...CHAPTERS.map((c) => c.title), ...STORY, ...Object.values(UI)];
const unquoted = (s: string) => s.replace(/"[^"]*"/g, "");
const quoted = (s: string) => [...s.matchAll(/"([^"]+)"/g)].map((m) => m[1]);

describe("honest numbers", () => {
  test("no digits in the words (the chapter count is the only one, and it is counted, not written)", () => {
    expect(EVERYTHING.flatMap((s) => s.match(/\d/g) ?? [])).toEqual([]);
    expect(chapterLabel(1)).toBe(`In plain words · 2 of ${CHAPTERS.length}`);
    expect(CHAPTERS).toHaveLength(5);
  });

  const num = (re: RegExp) => {
    const m = thesis.match(re);
    expect(m, `THESIS.md has no match for ${re}`).not.toBeNull();
    return Number(m![1].replace(/,/g, ""));
  };
  /** Each figure the words give, and the thesis line it rounds. */
  const SOURCED: { phrase: RegExp; check: () => void }[] = [
    { phrase: /\bthree times\b/g, check: () => expect(thesis).toMatch(/three slow passes of the room/) },
    { phrase: /\bone photo\b/g, check: () => expect(thesis).toMatch(/from one 360 still/) },
    { phrase: /\babout a metre\b/g, check: () => expect(Math.abs(num(/about ([\d.]+) m of hallway/) - 1)).toBeLessThanOrEqual(0.15) },
    { phrase: /\babout four in every hundred\b/g, check: () => expect(Math.round(num(/([\d.]+) % of its world/))).toBe(4) },
    { phrase: /\bmore than a million\b/g, check: () => expect(num(/([\d.]+) million (?:Gaussian )?splats/)).toBeGreaterThan(1) },
  ];
  for (const s of SOURCED) {
    test(`"${s.phrase.source.replace(/\\b/g, "")}" matches the thesis`, () => {
      expect(STORY.some((t) => s.phrase.test(t))).toBe(true);
      s.check();
    });
  }
  test("no other figure in the words", () => {
    const NUMBER_WORDS = /\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand|million|billion|dozen|twice|metres?|centimetres?|percent|per cent)\b/gi;
    const rest = STORY.map((t) => SOURCED.reduce((acc, s) => acc.replace(s.phrase, ""), unquoted(t)).replace(/\bwhich one\b/g, ""));
    expect(rest.flatMap((t) => t.match(NUMBER_WORDS) ?? [])).toEqual([]);
  });
});

describe("plain words", () => {
  // Field words may appear only in quotes, naming a label the reader can see.
  const JARGON = /\b(splats?|gaussian|colmap|provenance|coastlines?|render\w*|align\w*|residual|median|metric|benchmark|haze|mcmc|pixels?|shaders?|mesh\w*|buffers?|webgl|webxr|opacity|depth|normals?|\w*hatch\w*|lod|spz|models?|generat\w*|imagined|frustum|latency|percent)\b|[%±§]/i;
  test("field words appear only inside quotes", () => {
    expect(EVERYTHING.filter((s) => JARGON.test(unquoted(s))).map((s) => `${unquoted(s).match(JARGON)![0]}: ${s}`)).toEqual([]);
  });

  /** Flesch–Kincaid grade over the story's sentences, with the studio's syllable heuristic. */
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
  const longest = Math.max(...sentences.map((s) => s.length));

  test(`reads at grade 6 or below (Flesch–Kincaid ${grade.toFixed(1)})`, () => {
    expect(grade).toBeLessThanOrEqual(6);
  });
  test(`short sentences: 14 words on average, none over 25 (average ${(words.length / sentences.length).toFixed(1)}, longest ${longest})`, () => {
    expect(words.length / sentences.length).toBeLessThanOrEqual(14);
    expect(sentences.filter((s) => s.length > 25).map((s) => s.join(" "))).toEqual([]);
  });
  test("no draft notes", () => {
    expect(EVERYTHING.join("\n")).not.toMatch(/Draft|TODO|TBD|XXX/);
  });
  test("the controls use the studio's shared wording, the same as the first screen's invite", () => {
    expect(`${UI.invite} ${UI.follow}`).toBe("New to this? Read it in plain words");
    expect(UI.hide).toBe("Hide plain words");
    expect(UI.toggle).toBe("Plain words");
    expect(UI.label).toBe("In plain words");
    expect(PLAIN_INVITE).toEqual({ label: UI.label, lead: UI.invite, action: UI.follow });
  });
});

describe("quoted labels are the page's live labels", () => {
  // Where each label is set in the page's own code; a renamed control fails here until the words follow it.
  const LIVE = ["../ui.ts", "../inkswitch.ts", "../map.ts", "../walk-touch.ts", "../xr.ts"].map(here).join("\n");
  /** Quotes that name no control: the page's own word for the photograph's side, and an example label. */
  const NOT_LABELS = new Set(["measured", "made by AI"]);
  test("every quoted label is on the page", () => {
    const labels = [...new Set(STORY.flatMap(quoted))].filter((q) => !NOT_LABELS.has(q));
    expect(labels.length).toBeGreaterThanOrEqual(7);
    // A label is set either as a string or as an element's text in a template (the map's legend).
    expect(labels.filter((l) => !LIVE.includes(`"${l}"`) && !LIVE.includes(`${l}</`))).toEqual([]);
  });
  test("\"measured\" is the statement's own word", () => {
    expect(here("../ui.ts")).toMatch(/The photograph is what the camera measured\./);
  });
});

describe("placement", () => {
  test("every note is placed exactly once", () => {
    const layer = here("./layer.ts");
    const counts = Object.keys(NOTES).map((id) => [id, layer.split(`note("${id}"`).length - 1]);
    expect(counts.filter(([, n]) => n !== 1)).toEqual([]);
  });
});

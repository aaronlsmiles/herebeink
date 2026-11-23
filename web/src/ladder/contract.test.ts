import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { ContractError, SPLAT_FILE_REQUIRED } from "../contract.ts";
import {
  filesFor, FRUSTUM_REQUIRED, KEY_AGREEMENT_REQUIRED, LADDER_REQUIRED, MAP_REQUIRED, RUNG_FILE_KEYS, RUNG_IDS, RUNG_REQUIRED, rungById, validateLadder,
} from "./contract.ts";

const web = resolve(import.meta.dirname, "../..");
const readJson = (p: string) => JSON.parse(readFileSync(resolve(web, p), "utf8"));
const fixture = () => readJson("public/fixture-ladder/ladder.json");
const schema = () => readJson("../pipeline/schema/ladder.schema.json");

function problemsOf(fn: () => unknown): string[] {
  try {
    fn();
  } catch (e) {
    if (e instanceof ContractError) return e.problems;
    throw e;
  }
  return [];
}

describe("ladder.json contract", () => {
  it("accepts the committed fixture, its five steps and its not-placed rung", () => {
    const l = validateLadder(fixture());
    expect(l.steps).toEqual(["R1", "R2", "R4", "R8", "P"]);
    expect(rungById(l, "R4r")?.placed).toBe(false);
    expect(rungById(l, "R4r")?.imagined).toBeNull();
    expect(rungById(l, "R4")?.splats?.wrong.provenance).toBe(1);
  });

  it("names a missing field and says it is the ladder contract", () => {
    const l = fixture();
    delete l.camera;
    delete l.rungs[0].seenShareOfKey;
    delete l.rungs[1].splats.seen.matrix;
    let message = "";
    try { validateLadder(l, "https://x/ladder.json"); } catch (e) { message = (e as Error).message; }
    expect(message).toMatch(/^https:\/\/x\/ladder.json does not match the ladder contract:\n- /);
    const problems = problemsOf(() => validateLadder(l));
    expect(problems).toContain("camera: missing");
    expect(problems).toContain("rungs[0].seenShareOfKey: missing");
    expect(problems).toContain("rungs[1].splats.seen.matrix: missing");
  });

  it("refuses a file marked with the other half's provenance, so nothing seen is drawn in ink", () => {
    const l = fixture();
    l.rungs[0].splats.seen.provenance = 1;
    l.rungs[0].splats.wrong.provenance = 0;
    expect(problemsOf(() => validateLadder(l))).toEqual([
      "rungs[0].splats.seen.provenance: should be one of 0, got 1",
      "rungs[0].splats.wrong.provenance: should be one of 1, got 0",
    ]);
  });

  it("asks a placed rung for its files and its plotted share; a rung not placed needs neither", () => {
    const l = fixture();
    delete l.rungs[0].splats;
    l.rungs[0].imagined = null;
    expect(problemsOf(() => validateLadder(l))).toEqual([
      "rungs[0].splats: missing (a placed rung is drawn)",
      "rungs[0].imagined: should be a number on a placed rung (it is plotted)",
    ]);
  });

  it("refuses shares outside 0..1, but takes null where the scan has no agreement figure", () => {
    const l = fixture();
    l.rungs[0].shown = 1.2;
    l.rungs[1].keyAgreement.within15 = null;
    l.rungs[2].keyAgreement.within30 = -0.1;
    expect(problemsOf(() => validateLadder(l))).toEqual([
      "rungs[0].shown: should be at most 1, got 1.2",
      "rungs[2].keyAgreement.within30: should be at least 0, got -0.1",
    ]);
  });

  it("refuses a step with no rung behind it, and a rung listed twice", () => {
    const l = fixture();
    l.steps = ["R1", "R2", "R4", "R8", "R4r", "P"];
    l.rungs = l.rungs.filter((r: { id: string }) => r.id !== "R4r");
    l.rungs.push({ ...l.rungs[0] });
    const problems = problemsOf(() => validateLadder(l));
    expect(problems).toContain(`steps[4]: no rung "R4r" in rungs`);
    expect(problems).toContain(`rungs[${l.rungs.length - 1}].id: "R1" appears twice`);
  });

  it("checks a phone file set like any other, and a phone loads it in place of the full one", () => {
    const l = validateLadder(fixture());
    const p = rungById(l, "P")!;
    expect(filesFor(p, true)?.seen.url).toMatch(/-phone\.spz$/);
    expect(filesFor(p, false)?.seen.url).not.toMatch(/-phone/);
    expect(filesFor(rungById(l, "R4")!, true)).toBe(rungById(l, "R4")!.splats);
    const raw = fixture();
    raw.rungs.find((r: { id: string }) => r.id === "P").splatsPhone.imagined.matrix = [1, 0, 0];
    expect(problemsOf(() => validateLadder(raw))).toEqual([expect.stringMatching(/^rungs\[\d\]\.splatsPhone\.imagined\.matrix: should have 16 numbers, has 3$/)]);
  });

  it("keeps the same required fields, rung ids and file keys as the pipeline's schema", () => {
    const s = schema();
    const d = s.$defs;
    expect([...LADDER_REQUIRED].sort()).toEqual([...s.required].sort());
    expect([...RUNG_REQUIRED].sort()).toEqual([...d.rung.required].sort());
    expect([...FRUSTUM_REQUIRED].sort()).toEqual([...d.frustum.required].sort());
    expect([...MAP_REQUIRED].sort()).toEqual([...d.rung.properties.map.required].sort());
    expect([...KEY_AGREEMENT_REQUIRED].sort()).toEqual([...d.rung.properties.keyAgreement.required].sort());
    expect([...SPLAT_FILE_REQUIRED].sort()).toEqual([...d.splatFile.required].sort());
    expect([...RUNG_FILE_KEYS].sort()).toEqual([...d.rungFiles.required].sort());
    expect([...RUNG_IDS].sort()).toEqual([...d.rungId.enum].sort());
  });
});

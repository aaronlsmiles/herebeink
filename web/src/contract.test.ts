import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  COASTLINE_REQUIRED, ContractError, OPTIONAL_SPLAT_KEYS, SCENE_REQUIRED, SPLAT_FILE_REQUIRED, SPLAT_KEYS, validateCoastline, validateScene,
} from "./contract.ts";

const web = resolve(import.meta.dirname, "..");
const readJson = (p: string) => JSON.parse(readFileSync(resolve(web, p), "utf8"));
const fixture = () => readJson("public/fixture/scene.json");
const schema = (name: string) => readJson(`../pipeline/schema/${name}`);

function problemsOf(fn: () => unknown): string[] {
  try {
    fn();
  } catch (e) {
    if (e instanceof ContractError) return e.problems;
    throw e;
  }
  return [];
}

describe("scene.json contract", () => {
  it("accepts the committed fixture and the schema's example", () => {
    const s = validateScene(fixture());
    expect(s.splats.imagined.provenance).toBe(1);
    expect(s.splats.measured.matrix).toHaveLength(16);
    expect(() => validateScene(schema("scene.example.json"))).not.toThrow();
  });

  it("names a missing field", () => {
    const s = fixture();
    delete s.light;
    delete s.splats.overlap.matrix;
    const problems = problemsOf(() => validateScene(s));
    expect(problems).toContain("light: missing");
    expect(problems).toContain("splats.overlap.matrix: missing");
  });

  it("takes an optional lighter measured file for phones, checked like any other", () => {
    const s = fixture();
    s.splats.measuredPhone = { ...s.splats.measured, url: "measured-phone.spz" };
    s.counts.measuredPhone = s.splats.measured.splats;
    expect(validateScene(s).splats.measuredPhone?.url).toBe("measured-phone.spz");
    s.splats.measuredPhone.matrix = s.splats.measured.matrix.slice(0, 15);
    expect(problemsOf(() => validateScene(s))).toEqual(["splats.measuredPhone.matrix: should have 16 numbers, has 15"]);
  });

  it("refuses a matrix that is not 4 x 4", () => {
    const s = fixture();
    s.splats.measured.matrix = s.splats.measured.matrix.slice(0, 15);
    expect(problemsOf(() => validateScene(s))).toEqual(["splats.measured.matrix: should have 16 numbers, has 15"]);
  });

  it("refuses a matrix that is not a similarity the exporter could have written", () => {
    const problemsFor = (matrix: number[]) => {
      const s = fixture();
      s.splats.measured.matrix = matrix;
      return problemsOf(() => validateScene(s)).filter((p) => p.startsWith("splats.measured.matrix"));
    };
    // Column-major, so the bottom row is indices 3, 7, 11 and 15.
    const rotated = [0, 2, 0, 0, -2, 0, 0, 0, 0, 0, 2, 0, 5, 1, -3, 1];
    expect(problemsFor(rotated)).toEqual([]);
    expect(problemsFor([...rotated.slice(0, 15), 2])).toEqual(["splats.measured.matrix: last row should be 0, 0, 0, 1"]);
    expect(problemsFor(rotated.map((v, i) => (i === 7 ? 0.1 : v)))).toEqual(["splats.measured.matrix: last row should be 0, 0, 0, 1"]);
    expect(problemsFor([-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])).toEqual(["splats.measured.matrix: should not mirror or flatten (determinant should be positive)"]);
    expect(problemsFor([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])).toEqual(["splats.measured.matrix: should not mirror or flatten (determinant should be positive)"]);
    expect(problemsFor([1, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])).toEqual(["splats.measured.matrix: should scale evenly (column lengths differ)"]);
    // The exporter writes nine significant digits, so a hair of rounding is not uneven scaling.
    expect(problemsFor([1, 0, 0, 0, 0, 1.0000001, 0, 0, 0, 0, 0.9999999, 0, 3, 4, 5, 1])).toEqual([]);
  });

  it("refuses a film path that leaves eye height, since film mode walks at eye height", () => {
    const s = fixture();
    s.filmPath[1].position[1] = 1.2;
    s.filmPath[2].position[1] = s.floor.y + s.eyeHeightM + 0.015;
    expect(problemsOf(() => validateScene(s))).toEqual([
      `filmPath[1].position[1]: should be the eye height ${s.floor.y + s.eyeHeightM} (film mode walks at eye height), got 1.2`,
    ]);
  });

  it("refuses an unknown provenance value and a walkable polygon of two points", () => {
    const s = fixture();
    s.splats.imagined.provenance = 0.7;
    s.walkable.polygons = [[[0, 0], [1, 1]]];
    const problems = problemsOf(() => validateScene(s));
    expect(problems).toContain("splats.imagined.provenance: should be one of 0, 0.5, 1, got 0.7");
    expect(problems).toContain("walkable.polygons[0]: should have at least 3 item(s), has 2");
  });

  it("says which file failed in a readable message", () => {
    let message = "";
    try { validateScene({ schemaVersion: 2 }, "https://x/scene.json"); } catch (e) { message = (e as Error).message; }
    expect(message).toMatch(/^https:\/\/x\/scene.json does not match the scene contract:\n- /);
    expect(message).toContain("- light: missing");
    expect(message).toContain("- schemaVersion: should be one of 1, got 2");
    expect(message).not.toContain("frame: should be an object");
  });

  it("knows every splat file the pipeline's schema allows, optional ones included", () => {
    const s = schema("scene.schema.json");
    expect([...SPLAT_KEYS, ...OPTIONAL_SPLAT_KEYS].sort()).toEqual(Object.keys(s.properties.splats.properties).sort());
  });

  it("keeps the same required fields as the pipeline's schema", () => {
    const s = schema("scene.schema.json");
    expect([...SCENE_REQUIRED].sort()).toEqual([...s.required].sort());
    expect([...SPLAT_FILE_REQUIRED].sort()).toEqual([...s.$defs.splatFile.required].sort());
    expect([...SPLAT_KEYS].sort()).toEqual([...s.properties.splats.required].sort());
    expect([...COASTLINE_REQUIRED].sort()).toEqual([...schema("coastline.schema.json").required].sort());
  });
});

describe("coastline.json contract", () => {
  it("accepts the fixture's coastline", () => {
    const c = validateCoastline(readJson("public/fixture/coastline.json"));
    expect(c.polylines.length).toBeGreaterThan(0);
  });

  it("refuses a polyline with a three-number point", () => {
    const c = readJson("public/fixture/coastline.json");
    c.polylines[0].points[1] = [1, 2, 3];
    expect(problemsOf(() => validateCoastline(c))).toEqual(["polylines[0].points[1]: should have 2 numbers, has 3"]);
  });
});

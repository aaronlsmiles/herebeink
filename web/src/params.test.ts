import { describe, expect, it } from "vitest";
import { DEFAULT_LADDER_URL, DEFAULT_SCENE_URL, ladderUrlFor, parseParams, type SceneEnv } from "./params.ts";

describe("parseParams", () => {
  it("defaults to the fixture with ink and coastlines on", () => {
    const p = parseParams("");
    expect(p).toEqual({
      sceneUrl: DEFAULT_SCENE_URL, ink: true, coast: true, hud: false, map: false,
      lod: null, gscale: null, dpr: null, measured: null, pose: null, debug: null, walk: null, xr: null,
      film: false, dump: false, frameSet: null, frameRange: null, size: null, ladder: null, redPen: false,
    });
  });

  it("takes the env scene URL when there is no ?scene=", () => {
    expect(parseParams("", "https://media.example/v1/scene.json").sceneUrl).toBe("https://media.example/v1/scene.json");
    expect(parseParams("?scene=/x/scene.json", "https://media.example/v1/scene.json").sceneUrl).toBe("/x/scene.json");
  });

  it("takes ?dpr= as a pixel-ratio override, and ignores nonsense", () => {
    expect(parseParams("?dpr=2").dpr).toBe(2);
    expect(parseParams("?dpr=1.5").dpr).toBe(1.5);
    expect(parseParams("?dpr=0").dpr).toBeNull();
    expect(parseParams("?dpr=x").dpr).toBeNull();
  });

  it("takes ?measured=phone or full, and nothing else", () => {
    expect(parseParams("?measured=phone").measured).toBe("phone");
    expect(parseParams("?measured=full").measured).toBe("full");
    expect(parseParams("?measured=all").measured).toBeNull();
  });

  it("switches ink and coast off only on an explicit off", () => {
    expect(parseParams("?ink=off&coast=off")).toMatchObject({ ink: false, coast: false });
    expect(parseParams("?ink=0&coast=false")).toMatchObject({ ink: false, coast: false });
    expect(parseParams("?ink&coast=on")).toMatchObject({ ink: true, coast: true });
  });

  it("reads numeric overrides and ignores junk", () => {
    expect(parseParams("?lod=750000&gscale=0.5")).toMatchObject({ lod: 750000, gscale: 0.5 });
    expect(parseParams("?lod=lots&gscale=-1")).toMatchObject({ lod: null, gscale: null });
    expect(parseParams("?lod=0")).toMatchObject({ lod: null });
  });

  it("parses a pose and clamps its pitch", () => {
    expect(parseParams("?pose=1,1.6,-0.5,90,120").pose).toEqual({ position: [1, 1.6, -0.5], yawDeg: 90, pitchDeg: 90 });
    expect(parseParams("?pose=1,2,3").pose).toBeNull();
    expect(parseParams("?pose=1,2,x,4,5").pose).toBeNull();
  });

  it("reads ?walk= for the two controllers and ignores anything else", () => {
    expect(parseParams("?walk=touch").walk).toBe("touch");
    expect(parseParams("?walk=desktop").walk).toBe("desktop");
    expect(parseParams("?walk=gamepad").walk).toBeNull();
  });

  it("reads the film parameters: path=film, dump=1, a plain set name and a fixed size", () => {
    expect(parseParams("?path=film&dump=1&set=take-1&w=1920&h=1080")).toMatchObject({ film: true, dump: true, frameSet: "take-1", size: { width: 1920, height: 1080 } });
    expect(parseParams("?path=walk&dump=yes")).toMatchObject({ film: false, dump: false });
    expect(parseParams("?set=../x").frameSet).toBeNull();
    expect(parseParams("?from=96&frames=12").frameRange).toEqual({ from: 96, count: 12 });
    expect(parseParams("?frames=5").frameRange).toEqual({ from: 0, count: 5 });
    expect(parseParams("?from=-1&frames=0").frameRange).toBeNull();
    expect(parseParams("?w=1920").size).toBeNull();
    expect(parseParams("?w=1920.5&h=1080").size).toBeNull();
    expect(parseParams("?w=0&h=1080").size).toBeNull();
    expect(parseParams("?w=99999&h=1080").size).toBeNull();
  });

  it("knows ?xr=mock and nothing else", () => {
    expect(parseParams("?xr=mock").xr).toBe("mock");
    expect(parseParams("?xr=1").xr).toBeNull();
  });

  it("accepts only known debug views, and the flags hud and map only as 1", () => {
    expect(parseParams("?debug=edges").debug).toBe("edges");
    expect(parseParams("?debug=final").debug).toBeNull();
    expect(parseParams("?hud=1&map=1")).toMatchObject({ hud: true, map: true });
    expect(parseParams("?hud=yes&map=true")).toMatchObject({ hud: false, map: false });
  });
});

describe("?scene= in production", () => {
  const prod = (origin = "https://here.example", extra: Partial<SceneEnv> = {}): SceneEnv => ({ production: true, origin, ...extra });
  const scene = (qs: string, env: SceneEnv, envScene?: string) => parseParams(qs, envScene, env).sceneUrl;

  it("takes a same-origin URL, relative or absolute", () => {
    expect(scene("?scene=/other/scene.json", prod())).toBe("/other/scene.json");
    expect(scene("?scene=other/scene.json", prod())).toBe("other/scene.json");
    expect(scene("?scene=https://here.example/x/scene.json", prod())).toBe("https://here.example/x/scene.json");
  });

  it("takes the origin of the build's own scene URL, and only that one", () => {
    const env = "https://media.example/v1/scene.json";
    expect(scene("?scene=https://media.example/v2/scene.json", prod(), env)).toBe("https://media.example/v2/scene.json");
    expect(scene("?scene=https://media.example:8443/scene.json", prod(), env)).toBe(env);
  });

  it("falls back to the build's scene (or the default) for any other origin or scheme", () => {
    const env = "https://media.example/v1/scene.json";
    for (const bad of [
      "https://evil.example/scene.json", "//evil.example/scene.json", "http://here.example/scene.json", "https://here.example.evil.example/scene.json",
      "https://here.example@evil.example/scene.json", "https://here.example:444/scene.json", "javascript:alert(1)", "data:application/json,{}", "blob:https://here.example/x",
    ]) {
      expect(scene(`?scene=${encodeURIComponent(bad)}`, prod(), env), bad).toBe(env);
      expect(scene(`?scene=${encodeURIComponent(bad)}`, prod()), bad).toBe(DEFAULT_SCENE_URL);
    }
  });

  it("keeps any URL open in development", () => {
    expect(scene("?scene=https://evil.example/scene.json", { production: false, origin: "http://localhost:5299" })).toBe("https://evil.example/scene.json");
  });
});


describe("ladder parameters", () => {
  it("opens the ladder on a named rung, any case, or on its first step", () => {
    expect(parseParams("").ladder).toBeNull();
    expect(parseParams("?ladder=R4").ladder).toBe("R4");
    expect(parseParams("?ladder=r4b").ladder).toBe("R4b");
    expect(parseParams("?ladder=1").ladder).toBe("first");
    expect(parseParams("?ladder").ladder).toBe("first");
    expect(parseParams("?ladder=R3").ladder).toBeNull();
  });

  it("turns the red pen on only when asked", () => {
    expect(parseParams("?ladder=R1").redPen).toBe(false);
    expect(parseParams("?ladder=R1&redpen=1").redPen).toBe(true);
  });

  it("finds ladder.json beside the scene, unless the build names it", () => {
    expect(ladderUrlFor("https://media.example/herebeink/v3/scene.json", undefined, "https://page.example"))
      .toBe("https://media.example/herebeink/v3/ladder/ladder.json");
    expect(ladderUrlFor("https://media.example/herebeink/v3/scene.json", "https://media.example/x/ladder.json", "https://page.example"))
      .toBe("https://media.example/x/ladder.json");
    expect(ladderUrlFor(DEFAULT_SCENE_URL, undefined, "http://localhost:5173")).toBe(DEFAULT_LADDER_URL);
  });
});

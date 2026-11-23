import * as THREE from "three";
import { dyno, type SplatMesh } from "@sparkjsdev/spark";
import { HATCH_MEAN_GLSL } from "./strokes.ts";
import { TONE_GLSL } from "./tone.ts";

const { dynoBlock, Dyno, Gsplat, dynoFloat, dynoVec3 } = dyno;

export type DynoFloat = ReturnType<typeof dynoFloat>;

/** Uniforms every shade mesh shares, so one switch flips the whole imagined half at once. */
export interface ShadeUniforms {
  /** 1: the ink pass (imagined splats become paper); 0: the plain filter (desaturate and contrast). */
  ink: DynoFloat;
  paper: ReturnType<typeof dynoVec3>;
  /** Splats with world y above this are dropped: the map view's ceiling cut. */
  clipY: DynoFloat;
  /** The red pen's colour (sRGB); a mesh shows it only where its own red flag is 1. */
  red: ReturnType<typeof dynoVec3>;
}

/** THREE.Color holds linear values; splat rgb and the canvas are sRGB-encoded. */
export function srgbVector(hex: string): THREE.Vector3 {
  const c = new THREE.Color(hex).convertLinearToSRGB();
  return new THREE.Vector3(c.r, c.g, c.b);
}

export function makeShadeUniforms(paperHex: string, ink: boolean, redHex = "#b8322a"): ShadeUniforms {
  return { ink: dynoFloat(ink ? 1 : 0), paper: dynoVec3(srgbVector(paperHex)), clipY: dynoFloat(1e6), red: dynoVec3(srgbVector(redHex)) };
}

/**
 * How strongly the red pen tints the wrong file's paper. Only a wash: the strokes carry the red, and a lit
 * wall with no strokes still needs to read as marked, but the drawing must stay paper.
 */
export const RED_PAPER_WASH = 0.2;
/** Under the plain filter there are no strokes, so the wash is the whole mark. */
export const RED_FILTER_WASH = 0.45;

export const FILTER_CONTRAST = 1.35;

/**
 * The shade pass's per-mesh dyno. Measured: as captured. Imagined: flat paper (the strokes are
 * drawn per pixel in the present pass, so tone comes from line density, never from grey fill), or
 * the plain filter when the ink is switched off. Overlap: half of each. `reveal` is the mesh's own
 * 0 or 1: a file whose detail cut has not arrived yet is held at 0 so it is never drawn as the
 * tree's coarse root.
 */
export function shadeModifier(u: ShadeUniforms, provenance: number, reveal: DynoFloat, red: DynoFloat = dynoFloat(0)) {
  const prov = dynoFloat(provenance);
  return dynoBlock({ gsplat: Gsplat }, { gsplat: Gsplat }, ({ gsplat }) => {
    if (!gsplat) throw new Error("shadeModifier: no gsplat");
    const out = new Dyno({
      inTypes: { gsplat: Gsplat, prov: "float", ink: "float", paper: "vec3", clipY: "float", reveal: "float", red: "float", redInk: "vec3" },
      outTypes: { gsplat: Gsplat },
      inputs: { gsplat, prov, ink: u.ink, paper: u.paper, clipY: u.clipY, reveal, red, redInk: u.red },
      statements: ({ inputs: i, outputs: o }) => [
        `${o.gsplat} = ${i.gsplat};`,
        `${o.gsplat}.rgba.a *= ${i.reveal};`,
        `if (${i.gsplat}.center.y > ${i.clipY}) ${o.gsplat}.rgba.a = 0.0;`,
        `if (${i.prov} > 0.0) {`,
        `  vec3 photo = ${i.gsplat}.rgba.rgb;`,
        `  float y = dot(photo, vec3(0.2126, 0.7152, 0.0722));`,
        `  vec3 filtered = vec3(clamp((y - 0.5) * ${FILTER_CONTRAST.toFixed(2)} + 0.5, 0.0, 1.0));`,
        `  vec3 drawn = ${i.ink} > 0.5 ? mix(${i.paper}, ${i.redInk}, ${RED_PAPER_WASH.toFixed(2)} * ${i.red})`,
        `                         : mix(filtered, ${i.redInk}, ${RED_FILTER_WASH.toFixed(2)} * ${i.red});`,
        `  ${o.gsplat}.rgba.rgb = mix(photo, drawn, ${i.prov});`,
        `}`,
      ],
    });
    return { gsplat: out.outputs.gsplat };
  });
}

export function applyShade(mesh: SplatMesh, u: ShadeUniforms, provenance: number, reveal: DynoFloat, red?: DynoFloat) {
  mesh.worldModifier = shadeModifier(u, provenance, reveal, red);
  mesh.updateGenerator();
}

/**
 * Hatching for the present pass. `world` is the pixel's world position rebuilt from the G-buffer;
 * strokes are planes 3 cm apart in world space, so they stay on the surface as the walker moves,
 * while their width is a pen width in device pixels. Triplanar: on each face the strokes run at
 * 45° (and 135° for the cross-hatch) in that face's own plane.
 */
export const HATCH_GLSL = /* glsl */ `
${TONE_GLSL}
${HATCH_MEAN_GLSL}
uniform float hatchSpacing;
uniform float hatchWidthPx;
uniform float hatchMinPx;
float hatchHash(float n) { return fract(sin(n * 127.1 + 311.7) * 43758.5453); }
// u counts strokes across the surface (one per spacing), v runs along them, both in spacings and
// both fixed to the surface. Each stroke gets its own drift, weight and pen lifts, so the field
// reads as strokes laid by hand rather than a printed screen.
float strokes(float u, float v, float widthPx, float minPx, float seed) {
  float fw = max(fwidth(u), 1e-5);
  float spacingPx = 1.0 / fw;
  float id = floor(u);
  float h = hatchHash(id * 1.618 + seed);
  float drift = 0.11 * sin(v * (0.31 + 0.22 * h) + h * 6.2831);
  float d = abs(fract(u + drift) - 0.5) * spacingPx;
  float w = widthPx * (0.7 + 0.6 * h);
  float segLen = 5.0 + 6.0 * h;
  float seg = floor((v + 9.0 * h) / segLen);
  float lift = step(0.16, hatchHash(id * 7.31 + seg * 3.17 + seed));
  float line = clamp(0.5 * w + 0.5 - d, 0.0, 1.0) * lift;
  // Strokes closer than a few pixels would alias into moire: fade to their mean ink instead.
  return mix(line, hatchMean(spacingPx, widthPx, minPx), smoothstep(minPx, minPx * 0.5, spacingPx));
}
float hatchInk(vec3 world, vec3 n, vec3 lightTravel) {
  vec3 a = abs(n);
  vec2 q = a.y >= a.x && a.y >= a.z ? world.xz : (a.x >= a.z ? world.zy : world.xy);
  float u = (q.x + q.y) / hatchSpacing, v = (q.x - q.y) / hatchSpacing;
  // Both families every pixel: fwidth is undefined inside a branch that neighbours may not take.
  float h = strokes(u, v, hatchWidthPx, hatchMinPx, 0.0);
  float c = strokes(v, u, hatchWidthPx, hatchMinPx, 17.0);
  int level = toneLevel(n, lightTravel);
  return level == 0 ? 0.0 : (level == 1 ? h : max(h, c));
}
`;

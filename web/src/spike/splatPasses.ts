import * as THREE from "three";
import { dyno, SparkRenderer, SplatMesh, type GsplatModifier } from "@sparkjsdev/spark";

const { dynoBlock, Dyno, Gsplat, splitGsplat, gsplatNormal, dynoFloat, dynoBool } = dyno;

export const LAYER_SHADE = 0;
export const LAYER_GBUF = 1;
export const LAYER_FLAG = 2;

// Spark's own fragment shader converts sRGB to linear whenever it draws into a render target
// (encodeLinear), which would bend the depth and normal values; this copy keeps the kernel and
// the falloff identical so coverage matches the shade pass, and writes the values untouched.
export const DATA_FRAGMENT = /* glsl */ `
precision highp float;
precision highp int;

uniform float maxStdDev;
uniform float minAlpha;
uniform float falloff;

out vec4 fragColor;

in vec4 vRgba;
in vec2 vSplatUv;
flat in float adjustedStdDev;

void main() {
  vec4 rgba = vRgba;
  float z2 = dot(vSplatUv, vSplatUv);
  if (z2 > adjustedStdDev * adjustedStdDev) discard;
  if (rgba.a <= 1.0) {
    rgba.a = mix(rgba.a, rgba.a * exp(-0.5 * z2), falloff);
  } else {
    float a = exp((rgba.a * rgba.a - 1.0) / 2.718281828459045);
    float alpha = 1.0 - pow(1.0 - exp(-0.5 * z2), a);
    rgba.a = mix(1.0, alpha, falloff);
  }
  if (rgba.a < minAlpha) discard;
  fragColor = vec4(rgba.rgb * rgba.a, rgba.a);
}
`;

export interface SplitUniforms {
  // The spike has one file, so a world-space plane x = planeX splits it into a measured and an imagined half.
  planeX: ReturnType<typeof dynoFloat>;
  split: ReturnType<typeof dynoBool>;
  provenance: ReturnType<typeof dynoFloat>;
}

export function makeSplitUniforms(provenance: number, split: boolean): SplitUniforms {
  return { planeX: dynoFloat(0), split: dynoBool(split), provenance: dynoFloat(provenance) };
}

const FLAG_GLSL = (worldCenter: string, u: { planeX?: string; split?: string; provenance?: string }) =>
  `(${u.split} ? (${worldCenter}.x >= ${u.planeX} ? 1.0 : 0.0) : ${u.provenance})`;

/**
 * G-buffer modifier: rgb = (depth01, 0.5 + 0.5 n.x, 0.5 + 0.5 n.y) in view space.
 * The view transform reaches the dyno through the mesh's own worldToView SplatTransformer,
 * whose uniforms Spark refreshes from the camera on every generate.
 */
export function gbufferModifier(mesh: SplatMesh, near: ReturnType<typeof dynoFloat>, far: ReturnType<typeof dynoFloat>) {
  mesh.enableWorldToView = true;
  return dynoBlock({ gsplat: Gsplat }, { gsplat: Gsplat }, ({ gsplat }) => {
    if (!gsplat) throw new Error("gbufferModifier: no gsplat");
    const { center } = splitGsplat(gsplat).outputs;
    const viewCenter = mesh.context.worldToView.apply(center);
    const viewNormal = mesh.context.worldToView.applyDir(gsplatNormal(gsplat));
    const out = new Dyno({
      inTypes: { gsplat: Gsplat, viewCenter: "vec3", viewNormal: "vec3", near: "float", far: "float" },
      outTypes: { gsplat: Gsplat },
      inputs: { gsplat, viewCenter, viewNormal, near, far },
      statements: ({ inputs: i, outputs: o }) => [
        `${o.gsplat} = ${i.gsplat};`,
        `{`,
        `  vec3 n = normalize(${i.viewNormal});`,
        `  if (dot(n, ${i.viewCenter}) > 0.0) n = -n;`,
        `  float d01 = clamp((-${i.viewCenter}.z - ${i.near}) / (${i.far} - ${i.near}), 0.0, 1.0);`,
        `  ${o.gsplat}.rgba.rgb = vec3(d01, 0.5 + 0.5 * n.x, 0.5 + 0.5 * n.y);`,
        `}`,
      ],
    });
    return { gsplat: out.outputs.gsplat };
  });
}

/** Flag modifier: rgb = provenance flag (0 measured, 0.5 overlap, 1 imagined). */
export function flagModifier(u: SplitUniforms) {
  return dynoBlock({ gsplat: Gsplat }, { gsplat: Gsplat }, ({ gsplat }) => {
    if (!gsplat) throw new Error("flagModifier: no gsplat");
    const out = new Dyno({
      inTypes: { gsplat: Gsplat, planeX: "float", split: "bool", provenance: "float" },
      outTypes: { gsplat: Gsplat },
      inputs: { gsplat, planeX: u.planeX, split: u.split, provenance: u.provenance },
      statements: ({ inputs: i, outputs: o }) => [
        `${o.gsplat} = ${i.gsplat};`,
        `${o.gsplat}.rgba.rgb = vec3(${FLAG_GLSL(`${i.gsplat}.center`, i)});`,
      ],
    });
    return { gsplat: out.outputs.gsplat };
  });
}

/**
 * First cut of the paper dyno: three paper tones from a fixed light, 45° world-space hatching,
 * cross-hatch in the darkest tone. Applied only where the flag says imagined.
 * Hatching is evaluated at the splat centre, so its lines are as coarse as the splats.
 */
export function paperModifier(u: SplitUniforms, paper: THREE.Color, ink: THREE.Color) {
  const paperU = dyno.dynoVec3(new THREE.Vector3(paper.r, paper.g, paper.b));
  const inkU = dyno.dynoVec3(new THREE.Vector3(ink.r, ink.g, ink.b));
  return {
    paperU,
    inkU,
    modifier: dynoBlock({ gsplat: Gsplat }, { gsplat: Gsplat }, ({ gsplat }) => {
      if (!gsplat) throw new Error("paperModifier: no gsplat");
      const normal = gsplatNormal(gsplat);
      const out = new Dyno({
        inTypes: { gsplat: Gsplat, normal: "vec3", planeX: "float", split: "bool", provenance: "float", paper: "vec3", ink: "vec3" },
        outTypes: { gsplat: Gsplat },
        inputs: { gsplat, normal, planeX: u.planeX, split: u.split, provenance: u.provenance, paper: paperU, ink: inkU },
        statements: ({ inputs: i, outputs: o }) => [
          `${o.gsplat} = ${i.gsplat};`,
          `{`,
          `  float flag = ${FLAG_GLSL(`${i.gsplat}.center`, i)};`,
          `  if (flag > 0.5) {`,
          `    vec3 p = ${i.gsplat}.center;`,
          `    vec3 L = normalize(vec3(-0.4, 0.8, 0.45));`,
          // Splat normals have no inside or outside, so light either face.
          `    float lit = abs(dot(normalize(${i.normal}), L));`,
          `    float hatch = step(0.5, fract((p.x + p.z) / 0.03));`,
          `    float cross = step(0.5, fract((p.x - p.z) / 0.03));`,
          `    float tone = lit > 0.66 ? 1.0 : (lit > 0.33 ? mix(0.55, 1.0, hatch) : mix(0.3, 1.0, hatch * cross));`,
          `    ${o.gsplat}.rgba.rgb = mix(${i.ink}, ${i.paper}, tone);`,
          `  }`,
          `}`,
        ],
      });
      return { gsplat: out.outputs.gsplat };
    }),
  };
}

export interface DataPass {
  spark: SparkRenderer;
  mesh: SplatMesh;
  target: THREE.WebGLRenderTarget;
}

/**
 * An off-screen Spark pass over its own SplatMesh. The mesh shares the loaded PackedSplats with
 * the shade mesh, so the file is in memory once; each pass keeps its own accumulator and sort.
 * Layers keep each SparkRenderer's generate step to its own mesh.
 */
export function makeDataPass(opts: {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  source: SplatMesh;
  layer: number;
  width: number;
  height: number;
  maxStdDev: number;
  halfFloat: boolean;
  minSortIntervalMs: number;
  modifier: (mesh: SplatMesh) => GsplatModifier;
}): DataPass {
  const spark = new SparkRenderer({
    renderer: opts.renderer,
    maxStdDev: opts.maxStdDev,
    minSortIntervalMs: opts.minSortIntervalMs,
    // Ext accumulators keep per-splat rgb as fp16 rather than 8-bit, so depth fits in one channel.
    accumExtSplats: opts.halfFloat,
    fragmentShader: DATA_FRAGMENT,
    target: {
      width: opts.width,
      height: opts.height,
      type: opts.halfFloat ? THREE.HalfFloatType : THREE.UnsignedByteType,
      colorSpace: THREE.NoColorSpace,
      minFilter: THREE.NearestFilter,
      magFilter: THREE.NearestFilter,
    },
  });
  spark.layers.set(opts.layer);
  opts.scene.add(spark);

  const mesh = new SplatMesh({ packedSplats: opts.source.packedSplats });
  mesh.position.copy(opts.source.position);
  mesh.quaternion.copy(opts.source.quaternion);
  mesh.scale.copy(opts.source.scale);
  mesh.layers.set(opts.layer);
  mesh.worldModifier = opts.modifier(mesh);
  mesh.updateGenerator();
  opts.scene.add(mesh);

  if (!spark.target) throw new Error("SparkRenderer did not create its target");
  return { spark, mesh, target: spark.target };
}

/** Draws one data pass into its target, cleared to transparent black so alpha is coverage. */
export function renderDataPass(pass: DataPass, renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.Camera, layer: number) {
  const clear = renderer.getClearColor(new THREE.Color());
  const clearAlpha = renderer.getClearAlpha();
  renderer.setClearColor(0x000000, 0);
  camera.layers.set(layer);
  try {
    pass.spark.renderTarget({ scene, camera });
  } finally {
    camera.layers.set(LAYER_SHADE);
    renderer.setClearColor(clear, clearAlpha);
  }
}

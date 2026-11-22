import * as THREE from "three";
import { dyno, SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import { dataPixelRadii } from "../device.ts";
import { LAYER } from "./layers.ts";
import type { DynoFloat } from "./paper.ts";

const { dynoBlock, Dyno, Gsplat, splitGsplat, gsplatNormal, dynoFloat } = dyno;

// Spark's own fragment shader converts sRGB to linear whenever it draws into a render target,
// which would bend depth and normal values. This copy keeps its kernel and falloff, so coverage
// matches the shade pass, and writes the values untouched (spike S1).
const DATA_FRAGMENT = /* glsl */ `
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

/** rgb = (depth01, 0.5 + 0.5 n.x, 0.5 + 0.5 n.y) in view space, n turned to face the camera. */
function gbufferModifier(mesh: SplatMesh, near: DynoFloat, far: DynoFloat, reveal: DynoFloat) {
  mesh.enableWorldToView = true;
  return dynoBlock({ gsplat: Gsplat }, { gsplat: Gsplat }, ({ gsplat }) => {
    if (!gsplat) throw new Error("gbufferModifier: no gsplat");
    const { center } = splitGsplat(gsplat).outputs;
    const viewCenter = mesh.context.worldToView.apply(center);
    const viewNormal = mesh.context.worldToView.applyDir(gsplatNormal(gsplat));
    const out = new Dyno({
      inTypes: { gsplat: Gsplat, viewCenter: "vec3", viewNormal: "vec3", near: "float", far: "float", reveal: "float" },
      outTypes: { gsplat: Gsplat },
      inputs: { gsplat, viewCenter, viewNormal, near, far, reveal },
      statements: ({ inputs: i, outputs: o }) => [
        `${o.gsplat} = ${i.gsplat};`,
        `${o.gsplat}.rgba.a *= ${i.reveal};`,
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

/** rgb = the file's provenance: 0 measured, 0.5 overlap, 1 imagined. */
function flagModifier(provenance: DynoFloat, reveal: DynoFloat) {
  return dynoBlock({ gsplat: Gsplat }, { gsplat: Gsplat }, ({ gsplat }) => {
    if (!gsplat) throw new Error("flagModifier: no gsplat");
    const out = new Dyno({
      inTypes: { gsplat: Gsplat, provenance: "float", reveal: "float" },
      outTypes: { gsplat: Gsplat },
      inputs: { gsplat, provenance, reveal },
      statements: ({ inputs: i, outputs: o }) => [
        `${o.gsplat} = ${i.gsplat};`,
        `${o.gsplat}.rgba.a *= ${i.reveal};`,
        `${o.gsplat}.rgba.rgb = vec3(${i.provenance});`,
      ],
    });
    return { gsplat: out.outputs.gsplat };
  });
}

export interface Twin {
  gbuf: SplatMesh;
  flag: SplatMesh;
}

export interface DataPassOptions {
  width: number;
  height: number;
  near: number;
  far: number;
  maxStdDev: number;
  lodSplatCount: number;
  /** Data pixels per canvas pixel; also scales the LoD pixel limit so the cuts match the canvas's. */
  dataScale: number;
}

/**
 * The G-buffer and flag passes: two off-screen SparkRenderers, each drawing its own twin of every
 * shade mesh. Twins share the source's PackedSplats, so each file sits in memory once.
 */
export class DataPasses {
  readonly gbufSpark: SparkRenderer;
  readonly flagSpark: SparkRenderer;
  readonly gbufTarget: THREE.WebGLRenderTarget;
  readonly flagTarget: THREE.WebGLRenderTarget;
  private readonly near: DynoFloat;
  private readonly far: DynoFloat;
  private readonly twins = new Set<Twin>();
  private shown = true;

  constructor(private readonly renderer: THREE.WebGLRenderer, private readonly scene: THREE.Scene, o: DataPassOptions) {
    this.near = dynoFloat(o.near);
    this.far = dynoFloat(o.far);
    const radii = dataPixelRadii(o.dataScale);
    const make = (layer: number, halfFloat: boolean) => {
      const spark = new SparkRenderer({
        renderer,
        maxStdDev: o.maxStdDev,
        // Spark's splat size limits are in its own target's pixels, so they are scaled with the
        // target or a splat would be cut at a different size on screen than in the picture.
        minPixelRadius: radii.min,
        maxPixelRadius: radii.max,
        // Ext accumulators keep per-splat rgb as fp16 rather than 8-bit, so depth fits one channel.
        accumExtSplats: halfFloat,
        fragmentShader: DATA_FRAGMENT,
        lodSplatCount: o.lodSplatCount,
        // Spark sizes the LoD pixel limit by its own render height; a smaller target would pick a
        // coarser cut than the canvas does unless the limit is scaled back.
        lodRenderScale: o.dataScale,
        target: {
          width: o.width,
          height: o.height,
          type: halfFloat ? THREE.HalfFloatType : THREE.UnsignedByteType,
          colorSpace: THREE.NoColorSpace,
          // Linear so the full-resolution present pass can sample depth between data pixels;
          // the edge passes use texelFetch and are unaffected.
          minFilter: THREE.LinearFilter,
          magFilter: THREE.LinearFilter,
          generateMipmaps: false,
          // Splats never write depth, so a depth buffer here would only cost memory.
          depthBuffer: false,
        },
      });
      spark.layers.set(layer);
      this.scene.add(spark);
      if (!spark.target) throw new Error("SparkRenderer did not create its target");
      return spark;
    };
    this.gbufSpark = make(LAYER.gbuf, true);
    this.flagSpark = make(LAYER.flag, false);
    this.gbufTarget = this.gbufSpark.target!;
    this.flagTarget = this.flagSpark.target!;
  }

  /** `reveal` is the mesh's own 0 or 1, shared with its shade dyno so all three passes hold and show it together. */
  addTwin(source: SplatMesh, provenance: number, reveal: DynoFloat): Twin {
    const twin = (layer: number, modifier: (m: SplatMesh) => ReturnType<typeof flagModifier>) => {
      const m = new SplatMesh({ packedSplats: source.packedSplats });
      m.matrixAutoUpdate = source.matrixAutoUpdate;
      m.position.copy(source.position);
      m.quaternion.copy(source.quaternion);
      m.scale.copy(source.scale);
      m.layers.set(layer);
      m.worldModifier = modifier(m);
      m.updateGenerator();
      m.visible = this.shown;
      this.scene.add(m);
      return m;
    };
    const t: Twin = {
      gbuf: twin(LAYER.gbuf, (m) => gbufferModifier(m, this.near, this.far, reveal)),
      flag: twin(LAYER.flag, () => flagModifier(dynoFloat(provenance), reveal)),
    };
    this.twins.add(t);
    return t;
  }

  /**
   * Off for a headset session: three's XR cameras draw layers 1 and 2 as well, and Spark would
   * otherwise generate the twins into the shade pass. Invisible meshes are skipped by Spark.
   */
  setVisible(v: boolean) {
    this.shown = v;
    this.gbufSpark.visible = v;
    this.flagSpark.visible = v;
    for (const t of this.twins) t.gbuf.visible = t.flag.visible = v;
  }

  removeTwin(t: Twin) {
    // The PackedSplats belong to the source mesh, which disposes them; a twin owns nothing else.
    this.scene.remove(t.gbuf, t.flag);
    this.twins.delete(t);
  }

  setSize(w: number, h: number) {
    // SparkRenderer has no resize for its target; the WebGLRenderTarget resizes cleanly.
    this.gbufTarget.setSize(w, h);
    this.flagTarget.setSize(w, h);
  }

  setLod(lodSplatCount: number, dataScale: number) {
    const radii = dataPixelRadii(dataScale);
    for (const s of [this.gbufSpark, this.flagSpark]) {
      s.lodSplatCount = lodSplatCount;
      s.lodRenderScale = dataScale;
      s.minPixelRadius = radii.min;
      s.maxPixelRadius = radii.max;
    }
  }

  get activeSplats() {
    return { gbuf: this.gbufSpark.activeSplats, flag: this.flagSpark.activeSplats };
  }

  /** Both passes, each into its own target cleared to transparent black so alpha is coverage. */
  render(camera: THREE.Camera, restoreMask: number) {
    const clear = this.renderer.getClearColor(new THREE.Color());
    const clearAlpha = this.renderer.getClearAlpha();
    this.renderer.setClearColor(0x000000, 0);
    try {
      camera.layers.set(LAYER.gbuf);
      this.gbufSpark.renderTarget({ scene: this.scene, camera });
      camera.layers.set(LAYER.flag);
      this.flagSpark.renderTarget({ scene: this.scene, camera });
    } finally {
      camera.layers.mask = restoreMask;
      this.renderer.setClearColor(clear, clearAlpha);
    }
  }
}

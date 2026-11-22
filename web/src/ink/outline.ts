import * as THREE from "three";
import type { DebugView } from "../params.ts";
import { HATCH_GLSL } from "./paper.ts";
import { PEN } from "./pen.ts";
import { ROUGHNESS_GLSL, SURFACE_GLSL } from "./surface.ts";

const VERT = /* glsl */ `
void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

// Shared decoding of the G-buffer. Values are premultiplied by coverage, so divide by alpha;
// below half coverage a pixel counts as background.
const DECODE = /* glsl */ `
precision highp float;
precision highp int;
uniform highp sampler2D gTex;
uniform highp sampler2D fTex;
uniform float near;
uniform float far;
ivec2 clampPx(ivec2 q) { return clamp(q, ivec2(0), textureSize(gTex, 0) - 1); }
float viewZ(vec4 g) { return near + (g.r / max(g.a, 1e-4)) * (far - near); }
vec3 decodeN(vec4 g) {
  vec2 xy = (g.gb / max(g.a, 1e-4)) * 2.0 - 1.0;
  return vec3(xy, sqrt(max(0.0, 1.0 - dot(xy, xy))));
}
float flagOf(vec4 f) { return f.a > 0.01 ? f.r / f.a : 0.0; }
float flagAt(ivec2 q) { return flagOf(texelFetch(fTex, clampPx(q), 0)); }
float coverAt(ivec2 q) { return texelFetch(gTex, clampPx(q), 0).a; }
// Ink belongs to the imagined half only; the overlap ring (0.5) gets none.
float imaginedWeight(float flag) { return smoothstep(${PEN.imaginedFlagFrom.toFixed(2)}, ${PEN.imaginedFlagTo.toFixed(2)}, flag); }
`;

// Coverage, flag and depth after a small blur: r coverage, g flag premultiplied by its coverage,
// b that coverage, a depth01 premultiplied by coverage. Contours and weights read these, so
// single-splat specks and pinholes never get a line, and hatching rides a smooth surface.
const CLEAN = /* glsl */ `
uniform highp sampler2D cTex;
float cleanCover(ivec2 q) { return texelFetch(cTex, clamp(q, ivec2(0), textureSize(cTex, 0) - 1), 0).r; }
float cleanFlagOf(vec4 c) { return c.b > 0.01 ? c.g / c.b : 0.0; }
float cleanFlag(ivec2 q) { return cleanFlagOf(texelFetch(cTex, clamp(q, ivec2(0), textureSize(cTex, 0) - 1), 0)); }
float cleanViewZ(vec4 c) { return near + (c.a / max(c.r, 1e-4)) * (far - near); }
`;

// Separable Gaussian over (coverage, flag): the first pass reads the G-buffer and flag targets,
// the second the first pass's output.
const BLUR = /* glsl */ `
${DECODE}
uniform highp sampler2D srcTex;
uniform bool fromData;
uniform vec2 dir;
uniform float sigma;
out vec4 outColor;
vec4 sampleAt(ivec2 q) {
  if (fromData) {
    vec4 f = texelFetch(fTex, clampPx(q), 0);
    vec4 g = texelFetch(gTex, clampPx(q), 0);
    return vec4(g.a, f.r, f.a, g.r);
  }
  return texelFetch(srcTex, clampPx(q), 0);
}
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  if (sigma <= 0.0) { outColor = sampleAt(p); return; }
  int R = int(min(8.0, ceil(2.5 * sigma)));
  vec4 acc = vec4(0.0);
  float wsum = 0.0;
  for (int i = -R; i <= R; i++) {
    float w = exp(-0.5 * float(i * i) / (sigma * sigma));
    acc += w * sampleAt(p + ivec2(dir) * i);
    wsum += w;
  }
  outColor = acc / wsum;
}
`;

// Crease strength from Sobel on view depth and on the normal; 1.0 means "at threshold".
// Background neighbours borrow the centre value so a silhouette never reads as a depth crease:
// silhouettes come from the coverage contour instead. Alpha carries the pixel's roughness, which
// the composite averages into the surface weight.
const STRENGTH = /* glsl */ `
${DECODE}
${CLEAN}
${ROUGHNESS_GLSL}
uniform float depthStep;
uniform float coastAt;
uniform float normalCos;
out vec4 outColor;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  vec4 c = texelFetch(gTex, p, 0);
  if (c.a < 0.5) { outColor = vec4(0.0); return; }
  float zc = viewZ(c);
  vec3 nc = decodeN(c);
  vec2 gz = vec2(0.0), gn = vec2(0.0);
  for (int j = -1; j <= 1; j++) {
    for (int i = -1; i <= 1; i++) {
      vec4 g = texelFetch(gTex, clampPx(p + ivec2(i, j)), 0);
      if (g.a < 0.5) g = c;
      float wx = float(i) * (j == 0 ? 2.0 : 1.0);
      float wy = float(j) * (i == 0 ? 2.0 : 1.0);
      gz += vec2(wx, wy) * viewZ(g);
      gn += vec2(wx, wy) * (1.0 - dot(decodeN(g), nc));
    }
  }
  gz /= 8.0;
  gn /= 8.0;
  // A hard step of size s between two pixels gives a Sobel/8 response of s/2 on each side.
  float sd = length(gz) / (0.5 * depthStep * zc);
  float sn = length(gn) / (0.5 * (1.0 - normalCos));
  vec2 dir = sd >= sn ? gz : gn;
  // Hatching and creases fall only on imagined pixels, so the measured room skips the roughness.
  float rough = cleanFlag(p) > coastAt ? roughness(p) : 0.0;
  outColor = vec4(max(sd, sn), length(dir) > 0.0 ? normalize(dir) : vec2(1.0, 0.0), rough);
}
`;

// One-pixel-thin crease lines by non-maximum suppression along the gradient, each carrying the
// sub-pixel offset of the strength peak (a parabola through the three samples) so the line sits
// between pixel centres, not on them. r: line, g and b: offset x and y, a: the cleaned flag.
// Silhouettes and the coastline do not pass through here: the composite places them from the
// cleaned coverage and flag directly.
const THIN = /* glsl */ `
${DECODE}
${CLEAN}
uniform highp sampler2D sTex;
out vec4 outColor;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  if (cleanCover(p) < 0.5) { outColor = vec4(0.0); return; }
  vec4 s = texelFetch(sTex, p, 0);
  ivec2 d = ivec2(round(s.gb * 1.41421356));
  float lo = texelFetch(sTex, clampPx(p - d), 0).r;
  float hi = texelFetch(sTex, clampPx(p + d), 0).r;
  bool crease = s.r >= 1.0 && s.r > lo && s.r >= hi;
  float bend = lo - 2.0 * s.r + hi;
  float t = bend < 0.0 ? clamp(0.5 * (lo - hi) / bend, -0.5, 0.5) : 0.0;
  vec2 off = vec2(d) * t;
  outColor = vec4(crease ? 1.0 : 0.0, 0.5 + off, cleanFlag(p));
}
`;

// Exact two-pass Euclidean distance within a small window: the row pass keeps, per pixel, the
// signed horizontal offset to the nearest crease point in its row, that point's vertical offset
// and flag. It also takes the row minimum of the raw flag over covered pixels, the first half of
// the erosion the hatching and grain are weighted by.
const SPREAD = /* glsl */ `
${DECODE}
uniform highp sampler2D tTex;
uniform int R;
out vec4 outColor;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  float dx = 1e4, oy = 0.0, fe = 0.0;
  for (int i = -R; i <= R; i++) {
    vec4 t = texelFetch(tTex, clampPx(p + ivec2(i, 0)), 0);
    if (t.r < 0.5) continue;
    float x = float(i) + (t.g - 0.5);
    if (abs(x) < abs(dx) || (abs(x) == abs(dx) && t.a > fe)) { dx = x; oy = t.b - 0.5; fe = t.a; }
  }
  float lowest = 1.0;
  for (int i = -1; i <= 1; i++) {
    vec4 f = texelFetch(fTex, clampPx(p + ivec2(i, 0)), 0);
    if (f.a > 0.1) lowest = min(lowest, f.r / f.a);
  }
  outColor = vec4(dx, oy, fe, lowest);
}
`;

// Where a smooth field (the cleaned coverage, or the cleaned flag) crosses a level, to a fraction
// of a pixel. The field is a blurred step, so its slope is largest at the crossing and falls away
// in the tails: one Newton step from a pixel in a tail overshoots, and a second from where it
// lands settles. Returns the signed distance to the crossing (positive where the field is above
// the level), the crossing itself and the unit normal pointing uphill. A pixel whose first step is
// longer than the reach is too far from any crossing to matter, and a flat field gives no step at all
// (ok is false); the first step of a pixel in a tail runs up to twice the true distance.
const CONTOUR = /* glsl */ `
vec2 texel;
float field(vec2 at, int which) {
  vec4 c = textureLod(cTex, at * texel, 0.0);
  return which == 0 ? c.r : (c.b > 0.01 ? c.g / c.b : 0.0);
}
vec2 fieldGrad(vec2 at, int which) {
  return 0.5 * vec2(field(at + vec2(1.0, 0.0), which) - field(at - vec2(1.0, 0.0), which),
                    field(at + vec2(0.0, 1.0), which) - field(at - vec2(0.0, 1.0), which));
}
struct Hit { bool ok; float d; vec2 at; vec2 n; };
Hit contour(vec2 at, float level, int which, float reach) {
  Hit h = Hit(false, 0.0, at, vec2(0.0));
  vec2 g = fieldGrad(at, which);
  float gl = length(g);
  if (gl < 1e-4) return h;
  float d1 = (field(at, which) - level) / gl;
  if (abs(d1) > reach) return h;
  vec2 at1 = at - g / gl * d1;
  vec2 g1 = fieldGrad(at1, which);
  float gl1 = length(g1);
  if (gl1 < 1e-4) return h;
  vec2 n = g1 / gl1;
  float d2 = (field(at1, which) - level) / gl1;
  h.ok = true;
  h.d = d1 + d2;
  h.at = at1 - n * d2;
  h.n = n;
  return h;
}
`;

// The column pass finishes the crease distance: a point at distance d from the nearest crease
// point gets clamp((W + 1) / 2 - d, 0, 1), so the ink summed across a line is W device pixels
// whatever the splats underneath look like. Silhouettes and the coastline use the same ramp on
// the signed distance to the cleaned coverage = 0.5 and flag = coastAt contours; their line sits
// half a pixel on the covered, respectively more imagined, side of the contour, so the ink stays
// on the object's own side of its edge. Writes outline alpha to r, coastline alpha to g, and to b the raw
// flag eroded by one data pixel (the minimum over the 3 x 3 neighbourhood of covered pixels): a
// pixel next to anything measured is never imagined enough for hatching, and bilinear stretching
// to the canvas cannot pull a neighbour's value into a measured pixel. Creases are drawn only
// where the splats under them are one surface; that weight goes to alpha for the hatching.
const COMPOSITE = /* glsl */ `
${DECODE}
${CLEAN}
${CONTOUR}
${SURFACE_GLSL}
uniform highp sampler2D spreadTex;
uniform float edgeWidth;
uniform float coastWidth;
uniform float outlineOn;
uniform float coastAt;
out vec4 outColor;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  texel = 1.0 / vec2(textureSize(cTex, 0));
  vec2 at = vec2(p) + 0.5;
  int R = int(ceil((edgeWidth + 1.0) * 0.5 + 0.5));
  float he = (edgeWidth + 1.0) * 0.5, hc = (coastWidth + 1.0) * 0.5;
  float ae = 0.0, ac = 0.0;
  float surface = cleanFlag(p) > coastAt ? surfaceWeight(p) : 1.0;
  for (int j = -R; j <= R; j++) {
    vec4 s = texelFetch(spreadTex, clampPx(p + ivec2(0, j)), 0);
    float dy = float(j) + s.g;
    ae = max(ae, clamp(he - sqrt(dy * dy + s.r * s.r), 0.0, 1.0) * imaginedWeight(s.b) * surface);
  }
  float c0 = cleanCover(p);
  if (c0 > 0.03 && c0 < 0.97) {
    Hit h = contour(at, 0.5, 0, 2.0 * (he + 1.0));
    if (h.ok) {
      float a = clamp(he - abs(h.d - 0.5), 0.0, 1.0);
      if (a > 0.0) ae = max(ae, a * imaginedWeight(field(h.at + 0.5 * h.n, 1)));
    }
  }
  float f0 = cleanFlag(p);
  if (coastWidth > 0.0 && f0 > 0.02 && f0 < 0.48) {
    Hit h = contour(at, coastAt, 1, 2.0 * (hc + 1.0));
    if (h.ok) ac = clamp(hc - abs(h.d - 0.5), 0.0, 1.0) * clamp((field(h.at, 0) - 0.4) / 0.2, 0.0, 1.0);
  }
  float eroded = 1.0;
  for (int j = -1; j <= 1; j++) eroded = min(eroded, texelFetch(spreadTex, clampPx(p + ivec2(0, j)), 0).a);
  outColor = vec4(ae * outlineOn, ac, eroded, surface);
}
`;

// Full canvas resolution, over the shade pass: the outline ink stretched up from data resolution,
// the hatching per pixel in world space, and the paper grain. Debug views replace the frame.
// Outlines are spread a pixel either side of their line at data resolution, so the weight by the
// flag under the canvas pixel itself is applied here, where the pixel is known; pixels with no
// coverage (a silhouette against empty paper) take the line as it is.
const PRESENT = /* glsl */ `
${DECODE}
${CLEAN}
${HATCH_GLSL}
uniform highp sampler2D inkTex;
uniform vec2 canvasSize;
uniform mat4 projInv;
uniform mat4 camWorld;
uniform vec3 lightTravel;
uniform vec3 ink;
uniform vec3 paper;
uniform float hatchOn;
uniform float grain;
uniform int mode;
out vec4 outColor;
uniform float normalSpan;
vec3 worldAt(vec2 at) {
  vec4 c = texture(cTex, at);
  vec4 v = projInv * vec4(at * 2.0 - 1.0, 1.0, 1.0);
  vec3 ray = v.xyz / v.w;
  return (camWorld * vec4(ray * (cleanViewZ(c) / -ray.z), 1.0)).xyz;
}
float hash(vec2 p) {
  p = fract(p * vec2(443.897, 441.423));
  p += dot(p, p.yx + 19.19);
  return fract((p.x + p.y) * p.x);
}
void main() {
  vec2 uv = gl_FragCoord.xy / canvasSize;
  vec4 lines = texture(inkTex, uv);
  vec4 g = texture(gTex, uv);
  float cover = smoothstep(0.35, 0.65, g.a);
  float flag = cleanFlagOf(texture(cTex, uv));
  if (mode == 4) { outColor = vec4(mix(paper, ink, max(lines.r, lines.g)), 1.0); return; }
  if (mode == 1) { outColor = vec4(mix(paper, vec3(clamp(viewZ(g) / 8.0, 0.0, 1.0)), cover), 1.0); return; }
  if (mode == 2) { outColor = vec4(mix(paper, decodeN(g) * 0.5 + 0.5, cover), 1.0); return; }
  if (mode == 3) { outColor = vec4(mix(paper, mix(vec3(0.16, 0.42, 0.72), vec3(0.93, 0.55, 0.15), flag), cover), 1.0); return; }

  float imagined = imaginedWeight(lines.b);
  vec4 under = texture(fTex, uv);
  float outline = lines.r * mix(1.0, imaginedWeight(flagOf(under)), cover);
  float hatch = 0.0;
  // World position from the cleaned depth. The normal is the splats' own, averaged over a few
  // data pixels: normals rebuilt from depth are noisier on splats than this.
  vec3 world = worldAt(uv);
  vec2 k = normalSpan / canvasSize;
  vec4 gs = g + texture(gTex, uv + vec2(k.x, 0.0)) + texture(gTex, uv - vec2(k.x, 0.0))
              + texture(gTex, uv + vec2(0.0, k.y)) + texture(gTex, uv - vec2(0.0, k.y));
  vec3 worldN = normalize(mat3(camWorld) * decodeN(gs));
  float ht = hatchInk(world, worldN, lightTravel);
  if (hatchOn > 0.5) hatch = ht * imagined * cover * lines.a;
  float grainA = grain * hash(floor(gl_FragCoord.xy)) * imagined * cover * hatchOn;
  float a = 1.0 - (1.0 - outline) * (1.0 - lines.g) * (1.0 - hatch) * (1.0 - grainA);
  outColor = vec4(ink, a);
}
`;

const MODES: Record<DebugView | "final", number> = { final: 0, depth: 1, normal: 2, flag: 3, edges: 4, shade: 0 };

function material(fragmentShader: string, uniforms: Record<string, THREE.IUniform>, blend: boolean) {
  return new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: VERT,
    fragmentShader,
    uniforms,
    depthTest: false,
    depthWrite: false,
    transparent: blend,
    blending: blend ? THREE.NormalBlending : THREE.NoBlending,
  });
}

function dataTarget(w: number, h: number, type: THREE.TextureDataType, linear = false) {
  return new THREE.WebGLRenderTarget(w, h, {
    type,
    colorSpace: THREE.NoColorSpace,
    minFilter: linear ? THREE.LinearFilter : THREE.NearestFilter,
    magFilter: linear ? THREE.LinearFilter : THREE.NearestFilter,
    generateMipmaps: false,
    depthBuffer: false,
  });
}

export interface InkConfig {
  /** Data pixels per canvas pixel. */
  dataScale: number;
  dpr: number;
  ink: string;
  paper: string;
  lightTravel: readonly [number, number, number];
  /** The ink pass on the imagined half: outlines, hatching, grain. Off is the plain filter. */
  inkOn: boolean;
  coast: boolean;
  debug: DebugView | null;
}

/** The screen-space half of the ink: edges at data resolution, then one full-resolution present. */
export class InkPass {
  readonly strengthTarget: THREE.WebGLRenderTarget;
  readonly thinTarget: THREE.WebGLRenderTarget;
  readonly spreadTarget: THREE.WebGLRenderTarget;
  readonly inkTarget: THREE.WebGLRenderTarget;
  readonly blurA: THREE.WebGLRenderTarget;
  readonly blurB: THREE.WebGLRenderTarget;
  private readonly blurH: THREE.ShaderMaterial;
  private readonly blurV: THREE.ShaderMaterial;
  private readonly quad: THREE.Mesh;
  private readonly cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private readonly scene = new THREE.Scene();
  private readonly strength: THREE.ShaderMaterial;
  private readonly thin: THREE.ShaderMaterial;
  private readonly spread: THREE.ShaderMaterial;
  private readonly composite: THREE.ShaderMaterial;
  private readonly present_: THREE.ShaderMaterial;
  /** Test and measurement switches; the page itself only uses inkOn and coast. */
  readonly parts = { outline: true, hatch: true, grain: true };
  private config: InkConfig | null = null;

  constructor(gTex: THREE.Texture, fTex: THREE.Texture, w: number, h: number, near: number, far: number) {
    this.strengthTarget = dataTarget(w, h, THREE.HalfFloatType);
    this.thinTarget = dataTarget(w, h, THREE.UnsignedByteType);
    this.spreadTarget = dataTarget(w, h, THREE.HalfFloatType);
    this.inkTarget = dataTarget(w, h, THREE.UnsignedByteType, true);
    this.blurA = dataTarget(w, h, THREE.HalfFloatType);
    this.blurB = dataTarget(w, h, THREE.HalfFloatType, true);
    const shared = () => ({
      gTex: { value: gTex }, fTex: { value: fTex }, near: { value: near }, far: { value: far }, cTex: { value: this.blurB.texture },
    });
    const blur = (fromData: boolean, dir: [number, number], src: THREE.Texture | null) => material(BLUR, {
      ...shared(), srcTex: { value: src }, fromData: { value: fromData }, dir: { value: new THREE.Vector2(...dir) }, sigma: { value: 1 },
    }, false);
    this.blurH = blur(true, [1, 0], null);
    this.blurV = blur(false, [0, 1], this.blurA.texture);
    this.strength = material(STRENGTH, {
      ...shared(), depthStep: { value: PEN.depthStep }, normalCos: { value: Math.cos(THREE.MathUtils.degToRad(PEN.normalDeg)) },
      roughStride: { value: PEN.surfaceStridePx }, coastAt: { value: PEN.coastFlagAt },
    }, false);
    this.thin = material(THIN, { ...shared(), sTex: { value: this.strengthTarget.texture } }, false);
    this.spread = material(SPREAD, { ...shared(), tTex: { value: this.thinTarget.texture }, R: { value: 2 } }, false);
    this.composite = material(COMPOSITE, {
      ...shared(), spreadTex: { value: this.spreadTarget.texture }, roughTex: { value: this.strengthTarget.texture },
      edgeWidth: { value: 2 }, coastWidth: { value: 3 }, outlineOn: { value: 1 }, coastAt: { value: PEN.coastFlagAt },
      surfaceStep: { value: PEN.surfaceStepPx },
    }, false);
    this.present_ = material(PRESENT, {
      ...shared(),
      inkTex: { value: this.inkTarget.texture },
      canvasSize: { value: new THREE.Vector2() },
      projInv: { value: new THREE.Matrix4() },
      camWorld: { value: new THREE.Matrix4() },
      lightTravel: { value: new THREE.Vector3(0, -1, 0) },
      ink: { value: new THREE.Color() },
      paper: { value: new THREE.Color() },
      hatchOn: { value: 1 },
      grain: { value: PEN.grain },
      mode: { value: 0 },
      hatchSpacing: { value: PEN.hatchSpacingM },
      hatchWidthPx: { value: PEN.hatchCssPx },
      hatchMinPx: { value: PEN.hatchMinSpacingPx },
      normalSpan: { value: 3 },
    }, true);
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.strength);
    this.quad.frustumCulled = false;
    this.scene.add(this.quad);
  }

  setSize(w: number, h: number) {
    for (const t of [this.strengthTarget, this.thinTarget, this.spreadTarget, this.inkTarget, this.blurA, this.blurB]) t.setSize(w, h);
  }

  configure(c: InkConfig) {
    this.config = c;
    const k = c.dpr * c.dataScale;
    const cu = this.composite.uniforms;
    cu.edgeWidth.value = PEN.outlineCssPx * k;
    cu.coastWidth.value = c.coast ? PEN.coastCssPx * k : 0;
    this.blurH.uniforms.sigma.value = this.blurV.uniforms.sigma.value = PEN.cleanCssPx * k;
    this.strength.uniforms.roughStride.value = Math.max(1, Math.round(PEN.surfaceStridePx * k));
    cu.surfaceStep.value = Math.max(1, Math.round(PEN.surfaceStepPx * k));
    // A crease point can sit half a pixel off its pixel's centre, so the window reaches half a pixel further.
    this.spread.uniforms.R.value = Math.ceil((cu.edgeWidth.value as number + 1) / 2 + 0.5);
    const pu = this.present_.uniforms;
    // The present pass writes straight to the sRGB canvas, so hand it sRGB-encoded numbers.
    (pu.ink.value as THREE.Color).set(c.ink).convertLinearToSRGB();
    (pu.paper.value as THREE.Color).set(c.paper).convertLinearToSRGB();
    (pu.lightTravel.value as THREE.Vector3).set(...c.lightTravel).normalize();
    pu.hatchWidthPx.value = PEN.hatchCssPx * c.dpr;
    pu.hatchMinPx.value = PEN.hatchMinSpacingPx * c.dpr;
    // Canvas pixels spanning about three data pixels, whatever the data scale.
    pu.normalSpan.value = 3 / c.dataScale;
    pu.mode.value = MODES[c.debug ?? "final"];
    const blend = c.debug === null;
    this.present_.transparent = blend;
    this.present_.blending = blend ? THREE.NormalBlending : THREE.NoBlending;
    this.present_.needsUpdate = true;
    this.applyParts();
  }

  /** Re-reads `parts` after a test or the HUD changes them. */
  applyParts() {
    const on = this.config?.inkOn ?? true;
    this.composite.uniforms.outlineOn.value = on && this.parts.outline ? 1 : 0;
    this.present_.uniforms.hatchOn.value = on && this.parts.hatch ? 1 : 0;
    this.present_.uniforms.grain.value = on && this.parts.grain ? PEN.grain : 0;
  }

  /** Whether anything this pass draws is visible; with ink and coast both off it can be skipped. */
  get needed() {
    const c = this.config;
    return c !== null && (c.inkOn || c.coast || c.debug !== null);
  }

  private draw(renderer: THREE.WebGLRenderer, mat: THREE.ShaderMaterial, target: THREE.WebGLRenderTarget | null) {
    this.quad.material = mat;
    renderer.setRenderTarget(target);
    renderer.render(this.scene, this.cam);
  }

  /** The off-screen edge work at data resolution. */
  detect(renderer: THREE.WebGLRenderer) {
    const prev = renderer.getRenderTarget();
    this.draw(renderer, this.blurH, this.blurA);
    this.draw(renderer, this.blurV, this.blurB);
    this.draw(renderer, this.strength, this.strengthTarget);
    this.draw(renderer, this.thin, this.thinTarget);
    this.draw(renderer, this.spread, this.spreadTarget);
    this.draw(renderer, this.composite, this.inkTarget);
    renderer.setRenderTarget(prev);
  }

  /** Over the shade pass already on the canvas, or replacing it for a debug view. */
  present(renderer: THREE.WebGLRenderer, camera: THREE.PerspectiveCamera) {
    const u = this.present_.uniforms;
    renderer.getDrawingBufferSize(u.canvasSize.value as THREE.Vector2);
    (u.projInv.value as THREE.Matrix4).copy(camera.projectionMatrixInverse);
    (u.camWorld.value as THREE.Matrix4).copy(camera.matrixWorld);
    const autoClear = renderer.autoClear;
    renderer.autoClear = false;
    this.draw(renderer, this.present_, null);
    renderer.autoClear = autoClear;
  }
}

import * as THREE from "three";

export type DebugView = "shade" | "depth" | "normal" | "flag" | "edges" | "final";

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
float flagAt(ivec2 q) { vec4 f = texelFetch(fTex, clampPx(q), 0); return f.a > 0.01 ? f.r / f.a : 0.0; }
float coverAt(ivec2 q) { return texelFetch(gTex, clampPx(q), 0).a; }
`;

// Crease strength from Sobel on view depth (relative step of about 2 %) and on the normal
// (about 20°); 1.0 means "at threshold". Background neighbours borrow the centre value so a
// silhouette never reads as a depth crease: silhouettes come from the coverage contour instead.
const STRENGTH = /* glsl */ `
${DECODE}
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
      float z = viewZ(g);
      float f = 1.0 - dot(decodeN(g), nc);
      gz += vec2(wx, wy) * z;
      gn += vec2(wx, wy) * f;
    }
  }
  gz /= 8.0;
  gn /= 8.0;
  // A hard step of size s between two pixels gives a Sobel/8 response of s/2 on each side.
  float sd = length(gz) / (0.5 * 0.02 * zc);
  float sn = length(gn) / (0.5 * (1.0 - cos(radians(20.0))));
  vec2 dir = sd >= sn ? gz : gn;
  float s = max(sd, sn);
  outColor = vec4(s, length(dir) > 0.0 ? normalize(dir) : vec2(1.0, 0.0), 1.0);
}
`;

// One-pixel-thin edges: creases by non-maximum suppression along the gradient, silhouettes and
// the coastline as the inside pixels of the coverage = 0.5 and flag = 0.5 contours.
const THIN = /* glsl */ `
${DECODE}
uniform highp sampler2D sTex;
out vec4 outColor;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  float a = coverAt(p);
  if (a < 0.5) { outColor = vec4(0.0); return; }
  vec4 s = texelFetch(sTex, p, 0);
  ivec2 d = ivec2(round(s.gb * 1.41421356));
  float sMinus = texelFetch(sTex, clampPx(p - d), 0).r;
  float sPlus = texelFetch(sTex, clampPx(p + d), 0).r;
  bool crease = s.r >= 1.0 && s.r > sMinus && s.r >= sPlus;

  ivec2 N[4] = ivec2[4](ivec2(1, 0), ivec2(-1, 0), ivec2(0, 1), ivec2(0, -1));
  bool silhouette = false;
  bool coast = false;
  float flag = flagAt(p);
  for (int k = 0; k < 4; k++) {
    ivec2 q = p + N[k];
    float aq = coverAt(q);
    if (aq < 0.5) silhouette = true;
    else if (flag >= 0.5 && flagAt(q) < 0.5) coast = true;
  }
  outColor = vec4((crease || silhouette) ? 1.0 : 0.0, coast ? 1.0 : 0.0, flag, 1.0);
}
`;

// Exact two-pass Euclidean distance within a small window: the row pass keeps, per pixel, the
// horizontal offset to the nearest line pixel in its row (and that pixel's flag); the column pass
// then minimises dy² + dx². Brute force over the full (2R+1)² window is kept for comparison.
const SPREAD = /* glsl */ `
${DECODE}
uniform highp sampler2D tTex;
uniform int R;
out vec4 outColor;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  float de = 1e4, fe = 0.0, dc = 1e4;
  for (int i = -R; i <= R; i++) {
    vec4 t = texelFetch(tTex, clampPx(p + ivec2(i, 0)), 0);
    float d = abs(float(i));
    if (t.r > 0.5 && (d < de || (d == de && t.b > fe))) { de = d; fe = t.b; }
    if (t.g > 0.5) dc = min(dc, d);
  }
  outColor = vec4(de, fe, dc, 1.0);
}
`;

// Widens the thin lines to a fixed width in device pixels with a one-pixel antialiased edge:
// a pixel at distance d from the nearest line pixel gets clamp((W + 1) / 2 - d, 0, 1), so the
// ink summed across the line is W whatever the splats underneath look like.
const COMPOSITE = /* glsl */ `
${DECODE}
uniform highp sampler2D tTex;
uniform highp sampler2D spreadTex;
uniform bool separable;
uniform float edgeWidth;
uniform float coastWidth;
uniform vec3 ink;
uniform vec3 paper;
uniform int mode;
uniform float dist;
out vec4 outColor;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  int R = int(ceil((max(edgeWidth, coastWidth) + 1.0) * 0.5));
  float ae = 0.0, ac = 0.0;
  float he = (edgeWidth + 1.0) * 0.5, hc = (coastWidth + 1.0) * 0.5;
  bool useCoast = coastWidth > 0.0;
  if (separable) {
    for (int j = -R; j <= R; j++) {
      vec4 s = texelFetch(spreadTex, clampPx(p + ivec2(0, j)), 0);
      float dy2 = float(j * j);
      ae = max(ae, clamp(he - sqrt(dy2 + s.r * s.r), 0.0, 1.0) * s.g);
      if (useCoast) ac = max(ac, clamp(hc - sqrt(dy2 + s.b * s.b), 0.0, 1.0));
    }
  } else {
    for (int j = -R; j <= R; j++) {
      for (int i = -R; i <= R; i++) {
        vec4 t = texelFetch(tTex, clampPx(p + ivec2(i, j)), 0);
        float d = length(vec2(i, j));
        if (t.r > 0.5) ae = max(ae, clamp(he - d, 0.0, 1.0) * t.b);
        if (t.g > 0.5 && useCoast) ac = max(ac, clamp(hc - d, 0.0, 1.0));
      }
    }
  }
  float alpha = max(ae, ac);
  vec4 g = texelFetch(gTex, p, 0);
  if (mode == 5) { outColor = vec4(ink, alpha); return; }
  if (mode == 4) { outColor = vec4(mix(paper, ink, alpha), 1.0); return; }
  vec3 bg = paper;
  if (mode == 1) {
    float z = viewZ(g);
    bg = mix(paper, vec3(clamp((z - (dist - 1.0)) / 2.0, 0.0, 1.0)), g.a);
  } else if (mode == 2) {
    bg = mix(paper, decodeN(g) * 0.5 + 0.5, g.a);
  } else if (mode == 3) {
    float f = flagAt(p);
    bg = mix(paper, mix(vec3(0.16, 0.42, 0.72), vec3(0.93, 0.55, 0.15), f), g.a);
  }
  outColor = vec4(bg, 1.0);
}
`;

// Data passes rendered below canvas resolution: the composite runs at data resolution into an
// ink target, and this pass stretches it over the canvas with bilinear filtering, which keeps
// the ink summed across a line (its width) while softening its edges.
const UPSCALE = /* glsl */ `
precision highp float;
uniform sampler2D inkTex;
uniform vec2 canvasSize;
out vec4 outColor;
void main() { outColor = texture(inkTex, gl_FragCoord.xy / canvasSize); }
`;

const MODES: Record<DebugView, number> = { shade: 0, depth: 1, normal: 2, flag: 3, edges: 4, final: 5 };

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

function dataTarget(w: number, h: number, type: THREE.TextureDataType) {
  return new THREE.WebGLRenderTarget(w, h, {
    type,
    colorSpace: THREE.NoColorSpace,
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    depthBuffer: false,
  });
}

export class OutlinePass {
  readonly strengthTarget: THREE.WebGLRenderTarget;
  readonly thinTarget: THREE.WebGLRenderTarget;
  readonly spreadTarget: THREE.WebGLRenderTarget;
  readonly inkTarget: THREE.WebGLRenderTarget;
  private readonly upscale: THREE.ShaderMaterial;
  private scale = 1;
  private readonly quad: THREE.Mesh;
  private readonly cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private readonly scene = new THREE.Scene();
  private readonly strength: THREE.ShaderMaterial;
  private readonly thin: THREE.ShaderMaterial;
  private readonly spread: THREE.ShaderMaterial;
  private separable = true;
  readonly composite: THREE.ShaderMaterial;

  constructor(gTex: THREE.Texture, fTex: THREE.Texture, w: number, h: number, near: number, far: number) {
    this.strengthTarget = dataTarget(w, h, THREE.HalfFloatType);
    this.thinTarget = dataTarget(w, h, THREE.UnsignedByteType);
    this.spreadTarget = dataTarget(w, h, THREE.HalfFloatType);
    this.inkTarget = dataTarget(w, h, THREE.UnsignedByteType);
    this.inkTarget.texture.minFilter = THREE.LinearFilter;
    this.inkTarget.texture.magFilter = THREE.LinearFilter;
    const shared = {
      gTex: { value: gTex },
      fTex: { value: fTex },
      near: { value: near },
      far: { value: far },
    };
    this.strength = material(STRENGTH, { ...shared }, false);
    this.thin = material(THIN, { ...shared, sTex: { value: this.strengthTarget.texture } }, false);
    this.spread = material(SPREAD, { ...shared, tTex: { value: this.thinTarget.texture }, R: { value: 2 } }, false);
    this.composite = material(
      COMPOSITE,
      {
        ...shared,
        tTex: { value: this.thinTarget.texture },
        spreadTex: { value: this.spreadTarget.texture },
        separable: { value: true },
        edgeWidth: { value: 2 },
        coastWidth: { value: 3 },
        ink: { value: new THREE.Color() },
        paper: { value: new THREE.Color() },
        mode: { value: MODES.final },
        dist: { value: 3 },
      },
      true,
    );
    this.upscale = material(UPSCALE, { inkTex: { value: this.inkTarget.texture }, canvasSize: { value: new THREE.Vector2() } }, true);
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.strength);
    this.quad.frustumCulled = false;
    this.scene.add(this.quad);
  }

  setSize(w: number, h: number) {
    this.strengthTarget.setSize(w, h);
    this.thinTarget.setSize(w, h);
    this.spreadTarget.setSize(w, h);
    this.inkTarget.setSize(w, h);
  }

  /** dpr × scale turns the CSS-pixel widths into data pixels; scale is data pixels per canvas pixel. */
  configure(opts: { scale: number; dpr: number; ink: string; paper: string; view: DebugView; dist: number; coast: boolean; separable: boolean }) {
    const u = this.composite.uniforms;
    this.scale = opts.scale;
    u.edgeWidth.value = 2 * opts.dpr * opts.scale;
    u.coastWidth.value = opts.coast ? 3 * opts.dpr * opts.scale : 0;
    // The composite writes straight to the sRGB canvas, so hand it sRGB-encoded numbers.
    (u.ink.value as THREE.Color).set(opts.ink).convertLinearToSRGB();
    (u.paper.value as THREE.Color).set(opts.paper).convertLinearToSRGB();
    u.mode.value = MODES[opts.view];
    u.separable.value = opts.separable;
    this.separable = opts.separable;
    this.spread.uniforms.R.value = Math.ceil((Math.max(u.edgeWidth.value as number, u.coastWidth.value as number) + 1) / 2);
    u.dist.value = opts.dist;
    const blendOnCanvas = opts.view === "final";
    const direct = opts.scale === 1;
    this.composite.transparent = direct && blendOnCanvas;
    this.composite.blending = direct && blendOnCanvas ? THREE.NormalBlending : THREE.NoBlending;
    this.composite.needsUpdate = true;
    this.upscale.transparent = blendOnCanvas;
    this.upscale.blending = blendOnCanvas ? THREE.NormalBlending : THREE.NoBlending;
    this.upscale.needsUpdate = true;
  }

  private draw(renderer: THREE.WebGLRenderer, mat: THREE.ShaderMaterial, target: THREE.WebGLRenderTarget | null) {
    this.quad.material = mat;
    renderer.setRenderTarget(target);
    renderer.render(this.scene, this.cam);
  }

  /** All off-screen work: edge detection, and the composite too when the data passes are scaled down. */
  detect(renderer: THREE.WebGLRenderer) {
    const prev = renderer.getRenderTarget();
    this.draw(renderer, this.strength, this.strengthTarget);
    this.draw(renderer, this.thin, this.thinTarget);
    if (this.separable) this.draw(renderer, this.spread, this.spreadTarget);
    if (this.scale !== 1) this.draw(renderer, this.composite, this.inkTarget);
    renderer.setRenderTarget(prev);
  }

  /** Over the shade pass already on the canvas (final), or replacing it (debug views). */
  present(renderer: THREE.WebGLRenderer) {
    const autoClear = renderer.autoClear;
    renderer.autoClear = false;
    if (this.scale === 1) {
      this.draw(renderer, this.composite, null);
    } else {
      renderer.getDrawingBufferSize(this.upscale.uniforms.canvasSize.value as THREE.Vector2);
      this.draw(renderer, this.upscale, null);
    }
    renderer.autoClear = autoClear;
  }
}

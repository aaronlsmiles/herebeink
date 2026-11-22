// Two independent clocks for the cost of each pass, so each can check the other:
// GPU timer queries where the browser exposes them, and CPU wall time around a forced sync.

interface TimerExt { TIME_ELAPSED_EXT: number; GPU_DISJOINT_EXT: number }

export type PassName = "shade" | "gbuf" | "flag" | "post";
export const PASSES: PassName[] = ["shade", "gbuf", "flag", "post"];

export class PassTimer {
  private readonly gl: WebGL2RenderingContext;
  private readonly ext: TimerExt | null;
  private pending: { name: PassName; q: WebGLQuery }[] = [];
  private open: WebGLQuery | null = null;
  readonly gpu: Record<PassName, number[]> = { shade: [], gbuf: [], flag: [], post: [] };
  readonly wall: Record<PassName, number[]> = { shade: [], gbuf: [], flag: [], post: [] };
  // CPU time spent issuing each pass (no sync), which is what an uncapped frame pays on the main thread.
  readonly cpu: Record<PassName, number[]> = { shade: [], gbuf: [], flag: [], post: [] };
  readonly frame: number[] = [];
  private syncBuf = new Uint8Array(4);
  private t0 = 0;

  // Timer queries are opt-in: on ANGLE's Metal backend each one costs real frame time.
  constructor(gl: WebGL2RenderingContext, readonly sync: boolean, queries: boolean) {
    this.gl = gl;
    this.ext = queries ? (gl.getExtension("EXT_disjoint_timer_query_webgl2") as TimerExt | null) : null;
  }

  get hasGpuTimer() { return this.ext !== null; }

  private finish() {
    // A one-pixel read from the canvas cannot return until every earlier command has run.
    // three.js caches the bound framebuffer, so put back whatever it thinks is bound.
    const gl = this.gl;
    const bound = gl.getParameter(gl.FRAMEBUFFER_BINDING) as WebGLFramebuffer | null;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, this.syncBuf);
    gl.bindFramebuffer(gl.FRAMEBUFFER, bound);
  }

  begin(name: PassName) {
    if (this.sync) this.finish();
    this.t0 = performance.now();
    if (this.ext) {
      const q = this.gl.createQuery();
      if (q) { this.gl.beginQuery(this.ext.TIME_ELAPSED_EXT, q); this.open = q; this.pending.push({ name, q }); }
    }
  }

  end(name: PassName) {
    if (this.ext && this.open) { this.gl.endQuery(this.ext.TIME_ELAPSED_EXT); this.open = null; }
    if (this.sync) { this.finish(); this.wall[name].push(performance.now() - this.t0); }
    else this.cpu[name].push(performance.now() - this.t0);
  }

  /** Collects finished queries; called once a frame, never blocks. */
  poll(frameMs: number) {
    this.frame.push(frameMs);
    if (!this.ext) return;
    const gl = this.gl;
    const disjoint = gl.getParameter(this.ext.GPU_DISJOINT_EXT) as boolean;
    const still: typeof this.pending = [];
    for (const p of this.pending) {
      if (!gl.getQueryParameter(p.q, gl.QUERY_RESULT_AVAILABLE)) { still.push(p); continue; }
      if (!disjoint) this.gpu[p.name].push((gl.getQueryParameter(p.q, gl.QUERY_RESULT) as number) / 1e6);
      gl.deleteQuery(p.q);
    }
    this.pending = still;
  }

  reset() {
    for (const n of PASSES) { this.gpu[n].length = 0; this.wall[n].length = 0; this.cpu[n].length = 0; }
    this.frame.length = 0;
  }
}

export function median(xs: number[]) {
  if (xs.length === 0) return NaN;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : 0.5 * (s[m - 1] + s[m]);
}

export function quantile(xs: number[], q: number) {
  if (xs.length === 0) return NaN;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.max(0, Math.round(q * (s.length - 1))))];
}

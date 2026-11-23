export interface HudNumbers {
  medianFrameMs: number;
  p90FrameMs: number;
  frames: number;
  windowS: number;
  splatsRendered: number;
  splatsLoaded: number;
  lod: { enabled: boolean; splatBudget: number; deviceClass: string };
  measuredFile: string;
  dataScale: number;
  dataPassPx: [number, number];
  canvasPx: [number, number];
  dpr: number;
  ink: boolean;
  userAgent: string;
}

const WINDOW_MS = 5000;

/** Frame times over a sliding 5 s window; the median is what the phone criterion reads. */
export class FrameWindow {
  private readonly t: number[] = [];
  private readonly dt: number[] = [];

  push(now: number, dtMs: number) {
    this.t.push(now);
    this.dt.push(dtMs);
    while (this.t.length && now - this.t[0] > WINDOW_MS) { this.t.shift(); this.dt.shift(); }
  }

  stats() {
    const s = [...this.dt].sort((a, b) => a - b);
    const q = (p: number) => (s.length ? s[Math.min(s.length - 1, Math.round(p * (s.length - 1)))] : NaN);
    const mid = s.length >> 1;
    const median = s.length === 0 ? NaN : s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
    const windowS = this.t.length > 1 ? (this.t[this.t.length - 1] - this.t[0]) / 1000 : 0;
    return { median, p90: q(0.9), frames: s.length, windowS };
  }
}

export class Hud {
  readonly root: HTMLElement;
  private readonly pre: HTMLPreElement;
  private readonly copy: HTMLButtonElement;
  private last = 0;

  constructor(container: HTMLElement, private readonly read: () => HudNumbers) {
    this.root = document.createElement("section");
    this.root.className = "hud";
    this.root.setAttribute("aria-label", "Performance numbers");
    this.pre = document.createElement("pre");
    this.copy = document.createElement("button");
    this.copy.type = "button";
    this.copy.className = "chip";
    this.copy.textContent = "Copy numbers";
    this.copy.addEventListener("click", () => void this.copyJson());
    this.root.append(this.pre, this.copy);
    container.appendChild(this.root);
  }

  /** Refreshes the text at most twice a second; reading the numbers is cheap, layout is not. */
  tick(now: number) {
    if (now - this.last < 500) return;
    this.last = now;
    const n = this.read();
    this.pre.textContent = [
      `frame   ${n.medianFrameMs.toFixed(1)} ms median, ${n.p90FrameMs.toFixed(1)} p90 (${n.frames} in ${n.windowS.toFixed(1)} s)`,
      `splats  ${n.splatsRendered.toLocaleString("en-GB")} drawn of ${n.splatsLoaded.toLocaleString("en-GB")} loaded`,
      `lod     ${n.lod.enabled ? "on" : "off"}, budget ${n.lod.splatBudget.toLocaleString("en-GB")} (${n.lod.deviceClass})`,
      `file    ${n.measuredFile.startsWith("ladder") ? n.measuredFile : n.measuredFile === "measuredPhone" ? "phone (lighter measured file)" : "full measured file"}`,
      `data    ×${n.dataScale.toFixed(2)} = ${n.dataPassPx[0]}×${n.dataPassPx[1]} of ${n.canvasPx[0]}×${n.canvasPx[1]} @ dpr ${n.dpr}`,
      `ink     ${n.ink ? "on" : "filter"}`,
    ].join("\n");
  }

  private async copyJson() {
    const json = JSON.stringify({ ...this.read(), at: new Date().toISOString() }, null, 1);
    try {
      await navigator.clipboard.writeText(json);
      this.copy.textContent = "Copied";
    } catch {
      // Clipboard access can be refused (insecure origin, permissions); show it to copy by hand.
      this.pre.textContent = json;
      this.copy.textContent = "Select and copy";
    }
    setTimeout(() => { this.copy.textContent = "Copy numbers"; }, 2000);
  }
}

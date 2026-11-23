// The ladder's chart, as pure geometry and an SVG string: x the share of all directions a rung's inputs
// showed, y the share of the room's directions where its world is imagined. Its inputs carry no right or
// wrong figure at all, so the chart cannot show one (stance A).
import type { Ladder, LadderRung, RungId } from "./contract.ts";
import { CHART, LADDER, POINT_LABEL, POINT_LABEL_BOTH_SEEDS, pointTitle, SCAN_READING } from "./words.ts";

export const CHART_BOX = { width: 300, height: 214, left: 44, right: 286, top: 14, bottom: 172 } as const;
const LABEL_H = 11;
/** A label's box for the overlap test: a little under its line height, since the glyphs never fill it. */
const LABEL_BOX_H = 8;
const CHAR_W = 6.1;
const GAP = 7;

export interface ChartPoint {
  id: RungId;
  /** Plot coordinates in the SVG's units. */
  px: number;
  py: number;
  label: string;
  /** Where the label sits beside its point. */
  anchor: "start" | "end";
  lx: number;
  ly: number;
  reconstruction: boolean;
  current: boolean;
  /** Its placing rests on the scan's least certain part: the caption's footnote. */
  footnote: boolean;
  title: string;
}

export interface ChartModel {
  points: ChartPoint[];
  /** The floor line through (shown, 1 − seenShareOfKey), left to right, in plot coordinates. */
  floor: [number, number][];
  /** Rungs that exist but have no point (not placed). */
  missing: RungId[];
}

export const toX = (share: number) => CHART_BOX.left + share * (CHART_BOX.right - CHART_BOX.left);
export const toY = (share: number) => CHART_BOX.bottom - share * (CHART_BOX.bottom - CHART_BOX.top);

interface Box { x0: number; x1: number; y0: number; y1: number }
const overlaps = (a: Box, b: Box) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

/** Labels go right of their point unless that would hit another label, a point or the plot's edge. */
function placeLabels(pts: Omit<ChartPoint, "anchor" | "lx" | "ly">[]): ChartPoint[] {
  const taken: Box[] = pts.map((p) => ({ x0: p.px - 4, x1: p.px + 4, y0: p.py - 4, y1: p.py + 4 }));
  const placed: ChartPoint[] = [];
  for (const p of [...pts].sort((a, b) => a.px - b.px || b.py - a.py)) {
    if (!p.label) { placed.push({ ...p, anchor: "start", lx: p.px, ly: p.py }); continue; }
    const w = p.label.length * CHAR_W + (p.footnote ? CHAR_W : 0);
    // the current point is drawn with a wider ring, so its label stands further off
    const g = p.current ? GAP + 4 : GAP;
    const tries: { anchor: "start" | "end"; dx: number; dy: number }[] = [
      { anchor: "start", dx: g, dy: 0 }, { anchor: "end", dx: -g, dy: 0 },
      { anchor: "start", dx: g, dy: LABEL_H }, { anchor: "end", dx: -g, dy: LABEL_H },
      { anchor: "start", dx: g, dy: -LABEL_H }, { anchor: "end", dx: -g, dy: -LABEL_H },
    ];
    let pick = tries[0], box: Box | null = null;
    for (const t of tries) {
      const x0 = t.anchor === "start" ? p.px + t.dx : p.px + t.dx - w;
      const b = { x0, x1: x0 + w, y0: p.py + t.dy - LABEL_BOX_H / 2, y1: p.py + t.dy + LABEL_BOX_H / 2 };
      const inside = b.x0 >= CHART_BOX.left - 2 && b.x1 <= CHART_BOX.width && b.y0 >= 0 && b.y1 <= CHART_BOX.bottom + 2;
      if (inside && !taken.some((o) => overlaps(o, b))) { pick = t; box = b; break; }
    }
    if (!box) {
      const x0 = pick.anchor === "start" ? p.px + pick.dx : p.px + pick.dx - w;
      box = { x0, x1: x0 + w, y0: p.py - LABEL_H / 2, y1: p.py + LABEL_H / 2 };
    }
    taken.push(box);
    placed.push({ ...p, anchor: pick.anchor, lx: p.px + pick.dx, ly: p.py + pick.dy });
  }
  return placed;
}

export function chartModel(ladder: Ladder, currentId: RungId | null): ChartModel {
  const plotted = ladder.rungs.filter((r): r is LadderRung & { imagined: number } => r.placed && r.imagined !== null);
  // Two seeds that land within a few units of each other share one label, or the two collide on the point.
  const r4 = plotted.find((r) => r.id === "R4"), r4b = plotted.find((r) => r.id === "R4b");
  const seedsTogether = !!r4 && !!r4b && Math.abs(toY(r4.imagined) - toY(r4b.imagined)) < LABEL_H;
  const labelOf = (id: RungId) => (seedsTogether && id === "R4" ? POINT_LABEL_BOTH_SEEDS : seedsTogether && id === "R4b" ? "" : POINT_LABEL[id]);
  const points = placeLabels(plotted.map((r) => ({
    id: r.id,
    px: toX(r.shown),
    py: toY(r.imagined),
    label: labelOf(r.id),
    reconstruction: r.mode === "reconstruction",
    current: r.id === currentId,
    footnote: SCAN_READING.includes(r.id),
    title: pointTitle(r),
  })));
  // One floor point per distinct x: R4, its second seed and R4r share their inputs, so they share s too.
  const byX = new Map<number, number>();
  for (const r of ladder.rungs) if (!byX.has(r.shown)) byX.set(r.shown, 1 - r.seenShareOfKey);
  const floor = [...byX.entries()].sort((a, b) => a[0] - b[0]).map(([x, y]) => [toX(x), toY(y)] as [number, number]);
  const missing = ladder.rungs.filter((r) => !r.placed || r.imagined === null).map((r) => r.id);
  return { points, floor, missing };
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const f = (n: number) => n.toFixed(1);

/** The chart as SVG markup; each point is a focusable button that loads its rung (wired by the panel). */
export function chartSvg(m: ChartModel): string {
  const B = CHART_BOX;
  const ticks = [0, 0.5, 1];
  const grid = ticks.map((t) => `
    <line class="lc-grid" x1="${f(toX(t))}" y1="${B.top}" x2="${f(toX(t))}" y2="${B.bottom}"/>
    <line class="lc-grid" x1="${B.left}" y1="${f(toY(t))}" x2="${B.right}" y2="${f(toY(t))}"/>
    <text class="lc-tick" x="${f(toX(t))}" y="${B.bottom + 14}" text-anchor="${t === 0 ? "start" : t === 1 ? "end" : "middle"}">${Math.round(t * 100)}%</text>
    <text class="lc-tick" x="${B.left - 6}" y="${f(toY(t) + 3.5)}" text-anchor="end">${Math.round(t * 100)}%</text>`).join("");
  const floor = m.floor.length > 1
    ? `<polyline class="lc-floor" points="${m.floor.map(([x, y]) => `${f(x)},${f(y)}`).join(" ")}"/>` : "";
  const pts = m.points.map((p) => `
    <g class="lc-point${p.current ? " is-current" : ""}${p.reconstruction ? " is-rec" : ""}" data-rung="${p.id}" tabindex="0" role="button" aria-label="${esc(p.title)}"${p.current ? ` aria-current="true"` : ""}>
      <title>${esc(p.title)}</title>
      <circle class="lc-hit" cx="${f(p.px)}" cy="${f(p.py)}" r="11"/>
      ${p.current ? `<circle class="lc-ring" cx="${f(p.px)}" cy="${f(p.py)}" r="7.5"/>` : ""}
      <circle class="lc-dot" cx="${f(p.px)}" cy="${f(p.py)}" r="${p.reconstruction ? 3.6 : 4}"/>
      ${p.label ? `<text class="lc-label" x="${f(p.lx)}" y="${f(p.ly + 3.5)}" text-anchor="${p.anchor}">${esc(p.label)}${p.footnote ? "*" : ""}</text>` : ""}
    </g>`).join("");
  return `<svg class="ladder-chart" viewBox="0 0 ${B.width} ${B.height}" role="group" aria-label="${esc(LADDER.chartTitle)}">
    <g aria-hidden="true">${grid}
      <line class="lc-axis" x1="${B.left}" y1="${B.bottom}" x2="${B.right}" y2="${B.bottom}"/>
      <line class="lc-axis" x1="${B.left}" y1="${B.top}" x2="${B.left}" y2="${B.bottom}"/>
      ${floor}
      <text class="lc-axis-label" x="${(B.left + B.right) / 2}" y="${B.height - 6}" text-anchor="middle">${esc(CHART.x)}</text>
      <text class="lc-axis-label" transform="translate(11 ${(B.top + B.bottom) / 2}) rotate(-90)" text-anchor="middle">${esc(CHART.y)}</text>
    </g>${pts}
  </svg>`;
}

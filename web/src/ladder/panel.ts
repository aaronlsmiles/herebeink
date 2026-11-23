// The ladder's panel: a second cartouche on the sheet, with the steps as a surveyor's scale bar, the step's
// coverage readout, the chart, the red pen and the ladder's own key. DOM only; mode.ts decides what it shows.
import "./ladder.css";
import { DRAWING_SWATCH, PHOTO_SAMPLE_PNG } from "../map.ts";
import { ladderNote } from "../plainwords/layer.ts";
import { chartModel, chartSvg } from "./chart.ts";
import type { Ladder, LadderRung, RungId } from "./contract.ts";
import { CHART, LADDER, LEGEND, READOUT, STEP_LABEL } from "./words.ts";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> & { className?: string } = {}, ...children: (Node | string)[]) {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...children);
  return e;
}

/** A short stretch of red pen over paper: the red pen's own swatch. */
const RED_SWATCH = `<svg class="swatch red" viewBox="0 0 20 14" aria-hidden="true" focusable="false"><rect x="0.75" y="0.75" width="18.5" height="12.5" fill="color-mix(in srgb, var(--red) 20%, var(--paper))" stroke="var(--red)" stroke-width="1.5"/><path d="M3 11 9 3M8 11l6-8M13 11l4-5.3" stroke="var(--red)" stroke-width="1.2" fill="none"/></svg>`;
const FRAME_SWATCH = `<svg class="swatch frame" viewBox="0 0 20 14" aria-hidden="true" focusable="false"><path d="M1 7 19 1M1 7l18 6M19 1v12" stroke="var(--ink)" stroke-width="1" stroke-opacity="0.6" fill="none"/></svg>`;

/**
 * The ladder's key: its own classes, never Part 1's. `you` adds the visitor's marker, for the map; `compact` is
 * the panel's one-line form, its descriptions kept for screen readers.
 */
export function legendList(you = false, compact = false) {
  const row = (swatch: string | HTMLElement, [term, text]: readonly [string, string], cls = "") => {
    const dt = el("dt");
    if (typeof swatch === "string") dt.insertAdjacentHTML("afterbegin", swatch);
    else dt.append(swatch);
    dt.append(term);
    return el("div", { className: cls }, dt, el("dd", { className: compact ? "visually-hidden" : "" }, text));
  };
  const photo = el("span", { className: "swatch photo" });
  const line = el("span", { className: "swatch line" });
  const dl = el("dl", { className: compact ? "ladder-key compact" : "ladder-key" },
    row(photo, LEGEND.seen),
    row(DRAWING_SWATCH, LEGEND.imagined),
    row(RED_SWATCH, LEGEND.wrong, "is-red"),
    row(FRAME_SWATCH, LEGEND.frames),
    row(line, LEGEND.line),
  );
  if (you) {
    const dot = el("span", { className: "swatch you" }, el("span"));
    dl.append(row(dot, ["You", "where you stand"]));
  }
  return dl;
}

export interface PanelHandlers {
  step(id: RungId): void;
  redPen(on: boolean): void;
}

export class LadderPanel {
  readonly root: HTMLElement;
  readonly redPenButton: HTMLButtonElement;
  readonly mapLegend: HTMLElement;
  private readonly steps = new Map<RungId, HTMLButtonElement>();
  private readonly status: HTMLElement;
  private readonly now: HTMLElement;
  private readonly chart: HTMLElement;
  private readonly notPlacedNote: HTMLElement;
  private readonly framesNote: HTMLElement;
  private current: RungId | null = null;

  constructor(private readonly ladder: Ladder, private readonly on: PanelHandlers, wide: boolean) {
    const title = el("h2", { id: "ladder-title" }, LADDER.heading);
    const bar = el("div", { className: "ladder-steps" });
    bar.setAttribute("role", "group");
    bar.setAttribute("aria-label", LADDER.stepsLabel);
    ladder.steps.forEach((id, i) => {
      const rung = ladder.rungs.find((r) => r.id === id)!;
      const b = el("button", { type: "button", className: "ladder-step" }, el("span", { className: "tick" }), el("span", { className: "name" }, STEP_LABEL[id]));
      b.dataset.rung = id;
      b.dataset.alt = String(i % 2);
      b.setAttribute("aria-pressed", "false");
      b.setAttribute("aria-label", rung.label);
      b.addEventListener("click", () => on.step(id));
      b.addEventListener("keydown", (e) => this.arrowKeys(e, i));
      this.steps.set(id, b);
      bar.append(b);
    });

    this.redPenButton = el("button", { type: "button", className: "chip ladder-red", title: LADDER.redPenTitle }, el("span", { className: "pen", ariaHidden: "true" }), LADDER.redPen);
    this.redPenButton.dataset.control = "redpen";
    this.redPenButton.setAttribute("aria-pressed", "false");
    this.redPenButton.addEventListener("click", () => on.redPen(this.redPenButton.getAttribute("aria-pressed") !== "true"));

    this.status = el("p", { className: "ladder-status" });
    this.status.setAttribute("role", "status");
    this.now = el("div", { className: "ladder-now" });
    this.now.setAttribute("aria-live", "polite");
    this.notPlacedNote = ladderNote("notPlaced");
    this.framesNote = ladderNote("frames");

    this.chart = el("figure", { className: "ladder-figure" });
    this.chart.addEventListener("click", (e) => {
      const g = (e.target as Element).closest<SVGGElement>("[data-rung]");
      if (g) on.step(g.dataset.rung as RungId);
    });
    this.chart.addEventListener("keydown", (e) => {
      const g = (e.target as Element).closest<SVGGElement>("[data-rung]");
      if (g && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); on.step(g.dataset.rung as RungId); }
    });
    const more = el("details", { className: "ladder-more", open: wide },
      el("summary", {}, LADDER.chartTitle),
      ladderNote("chart"),
      this.chart,
    );

    this.root = el("section", { className: "ladder", hidden: true },
      el("header", { className: "ladder-head" }, title, el("div", { className: "ladder-tools" }, this.redPenButton)),
      ladderNote("ladder"),
      bar,
      this.status,
      this.now,
      this.notPlacedNote,
      this.framesNote,
      legendList(false, true),
      ladderNote("redPen"),
      more,
    );
    this.root.setAttribute("aria-labelledby", "ladder-title");
    this.root.style.setProperty("--photo-sample", `url("data:image/png;base64,${PHOTO_SAMPLE_PNG}")`);

    this.mapLegend = el("section", { className: "map-legend ladder-map-key" }, el("h2", {}, "The ladder from above"), legendList(true));
    this.mapLegend.setAttribute("aria-label", "Map legend");
  }

  /** Left and right walk the steps, as along a scale bar; Home and End jump to its ends. */
  private arrowKeys(e: KeyboardEvent, i: number) {
    const n = this.ladder.steps.length;
    const to = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : null;
    if (to === null || to < 0 || to >= n) return;
    e.preventDefault();
    const id = this.ladder.steps[to];
    this.steps.get(id)!.focus();
    this.on.step(id);
  }

  show(rung: LadderRung) {
    this.current = rung.id;
    for (const [id, b] of this.steps) b.setAttribute("aria-pressed", String(id === rung.id));
    // R4's second seed and R4r are not steps; their nearest step stays marked so the bar still says where you are.
    if (!this.steps.has(rung.id)) {
      const near = rung.id === "R4b" || rung.id === "R4r" ? "R4" : null;
      if (near) this.steps.get(near)?.setAttribute("aria-pressed", "mixed");
    }
    const head = el("h3", {}, rung.label);
    if (rung.mode === "reconstruction" && !rung.label.includes(LADDER.reconstruction)) head.append(" ", el("span", { className: "tag", title: LADDER.reconstructionText }, LADDER.reconstruction));
    if (!rung.placed) {
      head.append(" ", el("span", { className: "tag" }, LADDER.notPlaced));
      this.now.replaceChildren(head, el("p", { className: "ladder-text" }, LADDER.notPlacedText));
    } else {
      const dl = el("dl", { className: "ladder-readout" },
        el("div", {}, el("dt", {}, READOUT.shown), el("dd", {}, READOUT.shownText(rung))),
        el("div", {}, el("dt", {}, READOUT.imagined), el("dd", {}, READOUT.imaginedText(rung))),
        el("div", {}, el("dt", {}, READOUT.check), el("dd", {}, READOUT.checkText(rung))),
      );
      this.now.replaceChildren(head, dl);
    }
    this.notPlacedNote.hidden = rung.placed;
    this.framesNote.hidden = rung.frustums.length === 0;
    const model = chartModel(this.ladder, rung.id);
    const unplotted = model.missing.map((id) => this.ladder.rungs.find((r) => r.id === id)!.label);
    this.chart.innerHTML = `${chartSvg(model)}
      <figcaption>${unplotted.length ? `<p>${CHART.notPlotted(unplotted)}</p>` : ""}
        <p>${CHART.floor}</p>
        <p>${CHART.reconstruction} ${CHART.seeds}</p>
        <p><span aria-hidden="true">* </span>${CHART.scanReading}</p>
      </figcaption>`;
  }

  setStatus(text: string) {
    this.status.textContent = text;
  }

  setRedPen(on: boolean) {
    this.redPenButton.setAttribute("aria-pressed", String(on));
    this.root.dataset.red = on ? "1" : "0";
    this.mapLegend.dataset.red = on ? "1" : "0";
  }

  get rung() {
    return this.current;
  }
}

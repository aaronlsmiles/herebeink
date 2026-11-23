// Every sentence the ladder mode shows. Under the publication stance (plan §6, stance A) a number on this page
// is only ever a coverage number: how much the inputs showed, how much of a world is imagined, and how far the
// scan agrees with itself. Right and wrong are colour only (the red pen); words.test.ts guards it.
import type { LadderRung, RungId } from "./contract.ts";

export const LADDER = {
  /** The bar's switch into ladder mode, and its pressed state's hint. */
  chip: "Ladder",
  chipTitle: "Step through worlds Marble built from more and more of the room",
  heading: "What Marble saw",
  stepsLabel: "How much of the room Marble was shown",
  redPen: "Red pen",
  redPenTitle: "Mark in red the imagined parts that land away from where the scan puts the room. The scan is unsure in places too, so red can be its error, not Marble's",
  loading: (label: string) => `Loading ${label}…`,
  failed: "This world did not arrive. Try another step.",
  notPlaced: "Not placed",
  notPlacedText: "This world could not be set on the room, so it is neither drawn nor plotted. Its photos' frames still show.",
  reconstruction: "reconstruction mode",
  reconstructionText: "Marble laid the photos out itself.",
  chartTitle: "Shown against imagined",
} as const;

/** The control's own labels: "What Marble saw: 1 photo · 2 · 4 · 8 · the 360 still". */
export const STEP_LABEL: Record<RungId, string> = {
  R1: "1 photo", R2: "2", R4: "4", R4b: "4, seed 2", R8: "8", R4r: "4, rec.", P: "the 360 still",
};

/** A point's label on the chart: short, since the axes say the rest. */
export const POINT_LABEL: Record<RungId, string> = {
  R1: "1", R2: "2", R4: "4", R4b: "4 (seed 2)", R8: "8", R4r: "4 (rec.)", P: "360",
};

/** One label for both R4 seeds when their points nearly coincide. */
export const POINT_LABEL_BOTH_SEEDS = "4 (two seeds)";

/** The two rungs whose points rest on the scan's least certain part (frozen in STATUS: the chart's caption says so). */
export const SCAN_READING: readonly RungId[] = ["R1", "R2"];

/** A coverage share as the page writes it: one decimal under 10 %, whole numbers above. */
export function pct(share: number): string {
  const p = share * 100;
  if (p > 0 && p < 10) return `${p.toFixed(1)}%`;
  return `${Math.round(p)}%`;
}

export const READOUT = {
  shown: "Shown",
  shownText: (r: LadderRung) => `${pct(r.shown)} of the view from this spot`,
  imagined: "Imagined",
  imaginedText: (r: LadderRung) => (r.imagined === null ? "not measured" : `${pct(r.imagined)} of the scanned room, by direction`),
  check: "Scan's own check",
  checkText: (r: LadderRung) => {
    const { within15: a, within30: b } = r.keyAgreement;
    if (a === null && b === null) return "not available for this view";
    if (a === null) return `agrees within 30 cm in ${pct(b!)} of this view`;
    return `agrees within 15 cm in ${pct(a)} of this view${b === null ? "" : ` (${pct(b)} within 30 cm)`}`;
  },
};

/** A point's tooltip and accessible name: coverage only. */
export function pointTitle(r: LadderRung): string {
  const mode = r.mode === "reconstruction" ? `, ${LADDER.reconstruction}` : "";
  const base = `${r.label}${mode}: shown ${pct(r.shown)}, imagined ${r.imagined === null ? "not measured" : pct(r.imagined)}.`;
  const { within15: a } = r.keyAgreement;
  return a === null ? base : `${base} The scan agrees with itself in ${pct(a)} of this view.`;
}

export const CHART = {
  x: "Shown to Marble, share of all directions",
  y: "Imagined, share of the room",
  floor: "Dashed: a floor this measure cannot go below, the scanned room the photos did not show.",
  reconstruction: "Open rings: reconstruction mode, where Marble laid the photos out itself.",
  scanReading: "For 1 and 2 photos, the placing and the split rest on the part of the scan that agrees least with the camera survey, so those two points are the scan's own reading.",
  seeds: "4 photos is plotted twice, once for each seed.",
  notPlotted: (labels: string[]) => `Not placed, so not plotted: ${labels.join("; ")}.`,
};

export const LEGEND = {
  heading: "The ladder's key",
  seen: ["Seen", "shown to Marble, and kept where the room is"],
  imagined: ["Imagined", "made up beyond the photos"],
  wrong: ["Imagined and wrong", "made up, and away from where the scan puts the room (with the red pen on); where the scan is unsure, red can be the scan's error"],
  frames: ["Photo frames", "what each photo showed, from where it was taken"],
  line: ["Pen line", "where the seen floor ends"],
} as const;

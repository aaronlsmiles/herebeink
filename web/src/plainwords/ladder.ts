// "In plain words" for the ladder mode: Part 2's story for a bright 12-year-old, beside the ladder's own parts.
// Additive: it sits beside the walk's chapters and notes and changes none of them. ladder.test.ts holds the same
// rules as the walk's words (no digits, no figure without a source, field words only in quotes, the reading
// level, quoted labels that are the page's live labels), and one more: no share of right or wrong, ever.

export const LADDER_NOTES = {
  /** Beside the steps, at the top of the ladder's panel. */
  ladder: [
    "This is a second test, in the same room. I asked Marble to build my room again and again.",
    "Each time, I gave it more photos of the room, all taken from the same spot. The steps go from a single photo up to the whole round view.",
    "Where you see a photo, Marble was shown that part and kept it in the right place. Where you see a drawing, Marble made it up.",
  ],
  /** Under the step's readout, while the step's world is drawn. */
  frames: [
    "The thin pen lines that fan out from the middle show where each photo was pointing. Marble never saw anything outside them.",
  ],
  /** Beside the red pen switch. */
  redPen: [
    "Turn on \"Red pen\" and the made-up parts that ended up in the wrong place turn red, like a teacher marking homework.",
    "The black ink parts are made up too. But they landed where my real room is.",
  ],
  /** Above the chart. */
  chart: [
    "The little chart puts each world on its own dot. Further right, Marble was shown more of the room. Higher up, more of its world was made up.",
    "The dashed line is as low as a dot could go. It marks the part of the room the photos never showed.",
  ],
  /** Shown only on a step whose world could not be set on the room. */
  notPlaced: [
    "Sometimes the world Marble built would not line up with my room. Then the page can't tell which parts it saw, so it leaves that world out.",
  ],
  /** In the top bar's fold, under the Ladder switch's live label. */
  ladderButton: ["This switches to the second test: the same room, built again from more photos each time. Tap it again to go back to walking."],
} satisfies Record<string, string[]>;

export type LadderNoteId = keyof typeof LADDER_NOTES;

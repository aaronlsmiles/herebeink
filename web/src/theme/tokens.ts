export type Scheme = "light" | "dark";
export interface Tokens {
  paper: string;
  ink: string;
  /**
   * What shows where nothing was captured or imagined: the canvas behind every splat. Paper is the
   * drawing's own material, so a hole the capture missed would otherwise pass for drawing; this
   * flat grey is neither photograph nor ink. LOG.md records why this tone.
   */
  unscanned: string;
  /** The red pen: the ladder's imagined splats that landed wrong. A teacher's correction, so it reads as a mark, not a class of matter. */
  red: string;
}

export const TOKENS: Record<Scheme, Tokens> = {
  light: { paper: "#f4efe4", ink: "#1c1a17", unscanned: "#8f908c", red: "#b8322a" },
  dark: { paper: "#1c1a17", ink: "#e8e2d4", unscanned: "#5c5d5a", red: "#ff7a66" },
};

export function tokensFor(prefersDark: boolean): Tokens {
  return TOKENS[prefersDark ? "dark" : "light"];
}

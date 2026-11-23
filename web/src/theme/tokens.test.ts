import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { TOKENS, tokensFor } from "./tokens.ts";

describe("tokensFor", () => {
  it("returns the light pair on paper", () => {
    expect(tokensFor(false)).toEqual({ paper: "#f4efe4", ink: "#1c1a17", unscanned: "#8f908c", red: "#b8322a" });
  });
  it("swaps paper and ink in the dark scheme", () => {
    expect(tokensFor(true)).toEqual({ paper: "#1c1a17", ink: "#e8e2d4", unscanned: "#5c5d5a", red: "#ff7a66" });
  });
  it("keeps the unscanned tone apart from both paper and ink in each scheme", () => {
    const lum = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).reduce((a, b) => a + b, 0) / 3;
    for (const t of Object.values(TOKENS)) {
      expect(Math.abs(lum(t.unscanned) - lum(t.paper))).toBeGreaterThan(40);
      expect(Math.abs(lum(t.unscanned) - lum(t.ink))).toBeGreaterThan(40);
    }
  });
});

describe("tokens.css", () => {
  const css = readFileSync(resolve(import.meta.dirname, "tokens.css"), "utf8");
  const block = (start: number) => css.slice(start, css.indexOf("}", start));
  const light = block(css.indexOf(":root {"));
  const dark = block(css.indexOf(":root {", css.indexOf("prefers-color-scheme: dark")));

  it("carries the same values as the canvas, so the legend's swatches match what is drawn", () => {
    for (const [scheme, text] of [["light", light], ["dark", dark]] as const) {
      for (const [name, value] of Object.entries(TOKENS[scheme])) {
        expect(text).toContain(`--${name}: ${value};`);
      }
    }
  });
});

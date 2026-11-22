import { describe, expect, it } from "vitest";
import { addressWithoutPlain, layerAllowed, startMode, storeMode, STORE_KEY } from "./state.ts";

function memory(initial: Record<string, string> = {}) {
  const m = new Map(Object.entries(initial));
  return {
    writes: [] as [string, string][],
    getItem: (k: string) => m.get(k) ?? null,
    setItem(k: string, v: string) { this.writes.push([k, v]); m.set(k, v); },
  };
}

describe("layerAllowed", () => {
  it("is on for the page as published", () => {
    expect(layerAllowed({ coast: true, film: false })).toBe(true);
  });
  it("is off on the hallway link, where chapters 2 and 3 would say where the line falls", () => {
    expect(layerAllowed({ coast: false, film: false })).toBe(false);
  });
  it("is off for the film's recording path", () => {
    expect(layerAllowed({ coast: true, film: true })).toBe(false);
  });
});

describe("startMode", () => {
  it("asks (unset) on a first visit", () => {
    expect(startMode("", true, memory())).toBe("unset");
  });
  it("opens straight into the layer from ?plain=1, and remembers it", () => {
    const s = memory();
    expect(startMode("?plain=1", true, s)).toBe("on");
    expect(s.writes).toEqual([[STORE_KEY, "on"]]);
  });
  it("keeps the layer away from ?plain=0", () => {
    expect(startMode("?plain=0", true, memory({ [STORE_KEY]: "on" }))).toBe("off");
  });
  it("follows the reader's last choice when the link says nothing", () => {
    expect(startMode("", true, memory({ [STORE_KEY]: "on" }))).toBe("on");
    expect(startMode("", true, memory({ [STORE_KEY]: "off" }))).toBe("off");
    expect(startMode("", true, memory({ [STORE_KEY]: "maybe" }))).toBe("unset");
  });
  it("ignores ?plain=1 where the layer is not allowed, and stores nothing", () => {
    const s = memory();
    expect(startMode("?coast=off&plain=1", false, s)).toBeNull();
    expect(s.writes).toEqual([]);
  });
  it("still works when storage is unavailable or throws", () => {
    expect(startMode("?plain=1", true, null)).toBe("on");
    const throwing = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(startMode("", true, throwing)).toBe("unset");
    expect(startMode("?plain=1", true, throwing)).toBe("on");
    expect(() => storeMode(throwing, "off")).not.toThrow();
  });
});

describe("addressWithoutPlain", () => {
  it("drops ?plain= and keeps every other parameter", () => {
    expect(addressWithoutPlain("https://x.test/?plain=1&ink=off#a")).toBe("/?ink=off#a");
    expect(addressWithoutPlain("https://x.test/?ink=off&plain=0")).toBe("/?ink=off");
  });
  it("leaves an address without it alone", () => {
    expect(addressWithoutPlain("https://x.test/?ink=off")).toBeNull();
  });
});

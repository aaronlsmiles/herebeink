// Whether the plain-words layer is on, off, or still to be offered, and what a link or a past visit says about it.

/** unset: the invite shows; on: the bands and the notes; off: only the top-bar switch. */
export type PlainMode = "unset" | "on" | "off";
export const STORE_KEY = "herebeink-plain";

type Store = Pick<Storage, "getItem" | "setItem">;

/**
 * The hallway link (?coast=off) is the blind condition of the hallway test: chapters 2 and 3 and the
 * coastline note say where the line falls, so the layer is not there at all. The film records the
 * canvas alone.
 */
export function layerAllowed(p: { coast: boolean; film: boolean }) {
  return p.coast && !p.film;
}

export function storeMode(store: Store | null, m: "on" | "off") {
  try { store?.setItem(STORE_KEY, m); } catch { /* storage may be blocked: the choice lasts for this visit */ }
}

/** ?plain=1 or ?plain=0 wins (a link sent to someone), then the reader's last choice; null where the layer is not allowed. */
export function startMode(search: string, allowed: boolean, store: Store | null): PlainMode | null {
  if (!allowed) return null;
  const p = new URLSearchParams(search).get("plain");
  const asked = p === "1" ? "on" : p === "0" ? "off" : null;
  if (asked) { storeMode(store, asked); return asked; }
  try {
    const v = store?.getItem(STORE_KEY);
    if (v === "on" || v === "off") return v;
  } catch { /* fall through: ask */ }
  return "unset";
}

/** A reader's own click settles it, so the address drops ?plain= and a reload keeps what they chose. */
export function addressWithoutPlain(href: string): string | null {
  const u = new URL(href);
  if (!u.searchParams.has("plain")) return null;
  u.searchParams.delete("plain");
  return `${u.pathname}${u.search}${u.hash}`;
}

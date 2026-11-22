// The page's chrome: the survey's cartouche (title, statement, how to walk) and its controls,
// keyboard reachable, restyled through the tokens in theme/.

export const STATEMENT = [
  "Everything you can walk through here was either measured by a camera or imagined by a model.",
  "The photograph is what the camera measured.",
  "The drawing is what the model made up beyond it.",
];
export const PEN_LINE_SENTENCE = "The pen line on the floor is where one ends and the other begins.";
export const DEVICE_LINE = "Measured on an iPhone 15 Pro. Android phones are not supported yet.";
/**
 * The design pass's verdict on the ink (kill rule 2): it reads as a filter, so the page says so beside the ink
 * rather than hiding it. LOG.md, 22 Nov, has the five views it was judged at.
 */
export const FINDING = [
  "Here the ink reads as a filter, not a drawing.",
  "The scene's light runs straight down the imagined hallway, so the pen lays one even cross-hatch over every wall, and the door, picture and skirting board Marble gave it are only colour, which the ink leaves out.",
  "Once you walk in, flip “Imagined half” at the top to compare.",
];
/** The studio's shared words for the plain-words invite, the same on every studio site. */
export const PLAIN_INVITE = { label: "In plain words", lead: "New to this?", action: "Read it in plain words" };

type HintPart = string | { key: string };
interface Hint { term: string; parts: HintPart[] }
const key = (k: string) => ({ key: k });

const DESKTOP_HINTS: Hint[] = [
  { term: "Walk", parts: [key("W"), " ", key("A"), " ", key("S"), " ", key("D"), " or the arrow keys; hold ", key("Shift"), " to run."] },
  { term: "Look", parts: ["move the mouse once you are in; ", key("←"), " and ", key("→"), " turn too."] },
  { term: "Map", parts: [key("M"), " opens it; ", key("Esc"), " frees the mouse."] },
];
const TOUCH_HINTS: Hint[] = [
  { term: "Walk", parts: ["rest your left thumb on the screen and push the way you want to go."] },
  { term: "Look", parts: ["drag with another finger, or tap “Look by tilting the phone” once you are in."] },
  { term: "Map", parts: ["the Map button, top right once you are in."] },
];

export const PENCIL_SVG = `<svg class="pw-mark" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"><path d="M2.5 13.5 3.4 10 11 2.4a1.4 1.4 0 0 1 2 0l.6.6a1.4 1.4 0 0 1 0 2L6 12.6ZM9.6 3.8l2.6 2.6M3.4 10l2.6 2.6" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round" stroke-linecap="round"/></svg>`;

export interface Chrome {
  /** The first screen; the plain-words layer mounts beside the statement here. */
  intro: HTMLElement;
  bar: HTMLElement;
  walkIn: HTMLButtonElement;
  mapButton: HTMLButtonElement;
  showIntro(): void;
  hideIntro(): void;
  setStatus(text: string): void;
  /**
   * Shows the plain-words invite, which calls `open` when taken; null takes it away. The hallway
   * link (?coast=off) never shows it: the layer says where the line falls, which the walkers must
   * find for themselves.
   */
  offerPlainWords(open: (() => void) | null): void;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> & { className?: string } = {}, ...children: (Node | string)[]) {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...children);
  return e;
}

function hintList(hints: Hint[]) {
  return el("dl", { className: "hint" }, ...hints.map((h) => el("div", {},
    el("dt", {}, h.term),
    el("dd", {}, ...h.parts.map((p) => (typeof p === "string" ? p : el("kbd", {}, p.key)))),
  )));
}

/** On a touch screen the key folds away, so the first screen leaves more of the room in view; the thumb finds the walk anyway. */
function howToWalk(touch: boolean) {
  if (!touch) return hintList(DESKTOP_HINTS);
  return el("details", { className: "how" }, el("summary", {}, "How to walk"), hintList(TOUCH_HINTS));
}

export function buildChrome(root: HTMLElement, opts: { coast: boolean; credit: string; touch?: boolean; onWalkIn: () => void }): Chrome {
  const statement = el("p", { className: "statement" }, STATEMENT.join(" "));
  if (opts.coast) statement.append(" ", el("span", { className: "pen-line-sentence" }, PEN_LINE_SENTENCE));

  let plainOpen: (() => void) | null = null;
  const arrow = el("span", {}, "→");
  arrow.setAttribute("aria-hidden", "true");
  const inviteButton = el("button", { type: "button", className: "pw-btn" }, PLAIN_INVITE.action, " ", arrow);
  inviteButton.addEventListener("click", () => plainOpen?.());
  const invite = el("aside", { className: "pw-invite", hidden: true }, el("span", { className: "pw-lead" }, PLAIN_INVITE.lead), inviteButton);
  invite.setAttribute("aria-label", PLAIN_INVITE.label);
  invite.insertAdjacentHTML("afterbegin", PENCIL_SVG);

  const walkIn = el("button", { type: "button", className: "primary" }, "Walk in");
  const status = el("p", { className: "status" });
  status.setAttribute("role", "status");
  const intro = el("section", { className: "intro" },
    el("h1", { id: "intro-title" }, "Here Be Ink"),
    statement,
    invite,
    el("div", { className: "actions" }, walkIn, status),
    howToWalk(opts.touch ?? false),
    el("div", { className: "notes" },
      // Not on the hallway link: naming the hallway, or calling the ink a filter, would answer or prime the walkers' question.
      ...(opts.coast ? [el("p", { className: "small finding" }, FINDING.join(" "))] : []),
      el("p", { className: "small credit" }, opts.credit),
      el("p", { className: "small device" }, DEVICE_LINE),
    ),
  );
  intro.setAttribute("aria-labelledby", "intro-title");

  const about = el("button", { type: "button", className: "chip" }, "About");
  about.dataset.control = "about";
  const mapButton = el("button", { type: "button", className: "chip" }, "Map");
  mapButton.dataset.control = "map";
  mapButton.setAttribute("aria-pressed", "false");
  const bar = el("nav", { className: "bar" }, about, mapButton);
  bar.setAttribute("aria-label", "View controls");
  bar.hidden = true;
  root.append(intro, bar);

  const chrome: Chrome = {
    intro, bar, walkIn, mapButton,
    showIntro() { intro.hidden = false; walkIn.focus(); },
    hideIntro() { intro.hidden = true; bar.hidden = false; },
    setStatus(text) { status.textContent = text; },
    offerPlainWords(open) {
      plainOpen = opts.coast ? open : null;
      invite.hidden = plainOpen === null;
    },
  };
  walkIn.addEventListener("click", () => { chrome.hideIntro(); opts.onWalkIn(); });
  about.addEventListener("click", () => chrome.showIntro());
  return chrome;
}

/** Shown instead of the world when the browser cannot draw it, so nobody gets a blank page. */
export function showFatal(root: HTMLElement, title: string, detail: string) {
  root.replaceChildren(el("section", { className: "intro fatal" },
    el("h1", {}, "Here Be Ink"),
    el("p", { className: "statement" }, STATEMENT.join(" ")),
    el("h2", {}, title),
    el("p", {}, detail),
    el("p", { className: "small device" }, DEVICE_LINE),
  ));
  document.documentElement.dataset.fatal = "1";
}

/** WebGL2 with half-float colour buffers is what the ink pass needs; check before building anything. */
export function checkGraphics(): { ok: true } | { ok: false; title: string; detail: string } {
  const canvas = document.createElement("canvas");
  const gl = canvas.getContext("webgl2");
  if (!gl) {
    return { ok: false, title: "This browser cannot show the world", detail: "It needs WebGL 2, which this browser or device does not offer. A recent Safari, Chrome, Firefox or Edge will work." };
  }
  const floatTargets = gl.getExtension("EXT_color_buffer_half_float") ?? gl.getExtension("EXT_color_buffer_float");
  gl.getExtension("WEBGL_lose_context")?.loseContext();
  if (!floatTargets) {
    return { ok: false, title: "This device cannot draw the ink", detail: "The drawing needs floating-point render targets (EXT_color_buffer_half_float), which this browser does not offer." };
  }
  return { ok: true };
}

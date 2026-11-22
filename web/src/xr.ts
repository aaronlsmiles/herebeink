import { budgetFor, type Budget } from "./device.ts";
import type { Params } from "./params.ts";
import type { Viewer } from "./viewer.ts";
import { sessionSource, XrWalk } from "./walk-xr.ts";

export const XR_NOTE = "Not yet tried in a headset. In one, the photograph and the paper are drawn, but the outlines are drawn on screens, not yet in the headset.";

/** `?xr=mock` pretends a headset exists, so the button and the budget switch can be checked without one. */
async function xrSupported(mock: boolean): Promise<boolean> {
  if (mock) return true;
  try {
    return (await navigator.xr?.isSessionSupported("immersive-vr")) === true;
  } catch {
    return false;
  }
}

/**
 * The "Enter VR" control, added only when the browser says a headset session can start. Desktop
 * and phone pages never see it, and nothing here runs until it is clicked.
 */
export async function setupXr(viewer: Viewer, params: Pick<Params, "xr" | "lod" | "gscale">, mount: { bar: HTMLElement; intro: HTMLElement }) {
  const mock = params.xr === "mock";
  if (!(await xrSupported(mock))) return null;

  const button = Object.assign(document.createElement("button"), { type: "button", className: "chip", textContent: "Enter VR" });
  button.dataset.control = "xr";
  button.setAttribute("aria-pressed", "false");
  mount.bar.append(button);
  (mount.intro.querySelector(".notes") ?? mount.intro).append(Object.assign(document.createElement("p"), { className: "small xr-note", textContent: XR_NOTE }));

  const scene = viewer.sceneContract;
  const xrBudget = (): Budget => budgetFor({
    userAgent: navigator.userAgent, maxTouchPoints: navigator.maxTouchPoints, devicePixelRatio: window.devicePixelRatio, xr: true,
  }, params);
  const makeWalk = () => {
    const start = viewer.walk.pose();
    const source = mock ? { inputs: () => ({ left: [0, 0] as const, right: [0, 0] as const }), head: () => null } : sessionSource(viewer.renderer.xr);
    return new XrWalk(source, scene.walkable.polygons, scene.floor.y, { position: start.position, yaw: start.yaw });
  };
  const label = (inSession: boolean) => {
    button.textContent = inSession ? "Exit VR" : "Enter VR";
    button.setAttribute("aria-pressed", String(inSession));
  };

  let session: XRSession | null = null;
  const leave = () => {
    viewer.renderer.xr.enabled = false;
    viewer.setXr(null);
    session = null;
    label(false);
  };

  // three's own end handler runs first and clears isPresenting, so the canvas can be resized back here.
  viewer.renderer.xr.addEventListener("sessionend", () => { if (viewer.xrActive) leave(); });

  button.addEventListener("click", async () => {
    if (viewer.xrActive) {
      if (session) await session.end().catch(() => {});
      else leave();
      return;
    }
    if (mock) { viewer.setXr({ budget: xrBudget(), walk: makeWalk() }); label(true); return; }
    try {
      // Asked for first, straight from the click, since browsers only grant a session to a gesture.
      session = await navigator.xr!.requestSession("immersive-vr", { requiredFeatures: ["local-floor"], optionalFeatures: ["bounded-floor"] });
      viewer.setXr({ budget: xrBudget(), walk: makeWalk() });
      viewer.renderer.xr.enabled = true;
      viewer.renderer.xr.setReferenceSpaceType("local-floor");
      await viewer.renderer.xr.setSession(session);
      label(true);
    } catch (e) {
      console.warn("The headset session did not start", e);
      if (viewer.xrActive) leave();
      session = null;
    }
  });
  return button;
}

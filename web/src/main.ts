import * as THREE from "three";
import "./theme/tokens.css";
import "./theme/page.css";
import { budgetFor, measuredKeyFor } from "./device.ts";
import { ContractError } from "./contract.ts";
import { Hud } from "./hud.ts";
import { InkSwitch } from "./inkswitch.ts";
import { parseParams } from "./params.ts";
import { mountPlainWords } from "./plainwords/layer.ts";
import { layerAllowed } from "./plainwords/state.ts";
import { loadScene } from "./scene.ts";
import { tokensFor } from "./theme/tokens.ts";
import { buildChrome, checkGraphics, showFatal } from "./ui.ts";
import { runFilm } from "./film.ts";
import { Viewer } from "./viewer.ts";
import { setupXr } from "./xr.ts";

const root = document.getElementById("app")!;
const params = parseParams(location.search, import.meta.env.VITE_SCENE_URL as string | undefined, {
  production: import.meta.env.PROD,
  origin: location.origin,
});
const dark = window.matchMedia("(prefers-color-scheme: dark)");

async function boot() {
  const gfx = checkGraphics();
  if (!gfx.ok) { showFatal(root, gfx.title, gfx.detail); return; }

  document.documentElement.dataset.sceneFetch = performance.now().toFixed(0);
  let loaded;
  try {
    loaded = await loadScene(params.sceneUrl);
  } catch (e) {
    const detail = e instanceof ContractError ? e.message : `The scene could not be loaded: ${(e as Error).message}`;
    showFatal(root, "The world did not arrive", detail);
    console.warn(e);
    return;
  }
  const s = loaded.scene;
  const budget = budgetFor({
    userAgent: navigator.userAgent, maxTouchPoints: navigator.maxTouchPoints,
    devicePixelRatio: params.size ? 1 : window.devicePixelRatio, xr: false,
  }, params);
  const startPose = params.pose ?? s.start;
  const viewer = new Viewer({
    loaded, budget, tokens: tokensFor(dark.matches), ink: params.ink, coast: params.coast, debug: params.debug, walk: params.walk, fixedSize: params.size, container: root,
    measuredFile: measuredKeyFor(budget.deviceClass, s.splats.measuredPhone !== undefined, params.measured),
    start: {
      position: new THREE.Vector3(...startPose.position),
      yaw: THREE.MathUtils.degToRad(startPose.yawDeg),
      pitch: THREE.MathUtils.degToRad(startPose.pitchDeg),
    },
  });
  dark.addEventListener("change", () => viewer.setTokens(tokensFor(dark.matches)));

  // A browser can take the graphics memory back at any moment (a phone put to sleep, a driver reset).
  // Nothing drawn after that would show, and a restored context has none of the splats' textures, so
  // the page says so and starts again rather than going on drawing into nothing.
  const canvas = viewer.renderer.domElement;
  canvas.addEventListener("webglcontextlost", (e) => {
    e.preventDefault();
    viewer.stop();
    showFatal(root, "The picture stopped", "The browser took back the graphics memory this page was using. Reload the page to walk in again.");
  });
  canvas.addEventListener("webglcontextrestored", () => location.reload());

  const chrome = buildChrome(root, { coast: params.coast, credit: s.credit, touch: viewer.walkMode === "touch", onWalkIn: () => viewer.walk.engage() });
  const inkSwitch = new InkSwitch(params.ink, (on) => viewer.setInk(on));
  chrome.bar.append(inkSwitch.button);
  const plain = mountPlainWords({
    root, chrome, viewer, coastline: loaded.coastline, doorOutward: s.door.outward,
    search: location.search, allowed: layerAllowed(params),
  });
  // The button follows the map however it closes, including by entering a headset.
  viewer.onMapChange = (open) => {
    chrome.mapButton.setAttribute("aria-pressed", String(open));
    plain?.mapChanged(open);
  };
  // A keyboard toggle answers at once; the key is laid down with a short move only when the button opens the map.
  const toggleMap = (via: "key" | "pointer") => {
    viewer.map.root.dataset.via = via;
    viewer.setMap(!viewer.mapOn);
  };
  chrome.mapButton.addEventListener("click", () => toggleMap("pointer"));
  window.addEventListener("keydown", (e) => {
    if (e.code === "KeyM" && !e.repeat && !e.metaKey && !e.ctrlKey && !e.altKey) toggleMap("key");
  });
  if (params.map) toggleMap("key");

  chrome.setStatus("Loading the room…");
  plain?.setLoading(true);
  void viewer.world.firstSplats.then(() => chrome.setStatus("The room is here; the rest is on its way."));
  viewer.world.complete.then(
    () => { chrome.setStatus(""); plain?.setLoading(false); },
    (e: unknown) => { chrome.setStatus("Part of the world failed to load."); plain?.setLoading(false); console.warn(e); },
  );

  const hud = params.hud && !params.film ? new Hud(root, () => viewer.hudNumbers()) : null;
  if (hud) {
    const tick = () => { hud.tick(performance.now()); requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  if (!params.film) void setupXr(viewer, params, { bar: chrome.bar, intro: chrome.intro });

  if (params.film) {
    // A recording path: no chrome, no loop; the film module steps the viewer frame by frame.
    document.documentElement.dataset.film = "1";
    chrome.hideIntro();
    chrome.bar.hidden = true;
    runFilm(viewer, { dump: params.dump, set: params.frameSet, range: params.frameRange }).catch((e: unknown) => {
      document.documentElement.dataset.filmError = (e as Error).message;
      console.error(e);
    });
  } else {
    viewer.start();
  }

  if (import.meta.env.DEV) {
    (window as unknown as { __hbi: unknown }).__hbi = {
      viewer, chrome, inkSwitch, params,
      setPose: (x: number, y: number, z: number, yawDeg: number, pitchDeg: number) =>
        viewer.walk.setPose({ position: { x, y, z }, yaw: THREE.MathUtils.degToRad(yawDeg), pitch: THREE.MathUtils.degToRad(pitchDeg) }),
      setParts: (p: Partial<typeof viewer.ink.parts>) => { Object.assign(viewer.ink.parts, p); viewer.ink.applyParts(); },
      frame: () => viewer.frameCount,
      // The flag target as coverage-weighted flag bytes, for the e2e checks of where ink falls.
      readFlag: () => {
        const t = viewer.data.flagTarget;
        const px = new Uint8Array(t.width * t.height * 4);
        viewer.renderer.readRenderTargetPixels(t, 0, 0, t.width, t.height, px);
        return { width: t.width, height: t.height, rgba: Array.from(px) };
      },
      hud: () => viewer.hudNumbers(),
    };
  }
}

void boot();

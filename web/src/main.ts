import * as THREE from "three";
import "./theme/tokens.css";
import "./theme/page.css";
import { budgetFor, measuredKeyFor } from "./device.ts";
import { ContractError } from "./contract.ts";
import { Hud } from "./hud.ts";
import { InkSwitch } from "./inkswitch.ts";
import { ladderUrlFor, parseParams } from "./params.ts";
import { rungById } from "./ladder/contract.ts";
import { LadderMode, loadLadder } from "./ladder/mode.ts";
import { RungWorld } from "./ladder/world.ts";
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
  // The ladder is offered only where its file is published and valid; a page without one is Part 1 as it was.
  const ladderUrl = ladderUrlFor(params.sceneUrl, import.meta.env.VITE_LADDER_URL as string | undefined, location.origin);
  // Not on the hallway link either: the ladder draws where the measuring stops, which those walkers must find.
  const ladderLoad = params.film || !params.coast ? Promise.resolve(null) : loadLadder(ladderUrl).catch((e: unknown) => {
    if (params.ladder) console.warn(e);
    return null;
  });
  // Opened straight into the ladder, the page waits for it, so Part 1's files are never fetched.
  const ladderFirst = params.ladder ? await ladderLoad : null;
  let loaded;
  try {
    loaded = await loadScene(params.sceneUrl, location.href, { preview: !ladderFirst });
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
    world: ladderFirst
      ? (three, hooks) => new RungWorld(three, ladderFirst.ladder.rungs[0], undefined, ladderFirst.base, hooks)
      : undefined,
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
  const ladderReady = await (ladderFirst ? Promise.resolve(ladderFirst) : Promise.race([ladderLoad, Promise.resolve(null)]));
  let ladder: LadderMode | null = null;
  const mountLadder = (l: NonNullable<typeof ladderReady>) => {
    ladder = new LadderMode({
      viewer, chrome, root, ladder: l.ladder, base: l.base, phone: budget.deviceClass === "phone",
      redPen: params.redPen, coastline: loaded.coastline,
    });
    return ladder;
  };
  if (ladderReady) mountLadder(ladderReady);
  // A ladder that arrives after the first screen still gets its switch.
  else void ladderLoad.then((l) => { if (l && !ladder) mountLadder(l); });
  if (params.ladder && ladderFirst) {
    const asked = params.ladder === "first" || rungById(ladderFirst.ladder, params.ladder) ? params.ladder : "first";
    ladder!.enter(asked, { standAtCamera: params.pose === null });
    viewer.walk.engage();
  } else if (params.ladder) {
    chrome.setStatus("The ladder could not be loaded, so this is the walk.");
  }
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
      viewer, chrome, inkSwitch, params, ladder: () => ladder,
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

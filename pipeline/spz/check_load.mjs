// Loads a scene folder (scene.json and its splat files) in Spark, in headless Chromium, the way the viewer
// will: each file as a SplatMesh with its matrix. Prints the splats Spark decoded per file and saves a
// screenshot from the start pose.
//   node spz/check_load.mjs SCENE_DIR OUT.png [WIDTH HEIGHT]
// Uses web/'s own Spark, three and Playwright (read only).
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { writeFileSync } from "node:fs";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const nm = resolve(here, "../../web/node_modules");
const [sceneDir, outPng, w = "1280", h = "720"] = process.argv.slice(2);
const { chromium } = await import(join(nm, "playwright/index.mjs"));

const page = `<!doctype html><html><body style="margin:0;background:#f4efe4">
<script type="importmap">{"imports":{"three":"/nm/three/build/three.module.js","three/addons/":"/nm/three/examples/jsm/",
"@sparkjsdev/spark":"/nm/@sparkjsdev/spark/dist/spark.module.js"}}</script>
<script type="module">
import * as THREE from "three";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
const scene = await (await fetch("/scene/scene.json")).json();
const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true });
renderer.setSize(${w}, ${h}); renderer.setClearColor(0xf4efe4);
document.body.appendChild(renderer.domElement);
const world = new THREE.Scene();
const spark = new SparkRenderer({ renderer }); world.add(spark);
const camera = new THREE.PerspectiveCamera(70, ${w} / ${h}, 0.02, 100);
const s = scene.start;
camera.position.fromArray(s.position);
camera.rotation.set(THREE.MathUtils.degToRad(s.pitchDeg), THREE.MathUtils.degToRad(s.yawDeg), 0, "YXZ");
const counts = {};
for (const key of ["measured", "overlap", "imagined", ...(scene.splats.measuredPhone ? ["measuredPhone"] : [])]) {
  const f = scene.splats[key];
  const mesh = new SplatMesh({ url: "/scene/" + f.url });
  await mesh.initialized;
  const m = new THREE.Matrix4().fromArray(f.matrix);
  m.decompose(mesh.position, mesh.quaternion, mesh.scale);
  world.add(mesh);
  counts[key] = (mesh.packedSplats ?? mesh.extSplats).numSplats;
}
const preview = new SplatMesh({ url: "/scene/" + scene.splats.measuredPreview.url });
await preview.initialized;
counts.measuredPreview = (preview.packedSplats ?? preview.extSplats).numSplats;
let n = 0;
await new Promise((res) => { const f = () => { renderer.render(world, camera); if (++n >= 60) res(); else requestAnimationFrame(f); }; requestAnimationFrame(f); });
window.__result = counts;
document.documentElement.dataset.ready = "1";
</script></body></html>`;

const types = { ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json", ".wasm": "application/wasm" };
const server = createServer(async (req, res) => {
  const url = decodeURIComponent(req.url.split("?")[0]);
  try {
    if (url === "/") { res.writeHead(200, { "content-type": "text/html" }); res.end(page); return; }
    const file = url.startsWith("/nm/") ? join(nm, url.slice(4)) : url.startsWith("/scene/") ? join(sceneDir, url.slice(7)) : null;
    if (!file) throw new Error("not found");
    const body = await readFile(file);
    res.writeHead(200, { "content-type": types[extname(file)] ?? "application/octet-stream" });
    res.end(body);
  } catch { res.writeHead(404); res.end(); }
}).listen(0);
const port = server.address().port;
// Headless Chromium has no GPU; SwiftShader gives the software WebGL2 context Spark needs (as web/e2e does).
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const tab = await browser.newPage({ viewport: { width: Number(w), height: Number(h) } });
const errors = [];
tab.on("pageerror", (e) => errors.push(e.message));
try {
  await tab.goto(`http://localhost:${port}/`);
  await tab.waitForSelector("html[data-ready='1']", { timeout: 180_000 });
  const counts = await tab.evaluate(() => window.__result);
  writeFileSync(outPng, await tab.screenshot());
  console.log(JSON.stringify({ counts, errors }));
} finally {
  await browser.close();
  server.close();
}

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import "./theme/tokens.css";
import { tokensFor } from "./theme/tokens.ts";

const dark = window.matchMedia("(prefers-color-scheme: dark)");

// Spark's docs ask for antialias: false; splats are sorted and blended per pixel, so MSAA buys nothing.
const renderer = new THREE.WebGLRenderer({ antialias: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setClearColor(tokensFor(dark.matches).paper);
document.body.appendChild(renderer.domElement);
dark.addEventListener("change", () => renderer.setClearColor(tokensFor(dark.matches).paper));

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.01, 1000);
camera.position.set(0, 0, 0);

const spark = new SparkRenderer({ renderer });
scene.add(spark);

const mesh = new SplatMesh({ url: "/sample/butterfly.spz" });
// Splat files are authored y-down; a half-turn about x stands the sample upright.
mesh.quaternion.set(1, 0, 0, 0);
mesh.position.set(0, 0, -3);
scene.add(mesh);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.copy(mesh.position);
controls.enableDamping = true;

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

let loaded = false;
void mesh.initialized.then(() => { loaded = true; });

renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(scene, camera);
  // Set after a frame has been drawn with the splat in place, so tests never read a blank canvas.
  if (loaded && document.documentElement.dataset.ready !== "1") {
    document.documentElement.dataset.ready = "1";
  }
});

if (import.meta.env.DEV) {
  (window as unknown as { __hbi: unknown }).__hbi = { renderer, scene, camera, spark, mesh };
}

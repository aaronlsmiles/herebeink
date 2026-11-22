// Cuts the film from film/edl.json: the dumped frame sets, the page shots, an optional headset clip, and captions
// set in Geist as PNGs (Homebrew's ffmpeg has neither libass nor drawtext), burned in and written as WebVTT and SRT.
// Usage: node tools/film-cut.mjs [--aspect 16x9|9x16|both] [--no-check] [--crf 23] [--only id,id (a draft of some segments, to film/out/draft-*)]
// Segments are cut at CRF 16 and joined into a master in film/frames/cut/<aspect>/; the film itself is that master
// encoded once more at --crf for the web (23 keeps the pen lines; the paper's grain is what costs bits).
// Outputs in film/out/ (gitignored): herebeink-<aspect>.mp4, herebeink.vtt, herebeink.srt, herebeink-poster.png and .jpg,
// herebeink-loop.mp4 (silent, uncaptioned, for the portfolio card) and a contact sheet per aspect.
// No audio track: the film is silent until Aaron's own music is laid in (film/README.md).
import { chromium } from "@playwright/test";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "..");
const repoRoot = resolve(webRoot, "..");
const framesRoot = resolve(repoRoot, "film/frames");
const outDir = resolve(repoRoot, "film/out");
const work = resolve(framesRoot, "cut");

const argv = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] !== undefined ? argv[i + 1] : fallback;
};
const edl = JSON.parse(readFileSync(resolve(repoRoot, "film/edl.json"), "utf8"));
const FPS = edl.fps;
const aspects = opt("aspect", "both") === "both" ? Object.keys(edl.aspects) : [opt("aspect")];
const check = !argv.includes("--no-check");
const only = opt("only", null)?.split(",") ?? null;
const crf = opt("crf", "23");

const INK = "#1c1915", PAPER = "#ecebe6", MUTED = "#a8a297", GOLD = "#bf9032", GOLD_RGB = [191, 144, 50];
// A page set from a string cannot load file: URLs, so the faces travel inside it.
const font = (f) => `data:font/woff2;base64,${readFileSync(resolve(webRoot, "public/fonts", f)).toString("base64")}`;

function ff(args, what) {
  const r = spawnSync("ffmpeg", ["-hide_banner", "-v", "error", "-y", ...args], { encoding: "utf8", maxBuffer: 1 << 26 });
  if (r.status !== 0) throw new Error(`ffmpeg failed (${what}):\n${r.stderr}`);
  return r.stderr;
}

function probeSeconds(file) {
  const r = spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file], { encoding: "utf8" });
  return Number(r.stdout.trim());
}

const pad = (n) => String(n).padStart(5, "0");
const setDir = (aspect, set) => resolve(framesRoot, `${aspect}-${set}`);
const stillsDir = (aspect) => resolve(framesRoot, "stills", aspect);

/** Each segment's source, its length in seconds, or null when an optional source is missing. */
function sourceOf(seg, aspect) {
  const s = seg.src;
  if (s.frames) {
    const dir = setDir(aspect, s.frames);
    for (const n of [s.from, s.to - 1]) if (!existsSync(resolve(dir, `${pad(n)}.png`))) throw new Error(`${seg.id}: ${dir}/${pad(n)}.png is missing; dump the "${s.frames}" shot first`);
    return { kind: "frames", dir, from: s.from, count: s.to - s.from, dur: (s.to - s.from) / FPS };
  }
  if (s.wipe) {
    const w = s.wipe;
    const a = setDir(aspect, w.a), b = setDir(aspect, w.b);
    for (const d of [a, b]) for (const n of [w.from, w.to - 1]) if (!existsSync(resolve(d, `${pad(n)}.png`))) throw new Error(`${seg.id}: ${d}/${pad(n)}.png is missing`);
    return { kind: "wipe", a, b, from: w.from, count: w.to - w.from, dur: (w.to - w.from) / FPS, moves: w.moves };
  }
  if (s.still) {
    const file = resolve(stillsDir(aspect), `${s.still}.png`);
    if (!existsSync(file)) throw new Error(`${seg.id}: ${file} is missing; run tools/film-shots.mjs`);
    return { kind: "still", file, dur: s.dur };
  }
  if (s.seq) {
    const dir = resolve(stillsDir(aspect), s.seq);
    const n = existsSync(dir) ? readdirSync(dir).filter((f) => /^\d{5}\.png$/.test(f)).length : 0;
    if (n === 0) throw new Error(`${seg.id}: no frames in ${dir}; run tools/film-shots.mjs`);
    return { kind: "seq", dir, from: 0, count: n, dur: n / FPS };
  }
  if (s.video) {
    const file = resolve(repoRoot, s.video);
    if (!existsSync(file)) {
      if (seg.optional) return null;
      throw new Error(`${seg.id}: ${file} is missing`);
    }
    return { kind: "video", file, dur: Math.min(probeSeconds(file), s.maxDur ?? Infinity) };
  }
  if (s.card) return { kind: "card", card: s.card, dur: s.dur };
  throw new Error(`${seg.id}: unknown source`);
}

/** A segment's captions cut to its length: a headset clip shorter than its slot must not carry words past its end. */
function fit(captions, dur) {
  return (captions ?? []).filter((c) => c.t0 < dur - 0.5).map((c) => ({ ...c, t1: Math.min(c.t1, dur - 0.1) }));
}

// ---------------------------------------------------------------- text: HTML set in Geist, shot with Playwright

function css(aspect) {
  const v = aspect === "9x16";
  return `
@font-face { font-family: 'Geist'; src: url('${font("geist-latin.woff2")}') format('woff2'); font-weight: 100 900; }
@font-face { font-family: 'Geist Mono'; src: url('${font("geist-mono-latin.woff2")}') format('woff2'); font-weight: 100 900; }
html, body { margin: 0; background: transparent; }
* { box-sizing: border-box; }
.cap { position: absolute; background: rgba(28, 25, 21, 0.94); color: ${PAPER}; border-left: 4px solid ${GOLD};
       padding: 18px 30px 22px 26px; max-width: 1180px; }
.cap.left { left: 88px; bottom: 76px; }
.cap.right { right: 88px; bottom: 76px; }
.label { font: 500 17px/1 'Geist Mono', monospace; letter-spacing: 0.08em; text-transform: uppercase; color: ${MUTED}; margin-bottom: 11px; }
.text { font: 500 38px/1.24 'Geist', sans-serif; letter-spacing: -0.01em; text-wrap: balance; }
.band { position: absolute; left: 0; width: 1080px; padding: 0 64px; display: flex; flex-direction: column; justify-content: center; }
.band .label { font-size: 22px; margin-bottom: 16px; }
.band .rule { width: 56px; height: 3px; background: ${GOLD}; margin-bottom: 22px; }
.band .text { font-size: 46px; line-height: 1.22; color: ${PAPER}; }
.top { font: 500 26px/1 'Geist Mono', monospace; letter-spacing: 0.12em; text-transform: uppercase; color: ${PAPER}; }
.card { position: absolute; inset: 0; background: ${PAPER}; color: ${INK}; display: flex; flex-direction: column; justify-content: center;
        padding: ${v ? "0 80px" : "0 160px"}; }
.card h1 { font: 600 ${v ? 104 : 120}px/1 'Geist', sans-serif; letter-spacing: -0.035em; margin: 0 0 22px; }
.card .sub { font: 400 ${v ? 34 : 36}px/1.3 'Geist', sans-serif; color: #4a453d; margin: 0 0 ${v ? 56 : 48}px; max-width: 1200px; }
.card .url { font: 500 ${v ? 34 : 34}px/1 'Geist Mono', monospace; padding-bottom: 10px; border-bottom: 3px solid #8f6410; align-self: flex-start; margin-bottom: ${v ? 80 : 64}px; }
.card .credits { font: 400 ${v ? 25 : 23}px/1.5 'Geist', sans-serif; color: #4a453d; max-width: ${v ? 920 : 1300}px; }
.card .credits p { margin: 0 0 6px; }
`;
}

const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function captionHtml(aspect, c) {
  const A = edl.aspects[aspect];
  if (aspect === "9x16") {
    const top = A.at[1] + A.frame[1];
    return `<div class="band" style="top:${top}px;height:${A.size[1] - top}px"><div class="rule"></div><div class="label">${esc(c.label)}</div><div class="text">${esc(c.text)}</div></div>`;
  }
  return `<div class="cap ${c.side ?? "left"}"><div class="label">${esc(c.label)}</div><div class="text">${esc(c.text)}</div></div>`;
}

function topBandHtml(aspect) {
  const A = edl.aspects[aspect];
  return `<div class="band top" style="top:0;height:${A.at[1]}px">${esc(edl.title)}</div>`;
}

function cardHtml() {
  const e = edl.end;
  return `<div class="card"><h1>${esc(e.title)}</h1><p class="sub">${esc(e.sub)}</p><div class="url">${esc(edl.url)}</div>
    <div class="credits">${e.credits.map((c) => `<p>${esc(c)}</p>`).join("")}</div></div>`;
}

/** Renders each distinct piece of text once per aspect, as a full-frame PNG with a transparent ground. */
async function renderText(browser, aspect, html) {
  const [w, h] = edl.aspects[aspect].size;
  const doc = `<!doctype html><meta charset="utf-8"><style>${css(aspect)}</style><body style="width:${w}px;height:${h}px;position:relative">${html}</body>`;
  const key = createHash("sha256").update(doc).digest("hex").slice(0, 16);
  const dir = resolve(work, "text", aspect);
  mkdirSync(dir, { recursive: true });
  const file = resolve(dir, `${key}.png`);
  if (existsSync(file)) return file;
  const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  await page.setContent(doc);
  // A face no element uses is never fetched, so both are asked for by name before the check.
  const faces = await page.evaluate(async () => {
    await Promise.all(["Geist", "Geist Mono"].map((f) => document.fonts.load(`16px '${f}'`)));
    return ["Geist", "Geist Mono"].map((f) => document.fonts.check(`16px '${f}'`));
  });
  if (faces.includes(false)) throw new Error("Geist did not load for the captions");
  await page.screenshot({ path: file, omitBackground: true });
  await page.close();
  return file;
}

// ---------------------------------------------------------------- the wipe: a divider position as an ffmpeg expression of T

function dividerExpr(moves) {
  // u: the share of the width showing b. Smoothstep between t0 and t1, held between moves.
  let expr = String(moves[moves.length - 1].to);
  for (let i = moves.length - 1; i >= 0; i--) {
    const m = moves[i];
    const before = i === 0 ? String(m.from) : String(moves[i - 1].to);
    const s = `clip((T-${m.t0})/${m.t1 - m.t0},0,1)`;
    const ease = `(${s}*${s}*(3-2*${s}))`;
    expr = `if(lt(T,${m.t0}),${before},if(lt(T,${m.t1}),${m.from}+${m.to - m.from}*${ease},${expr}))`;
  }
  return expr;
}

function wipeFilter(moves) {
  const u = dividerExpr(moves);
  const inMove = moves.map((m) => `between(T,${m.t0},${m.t1})`).join("+");
  // gbrp planes are G, B, R; the divider is drawn only while it moves.
  const plane = (c) => `'if(gt(${inMove},0)*lt(abs(X-W*(${u})),2),${c},if(lt(X,W*(${u})),B,A))'`;
  return `blend=c0_expr=${plane(GOLD_RGB[1])}:c1_expr=${plane(GOLD_RGB[2])}:c2_expr=${plane(GOLD_RGB[0])}`;
}

// ---------------------------------------------------------------- one segment to one mp4

async function cutSegment(browser, aspect, seg, src, idx, opts) {
  const A = edl.aspects[aspect];
  const [W, H] = A.size, [FW, FH] = A.frame, [AX, AY] = A.at;
  const frames = Math.round(src.dur * FPS);
  const inputs = [];
  const graph = [];
  let pic;
  const add = (...a) => { inputs.push(...a); return inputs.filter((x) => x === "-i").length - 1; };

  if (src.kind === "frames" || src.kind === "seq") {
    const i = add("-framerate", String(FPS), "-start_number", String(src.from), "-i", resolve(src.dir, "%05d.png"));
    graph.push(`[${i}:v]scale=${FW}:${FH}:flags=lanczos,setsar=1,format=rgb24[pic]`);
  } else if (src.kind === "wipe") {
    const a = add("-framerate", String(FPS), "-start_number", String(src.from), "-i", resolve(src.a, "%05d.png"));
    const b = add("-framerate", String(FPS), "-start_number", String(src.from), "-i", resolve(src.b, "%05d.png"));
    graph.push(`[${a}:v]scale=${FW}:${FH},format=gbrp[wa];[${b}:v]scale=${FW}:${FH},format=gbrp[wb];[wa][wb]${wipeFilter(src.moves)},format=rgb24[pic]`);
  } else if (src.kind === "still") {
    const i = add("-loop", "1", "-framerate", String(FPS), "-t", String(src.dur), "-i", src.file);
    graph.push(`[${i}:v]scale=${FW}:${FH}:flags=lanczos,setsar=1,format=rgb24[pic]`);
  } else if (src.kind === "video") {
    const i = add("-t", String(src.dur), "-i", src.file);
    graph.push(`[${i}:v]fps=${FPS},scale=${FW}:${FH}:force_original_aspect_ratio=increase,crop=${FW}:${FH},setsar=1,format=rgb24[pic]`);
  } else if (src.kind === "card") {
    const i = add("-loop", "1", "-framerate", String(FPS), "-t", String(src.dur), "-i", await renderText(browser, aspect, cardHtml()));
    graph.push(`[${i}:v]format=rgb24[pic]`);
  }
  pic = "pic";

  // The picture on its ground: all of 16:9; in 9:16 a 4:5 window between two ink bands.
  if (src.kind === "card" || (W === FW && H === FH)) {
    graph.push(`[${pic}]null[base0]`);
  } else {
    const bg = add("-f", "lavfi", "-i", `color=c=${INK}:s=${W}x${H}:r=${FPS}:d=${src.dur}`);
    const top = add("-loop", "1", "-framerate", String(FPS), "-t", String(src.dur), "-i", await renderText(browser, aspect, topBandHtml(aspect)));
    graph.push(`[${bg}:v]format=rgb24[bg];[bg][${pic}]overlay=${AX}:${AY}:shortest=1[bp];[bp][${top}:v]overlay=0:0[base0]`);
  }

  let last = "base0";
  fit(seg.captions, src.dur).forEach((c, k) => {
    const png = opts.captions[k];
    const i = add("-loop", "1", "-framerate", String(FPS), "-t", String(src.dur), "-i", png);
    const fade = 0.25;
    graph.push(`[${i}:v]format=rgba,fade=t=in:st=${c.t0}:d=${fade}:alpha=1,fade=t=out:st=${Math.max(c.t0, c.t1 - fade)}:d=${fade}:alpha=1[c${k}]`);
    graph.push(`[${last}][c${k}]overlay=0:0:format=auto[o${k}]`);
    last = `o${k}`;
  });

  const fades = [];
  if (seg.fadeIn) fades.push(`fade=t=in:st=0:d=${seg.fadeIn}:color=${PAPER}`);
  if (seg.fadeOut) fades.push(`fade=t=out:st=${src.dur - seg.fadeOut}:d=${seg.fadeOut}:color=${PAPER}`);
  graph.push(`[${last}]${fades.length ? fades.join(",") + "," : ""}format=yuv420p[out]`);

  const file = resolve(work, aspect, `${String(idx).padStart(2, "0")}-${seg.id}.mp4`);
  mkdirSync(dirname(file), { recursive: true });
  ff([...inputs, "-filter_complex", graph.join(";"), "-map", "[out]", "-frames:v", String(frames), "-r", String(FPS),
    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-an", file], `${aspect} ${seg.id}`);
  return { file, frames };
}

// ---------------------------------------------------------------- checks on the frame sets: blank paper, pops, unsettled frames

function frameStats(dir, from, count) {
  const r = spawnSync("ffmpeg", ["-hide_banner", "-v", "error", "-framerate", String(FPS), "-start_number", String(from), "-i", resolve(dir, "%05d.png"),
    "-frames:v", String(count), "-vf", "scale=480:-2,signalstats,metadata=print:file=-", "-f", "null", "-"], { encoding: "utf8", maxBuffer: 1 << 28 });
  const rows = [];
  let cur = null;
  for (const line of r.stdout.split("\n")) {
    if (line.startsWith("frame:")) { cur = {}; rows.push(cur); }
    const m = line.match(/lavfi\.signalstats\.(YDIF|YLOW|YHIGH|YAVG)=([\d.]+)/);
    if (m && cur) cur[m[1]] = Number(m[2]);
  }
  return rows;
}

/**
 * A frame is suspect when it is nearly one flat tone (blank paper or fog: the camera inside a wall), or when its change
 * from the frame before is far above the changes around it (a pop: splats arriving late, a level-of-detail cut
 * switching). A steady pan changes every frame a lot, so the bar is the local median, not the whole set's.
 */
function checkSet(name, dir, from, count) {
  const rows = frameStats(dir, from, count);
  const problems = [];
  const difs = rows.map((r) => r.YDIF ?? 0);
  const W = 8;
  rows.forEach((r, k) => {
    const n = from + k;
    if (r.YHIGH - r.YLOW < 12) problems.push(`${name} ${pad(n)}: flat (Y ${r.YLOW}-${r.YHIGH})`);
    if (k === 0) return;
    const near = difs.slice(Math.max(1, k - W), k + W + 1).filter((_, i) => Math.max(1, k - W) + i !== k).sort((a, b) => a - b);
    const local = near[Math.floor(near.length / 2)] ?? 0;
    if (difs[k] > Math.max(2, 2.5 * local)) problems.push(`${name} ${pad(n)}: pops (changes ${difs[k].toFixed(1)}; around it ${local.toFixed(2)})`);
  });
  return { problems, frames: rows.length };
}

// ---------------------------------------------------------------- the whole cut

function vttTime(s) {
  const ms = Math.round(s * 1000);
  const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000), sec = Math.floor((ms % 60000) / 1000), r = ms % 1000;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}.${String(r).padStart(3, "0")}`;
}

const browser = await chromium.launch();
try {
  mkdirSync(outDir, { recursive: true });
  let cues = null;
  for (const aspect of aspects) {
    const plan = edl.segments.filter((seg) => !only || only.includes(seg.id))
      .map((seg) => ({ seg, src: sourceOf(seg, aspect) })).filter((p) => p.src !== null);
    const skipped = edl.segments.filter((s) => (!only || only.includes(s.id)) && !plan.some((p) => p.seg === s)).map((s) => s.id);
    if (skipped.length) console.log(`${aspect}: skipped (no source): ${skipped.join(", ")}`);

    if (check) {
      const all = [];
      for (const { seg, src } of plan) {
        if (src.kind === "frames" || src.kind === "seq") all.push(...checkSet(`${seg.id}`, src.dir, src.from, src.count).problems);
        if (src.kind === "wipe") for (const d of [src.a, src.b]) all.push(...checkSet(`${seg.id}`, d, src.from, src.count).problems);
      }
      if (all.length) {
        console.error(`${aspect}: ${all.length} suspect frames (cut anyway with --no-check):\n  ${all.join("\n  ")}`);
        process.exitCode = 1;
        continue;
      }
      console.log(`${aspect}: frames checked, none flat or popping`);
    }

    rmSync(resolve(work, aspect), { recursive: true, force: true });
    const parts = [];
    const segCues = [];
    let t = 0;
    for (let k = 0; k < plan.length; k++) {
      const { seg, src } = plan[k];
      const captions = [];
      for (const c of fit(seg.captions, src.dur)) captions.push(await renderText(browser, aspect, captionHtml(aspect, c)));
      const part = await cutSegment(browser, aspect, seg, src, k, { captions });
      parts.push(part.file);
      for (const c of fit(seg.captions, src.dur)) segCues.push({ start: t + c.t0, end: t + c.t1, text: c.text });
      console.log(`${aspect} ${vttTime(t)} ${seg.id} (${src.dur.toFixed(2)} s)`);
      t += part.frames / FPS;
    }
    const list = resolve(work, aspect, "parts.txt");
    writeFileSync(list, parts.map((p) => `file '${p}'`).join("\n") + "\n");
    const master = resolve(work, aspect, "master.mp4");
    ff(["-f", "concat", "-safe", "0", "-i", list, "-c", "copy", master], `${aspect} concat`);
    const film = resolve(outDir, `${only ? "draft" : "herebeink"}-${aspect}.mp4`);
    ff(["-i", master, "-c:v", "libx264", "-preset", "slow", "-crf", crf, "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", film], `${aspect} web encode`);
    console.log(`${aspect}: ${film} (${probeSeconds(film).toFixed(2)} s)`);

    const every = 3;
    const n = Math.ceil(t / every);
    const cols = aspect === "9x16" ? 8 : 6;
    ff(["-i", film, "-vf", `fps=1/${every},scale=${aspect === "9x16" ? 240 : 384}:-2,tile=${cols}x${Math.ceil(n / cols)}:padding=4:color=white`, "-frames:v", "1",
      resolve(outDir, `${only ? "draft" : "herebeink"}-contact-${aspect}.png`)], `${aspect} contact sheet`);
    cues ??= segCues;
  }

  if (cues && !only) {
    writeFileSync(resolve(outDir, "herebeink.vtt"), "WEBVTT\n\n" + cues.map((c, i) => `${i + 1}\n${vttTime(c.start)} --> ${vttTime(c.end)}\n${c.text}\n`).join("\n"));
    writeFileSync(resolve(outDir, "herebeink.srt"), cues.map((c, i) => `${i + 1}\n${vttTime(c.start).replace(".", ",")} --> ${vttTime(c.end).replace(".", ",")}\n${c.text}\n`).join("\n"));
  }

  // The poster and the loop come from the frames, not the cut, so they carry no caption.
  const poster = edl.poster;
  if (poster && !only && aspects.includes("16x9")) {
    const src = resolve(setDir("16x9", poster.set), `${pad(poster.frame)}.png`);
    ff(["-i", src, "-vf", "scale=1280:720:flags=lanczos", resolve(outDir, "herebeink-poster.png")], "poster");
    ff(["-i", src, "-vf", "scale=1280:720:flags=lanczos", "-q:v", "2", resolve(outDir, "herebeink-poster.jpg")], "poster jpg");
  }
  const loop = edl.loop;
  if (loop && !only && aspects.includes("16x9")) {
    ff(["-framerate", String(FPS), "-start_number", String(loop.from), "-i", resolve(setDir("16x9", loop.set), "%05d.png"), "-frames:v", String(loop.to - loop.from),
      "-vf", "scale=1280:720:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-an", "-movflags", "+faststart",
      resolve(outDir, "herebeink-loop.mp4")], "loop");
  }
} finally {
  await browser.close();
}

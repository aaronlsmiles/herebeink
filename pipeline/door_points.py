"""The two door-frame points that set the model's scale, in COLMAP's frame.

    uv run python door_points.py page       # -> work/door/pick.html: click the two corners in two or more views
    uv run python door_points.py solve      # triangulate the clicks pasted into capture/NOTES.md

Route 1 (chosen): the bottom inside corner of each jamb, where it meets the floor, clicked in two or more
registered views. The two ends of the NOTES "Check length" can be clicked too (C and D), for an
independent check on the scale, and the two top inside corners of the frame (E over A, F over B), which the
doorway fallback (align.py --mode doorway) needs. The camera poses are COLMAP's, so the corners are
triangulated exactly and the reprojection error says how well the clicks agree. A corner is refused when
its clicks disagree by more than 3 px RMS or its rays meet at under 5 degrees (views from nearly one place
fix depth badly); `solve --accept "reason"` records an overrule. NOTES.md lines, one per click:

    - Door click A rig/y000p00/5pano_0000.jpg: 558.0 1296.0
    - Door click B rig/y000p00/5pano_0000.jpg: 882.0 1296.0

Route 2 (fallback): two 3D points picked in SuperSplat on the splat, on the template's line:

    - Door points picked in the splat (two 3D points): 0.12 -0.45 1.23 ; 0.98 -0.43 1.24

SuperSplat may show a file flipped for display, so route 2 tries the file's own frame and the two
half-turns a viewer might apply, and keeps the one whose points sit on the splat.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from colmap_model import Model, read_model

CLICK_RE = re.compile(r"^- Door click ([ABCDEF]) (\S+): ([-0-9.]+) ([-0-9.]+)\s*$", re.M)
SPLAT_RE = re.compile(r"^- Door points picked in the splat \(two 3D points\):[ \t]*"
                      r"([-0-9.eE]+) ([-0-9.eE]+) ([-0-9.eE]+)[ \t]*;[ \t]*([-0-9.eE]+) ([-0-9.eE]+) ([-0-9.eE]+)[ \t]*$", re.M)
MAX_CLICK_RMS_PX = 3.0
MIN_RAY_ANGLE_DEG = 5.0
NO_CLICKS = 3
OPTIONAL = "CDEF"
LABELS = {"A": "A (left jamb, at the floor)", "B": "B (right jamb, at the floor)", "C": "C (check length, one end)",
          "D": "D (check length, other end)", "E": "E (left jamb, top inside corner)", "F": "F (right jamb, top inside corner)"}
FLIPS = {"as stored": np.diag([1.0, 1.0, 1.0]), "half-turn about x": np.diag([1.0, -1.0, -1.0]),
         "half-turn about z": np.diag([-1.0, -1.0, 1.0])}


def pose(model: Model, name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """K, R (camera from model), t for one registered image."""
    im = next((i for i in model.images.values() if i.name == name), None)
    if im is None:
        raise ValueError(f"{name} is not in the COLMAP model")
    cam = model.cameras[im.camera_id]
    fx, fy, cx, cy = cam.params[:4]
    k = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]])
    return k, Rotation.from_quat(im.qvec, scalar_first=True).as_matrix(), np.array(im.tvec)


def triangulate(model: Model, clicks: list[tuple[str, float, float]]) -> tuple[np.ndarray, float]:
    """Linear triangulation from two or more views; returns the point and the RMS reprojection error in pixels."""
    if len(clicks) < 2:
        raise ValueError("a door point needs clicks in at least two views")
    rows = []
    for name, u, v in clicks:
        k, r, t = pose(model, name)
        p = k @ np.hstack([r, t[:, None]])
        rows += [u * p[2] - p[0], v * p[2] - p[1]]
    _, _, vt = np.linalg.svd(np.array(rows))
    x = vt[-1][:3] / vt[-1][3]
    errs = []
    for name, u, v in clicks:
        k, r, t = pose(model, name)
        q = k @ (r @ x + t)
        errs.append(np.hypot(q[0] / q[2] - u, q[1] / q[2] - v))
    return x, float(np.sqrt(np.mean(np.square(errs))))


def centre(model: Model, name: str) -> np.ndarray:
    _, r, t = pose(model, name)
    return -r.T @ t


def ray_angle_deg(model: Model, clicks: list[tuple[str, float, float]], point: np.ndarray) -> float:
    """The widest angle between two of the rays that meet at the point: small means depth is poorly fixed."""
    rays = [point - centre(model, name) for name, _, _ in clicks]
    rays = [r / np.linalg.norm(r) for r in rays]
    best = 0.0
    for i in range(len(rays)):
        for j in range(i + 1, len(rays)):
            best = max(best, float(np.degrees(np.arccos(np.clip(rays[i] @ rays[j], -1, 1)))))
    return best


def from_clicks(model: Model, notes: str) -> dict | None:
    found = CLICK_RE.findall(notes)
    if not found:
        return None
    out = {}
    for label in "ABCDEF":
        clicks = [(name, float(u), float(v)) for lab, name, u, v in found if lab == label]
        if label in OPTIONAL and not clicks:
            continue
        point, rms = triangulate(model, clicks)
        out[label] = {"colmap": point.tolist(), "views": len(clicks), "rms_px": round(rms, 3),
                      "ray_angle_deg": round(ray_angle_deg(model, clicks, point), 2)}
    out["route"] = "clicks"
    return out


def problems(points: dict) -> list[str]:
    """Plain reasons, with what to do, for every clicked corner that cannot be trusted."""
    out = []
    for label, r in points.items():
        if not isinstance(r, dict) or "rms_px" not in r:
            continue
        if r["rms_px"] > MAX_CLICK_RMS_PX:
            out.append(f"corner {label}: reprojection RMS {r['rms_px']:.1f} px is over {MAX_CLICK_RMS_PX:.0f} px; the clicks "
                       f"disagree, so one is probably on the wrong spot: re-click {label} in every view, zoomed in")
        if r.get("ray_angle_deg") is not None and r["ray_angle_deg"] < MIN_RAY_ANGLE_DEG:
            out.append(f"corner {label}: its rays meet at {r['ray_angle_deg']:.1f} degrees (under {MIN_RAY_ANGLE_DEG:.0f}); "
                       "the views were taken from nearly one place, so depth is poorly fixed: re-click it in views from "
                       "further apart (another pass, or across the room)")
    return out


def from_splat_picks(notes: str, centres: np.ndarray, unit_hint: float) -> dict | None:
    m = SPLAT_RE.search(notes)
    if not m:
        return None
    raw = np.array([float(x) for x in m.groups()]).reshape(2, 3)
    tree = cKDTree(centres)
    best = None
    for label, flip in FLIPS.items():
        pts = raw @ flip.T
        d, _ = tree.query(pts)
        if best is None or d.max() < best[2].max():
            best = (label, pts, d)
    label, pts, d = best
    if d.max() > 0.05 * unit_hint:
        raise ValueError("the picked points do not sit on the splat in any frame tried; pick them again")
    return {"A": {"colmap": pts[0].tolist()}, "B": {"colmap": pts[1].tolist()}, "route": f"splat picks ({label})"}


def candidate_views(model: Model, n: int = 12, nearest_frames: int = 4) -> tuple[list[str], list[str]]:
    """(first, more): views offered for clicking, the likeliest first.

    The pano's front view faces the door by the protocol, so "towards the door" is its forward. First come
    the pano's front view, then up to n views facing that way from spread-out places, then every registered
    view of the frames that stood furthest towards the door (any view folder: the door may be beside or
    behind them). "More" is every other registered view facing within 90 degrees of the door's way.
    """
    rig = [i for i in model.images.values() if i.name.startswith("rig/")]
    pano = next((i for i in rig if i.name == "rig/y000p00/5pano_0000.jpg"), None)
    if pano is None:
        names = sorted(i.name for i in rig)
        return names[:n], names[n:]
    fwd = lambda im: Rotation.from_quat(im.qvec, scalar_first=True).as_matrix()[2]  # noqa: E731
    cen = lambda im: -Rotation.from_quat(im.qvec, scalar_first=True).as_matrix().T @ np.array(im.tvec)  # noqa: E731
    f0, c0 = fwd(pano), cen(pano)
    level = [i for i in rig if i is not pano and "p00/" in i.name and fwd(i) @ f0 > 0.7]
    chosen = [pano]
    while level and len(chosen) < n + 1:
        far = max(level, key=lambda i: min(np.linalg.norm(cen(i) - cen(c)) for c in chosen))
        chosen.append(far)
        level.remove(far)
    frames: dict[str, list] = {}
    for i in rig:
        frames.setdefault(Path(i.name).name, []).append(i)
    ahead = sorted((f for f in frames if f != Path(pano.name).name),
                   key=lambda f: -float((cen(frames[f][0]) - c0) @ f0))[:nearest_frames]
    first = [c.name for c in chosen]
    for f in ahead:
        first += sorted(i.name for i in frames[f] if i.name not in first)
    more = sorted(i.name for i in rig if i.name not in first and fwd(i) @ f0 > 0)
    return first, more


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Door corners</title>
<style>body{font:15px system-ui;margin:16px}#v{overflow:auto;max-height:70vh;border:1px solid #888}
#wrap{position:relative;display:inline-block}img{display:block;cursor:crosshair}
#marks{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none}
button{margin:2px}button.on{outline:3px solid #c22}textarea{width:100%;height:9em;font:13px monospace}
.views{max-height:8.5em;overflow:auto}</style></head><body>
<p>Click the <b>bottom inside corner of the left jamb</b> (A) and of the <b>right jamb</b> (B), where each meets the floor,
in at least two views taken from different places (three or more is better). Same physical corners in every view.
Clicking again with the same label in the same view replaces that click. Then copy the lines into capture/NOTES.md.</p>
<p>Label: <span id="labels"></span> now <b id="lab">A</b>; view <b id="cur"></b>; cursor at <b id="coords">-</b> px</p>
<div class="views" id="views"></div>
<p><button id="more"></button></p><div class="views" id="moreviews" hidden></div>
<div id="v"><div id="wrap"><img id="im" alt="view"><svg id="marks"></svg></div></div>
<textarea id="out" readonly></textarea>
<script>
const FIRST = @FIRST@, MORE = @MORE@, LABELS = @LABELS@, PREFIX = "@PREFIX@";
let L = "A", cur = FIRST[0];
const clicks = {};
const im = document.getElementById("im"), marks = document.getElementById("marks");
function button(text, parent, onClick) {
  const b = document.createElement("button");
  b.textContent = text; b.addEventListener("click", onClick); parent.appendChild(b); return b;
}
for (const [key, text] of Object.entries(LABELS)) {
  button(text, document.getElementById("labels"), () => { L = key; document.getElementById("lab").textContent = key; });
}
const viewButtons = {};
function addViews(list, parent, offset) {
  list.forEach((n, k) => { viewButtons[n] = button(String(offset + k + 1) + " " + n.replace(/^rig\//, "").replace(/\.jpg$/, ""), parent, () => show(n)); });
}
addViews(FIRST, document.getElementById("views"), 0);
addViews(MORE, document.getElementById("moreviews"), FIRST.length);
const more = document.getElementById("more");
more.textContent = "more views (" + MORE.length + ")";
more.disabled = MORE.length === 0;
more.addEventListener("click", () => { const m = document.getElementById("moreviews"); m.hidden = !m.hidden; });
function show(n) {
  cur = n; im.src = PREFIX + n;
  document.getElementById("cur").textContent = n;
  for (const [k, b] of Object.entries(viewButtons)) b.classList.toggle("on", k === n);
}
function pixel(e) {
  const r = im.getBoundingClientRect();
  return [(e.clientX - r.left) * im.naturalWidth / r.width, (e.clientY - r.top) * im.naturalHeight / r.height];
}
im.addEventListener("mousemove", (e) => { const [u, v] = pixel(e); document.getElementById("coords").textContent = u.toFixed(1) + " " + v.toFixed(1); });
im.addEventListener("click", (e) => {
  if (!im.naturalWidth) return;
  const [u, v] = pixel(e);
  clicks[L + " " + cur] = [u.toFixed(1), v.toFixed(1)];
  render();
});
im.addEventListener("load", drawMarks);
function drawMarks() {
  marks.setAttribute("viewBox", "0 0 " + im.naturalWidth + " " + im.naturalHeight);
  let svg = "";
  for (const [k, [u, v]] of Object.entries(clicks)) {
    const [lab, view] = k.split(" ");
    if (view !== cur) continue;
    svg += '<circle cx="' + u + '" cy="' + v + '" r="9" fill="none" stroke="#e11" stroke-width="3"/>' +
           '<text x="' + (Number(u) + 12) + '" y="' + (Number(v) - 10) + '" fill="#e11" font-size="28">' + lab + "</text>";
  }
  marks.innerHTML = svg;
}
function render() {
  document.getElementById("out").value = Object.entries(clicks).sort().map(([k, [u, v]]) => "- Door click " + k + ": " + u + " " + v).join("\\n");
  drawMarks();
}
show(cur);
</script></body></html>"""


def write_page(model: Model, work: Path) -> Path:
    first, more = candidate_views(model)
    data = lambda x: json.dumps(x).replace("</", "<\\/")  # noqa: E731
    page = (PAGE.replace("@FIRST@", data(first)).replace("@MORE@", data(more)).replace("@LABELS@", data(LABELS))
            .replace("@PREFIX@", "../images/"))
    out = work / "door" / "pick.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--notes", type=Path, default=Path("../capture/NOTES.md"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("page")
    so = sub.add_parser("solve")
    so.add_argument("--accept", default=None, metavar="REASON", help="go on despite the refusals below; recorded by scale.py")
    args = ap.parse_args(argv)
    model = read_model(args.work / json.loads((args.work / "colmap_report.json").read_text())["model_dir"])
    if args.cmd == "page":
        print(f"open {write_page(model, args.work)} and click; paste the lines into {args.notes}")
        return 0
    try:
        result = from_clicks(model, args.notes.read_text())
    except ValueError as e:
        print(f"door clicks refused: {e}")
        return 1
    if result is None:
        print("no '- Door click' lines in NOTES.md; scale.py will try the SuperSplat picks")
        return NO_CLICKS
    for label in (k for k in "ABCDEF" if k in result):
        r = result[label]
        print(f"point {label}: {r['views']} views, reprojection RMS {r['rms_px']:.2f} px, rays meet at {r['ray_angle_deg']:.1f} degrees")
    bad = problems(result)
    for b in bad:
        print(f"  REFUSED {b}")
    if bad and not args.accept:
        print("fix the clicks and solve again, or pass --accept \"reason\" after looking (scale.py will ask for it too)")
        return 1
    if bad:
        print(f"accepted despite the above: {args.accept}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

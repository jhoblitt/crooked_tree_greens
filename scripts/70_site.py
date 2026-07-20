#!/usr/bin/env python3
"""Stage 7: assemble the static GitHub Pages site into site/.

Stdlib only — CI runs this without installing the pipeline's dependencies.
Every course under courses/ with an outputs/greens/index.json gets its own
gallery at site/<slug>/ (slope/contours/pin-zone toggle per green), and the
root index.html is a course picker.
"""

import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COURSES = ROOT / "courses"
SITE = ROOT / "site"
REPO = "https://github.com/jhoblitt/green_maps"

CSS = """
:root { --bg:#f6f7f9; --card:#fff; --ink:#23282e; --muted:#6b737d;
        --line:#e2e6ea; --accent:#2f6f4f; --flag:#a15c00; --flagbg:#fff3e0; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14171a; --card:#1d2126; --ink:#e6e9ec; --muted:#9aa3ad;
          --line:#2c323a; --accent:#7fc9a2; --flag:#ffb85c; --flagbg:#3a2d17; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font:15px/1.5 system-ui, sans-serif; }
header, main, footer { max-width:1280px; margin:0 auto; padding:0 20px; }
header { padding-top:28px; }
h1 { font-size:24px; margin:0 0 4px; }
.sub { color:var(--muted); margin:0 0 12px; }
.controls { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:14px 0 6px; }
.seg { display:inline-flex; border:1px solid var(--line); border-radius:8px; overflow:hidden; }
.seg button { border:0; background:var(--card); color:var(--ink);
              padding:6px 14px; cursor:pointer; font:inherit; }
.seg button.on { background:var(--accent); color:var(--bg); }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(300px, 1fr));
        gap:16px; padding:14px 0 30px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px;
        overflow:hidden; }
.card img { width:100%; height:auto; display:block; background:#fff; }
.card .body { padding:10px 12px 12px; }
.card h2 { font-size:16px; margin:0 0 2px; }
.stats { color:var(--muted); font-size:13px; margin:0; }
.flag { display:inline-block; background:var(--flagbg); color:var(--flag);
        font-size:12px; border-radius:6px; padding:1px 7px; margin:6px 4px 0 0; }
.links { font-size:13px; margin-top:6px; }
a { color:var(--accent); }
footer { color:var(--muted); font-size:13px; padding-bottom:34px; }
.course-card { display:block; text-decoration:none; color:var(--ink);
               background:var(--card); border:1px solid var(--line);
               border-radius:10px; padding:16px 18px; }
.course-card:hover { border-color:var(--accent); }
.course-card h2 { margin:0 0 4px; font-size:18px; }
.viewer { position:relative; overflow:hidden; background:#fff; border:1px solid var(--line);
          border-radius:10px; height:min(78vh, 900px); touch-action:none; cursor:grab; }
.viewer img { position:absolute; top:0; left:0; width:100%; height:100%;
              object-fit:contain; transform-origin:0 0; user-select:none;
              -webkit-user-drag:none; }
.vbtns { position:absolute; top:10px; right:10px; display:flex; flex-direction:column;
         gap:6px; z-index:5; }
.vbtns button { width:34px; height:34px; border-radius:8px; border:1px solid var(--line);
                background:var(--card); color:var(--ink); font-size:16px; cursor:pointer; }
.vbtns button:hover { border-color:var(--accent); }
.nav { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:10px 0; }
.nav a.btn { border:1px solid var(--line); background:var(--card); border-radius:8px;
             padding:6px 12px; text-decoration:none; }
.nav a.btn:hover { border-color:var(--accent); }
"""

JS = """
function show(kind) {
  document.querySelectorAll('.card img').forEach(im => {
    im.src = im.dataset[kind];
  });
  document.querySelectorAll('.seg button').forEach(b =>
    b.classList.toggle('on', b.dataset.kind === kind));
}
"""


def green_card(slug, g, meta):
    label = g["label"]
    name = meta.get("display") or (
        f"Hole {g['hole']}" if g["hole"] else label.replace("_", " ").title())
    flags = "".join(f'<span class="flag">{html.escape(f)}</span>' for f in g["flags"])
    if meta.get("needs_review"):
        flags += '<span class="flag">polygon needs review</span>'
    pz = meta["pin_zones"]
    if pz["scarce_legal_area"]:
        flags += '<span class="flag">scarce legal pin area</span>'
    return f"""
  <div class="card" id="{label}">
    <a href="greens/{label}/">
      <img src="greens/{label}/slope_heatmap.png"
           data-slope="greens/{label}/slope_heatmap.png"
           data-contours="greens/{label}/contours.png"
           data-pins="greens/{label}/pin_zones.png"
           alt="{name} slope heatmap" loading="lazy"></a>
    <div class="body">
      <h2>{name}</h2>
      <p class="stats">slope μ {g["slope_mean_pct"]:.1f}% · max&#8239;1&#8239;m {meta["slope_max_sustained_pct"]:.1f}%
        · Δz {g["elevation_range_m"]:.2f} m · fit {g["fit_rms_m"]*100:.1f} cm
        · legal pin {pz["legal_area_m2"]:.0f}&#8239;m² ({pz["legal_fraction"]*100:.0f}%)</p>
      {flags}
      <p class="links"><a href="{REPO}/tree/main/courses/{slug}/outputs/greens/{label}">assets
        (heightmap, mesh, pin zones)</a></p>
    </div>
  </div>"""


VIEWER_JS = """
const viewer = document.getElementById('viewer');
const img = document.getElementById('view');
let s = 1, tx = 0, ty = 0, dragging = false, px = 0, py = 0;
const apply = () => { img.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`; };
function zoomAt(f, cx, cy) {
  const ns = Math.min(10, Math.max(1, s * f));
  tx = cx - (cx - tx) * (ns / s);
  ty = cy - (cy - ty) * (ns / s);
  s = ns;
  if (s === 1) { tx = 0; ty = 0; }
  apply();
}
function zoomBtn(f) {
  const r = viewer.getBoundingClientRect();
  zoomAt(f, r.width / 2, r.height / 2);
}
function resetView() { s = 1; tx = 0; ty = 0; apply(); }
viewer.addEventListener('wheel', e => {
  e.preventDefault();
  const r = viewer.getBoundingClientRect();
  zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX - r.left, e.clientY - r.top);
}, { passive: false });
viewer.addEventListener('dragstart', e => e.preventDefault());  // no native image drag
viewer.addEventListener('pointerdown', e => {
  if (e.target.closest('.vbtns')) return;  // let zoom/reset buttons receive the click
  e.preventDefault();  // suppress the native image drag that would cancel the pan
  dragging = true; px = e.clientX; py = e.clientY;
  viewer.setPointerCapture(e.pointerId); viewer.style.cursor = 'grabbing';
});
viewer.addEventListener('pointermove', e => {
  if (!dragging) return;
  tx += e.clientX - px; ty += e.clientY - py; px = e.clientX; py = e.clientY; apply();
});
['pointerup', 'pointercancel'].forEach(ev => viewer.addEventListener(ev, () => {
  dragging = false; viewer.style.cursor = 'grab';
}));
function show(kind) {
  img.src = img.dataset[kind];
  document.querySelectorAll('.seg button').forEach(b =>
    b.classList.toggle('on', b.dataset.kind === kind));
}
"""


def green_page(slug, g, meta, course_title, prev_label, next_label):
    label = g["label"]
    name = meta.get("display") or (
        f"Hole {g['hole']}" if g["hole"] else label.replace("_", " ").title())
    pz = meta["pin_zones"]
    flags = "".join(f'<span class="flag">{html.escape(f)}</span>' for f in g["flags"])
    if meta.get("needs_review"):
        flags += '<span class="flag">polygon needs review</span>'
    if pz["scarce_legal_area"]:
        flags += '<span class="flag">scarce legal pin area</span>'
    approach = meta.get("approach_deg")
    approach_txt = f" · approach {approach:.0f}°" if approach is not None else ""
    header = f"""
  <h1>{html.escape(course_title)} — {html.escape(name)}</h1>
  <p class="stats">slope μ {g["slope_mean_pct"]:.1f}% · Δz {g["elevation_range_m"]:.2f} m ·
    fit {g["fit_rms_m"]*100:.1f} cm · legal pin {pz["legal_area_m2"]:.0f}&#8239;m²
    ({pz["legal_fraction"]*100:.0f}%){approach_txt}</p>
  {flags}
  <div class="nav">
    <a class="btn" href="../../">↩ {html.escape(course_title)} gallery</a>
    <a class="btn" href="../../greens_overview.html">course overview map</a>
    <a class="btn" href="../{prev_label}/">← prev</a>
    <a class="btn" href="../{next_label}/">next →</a>
    <div class="seg">
      <button class="on" data-kind="slope" onclick="show('slope')">slope</button>
      <button data-kind="contours" onclick="show('contours')">contours</button>
      <button data-kind="pins" onclick="show('pins')">pin zones</button>
    </div>
  </div>"""
    body = f"""
  <div class="viewer" id="viewer">
    <div class="vbtns">
      <button onclick="zoomBtn(1.3)" title="zoom in">+</button>
      <button onclick="zoomBtn(1/1.3)" title="zoom out">−</button>
      <button onclick="resetView()" title="reset">⌂</button>
    </div>
    <img id="view" src="slope_heatmap.png" draggable="false"
         data-slope="slope_heatmap.png" data-contours="contours.png"
         data-pins="pin_zones.png" alt="{html.escape(name)} surface map">
  </div>
  <p class="links"><a href="{REPO}/tree/main/courses/{slug}/outputs/greens/{label}">raw assets
    (heightmap npz/tif, mesh obj/glb, pin-zone rasters)</a></p>"""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(course_title)} — {html.escape(name)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
{header}
</header>
<main>
{body}
</main>
<footer>drag to pan, scroll or buttons to zoom · arrows point downhill · code Apache-2.0,
  map data © OpenStreetMap contributors (ODbL), LiDAR public domain (USGS 3DEP).</footer>
<script>{VIEWER_JS}</script>
</body>
</html>
"""


def page(title_html, header_extra, body, footer_extra=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_html}</title>
<style>{CSS}</style>
</head>
<body>
<header>
{header_extra}
</header>
<main>
{body}
</main>
<footer>{footer_extra} code Apache-2.0, map data © OpenStreetMap contributors (ODbL),
  LiDAR public domain (USGS 3DEP).</footer>
<script>{JS}</script>
</body>
</html>
"""


def build_course(slug, out_dir):
    idx = json.loads((out_dir / "index.json").read_text())
    dst_root = SITE / slug
    cards = []
    course_title = idx["course"].split(",")[0]
    labels = [g["label"] for g in idx["greens"]]
    for i, g in enumerate(idx["greens"]):
        label = g["label"]
        meta = json.loads((out_dir / label / "meta.json").read_text())
        dst = dst_root / "greens" / label
        dst.mkdir(parents=True)
        for png in ("slope_heatmap.png", "contours.png", "pin_zones.png"):
            shutil.copy2(out_dir / label / png, dst / png)
        cards.append(green_card(slug, g, meta))
        (dst / "index.html").write_text(green_page(
            slug, g, meta, course_title,
            labels[i - 1], labels[(i + 1) % len(labels)]))

    overview = COURSES / slug / "reports" / "greens_overview.html"
    if overview.exists():
        shutil.copy2(overview, dst_root / "greens_overview.html")

    dates = ", ".join(idx["acquisition_dates"])
    header = f"""
  <h1>{html.escape(idx["course"])} — green surface maps</h1>
  <p class="sub">USGS 3DEP LiDAR
    ({html.escape(", ".join(idx["source_work_units"]))}, acquired {dates}) ·
    {idx["cell_size_m"]} m grid · status {idx["status"]}</p>
  <p class="sub">{html.escape(idx["vertical_fidelity"])}.</p>
  <div class="controls">
    <div class="seg">
      <button class="on" data-kind="slope" onclick="show('slope')">slope heatmaps</button>
      <button data-kind="contours" onclick="show('contours')">contours (2.5 cm)</button>
      <button data-kind="pins" onclick="show('pins')">legal pin zones</button>
    </div>
    <a href="../">all courses</a>
    <a href="greens_overview.html">course overview map</a>
    <a href="{REPO}/blob/main/courses/{slug}/reports/qc_report.md">QC report</a>
  </div>"""
    body = f'  <div class="grid">{"".join(cards)}\n  </div>'
    footer = f"Generated {html.escape(idx['generated'])} · heights {html.escape(idx['crs_vertical'])} · arrows point downhill ·"
    (dst_root / "index.html").write_text(
        page(f"{html.escape(idx['course'])} — greens", header, body, footer))
    return idx


def main() -> int:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    course_cards = []
    n = 0
    for cdir in sorted(COURSES.iterdir()):
        out_dir = cdir / "outputs" / "greens"
        if not (out_dir / "index.json").exists():
            continue
        idx = build_course(cdir.name, out_dir)
        n += 1
        n_greens = len(idx["greens"])
        n_holes = len([g for g in idx["greens"] if g["hole"]])
        course_cards.append(f"""
  <a class="course-card" href="{cdir.name}/">
    <h2>{html.escape(idx["course"].split(",")[0])}</h2>
    <p class="stats">{n_holes} hole greens · {n_greens} surfaces · status {idx["status"]}
      · acquired {html.escape(", ".join(idx["acquisition_dates"]))}</p>
  </a>""")
        print(f"site: {cdir.name}: {n_greens} greens")

    header = """
  <h1>green_maps — LiDAR putting-green surface models</h1>
  <p class="sub">Simulation-ready heightmaps, meshes, slope/contour maps, and legal
    pin zones derived from public USGS 3DEP LiDAR.</p>
  <div class="controls"><a href="{repo}">repo</a></div>""".replace("{repo}", REPO)
    body = f'  <div class="grid">{"".join(course_cards)}\n  </div>'
    (SITE / "index.html").write_text(page("green_maps — courses", header, body))
    print(f"site: {n} course(s) -> site/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

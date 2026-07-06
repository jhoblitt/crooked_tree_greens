#!/usr/bin/env python3
"""Stage 7: assemble the static GitHub Pages site into site/.

Stdlib only — CI runs this without installing the pipeline's dependencies.
Builds an index.html gallery of every green's slope heatmap (toggleable to
contours) from outputs/greens/index.json + per-green meta.json, and copies the
PNGs and the folium overview map alongside it.
"""

import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "greens"
SITE = ROOT / "site"
REPO = "https://github.com/jhoblitt/crooked_tree_greens"

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


def card(g, meta):
    label = g["label"]
    name = f"Hole {g['hole']}" if g["hole"] else label.replace("_", " ").title()
    flags = "".join(f'<span class="flag">{html.escape(f)}</span>' for f in g["flags"])
    if meta.get("needs_review"):
        flags += '<span class="flag">polygon needs review</span>'
    return f"""
  <div class="card" id="{label}">
    <a href="greens/{label}/slope_heatmap.png" target="_blank">
      <img src="greens/{label}/slope_heatmap.png"
           data-slope="greens/{label}/slope_heatmap.png"
           data-contours="greens/{label}/contours.png"
           alt="{name} slope heatmap" loading="lazy"></a>
    <div class="body">
      <h2>{name}</h2>
      <p class="stats">slope μ {g["slope_mean_pct"]:.1f}% · max&#8239;1&#8239;m {meta["slope_max_sustained_pct"]:.1f}%
        · Δz {g["elevation_range_m"]:.2f} m · fit {g["fit_rms_m"]*100:.1f} cm
        · {meta["class2_density_on_green_pts_m2"]:.0f} pts/m²</p>
      {flags}
      <p class="links"><a href="{REPO}/tree/main/outputs/greens/{label}">assets
        (heightmap npz/tif, mesh obj/glb)</a></p>
    </div>
  </div>"""


def main() -> int:
    idx = json.loads((OUT / "index.json").read_text())
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    cards = []
    for g in idx["greens"]:
        label = g["label"]
        meta = json.loads((OUT / label / "meta.json").read_text())
        dst = SITE / "greens" / label
        dst.mkdir(parents=True)
        for png in ("slope_heatmap.png", "contours.png"):
            shutil.copy2(OUT / label / png, dst / png)
        cards.append(card(g, meta))

    overview = ROOT / "reports" / "greens_overview.html"
    if overview.exists():
        shutil.copy2(overview, SITE / "greens_overview.html")

    dates = ", ".join(idx["acquisition_dates"])
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Crooked Tree greens — heatmaps</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>Crooked Tree Golf Course — green surface maps</h1>
  <p class="sub">{html.escape(idx["course"])} · USGS 3DEP LiDAR
    ({html.escape(", ".join(idx["source_work_units"]))}, acquired {dates}) ·
    {idx["cell_size_m"]} m grid · status {idx["status"]}</p>
  <p class="sub">{html.escape(idx["vertical_fidelity"])}.</p>
  <div class="controls">
    <div class="seg">
      <button class="on" data-kind="slope" onclick="show('slope')">slope heatmaps</button>
      <button data-kind="contours" onclick="show('contours')">contours (2.5 cm)</button>
    </div>
    <a href="greens_overview.html">course overview map</a>
    <a href="{REPO}/blob/main/reports/qc_report.md">QC report</a>
    <a href="{REPO}">repo</a>
  </div>
</header>
<main>
  <div class="grid">{"".join(cards)}
  </div>
</main>
<footer>Generated {html.escape(idx["generated"])} · heights NAVD88 m (EPSG:6341 grid) ·
  arrows point downhill · code Apache-2.0, map data © OpenStreetMap contributors (ODbL),
  LiDAR public domain (USGS 3DEP).</footer>
<script>{JS}</script>
</body>
</html>
"""
    (SITE / "index.html").write_text(page)
    print(f"site: {len(cards)} greens -> {SITE.relative_to(ROOT)}/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

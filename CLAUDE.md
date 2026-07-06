# CLAUDE.md — Crooked Tree Greens: LiDAR → 3D Surface Models

## Project goal

Build simulation-ready 3D surface models of every putting green at **Crooked Tree Golf Course (Arthur Pack Regional Park), 9101 N Thornydale Rd, Tucson, AZ 85742** from public USGS 3DEP LiDAR. Outputs feed a rigid-sphere-on-heightmap putting physics simulation.

Final deliverable per green: a regular-grid heightmap (meters, Z-up, local origin), a triangle mesh (OBJ + GLB), slope/contour QC plots, and a `meta.json`. Plus one repo-level QC report.

## Ground rules

- Work stage by stage (Stage 0 → 6). Each stage is a numbered, idempotent script in `scripts/`. Cache all downloads; never re-fetch on rerun.
- **Halt on QC failure** at any checkpoint and report, rather than proceeding with bad data.
- All geometry math in a **projected metric CRS (NAD83(2011) / UTM 12N, EPSG:6341; EPSG:26912 acceptable)**. Never compute slopes or distances in EPSG:3857 or 4326.
- Units: meters everywhere. Normalize immediately on ingest; some AZ deliverables are in feet — check LAZ headers, do not assume.
- Python via `uv` (`uv init`, `uv add ...`). Prefer pure-pip dependencies; PDAL is an optional fast path only if already installed or trivially available (e.g., `mamba install -c conda-forge pdal`).

Core deps: `numpy scipy laspy[lazrs] pyproj shapely rasterio matplotlib trimesh requests folium`

## Known facts and things to VERIFY (do not skip)

Facts (verified July 2026, re-check cheaply):
- Tucson is covered by USGS 3DEP collection(s) named like `AZ_PimaCo_1_2021` / `AZ_PimaCo_2_2021` (PAG-sponsored, open access, public domain). Tucson proper is in PimaCo **2**.
- 3DEP LAZ point clouds are free via the TNM Access API and as Entwine Point Tiles (EPT) in the `usgs-lidar-public` S3 bucket.
- The EPT copies in `usgs-lidar-public` are reprojected to **EPSG:3857** — horizontal scale at this latitude is distorted ~18%. Reproject to UTM 12N before any slope/distance computation.

Verify at runtime:
1. Exact course center/boundary: geocode via Nominatim, cross-check against the OSM `leisure=golf_course` polygon. Approximate center for search seeding: **32.394, -111.049** (treat as approximate until verified).
2. Exact 3DEP work-unit name covering the course footprint: grep `https://raw.githubusercontent.com/hobuinc/usgs-lidar/master/boundaries/resources.geojson` for `PimaCo`, and/or query the TNM API (below) and inspect returned product names.
3. LAZ header CRS + units (horizontal and vertical) on first downloaded tile. Expect NAD83(2011) UTM 12N or AZ State Plane Central, NAVD88 heights, meters or feet.
4. Acquisition date of the tiles actually used (record in metadata; greens may have been altered since).

## Pipeline

### Stage 0 — Environment + repo layout
```
crooked-tree-greens/
  scripts/            # 00_env_check.py ... 60_report.py
  data/raw/           # LAZ tiles as downloaded (gitignored)
  data/polygons/      # course.geojson, greens.geojson
  data/interim/       # per-green clipped points (npz)
  outputs/greens/hole_NN/   # final artifacts
  reports/
```
`00_env_check.py`: import all deps, print versions, confirm outbound HTTPS to `tnmaccess.nationalmap.gov` and `overpass-api.de`.

### Stage 1 — Green polygons
Primary: OSM Overpass. Find the course way, then `golf=green` features within/near it:
```
[out:json][timeout:90];
way["leisure"="golf_course"]["name"~"Crooked Tree",i](32.36,-111.09,32.42,-111.01);
out geom;
```
then query `way["golf"="green"]` within the course bbox. Save as `data/polygons/greens.geojson` (EPSG:4326), one feature per green, attribute `hole` (int; use `ref`/`name` tags if present, else label sequentially and flag for human review).

Fallback if OSM has no greens mapped: generate `reports/digitize_map.html` — a folium map over Esri World Imagery centered on the course with a drawing plugin — and STOP. Ask the user to draw green polygons, export GeoJSON to `data/polygons/greens.geojson`, then rerun.

Checkpoint: 18 green polygons (+ optional practice green). Render all polygons on a folium satellite map (`reports/greens_overview.html`) for eyeball QC. Each polygon area sanity: 250–1,200 m².

### Stage 2 — Point acquisition
Buffer each green polygon by **12 m** (collar/surrounds provide sim boundary and fitting support). Union the buffered set, take its bbox in EPSG:4326.

Default path (pure Python): TNM Access API →
`GET https://tnmaccess.nationalmap.gov/api/v1/products?datasets=Lidar Point Cloud (LPC)&bbox=<xmin,ymin,xmax,ymax>&prodFormats=LAS,LAZ&outputFormat=JSON`
Filter results to the PimaCo 2021 work unit; download the intersecting LAZ tiles to `data/raw/` (a course footprint should be a handful of tiles).

Optional fast path (only if PDAL CLI available): `readers.ept` against `https://s3-us-west-2.amazonaws.com/usgs-lidar-public/<WORKUNIT>/ept.json` with bounds in EPSG:3857, `filters.range` `Classification[2:2]`, `filters.reprojection` → EPSG:6341, write one LAZ per green.

Checkpoint: report tile count, total points, CRS/units read from headers.

### Stage 3 — Clip + clean per green
For each green (laspy):
- Reproject polygon to point CRS; clip points to the 12 m-buffered polygon.
- Keep **class 2 (ground)** returns only.
- Normalize XYZ to meters; transform to EPSG:6341 if not already.
- Outlier rejection: fit a plane, compute residuals, drop |residual| > 3.5×MAD, refit once.
- Save `data/interim/hole_NN.npz` (x, y, z arrays + provenance dict).

Checkpoint per green: **class-2 density on the green polygon itself** (pts/m²). Flag < 1.5 pts/m²; halt and report if any green < 0.8 (data likely unusable there).

### Stage 4 — Surface fitting (the part that matters)
Philosophy: LiDAR vertical noise is ~5–10 cm RMSE; individual points must NOT be honored. Fit a smooth surface through the noise; recover macro contours (tiers, main slopes), accept that sub-1% micro-break is below the noise floor.

Per green:
1. Detrend with best-fit plane (conditioning); work on residuals.
2. Grid: axis-aligned in UTM, **0.25 m cell**, extent = buffered polygon bbox.
3. Fit `scipy.interpolate.RBFInterpolator(kernel="thin_plate_spline", smoothing=λ)` on (x,y)→residual. Sweep λ over a log grid; pick the smallest λ whose fit residual RMS lands in **3–6 cm**. If the sweep can't reach that band, report and pick nearest.
4. Add plane back; evaluate on grid → heightmap. Mask cells outside the buffered polygon (NaN).
5. Slopes: `np.gradient` on the grid → slope % and aspect. Sanity: on-green mean slope 0.5–4%, flag any green with max sustained slope > 8% or < 0.3% (suspiciously flat = oversmoothed).

### Stage 5 — Exports (per green → `outputs/greens/hole_NN/`)
- `heightmap.npz`: `z` (2D float32, meters, NaN outside), `x0`, `y0` (UTM of grid origin), `dx` (=dy, 0.25), `local_origin` (green centroid UTM). Grid row-major, north-up.
- `heightmap.tif`: same grid as GeoTIFF, EPSG:6341, NAVD88 meters.
- `mesh.obj` + `mesh.glb` (trimesh): vertices in **local coordinates** (centroid-origin, Z-up, meters) so the sim gets small numbers.
- `slope_heatmap.png`: slope % heatmap with aspect arrows (StrackaLine-style).
- `contours.png`: 2.5 cm contour intervals over the green polygon.
- `meta.json`: hole, source work unit + acquisition date, tile names, CRS strings, cell size, grid shape, class-2 density, λ, fit residual RMS, slope stats (mean/max %), elevation range, generated timestamp, and the caveat string: `"vertical_fidelity": "macro contours only; source RMSE ~5-10 cm; micro-break below noise floor"`.

### Stage 6 — QC report
`reports/qc_report.md`: table of all greens (density, residual RMS, λ, mean/max slope, elevation range, flags), links to per-green PNGs, list of anything halted/flagged, and the data-honesty paragraph above. Also emit `outputs/greens/index.json` enumerating all greens for the sim to consume.

## Definition of done
- 18 greens (+ practice green if polygon exists) each with all six artifacts present.
- No green below 0.8 pts/m² class-2 density without an explicit note.
- All fit residual RMS values in (or documented near) the 3–6 cm band.
- All slope sanity checks pass or are flagged with explanation.
- `reports/qc_report.md` complete; `greens_overview.html` shows polygons correctly placed on imagery.

## Gotchas (encode these; they are the failure modes)
- EPSG:3857 slope math ⇒ ~18% error at 32.4°N. Reproject first, always.
- Feet vs meters in AZ deliverables. Read the header; convert once, at ingest.
- Exact-interpolating through raw points produces garbage micro-break that looks like signal. Smooth to the 3–6 cm residual band instead.
- OSM hole numbering (`ref` tags) may not match the scorecard; flag for human confirmation rather than guessing.
- Desert course: class-2 coverage on greens should be dense (open turf), but overhanging trees near collars can thin edges — the 12 m buffer + spline handles this; do not extrapolate meshes past the buffered polygon.

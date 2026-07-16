# crooked_tree_greens

Simulation-ready 3D surface models of the putting greens at Crooked Tree Golf
Course (Arthur Pack Regional Park, Tucson, AZ), built from public USGS 3DEP
LiDAR. Browse the green heatmaps at
<https://jhoblitt.github.io/crooked_tree_greens/>. Per green: a 0.25 m heightmap (`.npz` + GeoTIFF), a triangle mesh
(OBJ/GLB, centroid-local, Z-up, meters), slope/contour QC plots, and
provenance metadata. Outputs feed a rigid-sphere-on-heightmap putting physics
simulation.

## Pipeline

```
uv run scripts/00_env_check.py      # deps + endpoint reachability
uv run scripts/10_green_polygons.py # green polygons (OSM + manual digitization)
uv run scripts/20_fetch_lidar.py    # 3DEP LAZ tiles via TNM Access API
uv run scripts/30_clip_clean.py     # clip class-2 ground returns per green
uv run scripts/40_fit_surface.py    # thin-plate-spline fit, 3-6 cm residual band
uv run scripts/45_pin_zones.py      # legal pin-zone map (USGA-guided, tiered)
uv run scripts/50_export.py         # heightmaps, meshes, plots, pin zones, meta.json
uv run scripts/60_report.py         # reports/qc_report.md + outputs/greens/index.json
uv run scripts/70_site.py           # site/ GitHub Pages gallery
```

Per-green artifacts (`outputs/greens/<label>/`): `heightmap.npz`/`.tif`, `mesh.obj`/`.glb`,
`slope_heatmap.png`, `contours.png`, and a **legal pin-zone map** —
`pin_zones.png`/`.tif`/`.npz`/`.geojson` — marking where a hole could be fairly cut
(on the putting surface, ≥3 m from the edge, macro slope ≤ 1.5/2/3% over a 0.5 m cup
bench, per USGA guidance). Steep greens with little or no legal pin area are flagged in
the QC report.

Stages are idempotent; downloads are cached. If OSM lacks green polygons the
polygon stage writes `reports/digitize_map.html` for hand-tracing the missing
greens; save its export as `data/polygons/greens_manual.geojson` and rerun.

All geometry math is done in NAD83(2011) / UTM 12N (EPSG:6341), NAVD88 heights,
meters. See `reports/qc_report.md` for per-green QC and caveats — the surfaces
capture macro contours only; the source LiDAR's ~5-10 cm vertical noise floor
hides sub-1% micro-break.

## Development

`uv run pytest` runs the regression suite (~1 minute): per-stage tests over
synthetic LiDAR tiles and polygons (no network, no real tiles needed), a mini
end-to-end pipeline, integrity checks of the committed artifact tree, and a
replay of the committed OSM responses through the polygon-parsing stage. Run
it after any change to `scripts/` — it specifically guards against stale LAZ
files blending into fits and stale or torn output directories passing the QC
report. `uv run pytest -m "not slow"` skips the end-to-end run for a ~15 s
loop, and `uv run ruff check .` lints. CI (`.github/workflows/ci.yml`) runs
both on every push and pull request.

## Data sources

- LiDAR: USGS 3DEP work unit `AZ_PimaCounty_2021_B21` (acquired 2021-10-04),
  public domain, via the TNM Access API.
- Course outline, hole lines, and part of the green polygons: ©
  [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors,
  ODbL 1.0 (`data/polygons/*.geojson` are derived from OSM data).
- Remaining green polygons hand-digitized over aerial imagery.

## License

Code is licensed under [Apache-2.0](LICENSE). Data files carry the terms of
their sources listed above.

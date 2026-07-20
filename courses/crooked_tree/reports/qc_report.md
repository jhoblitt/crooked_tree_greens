# Crooked Tree Golf Course — QC report

Generated 2026-07-20T23:15:07+00:00 · status: **COMPLETE** (18/18 hole greens + 2 practice)

- Course: Crooked Tree Golf Course, Arthur Pack Regional Park, 9101 N Thornydale Rd, Tucson, AZ 85742 (OSM 263321891; Nominatim cross-checked)
- LiDAR source: USGS Lidar Point Cloud AZ_PimaCounty_2021_B21 (USGS 3DEP, public domain), acquisition 2021-10-04, tiles: USGS_LPC_AZ_PimaCounty_2021_B21_494580.laz, USGS_LPC_AZ_PimaCounty_2021_B21_494581.laz
- CRS: horizontal EPSG:6341 NAD83(2011) / UTM zone 12N (m); vertical EPSG:5703 NAVD88 height (m), GEOID18
- Method: class-2 returns, 12 m collar buffer, 3.5×MAD plane-residual outlier rejection, thin-plate-spline RBF on plane residuals, λ swept to land fit RMS in 3–6 cm, 0.25 m grid

## Greens

| green | hole | area m² | pts/m² | λ | fit RMS cm | band | slope μ % | slope max* % | Δz m | legal pin m² (%) | flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| [Hole 1](../outputs/greens/hole_01/slope_heatmap.png) ([contours](../outputs/greens/hole_01/contours.png), [pins](../outputs/greens/hole_01/pin_zones.png)) | 1 | 296 | 18.3 | 316 | 3.3 | in_band | 1.67 | 3.33 | 0.29 | 136 (46%) | — |
| [Hole 2](../outputs/greens/hole_02/slope_heatmap.png) ([contours](../outputs/greens/hole_02/contours.png), [pins](../outputs/greens/hole_02/pin_zones.png)) | 2 | 387 | 8.9 | 100 | 3.2 | in_band | 3.60 | 7.34 | 1.03 | 29 (8%) | — |
| [Hole 3](../outputs/greens/hole_03/slope_heatmap.png) ([contours](../outputs/greens/hole_03/contours.png), [pins](../outputs/greens/hole_03/pin_zones.png)) | 3 | 384 | 9.0 | 100 | 3.7 | in_band | 3.18 | 17.23 | 0.81 | 82 (21%) | max_sustained_17.2%_gt_8% |
| [Hole 4](../outputs/greens/hole_04/slope_heatmap.png) ([contours](../outputs/greens/hole_04/contours.png), [pins](../outputs/greens/hole_04/pin_zones.png)) | 4 | 331 | 16.7 | 316 | 3.8 | in_band | 3.17 | 7.15 | 0.73 | 29 (9%) | — |
| [Hole 5](../outputs/greens/hole_05/slope_heatmap.png) ([contours](../outputs/greens/hole_05/contours.png), [pins](../outputs/greens/hole_05/pin_zones.png)) | 5 | 320 | 9.1 | 31.6 | 3.0 | in_band | 3.90 | 9.76 | 0.89 | 14 (4%) | max_sustained_9.8%_gt_8% |
| [Hole 6](../outputs/greens/hole_06/slope_heatmap.png) ([contours](../outputs/greens/hole_06/contours.png), [pins](../outputs/greens/hole_06/pin_zones.png)) | 6 | 452 | 16.7 | 100 | 3.4 | in_band | 2.92 | 6.73 | 0.71 | 15 (3%) | — |
| [Hole 7](../outputs/greens/hole_07/slope_heatmap.png) ([contours](../outputs/greens/hole_07/contours.png), [pins](../outputs/greens/hole_07/pin_zones.png)) | 7 | 575 | 17.0 | 100 | 3.2 | in_band | 3.80 | 10.90 | 0.86 | 126 (22%) | max_sustained_10.9%_gt_8% |
| [Hole 8](../outputs/greens/hole_08/slope_heatmap.png) ([contours](../outputs/greens/hole_08/contours.png), [pins](../outputs/greens/hole_08/pin_zones.png)) | 8 | 802 | 9.6 | 100 | 3.2 | in_band | 3.64 | 8.38 | 0.91 | 56 (7%) | max_sustained_8.4%_gt_8% |
| [Hole 9](../outputs/greens/hole_09/slope_heatmap.png) ([contours](../outputs/greens/hole_09/contours.png), [pins](../outputs/greens/hole_09/pin_zones.png)) | 9 | 382 | 18.1 | 100 | 3.4 | in_band | 2.92 | 7.36 | 0.86 | 61 (16%) | — |
| [Hole 10](../outputs/greens/hole_10/slope_heatmap.png) ([contours](../outputs/greens/hole_10/contours.png), [pins](../outputs/greens/hole_10/pin_zones.png)) | 10 | 301 | 16.2 | 100 | 3.5 | in_band | 3.52 | 7.14 | 0.63 | 2 (1%) | — |
| [Hole 11](../outputs/greens/hole_11/slope_heatmap.png) ([contours](../outputs/greens/hole_11/contours.png), [pins](../outputs/greens/hole_11/pin_zones.png)) | 11 | 293 | 19.5 | 100 | 3.3 | in_band | 3.77 | 7.48 | 0.76 | 19 (6%) | — |
| [Hole 12](../outputs/greens/hole_12/slope_heatmap.png) ([contours](../outputs/greens/hole_12/contours.png), [pins](../outputs/greens/hole_12/pin_zones.png)) | 12 | 292 | 8.6 | 100 | 3.6 | in_band | 4.40 | 8.13 | 0.96 | 5 (2%) | mean_slope_4.40%_outside_0.5-4%; max_sustained_8.1%_gt_8% |
| [Hole 13](../outputs/greens/hole_13/slope_heatmap.png) ([contours](../outputs/greens/hole_13/contours.png), [pins](../outputs/greens/hole_13/pin_zones.png)) | 13 | 283 | 8.1 | 1e+03 | 3.8 | in_band | 5.91 | 12.25 | 0.95 | 0 (0%) | mean_slope_5.91%_outside_0.5-4%; max_sustained_12.2%_gt_8% |
| [Hole 14](../outputs/greens/hole_14/slope_heatmap.png) ([contours](../outputs/greens/hole_14/contours.png), [pins](../outputs/greens/hole_14/pin_zones.png)) | 14 | 398 | 8.9 | 316 | 4.2 | in_band | 3.07 | 9.88 | 0.72 | 72 (18%) | max_sustained_9.9%_gt_8% |
| [Hole 15](../outputs/greens/hole_15/slope_heatmap.png) ([contours](../outputs/greens/hole_15/contours.png), [pins](../outputs/greens/hole_15/pin_zones.png)) | 15 | 290 | 8.4 | 100 | 3.8 | in_band | 2.29 | 5.43 | 0.35 | 54 (19%) | — |
| [Hole 16](../outputs/greens/hole_16/slope_heatmap.png) ([contours](../outputs/greens/hole_16/contours.png), [pins](../outputs/greens/hole_16/pin_zones.png)) | 16 | 484 | 18.1 | 316 | 3.6 | in_band | 3.67 | 6.66 | 1.06 | 39 (8%) | — |
| [Hole 17](../outputs/greens/hole_17/slope_heatmap.png) ([contours](../outputs/greens/hole_17/contours.png), [pins](../outputs/greens/hole_17/pin_zones.png)) | 17 | 377 | 8.3 | 100 | 3.1 | in_band | 2.86 | 6.63 | 0.79 | 60 (16%) | — |
| [Hole 18](../outputs/greens/hole_18/slope_heatmap.png) ([contours](../outputs/greens/hole_18/contours.png), [pins](../outputs/greens/hole_18/pin_zones.png)) | 18 | 258 | 8.3 | 1e+03 | 3.6 | in_band | 4.57 | 8.16 | 0.79 | 0 (0%) | mean_slope_4.57%_outside_0.5-4%; max_sustained_8.2%_gt_8% |
| [Practice](../outputs/greens/practice_1/slope_heatmap.png) ([contours](../outputs/greens/practice_1/contours.png), [pins](../outputs/greens/practice_1/pin_zones.png)) | — | 874 | 9.2 | 316 | 3.6 | in_band | 3.04 | 9.15 | 0.87 | 218 (25%) | max_sustained_9.1%_gt_8% |
| [Practice](../outputs/greens/practice_2/slope_heatmap.png) ([contours](../outputs/greens/practice_2/contours.png), [pins](../outputs/greens/practice_2/pin_zones.png)) | — | 331 | 8.2 | 10 | 3.8 | in_band | 3.01 | 7.19 | 0.69 | 62 (19%) | — |

`slope max*` = max slope sustained over a 1 m window on the green. Density flag threshold 1.5 pts/m², halt threshold 0.8 pts/m² — no green is below either.

## Legal pin zones

`legal pin` is the **standard** tier (≤2% macro slope over a 0.5 m cup bench, ≥3 m from the green edge) — a USGA-guided estimate of where a hole could be fairly cut. Two looser/stricter tiers (traditional ≤3%, premium ≤1.5%) are in each green's `pin_zones.png`/`.tif`/`.geojson`/`.npz`. This uses macro slope only (same caveat as the surfaces), so treat zones as guidance, not survey.

**Scarce legal area** (< 10 m² at standard tier): hole_10 (2 m²), hole_12 (5 m²), hole_13 (0 m²), hole_18 (0 m²). These are the steepest greens; a zero means no ≤3% bench exists anywhere on the surface — verify the polygon before trusting it.

## Flagged items

- **hole_03**: max_sustained_17.2%_gt_8%
- **hole_05**: max_sustained_9.8%_gt_8%
- **hole_07**: max_sustained_10.9%_gt_8%
- **hole_08**: max_sustained_8.4%_gt_8%
- **hole_12**: mean_slope_4.40%_outside_0.5-4%; max_sustained_8.1%_gt_8%
- **hole_13**: mean_slope_5.91%_outside_0.5-4%; max_sustained_12.2%_gt_8%
- **hole_14**: max_sustained_9.9%_gt_8%
- **hole_18**: mean_slope_4.57%_outside_0.5-4%; max_sustained_8.2%_gt_8%
- **practice_1**: max_sustained_9.1%_gt_8%

Notes on the flags: this course is built on a north-sloping bajada, so sustained-slope flags are mostly real terrain, and all flagged fits are still in the 3–6 cm residual band. Specifics from visual QC of the slope heatmaps: hole_03's 17% band is a steep bank clipped by the polygon's west edge (trim ~1–2 m or accept as collar); hole_13 genuinely tilts 4–6% north with its NW corner touching a bank; hole_18 sits on a uniform hillside (heaviest smoothing still fits at 3.6 cm); practice_1's 874 m² OSM polygon runs a touch large over a mound band. Hole numbering (1–18) and every green outline — including the 12 hand-digitized greens (holes 3–8, 12–17) and both practice greens — were human-confirmed on 2026-07-20.

## Data honesty

These surfaces recover **macro contours only** (tiers, main slopes). Source LiDAR vertical noise is ~5–10 cm RMSE, so the fit deliberately smooths to a 3–6 cm residual band rather than honoring individual returns; sub-1% micro-break is below the noise floor and is not represented. Greens may have been altered since acquisition (2021-10-04).

Overview map: [greens_overview.html](greens_overview.html)

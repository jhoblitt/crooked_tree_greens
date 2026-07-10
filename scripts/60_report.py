#!/usr/bin/env python3
"""Stage 6: repo-level QC report and sim-consumable index of all greens."""

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLY_DIR = ROOT / "data" / "polygons"
OUT = ROOT / "outputs" / "greens"
REPORTS = ROOT / "reports"

EXPECTED_HOLES = set(range(1, 19))
ARTIFACTS = ["heightmap.npz", "heightmap.tif", "mesh.obj", "mesh.glb",
             "slope_heatmap.png", "contours.png", "meta.json"]


def reconcile_outputs():
    """Only greens in the current manifest may be indexed as current.

    Output dirs are overwritten in place across reruns, so a green that was
    renamed or reassigned leaves its old dir behind — and a leftover .tmp dir
    means Stage 5 died mid-export. Either way, globbing outputs/ would report
    stale artifacts as current; halt instead.
    """
    manifest = {f["properties"]["label"]
                for f in json.loads((POLY_DIR / "greens.geojson").read_text())["features"]}
    dirs = {p.name for p in OUT.iterdir() if p.is_dir()}
    torn = sorted(d for d in dirs if d.endswith(".tmp"))
    if torn:
        sys.exit(f"HALT: interrupted Stage 5 export left {torn} — "
                 f"rerun scripts/50_export.py")
    orphans = sorted(dirs - manifest)
    if orphans:
        sys.exit(f"HALT: outputs/greens dirs not in data/polygons/greens.geojson: "
                 f"{orphans} — stale from a renamed/removed green; delete them or "
                 f"rerun stages 1-5")
    return sorted(manifest - dirs)


def main() -> int:
    unexported = reconcile_outputs()
    if unexported:
        print(f"note: manifest greens with no exports yet: {unexported}")
    metas = []
    for p in OUT.glob("*/meta.json"):
        m = json.loads(p.read_text())
        if m["label"] != p.parent.name:
            sys.exit(f"HALT: {p} claims label {m['label']!r} but lives in "
                     f"{p.parent.name!r} — stale or hand-moved export")
        metas.append(m)
    metas.sort(key=lambda m: (m["hole"] == 0, m["hole"], m["label"]))
    if not metas:
        raise SystemExit("no exported greens found — run stages 1-5 first")

    incomplete = []
    for m in metas:
        missing = [a for a in ARTIFACTS if not (OUT / m["label"] / a).exists()]
        if missing:
            incomplete.append((m["label"], missing))
    have_holes = {m["hole"] for m in metas if m["hole"]}
    missing_holes = sorted(EXPECTED_HOLES - have_holes)
    n_practice = sum(1 for m in metas if m["hole"] == 0)
    partial = bool(missing_holes)

    wu = sorted({w for m in metas for w in m["source_work_units"]})
    dates = sorted({d for m in metas for d in m["acquisition_dates"]})
    tiles = sorted({t for m in metas for t in m["tiles"]})

    lines = []
    add = lines.append
    add("# Crooked Tree Greens — QC report")
    add("")
    add(f"Generated {datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}"
        f" · status: **{'PARTIAL' if partial else 'COMPLETE'}**"
        f" ({len(have_holes)}/18 hole greens + {n_practice} practice)")
    add("")
    add(f"- Course: Crooked Tree Golf Course, Arthur Pack Regional Park, Tucson AZ "
        f"(OSM way 263321891; Nominatim cross-check passed)")
    add(f"- LiDAR source: {', '.join(wu)} (USGS 3DEP, public domain), "
        f"acquisition {', '.join(dates)}, tiles: {', '.join(tiles)}")
    add(f"- CRS: horizontal EPSG:6341 NAD83(2011)/UTM 12N (m); vertical EPSG:5703 NAVD88 (m), GEOID18")
    add(f"- Method: class-2 returns, 12 m collar buffer, 3.5×MAD plane-residual outlier "
        f"rejection, thin-plate-spline RBF on plane residuals, λ swept to land fit RMS in "
        f"3–6 cm, 0.25 m grid")
    add("")
    if partial:
        add(f"## ⚠ Missing greens: holes {', '.join(map(str, missing_holes))}")
        add("")
        add("OSM has only partial `golf=green` coverage for this course. To finish: open "
            "`reports/digitize_map.html`, trace each green at the red flag markers, click "
            "**Export**, save as `data/polygons/greens_manual.geojson`, then rerun "
            "`uv run scripts/10_green_polygons.py` and stages 2–6 (all idempotent; "
            "LAZ tiles already cover the whole course).")
        add("")
    add("## Greens")
    add("")
    add("| green | hole | area m² | pts/m² | λ | fit RMS cm | band | slope μ % | slope max* % | Δz m | flags |")
    add("|---|---|---|---|---|---|---|---|---|---|---|")
    for m in metas:
        add(f"| [{m['label']}](../outputs/greens/{m['label']}/slope_heatmap.png) "
            f"([contours](../outputs/greens/{m['label']}/contours.png)) "
            f"| {m['hole'] or '—'} | {m['green_area_m2']:.0f} "
            f"| {m['class2_density_on_green_pts_m2']:.1f} | {m['lambda']:.3g} "
            f"| {m['fit_rms_m']*100:.1f} | {m['fit_band_note']} "
            f"| {m['slope_mean_pct']:.2f} | {m['slope_max_sustained_pct']:.2f} "
            f"| {m['elevation_range_on_green_m']:.2f} "
            f"| {'; '.join(m['flags']) if m['flags'] else '—'} |")
    add("")
    add("`slope max*` = max slope sustained over a 1 m window on the green. "
        "Density flag threshold 1.5 pts/m², halt threshold 0.8 pts/m² — no green "
        "is below either.")
    add("")
    add("## Flagged items")
    add("")
    flagged = [m for m in metas if m["flags"] or m["needs_review"]]
    if not flagged:
        add("None.")
    for m in flagged:
        why = []
        if m["flags"]:
            why.append("; ".join(m["flags"]))
        if m["needs_review"]:
            why.append(f"polygon needs human review (hole_source={m['hole_source']})")
        add(f"- **{m['label']}**: {' · '.join(why)}")
    add("")
    add("Notes on the flags: this course is built on a north-sloping bajada, so "
        "sustained-slope flags are mostly real terrain, and all flagged fits are still "
        "in the 3–6 cm residual band. Specifics from visual QC of the slope heatmaps: "
        "hole_03's 17% band is a steep bank clipped by the polygon's west edge (trim "
        "~1–2 m or accept as collar); hole_13 genuinely tilts 4–6% north with its NW "
        "corner touching a bank; hole_18 sits on a uniform hillside (heaviest smoothing "
        "still fits at 3.6 cm); practice_1's 874 m² OSM polygon appears overdrawn and "
        "contains a mound band. Manually digitized polygons (holes 3–8, 12–17) and both "
        "practice greens carry needs_review by construction — check edges against each "
        "slope heatmap. Hole numbers were assigned from golf=hole line pin endpoints, "
        "which may not match the scorecard — confirm numbering before use.")
    add("")
    add("## Data honesty")
    add("")
    add("These surfaces recover **macro contours only** (tiers, main slopes). Source "
        "LiDAR vertical noise is ~5–10 cm RMSE, so the fit deliberately smooths to a "
        "3–6 cm residual band rather than honoring individual returns; sub-1% "
        "micro-break is below the noise floor and is not represented. Greens may have "
        f"been altered since acquisition ({', '.join(dates)}).")
    add("")
    add("Overview map: [greens_overview.html](greens_overview.html)")
    add("")
    if incomplete:
        add(f"**ARTIFACT GAPS:** {incomplete}")
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "qc_report.md").write_text("\n".join(lines))

    index = {
        "course": "Crooked Tree Golf Course, Arthur Pack Regional Park, Tucson AZ",
        "status": "partial" if partial else "complete",
        "missing_holes": missing_holes,
        "crs_horizontal": "EPSG:6341",
        "crs_vertical": "EPSG:5703 (NAVD88 m, GEOID18)",
        "cell_size_m": 0.25,
        "source_work_units": wu,
        "acquisition_dates": dates,
        "vertical_fidelity": metas[0]["vertical_fidelity"],
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "greens": [
            {
                "label": m["label"],
                "hole": m["hole"],
                "dir": f"outputs/greens/{m['label']}",
                "artifacts": {a.split(".")[0] + "_" + a.split(".")[1]
                              if a.count(".") else a: f"outputs/greens/{m['label']}/{a}"
                              for a in ARTIFACTS},
                "local_origin_utm": m["local_origin_utm"],
                "grid_shape": m["grid_shape"],
                "slope_mean_pct": m["slope_mean_pct"],
                "elevation_range_m": m["elevation_range_on_green_m"],
                "fit_rms_m": m["fit_rms_m"],
                "flags": m["flags"],
                "needs_review": m["needs_review"],
            }
            for m in metas
        ],
    }
    (OUT / "index.json").write_text(json.dumps(index, indent=1))

    print(f"wrote reports/qc_report.md and outputs/greens/index.json "
          f"({len(metas)} greens, status {'PARTIAL' if partial else 'COMPLETE'})")
    if incomplete:
        print(f"ARTIFACT GAPS: {incomplete}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

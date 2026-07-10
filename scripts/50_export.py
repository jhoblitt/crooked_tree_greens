#!/usr/bin/env python3
"""Stage 5: per-green exports.

For each fitted green: heightmap.npz, heightmap.tif (EPSG:6341, NAVD88 m),
mesh.obj + mesh.glb (local centroid origin, Z-up, meters), slope_heatmap.png,
contours.png (2.5 cm), meta.json -> outputs/greens/<label>/.
"""

import datetime
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import trimesh
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parent.parent
POLY_DIR = ROOT / "data" / "polygons"
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "outputs" / "greens"

DX = 0.25
CONTOUR_M = 0.025
INK, INK2 = "#3a3f45", "#8a9099"
CAVEAT = "macro contours only; source RMSE ~5-10 cm; micro-break below noise floor"

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:6341", always_xy=True).transform

plt.rcParams.update({
    "figure.dpi": 150, "font.size": 9, "text.color": INK,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "axes.linewidth": 0.6,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": "#e3e6ea", "grid.linewidth": 0.5,
})


def poly_rings_local(poly, cx, cy):
    rings = [np.asarray(poly.exterior.coords)] + [np.asarray(r.coords) for r in poly.interiors]
    return [(r[:, 0] - cx, r[:, 1] - cy) for r in rings]


def grid_mesh(zgrid, gx, gy, cx, cy, cz):
    ny, nx = zgrid.shape
    valid = np.isfinite(zgrid)
    vid = np.full(zgrid.shape, -1, dtype=np.int64)
    vid[valid] = np.arange(valid.sum())
    jj, ii = np.meshgrid(np.arange(nx), np.arange(ny))
    verts = np.column_stack([
        gx[jj[valid]] - cx, gy[ii[valid]] - cy, zgrid[valid] - cz,
    ])
    q = valid[:-1, :-1] & valid[:-1, 1:] & valid[1:, 1:] & valid[1:, :-1]
    a = vid[:-1, :-1][q]; b = vid[:-1, 1:][q]; c = vid[1:, 1:][q]; d = vid[1:, :-1][q]
    faces = np.concatenate([np.column_stack([a, b, c]), np.column_stack([a, c, d])])
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def slope_heatmap(path, title, slope, aspect_deg, in_green, gx, gy, cx, cy, poly, buf):
    lx, ly = gx - cx, gy - cy
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    shown = np.where(np.isfinite(slope), slope, np.nan)
    im = ax.imshow(shown, origin="lower", extent=(lx[0] - DX/2, lx[-1] + DX/2,
                                                  ly[0] - DX/2, ly[-1] + DX/2),
                   cmap="viridis", vmin=0, vmax=8, interpolation="nearest")
    cb = fig.colorbar(im, ax=ax, shrink=0.85, extend="max", pad=0.02)
    cb.set_label("slope [%]", color=INK)
    cb.ax.tick_params(color=INK2, labelcolor=INK2)

    step = 8  # 2 m arrow lattice
    sub = np.zeros_like(in_green, dtype=bool)
    sub[::step, ::step] = True
    m = in_green & sub & np.isfinite(slope)
    if m.any():
        ii, jj = np.nonzero(m)
        th = np.radians(aspect_deg[m])
        ax.quiver(lx[jj], ly[ii], np.cos(th), np.sin(th),
                  color="white", edgecolor="black", linewidth=0.4,
                  scale=28, width=0.004, headwidth=3.2, alpha=0.9)

    for rx, ry in poly_rings_local(poly, cx, cy):
        ax.plot(rx, ry, color="white", lw=1.6)
        ax.plot(rx, ry, color=INK, lw=0.5)
    for rx, ry in poly_rings_local(buf, cx, cy):
        ax.plot(rx, ry, color="white", lw=0.9, ls=(0, (4, 3)), alpha=0.8)

    ax.set_aspect("equal")
    ax.set_xlabel("east of centroid [m]"); ax.set_ylabel("north of centroid [m]")
    ax.set_title(title, color=INK, fontsize=10)
    fig.tight_layout()
    fig.savefig(path); plt.close(fig)


def contour_plot(path, title, zgrid, in_green, gx, gy, cx, cy, cz, poly):
    zg = np.where(in_green & np.isfinite(zgrid), zgrid - cz, np.nan)
    if not np.isfinite(zg).any():
        return
    lx, ly = gx - cx, gy - cy
    zmin, zmax = np.nanmin(zg), np.nanmax(zg)
    lo = np.floor(zmin / CONTOUR_M) * CONTOUR_M
    levels = np.arange(lo, zmax + CONTOUR_M, CONTOUR_M)
    index = levels[np.isclose(np.mod(np.round(levels / CONTOUR_M), 4), 0)]

    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    ax.contourf(lx, ly, zg, levels=levels, cmap="Blues_r", alpha=0.35)
    cs = ax.contour(lx, ly, zg, levels=levels, colors="#5b7fa6", linewidths=0.5)
    csi = ax.contour(lx, ly, zg, levels=index, colors="#2f4f74", linewidths=1.1)
    ax.clabel(csi, fmt=lambda v: f"{v:+.2f}", fontsize=7, colors=INK)

    for rx, ry in poly_rings_local(poly, cx, cy):
        ax.plot(rx, ry, color=INK, lw=1.2)

    ax.set_aspect("equal")
    ax.set_xlabel("east of centroid [m]"); ax.set_ylabel("north of centroid [m]")
    ax.set_title(title, color=INK, fontsize=10)
    fig.tight_layout()
    fig.savefig(path); plt.close(fig)


def export_green(feat):
    label = feat["properties"]["label"]
    g = np.load(INTERIM / f"{label}_grid.npz", allow_pickle=False)
    fit = json.loads(str(g["fit"]))
    prov = fit["provenance"]
    zgrid = g["z"].astype(np.float32)
    slope, aspect = g["slope_pct"], g["aspect_deg"]
    in_green = g["in_green"]
    x0, y0 = float(g["x0"]), float(g["y0"])
    ny, nx = zgrid.shape
    gx = x0 + np.arange(nx) * DX
    gy = y0 + np.arange(ny) * DX

    poly = shp_transform(TO_UTM, shape(feat["geometry"]))
    buf = poly.buffer(float(prov["buffer_m"]))
    cx, cy = poly.centroid.x, poly.centroid.y
    ci, cj = np.argmin(np.abs(gy - cy)), np.argmin(np.abs(gx - cx))
    cz = float(zgrid[ci, cj])

    # Stage 6 rejects leftover .tmp dirs, so an interrupted export can never
    # pass off a half-overwritten green as current.
    out = OUT / f"{label}.tmp"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    z_north_up = zgrid[::-1]
    np.savez_compressed(
        out / "heightmap.npz",
        z=z_north_up, x0=gx[0], y0=gy[-1], dx=DX,
        local_origin=np.array([cx, cy, cz]),
        crs="EPSG:6341 (NAD83(2011)/UTM 12N) + NAVD88 m (EPSG:5703)",
        layout="row-major north-up: z[0,0] node at (x0, y0), row step -dx north->south",
    )

    with rasterio.open(
        out / "heightmap.tif", "w", driver="GTiff",
        height=ny, width=nx, count=1, dtype="float32",
        crs="EPSG:6341", transform=from_origin(gx[0] - DX/2, gy[-1] + DX/2, DX, DX),
        nodata=np.nan,
    ) as dst:
        dst.write(z_north_up, 1)
        dst.update_tags(AREA_OR_POINT="Point",
                        VERTICAL_DATUM="NAVD88 height (EPSG:5703), meters, GEOID18",
                        SOURCE=";".join(prov["tiles"]), VERTICAL_FIDELITY=CAVEAT)

    mesh = grid_mesh(zgrid, gx, gy, cx, cy, cz)
    mesh.export(out / "mesh.obj")
    mesh.export(out / "mesh.glb")

    stitle = (f"{label} — slope, TPS λ={fit['lambda']:.3g}, "
              f"fit RMS {fit['fit_rms_m']*100:.1f} cm")
    slope_heatmap(out / "slope_heatmap.png", stitle, slope, aspect, in_green,
                  gx, gy, cx, cy, poly, buf)
    contour_plot(out / "contours.png", f"{label} — contours every 2.5 cm (rel. to centroid)",
                 zgrid, in_green, gx, gy, cx, cy, cz, poly)

    zvals = zgrid[in_green & np.isfinite(zgrid)]
    meta = {
        "hole": feat["properties"]["hole"],
        "label": label,
        "needs_review": feat["properties"]["needs_review"],
        "hole_source": feat["properties"]["hole_source"],
        "source_work_units": prov["work_units"],
        "acquisition_dates": prov["acquisition_dates"],
        "tiles": prov["tiles"],
        "crs_horizontal": "EPSG:6341 NAD83(2011) / UTM zone 12N (m)",
        "crs_vertical": "EPSG:5703 NAVD88 height (m), GEOID18",
        "cell_size_m": DX,
        "grid_shape": [int(ny), int(nx)],
        "grid_origin_north_up": [float(gx[0]), float(gy[-1])],
        "local_origin_utm": [cx, cy, cz],
        "green_area_m2": round(prov["green_area_m2"], 1),
        "class2_density_on_green_pts_m2": round(prov["density_on_green_pts_m2"], 2),
        "n_points_fit_region": fit["n_points"],
        "lambda": fit["lambda"],
        "fit_rms_m": round(fit["fit_rms_m"], 4),
        "fit_band_note": fit["band_note"],
        "slope_mean_pct": round(fit["mean_slope_pct"], 2),
        "slope_max_pct": round(fit["max_slope_pct"], 2),
        "slope_max_sustained_pct": round(fit["max_sustained_slope_pct"], 2),
        "sustained_window_m": fit["sustained_window_m"],
        "elevation_range_on_green_m": round(float(zvals.max() - zvals.min()), 3),
        "flags": fit["flags"],
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "vertical_fidelity": CAVEAT,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1))

    final = OUT / label
    if final.exists():
        shutil.rmtree(final)
    out.rename(final)
    return meta


def main() -> int:
    feats = json.loads((POLY_DIR / "greens.geojson").read_text())["features"]
    done = []
    for f in feats:
        meta = export_green(f)
        done.append(meta)
        print(f"  {meta['label']:>10}: grid {meta['grid_shape']}, "
              f"λ={meta['lambda']:.3g}, rms {meta['fit_rms_m']*100:.1f} cm, "
              f"slope μ {meta['slope_mean_pct']}% max* {meta['slope_max_sustained_pct']}%"
              + (f", flags: {'; '.join(meta['flags'])}" if meta["flags"] else ""))
    print(f"\nCHECKPOINT: exported {len(done)} greens to outputs/greens/<label>/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

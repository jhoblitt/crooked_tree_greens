#!/usr/bin/env python3
"""Stage 3: clip class-2 (ground) points to each buffered green and clean them.

Each LAZ tile is streamed once; every chunk is tested against all greens.
Points are already NAD83(2011)/UTM 12N + NAVD88 meters (verified in Stage 2).
Outliers are rejected on best-fit-plane residuals at 3.5x scaled MAD, then the
plane is refit once. Results land in data/interim/<label>.npz with provenance.

Checkpoint: class-2 density on the unbuffered green polygon. Flag < 1.5
pts/m^2; HALT if any green < 0.8 pts/m^2.
"""

import datetime
import json
import sys
from pathlib import Path

import laspy
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parent.parent
POLY_DIR = ROOT / "data" / "polygons"
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"

GREEN_BUFFER_M = 12.0
MAD_K = 3.5
DENSITY_FLAG = 1.5
DENSITY_HALT = 0.8

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:6341", always_xy=True).transform


def gps_to_date(t_adjusted: float) -> str:
    epoch = datetime.datetime(1980, 1, 6, tzinfo=datetime.UTC)
    return (epoch + datetime.timedelta(seconds=t_adjusted + 1e9)).date().isoformat()


def fit_plane(x, y, z):
    A = np.column_stack([x - x.mean(), y - y.mean(), np.ones_like(x)])
    coef, *_ = np.linalg.lstsq(A, z, rcond=None)
    resid = z - A @ coef
    return coef, resid


def clean(x, y, z):
    _, resid = fit_plane(x, y, z)
    med = np.median(resid)
    sigma = 1.4826 * np.median(np.abs(resid - med))
    thresh = MAD_K * sigma
    keep = np.abs(resid - med) <= thresh
    coef, resid2 = fit_plane(x[keep], y[keep], z[keep])
    return keep, coef, float(np.sqrt(np.mean(resid2**2))), float(sigma), float(thresh)


def manifest_tiles(tiles_meta):
    """The LAZ set Stage 3 may read is exactly the Stage 2-validated manifest.

    Anything else in data/raw (a superseded work unit's tiles, a hand-dropped
    file) would otherwise blend silently into the fits while provenance still
    cited the manifest.
    """
    names = [t["tile"] for t in tiles_meta["tiles"]]
    missing = [n for n in names if not (RAW / n).exists()]
    if missing:
        sys.exit(f"HALT: manifest tiles missing from data/raw: {missing} — "
                 f"rerun scripts/20_fetch_lidar.py")
    extras = sorted(p.name for p in RAW.glob("*.laz") if p.name not in set(names))
    if extras:
        sys.exit(f"HALT: LAZ files in data/raw not in tiles_meta.json: {extras} — "
                 f"remove them or rerun scripts/20_fetch_lidar.py")
    return [RAW / n for n in sorted(names)]


def main() -> int:
    tiles_meta = json.loads((RAW / "tiles_meta.json").read_text())
    assert all(u.lower().replace("metre", "meter") == "meter"
               for t in tiles_meta["tiles"] for _, u in t["axis_units"]), \
        "Stage 2 should have halted: non-meter units"

    feats = json.loads((POLY_DIR / "greens.geojson").read_text())["features"]
    greens = []
    for f in feats:
        poly = shp_transform(TO_UTM, shape(f["geometry"]))
        buf = poly.buffer(GREEN_BUFFER_M)
        greens.append({
            "label": f["properties"]["label"],
            "hole": f["properties"]["hole"],
            "poly": poly,
            "buf": buf,
            "bbox": buf.bounds,
            "xs": [], "ys": [], "zs": [], "tmin": np.inf, "tmax": -np.inf,
            "tiles": set(),
        })

    tile_paths = manifest_tiles(tiles_meta)
    for tp in tile_paths:
        with laspy.open(tp) as f:
            n_read = 0
            for pts in f.chunk_iterator(2_000_000):
                n_read += len(pts)
                gx, gy, gz = np.asarray(pts.x), np.asarray(pts.y), np.asarray(pts.z)
                cls = np.asarray(pts.classification)
                gt = np.asarray(pts.gps_time)
                ground = cls == 2
                for g in greens:
                    x0, y0, x1, y1 = g["bbox"]
                    m = ground & (gx >= x0) & (gx <= x1) & (gy >= y0) & (gy <= y1)
                    if not m.any():
                        continue
                    inside = shapely.contains_xy(g["buf"], gx[m], gy[m])
                    if not inside.any():
                        continue
                    g["xs"].append(gx[m][inside])
                    g["ys"].append(gy[m][inside])
                    g["zs"].append(gz[m][inside])
                    tsel = gt[m][inside]
                    g["tmin"] = min(g["tmin"], float(tsel.min()))
                    g["tmax"] = max(g["tmax"], float(tsel.max()))
                    g["tiles"].add(tp.name)
            print(f"streamed {tp.name}: {n_read:,} points")

    INTERIM.mkdir(parents=True, exist_ok=True)
    halts, flags = [], []
    print(f"\n{'green':>10} {'class2':>8} {'kept':>8} {'dens(green)':>11} "
          f"{'planeRMS':>9} {'madσ':>6} acquisition")
    for g in greens:
        if not g["xs"]:
            halts.append((g["label"], 0.0))
            print(f"{g['label']:>10} {'0':>8}  NO POINTS")
            continue
        x = np.concatenate(g["xs"])
        y = np.concatenate(g["ys"])
        z = np.concatenate(g["zs"])
        keep, coef, rms, sigma, thresh = clean(x, y, z)
        xk, yk, zk = x[keep], y[keep], z[keep]

        on_green = shapely.contains_xy(g["poly"], xk, yk)
        density = float(on_green.sum() / g["poly"].area)
        if density < DENSITY_HALT:
            halts.append((g["label"], density))
        elif density < DENSITY_FLAG:
            flags.append((g["label"], density))

        dates = sorted({gps_to_date(g["tmin"]), gps_to_date(g["tmax"])})
        prov = {
            "label": g["label"],
            "hole": g["hole"],
            "crs": "EPSG:6341 + NAVD88 (EPSG:5703), meters",
            "work_units": tiles_meta["work_units"],
            "tiles": sorted(g["tiles"]),
            "acquisition_dates": dates,
            "n_class2_in_buffer": int(len(x)),
            "n_after_outlier_reject": int(keep.sum()),
            "n_rejected": int((~keep).sum()),
            "mad_sigma_m": sigma,
            "reject_threshold_m": thresh,
            "plane_rms_m": rms,
            "density_on_green_pts_m2": density,
            "green_area_m2": g["poly"].area,
            "buffer_m": GREEN_BUFFER_M,
        }
        np.savez_compressed(
            INTERIM / f"{g['label']}.npz",
            x=xk, y=yk, z=zk,
            provenance=json.dumps(prov),
        )
        print(f"{g['label']:>10} {len(x):>8,} {keep.sum():>8,} {density:>11.2f} "
              f"{rms:>9.3f} {sigma:>6.3f} {'..'.join(dates)}")

    print()
    for label, d in flags:
        print(f"FLAG: {label} density {d:.2f} pts/m² < {DENSITY_FLAG}")
    if halts:
        for label, d in halts:
            print(f"HALT: {label} density {d:.2f} pts/m² < {DENSITY_HALT}")
        return 1
    print(f"CHECKPOINT OK: {len(greens)} greens clipped; all densities >= {DENSITY_HALT} pts/m²"
          + (f" ({len(flags)} flagged < {DENSITY_FLAG})" if flags else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

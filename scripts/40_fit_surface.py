#!/usr/bin/env python3
"""Stage 4: fit a smooth surface per green (thin-plate-spline RBF).

LiDAR vertical noise (~5-10 cm RMSE) must not be honored point-for-point.
Points are detrended with a best-fit plane, a TPS RBF is fit to the residuals
on a lambda (smoothing) sweep, and the smallest lambda whose fit-vs-data RMS
lands in the 3-6 cm band is selected. The surface is evaluated on a 0.25 m
axis-aligned UTM grid over the buffered polygon, masked outside it.

Writes data/interim/<label>_grid.npz. Slope sanity: on-green mean slope
0.5-4 %; flag max sustained (1 m boxcar) > 8 % or < 0.3 %.
"""

import json
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from scipy.interpolate import RBFInterpolator
from scipy.ndimage import uniform_filter
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parent.parent
POLY_DIR = ROOT / "data" / "polygons"
INTERIM = ROOT / "data" / "interim"

DX = 0.25
GREEN_BUFFER_M = 12.0
RMS_LO, RMS_HI = 0.03, 0.06
LAMBDAS = np.logspace(-3, 4, 15)
FIT_MAX_PTS = 3500
SUSTAIN_M = 1.0

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:6341", always_xy=True).transform


def fit_plane(xy, z):
    A = np.column_stack([xy[:, 0], xy[:, 1], np.ones(len(xy))])
    coef, *_ = np.linalg.lstsq(A, z, rcond=None)
    return coef, z - A @ coef


def rms_vs_all(rbf, xy, resid):
    pred = np.concatenate([rbf(c) for c in np.array_split(xy, max(1, len(xy) // 20000))])
    return float(np.sqrt(np.mean((pred - resid) ** 2)))


def sweep_lambda(xy_fit, resid_fit, xy_all, resid_all):
    """Ascending lambda sweep; RMS grows with lambda, so stop once past the band."""
    history = []
    for lam in LAMBDAS:
        rbf = RBFInterpolator(xy_fit, resid_fit, kernel="thin_plate_spline", smoothing=lam)
        rms = rms_vs_all(rbf, xy_all, resid_all)
        history.append((float(lam), rms))
        if rms >= RMS_LO:
            break
    in_band = [(lam, rms) for lam, rms in history if RMS_LO <= rms <= RMS_HI]
    if in_band:
        lam, rms = in_band[0]
        note = "in_band"
    else:
        lam, rms = min(history, key=lambda t: min(abs(t[1] - RMS_LO), abs(t[1] - RMS_HI)))
        note = "nearest_band"
    rbf = RBFInterpolator(xy_fit, resid_fit, kernel="thin_plate_spline", smoothing=lam)
    return rbf, lam, rms, note, history


def main() -> int:
    feats = json.loads((POLY_DIR / "greens.geojson").read_text())["features"]
    rng = np.random.default_rng(6341)
    any_flag = False

    print(f"{'green':>10} {'npts':>7} {'nfit':>5} {'lambda':>9} {'fitRMS':>7} {'band':>12} "
          f"{'mean%':>6} {'max%':>6} {'zrange':>7} flags")
    for f in feats:
        label = f["properties"]["label"]
        npz = np.load(INTERIM / f"{label}.npz", allow_pickle=False)
        x, y, z = npz["x"], npz["y"], npz["z"]
        prov = json.loads(str(npz["provenance"]))

        poly = shp_transform(TO_UTM, shape(f["geometry"]))
        buf = poly.buffer(GREEN_BUFFER_M)

        xy = np.column_stack([x, y])
        plane, resid = fit_plane(xy, z)

        if len(xy) > FIT_MAX_PTS:
            sel = rng.choice(len(xy), FIT_MAX_PTS, replace=False)
        else:
            sel = np.arange(len(xy))
        rbf, lam, rms, note, history = sweep_lambda(xy[sel], resid[sel], xy, resid)

        x0 = np.floor(buf.bounds[0] / DX) * DX
        y0 = np.floor(buf.bounds[1] / DX) * DX
        nx = int(np.ceil((buf.bounds[2] - x0) / DX)) + 1
        ny = int(np.ceil((buf.bounds[3] - y0) / DX)) + 1
        gx = x0 + np.arange(nx) * DX
        gy = y0 + np.arange(ny) * DX
        GX, GY = np.meshgrid(gx, gy)  # row 0 = south edge
        nodes = np.column_stack([GX.ravel(), GY.ravel()])

        in_buf = shapely.contains_xy(buf, nodes[:, 0], nodes[:, 1])
        zres = np.full(len(nodes), np.nan)
        idx = np.where(in_buf)[0]
        for c in np.array_split(idx, max(1, len(idx) // 20000)):
            zres[c] = rbf(nodes[c])
        zgrid = (zres + nodes @ plane[:2] + plane[2]).reshape(ny, nx)

        in_green = shapely.contains_xy(poly, nodes[:, 0], nodes[:, 1]).reshape(ny, nx)

        dzdy, dzdx = np.gradient(zgrid, DX)
        slope_pct = np.hypot(dzdx, dzdy) * 100.0
        aspect_deg = np.degrees(np.arctan2(-dzdy, -dzdx))  # downhill direction, math convention

        sg = slope_pct[in_green]
        sg = sg[np.isfinite(sg)]
        mean_slope, max_slope = float(sg.mean()), float(sg.max())

        k = max(1, int(round(SUSTAIN_M / DX)))
        sm = uniform_filter(np.nan_to_num(slope_pct), size=k)
        norm = uniform_filter(np.isfinite(slope_pct).astype(float), size=k)
        with np.errstate(invalid="ignore"):
            sustained = np.where(norm > 0.5, sm / np.maximum(norm, 1e-9), np.nan)
        smax = float(np.nanmax(np.where(in_green, sustained, np.nan)))

        zvals = zgrid[in_green & np.isfinite(zgrid)]
        zrange = float(zvals.max() - zvals.min())

        flags = []
        if not (0.5 <= mean_slope <= 4.0):
            flags.append(f"mean_slope_{mean_slope:.2f}%_outside_0.5-4%")
        if smax > 8.0:
            flags.append(f"max_sustained_{smax:.1f}%_gt_8%")
        if smax < 0.3:
            flags.append(f"max_sustained_{smax:.1f}%_lt_0.3%_oversmoothed?")
        if note != "in_band":
            flags.append(f"rms_{rms*100:.1f}cm_outside_3-6cm_band")
        any_flag |= bool(flags)

        np.savez_compressed(
            INTERIM / f"{label}_grid.npz",
            z=zgrid.astype(np.float32),
            slope_pct=slope_pct.astype(np.float32),
            aspect_deg=aspect_deg.astype(np.float32),
            in_green=in_green,
            x0=x0, y0=y0, dx=DX,
            plane=plane,
            fit=json.dumps({
                "lambda": lam, "fit_rms_m": rms, "band_note": note,
                "lambda_history": history, "n_points": int(len(xy)),
                "n_fit_subsample": int(len(sel)),
                "mean_slope_pct": mean_slope, "max_slope_pct": max_slope,
                "max_sustained_slope_pct": smax, "sustained_window_m": SUSTAIN_M,
                "z_range_on_green_m": zrange, "flags": flags,
                "provenance": prov,
            }),
        )
        print(f"{label:>10} {len(xy):>7,} {len(sel):>5} {lam:>9.3g} {rms*100:>6.1f}cm "
              f"{note:>12} {mean_slope:>6.2f} {smax:>6.2f} {zrange:>6.2f}m "
              f"{' '.join(flags) if flags else '-'}")

    print("\nCHECKPOINT " + ("OK (with flags — see above)" if any_flag else "OK") +
          ": all greens fitted; grids in data/interim/*_grid.npz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

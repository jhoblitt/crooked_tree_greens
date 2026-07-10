"""Stage 4 plumbing: lambda sweep band selection, gridding, masking, slopes."""

import json

import numpy as np
import pytest
from conftest import load_script

mod = load_script("40_fit_surface")


def test_sweep_lambda_rms_monotone_and_selection(monkeypatch):
    monkeypatch.setattr(mod, "LAMBDAS", np.logspace(-2, 2, 5))
    rng = np.random.default_rng(4)
    n = 500
    xy = np.column_stack([rng.uniform(0, 30, n), rng.uniform(0, 30, n)])
    resid = 0.1 * np.sin(xy[:, 0] / 6.0) + rng.normal(0, 0.04, n)
    rbf, lam, rms, note, history = mod.sweep_lambda(xy, resid, xy, resid)
    rmss = [r for _, r in history]
    assert all(b >= a - 1e-6 for a, b in zip(rmss, rmss[1:], strict=False))  # monotone up
    if note == "in_band":
        assert mod.RMS_LO <= rms <= mod.RMS_HI
        assert lam == min(lam_ for lam_, r in history if mod.RMS_LO <= r <= mod.RMS_HI)


def test_fit_lands_in_band_with_realistic_noise(staged_course):
    """0.04 m synthetic noise ≈ real LiDAR: the sweep must land in 3-6 cm."""
    m30, m40, m50, m60 = staged_course
    g = np.load(m40.INTERIM / "hole_01_grid.npz", allow_pickle=False)
    fit = json.loads(str(g["fit"]))
    assert fit["band_note"] == "in_band"
    assert mod.RMS_LO <= fit["fit_rms_m"] <= mod.RMS_HI


def test_fit_writes_grid_with_mask_and_slopes(staged_course):
    m30, m40, m50, m60 = staged_course
    g = np.load(m40.INTERIM / "hole_01_grid.npz", allow_pickle=False)
    z, in_green = g["z"], g["in_green"]
    fit = json.loads(str(g["fit"]))

    assert float(g["dx"]) == m40.DX
    assert np.isnan(z).any()                 # masked outside buffered polygon
    assert np.isfinite(z[in_green]).all()    # solid inside the green
    zg = z[in_green]
    assert 730.0 < zg.min() < zg.max() < 732.5
    assert 0.5 < fit["mean_slope_pct"] < 4.5
    assert fit["provenance"]["tiles"] == ["tile_a.laz"]


def test_grid_is_axis_aligned_quarter_meter(staged_course):
    m30, m40, m50, m60 = staged_course
    g = np.load(m40.INTERIM / "hole_01_grid.npz", allow_pickle=False)
    x0, y0 = float(g["x0"]), float(g["y0"])
    assert x0 == pytest.approx(round(x0 / 0.25) * 0.25)
    assert y0 == pytest.approx(round(y0 / 0.25) * 0.25)


def test_slope_matches_gradient_of_grid(staged_course):
    """slope_pct must be derivable from z — the sim trusts this field."""
    m30, m40, m50, m60 = staged_course
    g = np.load(m40.INTERIM / "hole_01_grid.npz", allow_pickle=False)
    z, slope = g["z"].astype(np.float64), g["slope_pct"]
    dzdy, dzdx = np.gradient(z, 0.25)
    expect = np.hypot(dzdx, dzdy) * 100.0
    m = np.isfinite(expect) & np.isfinite(slope)
    assert m.any()
    assert np.nanmax(np.abs(expect[m] - slope[m])) < 0.05


def test_aspect_points_downhill(staged_course):
    """Walking one meter along the stored aspect must descend.

    The slope heatmap arrows and any sim logic reading aspect_deg depend on
    this convention (math angle, downhill direction).
    """
    m30, m40, m50, m60 = staged_course
    g = np.load(m40.INTERIM / "hole_01_grid.npz", allow_pickle=False)
    z, aspect, slope, in_green = (g["z"].astype(np.float64), g["aspect_deg"],
                                  g["slope_pct"], g["in_green"])
    step = 4  # 1 m in 0.25 m cells
    ny, nx = z.shape
    ii, jj = np.nonzero(in_green & (slope > 1.0))
    checked = descended = 0
    for i, j in zip(ii[::7], jj[::7], strict=True):
        th = np.radians(float(aspect[i, j]))
        i2 = i + int(round(np.sin(th) * step))
        j2 = j + int(round(np.cos(th) * step))
        if not (0 <= i2 < ny and 0 <= j2 < nx) or not np.isfinite(z[i2, j2]):
            continue
        checked += 1
        descended += z[i2, j2] < z[i, j]
    assert checked > 20
    assert descended / checked > 0.95

"""Stage 4 plumbing: lambda sweep band selection, gridding, masking, slopes."""

import json

import numpy as np
import pytest

from conftest import (BASE_E, BASE_N, load_script, make_greens_geojson,
                      make_tile, make_tiles_meta)

mod = load_script("40_fit_surface")
clip = load_script("30_clip_clean")


@pytest.fixture
def fitted(sandbox, monkeypatch):
    """Run stages 3+4 on a small synthetic course; return the fit module."""
    m30, m40 = sandbox("30_clip_clean", "40_fit_surface")
    make_greens_geojson(m30.POLY_DIR / "greens.geojson",
                        [("hole_01", 1, BASE_E, BASE_N, 7.0)])
    tile = make_tile(m30.RAW / "tile_a.laz", BASE_E - 40, BASE_N - 40,
                     size=80, density=4.0)
    make_tiles_meta(m30.RAW, [tile])
    monkeypatch.setattr(m40, "POLY_DIR", m30.POLY_DIR)
    monkeypatch.setattr(m40, "INTERIM", m30.INTERIM)
    monkeypatch.setattr(m40, "FIT_MAX_PTS", 1200)
    monkeypatch.setattr(m40, "LAMBDAS", np.logspace(-2, 3, 6))
    assert clip is m30 and m30.main() == 0
    assert m40.main() == 0
    return m40


def test_sweep_lambda_rms_monotone_and_selection():
    rng = np.random.default_rng(4)
    n = 900
    xy = np.column_stack([rng.uniform(0, 30, n), rng.uniform(0, 30, n)])
    resid = 0.1 * np.sin(xy[:, 0] / 6.0) + rng.normal(0, 0.03, n)
    rbf, lam, rms, note, history = mod.sweep_lambda(xy, resid, xy, resid)
    rmss = [r for _, r in history]
    assert all(b >= a - 1e-6 for a, b in zip(rmss, rmss[1:]))  # monotone up
    assert note in ("in_band", "nearest_band")
    if note == "in_band":
        assert mod.RMS_LO <= rms <= mod.RMS_HI


def test_fit_writes_grid_with_mask_and_slopes(fitted):
    g = np.load(fitted.INTERIM / "hole_01_grid.npz", allow_pickle=False)
    z, in_green = g["z"], g["in_green"]
    fit = json.loads(str(g["fit"]))

    assert float(g["dx"]) == fitted.DX
    # NaN outside buffered polygon, finite inside the green
    assert np.isnan(z).any()
    assert np.isfinite(z[in_green]).all()
    # on-green z in the synthetic terrain's range
    zg = z[in_green]
    assert 730.0 < zg.min() < zg.max() < 732.5
    # gentle synthetic terrain: mean slope near the plane's 2.2%
    assert 0.5 < fit["mean_slope_pct"] < 4.5
    assert fit["band_note"] in ("in_band", "nearest_band")
    assert fit["provenance"]["tiles"] == ["tile_a.laz"]


def test_grid_is_axis_aligned_quarter_meter(fitted):
    g = np.load(fitted.INTERIM / "hole_01_grid.npz", allow_pickle=False)
    x0, y0 = float(g["x0"]), float(g["y0"])
    assert x0 == pytest.approx(round(x0 / 0.25) * 0.25)
    assert y0 == pytest.approx(round(y0 / 0.25) * 0.25)

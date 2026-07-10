"""Stage 3 plumbing: manifest binding (Codex finding 1), cleaning, density gates."""

import datetime
import json

import numpy as np
import pytest

from conftest import (BASE_E, BASE_N, gps_adjusted, load_script,
                      make_greens_geojson, make_tile, make_tiles_meta)

mod = load_script("30_clip_clean")


def setup_course(m, density=6.0, classification=None, green_r=8.0):
    make_greens_geojson(m.POLY_DIR / "greens.geojson",
                        [("hole_01", 1, BASE_E, BASE_N, green_r)])
    tile = make_tile(m.RAW / "tile_a.laz", BASE_E - 60, BASE_N - 60,
                     size=120, density=density, classification=classification)
    make_tiles_meta(m.RAW, [tile])
    return tile


def test_gps_to_date_matches_synthetic_time():
    assert mod.gps_to_date(gps_adjusted(datetime.date(2021, 10, 4))) == "2021-10-04"


def test_fit_plane_recovers_coefficients():
    rng = np.random.default_rng(2)
    x, y = rng.uniform(0, 50, 800), rng.uniform(0, 50, 800)
    z = 700 + 0.03 * x - 0.02 * y
    coef, resid = mod.fit_plane(x, y, z)
    assert abs(coef[0] - 0.03) < 1e-9 and abs(coef[1] + 0.02) < 1e-9
    assert np.max(np.abs(resid)) < 1e-9


def test_clean_drops_gross_outliers_keeps_inliers():
    rng = np.random.default_rng(3)
    n = 2000
    x, y = rng.uniform(0, 50, n), rng.uniform(0, 50, n)
    z = 700 + 0.02 * x + rng.normal(0, 0.02, n)
    z[:20] += 5.0  # birds / vegetation misclassified as ground
    keep, coef, rms, sigma, thresh = mod.clean(x, y, z)
    assert not keep[:20].any()
    assert keep[20:].mean() > 0.97
    assert rms < 0.03
    assert thresh == pytest.approx(3.5 * sigma)


def test_manifest_binding_halts_on_stray_laz(sandbox):
    """Regression: a leftover/foreign LAZ in data/raw must halt, not blend in."""
    m = sandbox("30_clip_clean")
    setup_course(m)
    make_tile(m.RAW / "stray_2019.laz", BASE_E - 60, BASE_N - 60, size=120, density=1)
    with pytest.raises(SystemExit, match="stray_2019.laz"):
        m.main()


def test_manifest_binding_halts_on_missing_tile(sandbox):
    m = sandbox("30_clip_clean")
    tile = setup_course(m)
    tile.unlink()
    with pytest.raises(SystemExit, match="missing from data/raw"):
        m.main()


def test_clip_produces_interim_with_sane_density(sandbox, capsys):
    m = sandbox("30_clip_clean")
    setup_course(m, density=6.0)  # ~5.4 class-2 pts/m²
    assert m.main() == 0
    npz = np.load(m.INTERIM / "hole_01.npz")
    prov = json.loads(str(npz["provenance"]))
    assert prov["acquisition_dates"] == ["2021-10-04"]
    assert prov["tiles"] == ["tile_a.laz"]
    assert 3.0 < prov["density_on_green_pts_m2"] < 8.0
    # every kept point is inside the buffered polygon bbox
    r_max = 8.0 + m.GREEN_BUFFER_M + 1.0
    d = np.hypot(npz["x"] - BASE_E, npz["y"] - BASE_N)
    assert d.max() <= r_max


def test_density_halt_below_floor(sandbox):
    m = sandbox("30_clip_clean")
    setup_course(m, density=0.5, classification=2)  # 0.5 pts/m² < 0.8 floor
    assert m.main() == 1


def test_non_ground_points_are_excluded(sandbox):
    m = sandbox("30_clip_clean")
    setup_course(m, density=6.0, classification=1)  # nothing is class 2
    assert m.main() == 1  # NO POINTS halt

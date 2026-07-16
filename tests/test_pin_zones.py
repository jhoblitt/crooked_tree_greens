"""Stage 45 plumbing: legal pin-zone masks, tiers, edge setback, cup bench."""

import numpy as np
import pytest
from conftest import load_script
from scipy.ndimage import binary_erosion

mod = load_script("45_pin_zones")
DX = 0.25


def disk_green(radius_m, dx=DX, pad_m=6.0):
    n = int((2 * radius_m + 2 * pad_m) / dx)
    c = n // 2
    yy, xx = np.ogrid[:n, :n]
    d = np.hypot((xx - c) * dx, (yy - c) * dx)
    return d <= radius_m, c, n


def test_disk_radius_and_center():
    d = mod._disk(0.5, DX)          # 0.5 m / 0.25 = 2-cell radius
    assert d.shape == (5, 5)
    assert d[2, 2] and not d[0, 0]


def test_flat_green_all_tiers_equal_and_setback_respected():
    in_green, _, _ = disk_green(10.0)
    slope = np.zeros_like(in_green, float)
    cls = mod.legal_pin_class(slope, in_green, DX)
    stats = mod.tier_stats(cls, DX)
    t = stats["tiers"]
    # a perfectly flat green: every tier admits the same area
    assert t["premium"]["area_m2"] == t["standard"]["area_m2"] == t["traditional"]["area_m2"]
    assert t["standard"]["area_m2"] > 0
    # every legal cell lies at least the setback inside the putting surface
    interior = binary_erosion(in_green, mod._disk(mod.EDGE_SETBACK_M, DX), border_value=0)
    legal = (cls != mod.OFF_GREEN) & (cls >= 1)
    assert legal[~interior].sum() == 0
    # off-green is sentinel
    assert (cls[~in_green] == mod.OFF_GREEN).all()


def test_slope_threshold_discriminates_tiers():
    in_green, _, _ = disk_green(10.0)
    # 2.5% everywhere: legal only under the traditional (≤3%) tier
    cls = mod.legal_pin_class(np.full(in_green.shape, 2.5), in_green, DX)
    t = mod.tier_stats(cls, DX)["tiers"]
    assert t["traditional"]["area_m2"] > 0
    assert t["standard"]["area_m2"] == 0 and t["premium"]["area_m2"] == 0
    # 3.5% everywhere: nothing is legal at any tier
    cls2 = mod.legal_pin_class(np.full(in_green.shape, 3.5), in_green, DX)
    assert (cls2 != mod.OFF_GREEN).any()               # still an on-green region
    assert (cls2[cls2 != mod.OFF_GREEN] == 0).all()    # but all illegal


def test_tiers_are_nested():
    in_green, _, _ = disk_green(10.0)
    rng = np.random.default_rng(0)
    slope = rng.uniform(0, 4, in_green.shape)
    cls = mod.legal_pin_class(slope, in_green, DX)
    t = mod.tier_stats(cls, DX)["tiers"]
    assert (t["premium"]["area_m2"] <= t["standard"]["area_m2"]
            <= t["traditional"]["area_m2"])


def test_cup_bench_excludes_neighborhood_of_a_spike():
    in_green, c, _ = disk_green(10.0)
    slope = np.zeros_like(in_green, float)
    slope[c, c] = 50.0  # one steep cell in the flat interior
    cls = mod.legal_pin_class(slope, in_green, DX)
    # every cell whose 0.5 m cup bench touches the spike must be illegal,
    # even though those cells are themselves flat
    r = int(round(mod.CUP_BENCH_RADIUS_M / DX))
    for di in range(-r, r + 1):
        for dj in range(-r, r + 1):
            if di * di + dj * dj <= r * r:
                assert cls[c + di, c + dj] == 0


def test_scarce_area_stats_shape():
    in_green, _, _ = disk_green(2.0)  # tiny green: setback erodes most of it
    cls = mod.legal_pin_class(np.zeros(in_green.shape), in_green, DX)
    stats = mod.tier_stats(cls, DX)
    assert stats["green_area_m2"] > 0
    assert set(stats["tiers"]) == {"traditional", "standard", "premium"}
    # area equals cell count * cell size
    assert stats["tiers"]["standard"]["area_m2"] == pytest.approx(
        ((cls != mod.OFF_GREEN) & (cls >= 2)).sum() * DX * DX, abs=1e-6)

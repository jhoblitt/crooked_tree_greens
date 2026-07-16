#!/usr/bin/env python3
"""Stage 4.5: legal pin-zone map per green.

A cell is a legal hole location when three conditions hold together:
  1. it is on the putting surface (the green polygon, not the collar buffer);
  2. it sits at least EDGE_SETBACK_M from the green edge (USGA guidance is
     ~4 paces / 10 ft from any edge);
  3. the macro slope stays under a threshold across the whole CUP_BENCH_RADIUS_M
     "bench" where the ball comes to rest — enforced by eroding the
     slope<=threshold mask, so a lone flat cell surrounded by fall-away does
     not qualify.

We emit three nested slope tiers rather than one number, because the fair-slope
threshold is a judgement call that scales with green speed: premium <=1.5%,
standard <=2.0% (the headline "legal" set), traditional <=3.0%. Slope here is
the smoothed macro slope (see the fit's vertical-fidelity caveat), which is
exactly the scale hole-location fairness depends on.

Reads data/interim/<label>_grid.npz; writes data/interim/<label>_pins.npz
(tier_class raster + params + per-tier stats). No halt: a green too steep to
hold a fair pin legitimately yields zero legal area and is flagged, not failed.
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion, label

ROOT = Path(__file__).resolve().parent.parent
POLY_DIR = ROOT / "data" / "polygons"
INTERIM = ROOT / "data" / "interim"

# class int -> (name, max on-bench slope %). Nested: premium ⊂ standard ⊂ traditional.
TIERS = [
    {"cls": 1, "name": "traditional", "slope_pct": 3.0},
    {"cls": 2, "name": "standard", "slope_pct": 2.0},
    {"cls": 3, "name": "premium", "slope_pct": 1.5},
]
HEADLINE_CLS = 2  # "standard" (<=2%) is the reported "legal" set
EDGE_SETBACK_M = 3.0
CUP_BENCH_RADIUS_M = 0.5
MIN_LEGAL_AREA_M2 = 10.0  # below this, fair pin placement is scarce -> flag
OFF_GREEN = 255


def _disk(radius_m, dx):
    r = max(1, int(round(radius_m / dx)))
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    return xx * xx + yy * yy <= r * r


def legal_pin_class(slope_pct, in_green, dx,
                    edge_setback_m=EDGE_SETBACK_M,
                    cup_bench_radius_m=CUP_BENCH_RADIUS_M,
                    tiers=TIERS):
    """Per-cell highest legal tier (0 on-green illegal, cls for each tier,
    OFF_GREEN off the putting surface). Native grid orientation (row 0 = south).
    """
    interior = binary_erosion(in_green, _disk(edge_setback_m, dx), border_value=0)
    bench = _disk(cup_bench_radius_m, dx)
    cls_map = np.zeros(slope_pct.shape, np.uint8)
    for t in sorted(tiers, key=lambda t: t["cls"]):  # loosest first; stricter overwrites
        flat = np.isfinite(slope_pct) & (slope_pct <= t["slope_pct"])
        legal = interior & binary_erosion(flat, bench, border_value=0)
        cls_map[legal] = t["cls"]
    cls_map[~in_green] = OFF_GREEN
    return cls_map


def tier_stats(cls_map, dx, tiers=TIERS):
    cell = dx * dx
    on_green = int((cls_map != OFF_GREEN).sum())
    out = {"green_cells": on_green, "green_area_m2": round(on_green * cell, 1),
           "tiers": {}}
    for t in tiers:
        mask = (cls_map != OFF_GREEN) & (cls_map >= t["cls"])
        _, n = label(mask)
        area = float(mask.sum()) * cell
        out["tiers"][t["name"]] = {
            "slope_max_pct": t["slope_pct"],
            "area_m2": round(area, 1),
            "fraction_of_green": round(area / (on_green * cell), 4) if on_green else 0.0,
            "n_zones": int(n),
        }
    return out


def main() -> int:
    feats = json.loads((POLY_DIR / "greens.geojson").read_text())["features"]
    print(f"pin-zone params: setback {EDGE_SETBACK_M} m, cup bench r={CUP_BENCH_RADIUS_M} m, "
          f"tiers " + ", ".join(f"{t['name']}<={t['slope_pct']}%" for t in TIERS))
    print(f"\n{'green':>10} {'green m²':>8} {'premium':>8} {'standard':>9} "
          f"{'trad':>7} {'std%':>6} {'zones':>6}  flag")
    any_flag = False
    for f in feats:
        label_ = f["properties"]["label"]
        g = np.load(INTERIM / f"{label_}_grid.npz", allow_pickle=False)
        cls_map = legal_pin_class(g["slope_pct"], g["in_green"], float(g["dx"]))
        stats = tier_stats(cls_map, float(g["dx"]))
        t = stats["tiers"]
        std = t["standard"]
        flag = std["area_m2"] < MIN_LEGAL_AREA_M2
        any_flag |= flag
        stats["headline_class"] = HEADLINE_CLS
        stats["edge_setback_m"] = EDGE_SETBACK_M
        stats["cup_bench_radius_m"] = CUP_BENCH_RADIUS_M
        stats["min_legal_area_m2"] = MIN_LEGAL_AREA_M2
        stats["scarce_legal_area"] = bool(flag)
        np.savez_compressed(
            INTERIM / f"{label_}_pins.npz",
            tier_class=cls_map, x0=g["x0"], y0=g["y0"], dx=g["dx"],
            stats=json.dumps(stats),
        )
        print(f"{label_:>10} {stats['green_area_m2']:>8.0f} {t['premium']['area_m2']:>8.0f} "
              f"{std['area_m2']:>9.0f} {t['traditional']['area_m2']:>7.0f} "
              f"{std['fraction_of_green']*100:>5.0f}% {std['n_zones']:>6}"
              f"  {'SCARCE legal area' if flag else ''}")

    print("\nCHECKPOINT " + ("OK (with scarce-area flags — see above)" if any_flag else "OK")
          + ": pin zones written to data/interim/*_pins.npz")
    return 0


if __name__ == "__main__":
    sys.exit(main())

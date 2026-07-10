"""Shared fixtures: script loading, path sandboxing, synthetic course data.

The pipeline scripts anchor their I/O on module-level Path constants derived
from the repo root. Tests rebind those constants into a per-test tmp tree so
every stage can run end-to-end on synthetic data with no network and no real
LiDAR tiles.
"""

import datetime
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import laspy
import numpy as np
import pytest
from pyproj import CRS, Transformer

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"

# UTM 12N coords in the course's neighborhood keep transforms realistic.
BASE_E, BASE_N = 494_800.0, 3_582_000.0
BASE_Z = 731.0
TO_LL = Transformer.from_crs("EPSG:6341", "EPSG:4326", always_xy=True).transform

_modules = {}


def load_script(stem):
    """Import scripts/<stem>.py under a cached module name."""
    if stem not in _modules:
        path = SCRIPTS / f"{stem}.py"
        name = "pipeline_" + stem.split("_", 1)[1]
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        _modules[stem] = mod
    return _modules[stem]


PATH_CONSTANTS = ("ROOT", "POLY_DIR", "CACHE_DIR", "RAW", "INTERIM", "OUT",
                  "REPORTS", "SITE")


def _rebind(mp, root, *stems):
    mods = []
    for stem in stems:
        mod = load_script(stem)
        for const in PATH_CONSTANTS:
            if not hasattr(mod, const):
                continue
            rel = getattr(mod, const).relative_to(REPO)
            target = root / rel
            target.mkdir(parents=True, exist_ok=True)
            mp.setattr(mod, const, target)
        mods.append(mod)
    return mods[0] if len(mods) == 1 else mods


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Rebind a script module's path constants into tmp_path and mkdir them."""

    def _sandbox(*stems):
        return _rebind(monkeypatch, tmp_path, *stems)

    return _sandbox


@pytest.fixture(scope="session")
def course_build(tmp_path_factory):
    """Stages 3+4 run ONCE on the shared synthetic course.

    Tests must not mutate this tree — clone it via staged_course. Noise is
    0.04 m (≈ real LiDAR) and the lambda ladder starts at real smoothing
    levels: with the RMS floor already inside the 3-6 cm band, tiny lambdas
    would legally win the "smallest in-band" rule with a noise-tracking fit,
    which is useless for slope/aspect contract tests.
    """
    root = tmp_path_factory.mktemp("course_build")
    mp = pytest.MonkeyPatch()
    try:
        m30, m40 = _rebind(mp, root, "30_clip_clean", "40_fit_surface")
        mp.setattr(m40, "FIT_MAX_PTS", 1200)
        mp.setattr(m40, "LAMBDAS", np.array([100.0, 300.0, 1000.0]))
        make_greens_geojson(m30.POLY_DIR / "greens.geojson",
                            [("hole_01", 1, BASE_E, BASE_N, 7.0)])
        tile = make_tile(m30.RAW / "tile_a.laz", BASE_E - 40, BASE_N - 40,
                         size=80, density=4.0, noise=0.04)
        make_tiles_meta(m30.RAW, [tile])
        assert m30.main() == 0
        assert m40.main() == 0
    finally:
        mp.undo()
    return root


@pytest.fixture
def staged_course(course_build, tmp_path, monkeypatch):
    """A private, mutable copy of the built course, all stage modules rebound."""
    shutil.copytree(course_build, tmp_path, dirs_exist_ok=True)
    return _rebind(monkeypatch, tmp_path, "30_clip_clean", "40_fit_surface",
                   "50_export", "60_report")


def utm_disk(cx, cy, r=10.0, n=14):
    """A polygon approximating a circle, in EPSG:4326, centered in UTM."""
    ring = [TO_LL(cx + r * np.cos(t), cy + r * np.sin(t))
            for t in np.linspace(0, 2 * np.pi, n, endpoint=False)]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def make_greens_geojson(path, greens):
    """greens: list of (label, hole, cx, cy, r)."""
    feats = []
    for label, hole, cx, cy, r in greens:
        feats.append({
            "type": "Feature",
            "properties": {
                "hole": hole, "label": label, "osm_id": None,
                "area_m2": round(np.pi * r * r, 1),
                "hole_source": "hole_line" if hole else "unassigned",
                "needs_review": hole == 0,
            },
            "geometry": utm_disk(cx, cy, r),
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return feats


def make_hole_lines_geojson(path, holes):
    """holes: list of (ref, (tee_e, tee_n), (pin_e, pin_n)) in UTM."""
    feats = []
    for ref, tee, pin in holes:
        feats.append({
            "type": "Feature",
            "properties": {"hole": ref, "osm_id": ref},
            "geometry": {"type": "LineString",
                         "coordinates": [TO_LL(*tee), TO_LL(*pin)]},
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))


def gps_adjusted(date=datetime.date(2021, 10, 4)):
    epoch = datetime.datetime(1980, 1, 6, tzinfo=datetime.UTC)
    dt = datetime.datetime(date.year, date.month, date.day, 12,
                           tzinfo=datetime.UTC)
    return (dt - epoch).total_seconds() - 1e9


def surface_z(x, y):
    """Deterministic smooth test terrain: gentle plane + one broad bump."""
    return (BASE_Z + 0.02 * (x - BASE_E) - 0.01 * (y - BASE_N)
            + 0.15 * np.exp(-(((x - BASE_E) ** 2 + (y - BASE_N) ** 2) / 60.0)))


def write_laz(path, x, y, z, classification=2):
    """Write a LAS 1.4 / point-format-6 LAZ with the compound course CRS."""
    header = laspy.LasHeader(version="1.4", point_format=6)
    header.add_crs(CRS.from_user_input("EPSG:6341+5703"))
    header.offsets = [float(np.min(x)), float(np.min(y)), float(np.min(z))]
    header.scales = [0.001, 0.001, 0.001]
    las = laspy.LasData(header)
    las.x, las.y, las.z = x, y, z
    cls = np.full(len(x), classification, dtype=np.uint8) \
        if np.isscalar(classification) else np.asarray(classification, dtype=np.uint8)
    las.classification = cls
    t0 = gps_adjusted()
    las.gps_time = np.linspace(t0, t0 + 600.0, len(x))
    path.parent.mkdir(parents=True, exist_ok=True)
    las.write(str(path))
    return path


def make_tile(path, e0, n0, size=120.0, density=6.0, rng_seed=6341,
              noise=0.02, classification=None):
    """A synthetic ground tile [e0,e0+size)x[n0,n0+size) sampled on jittered grid."""
    rng = np.random.default_rng(rng_seed)
    n = int(size * size * density)
    x = rng.uniform(e0, e0 + size, n)
    y = rng.uniform(n0, n0 + size, n)
    z = surface_z(x, y) + rng.normal(0, noise, n)
    cls = classification if classification is not None else \
        np.where(rng.uniform(size=n) < 0.9, 2, 1)  # 90% ground, 10% other
    write_laz(path, x, y, z, classification=cls)
    return path


def tile_header_meta(path):
    """tiles_meta.json 'tiles' entry for a synthetic tile, as Stage 2 writes it."""
    with laspy.open(str(path)) as f:
        h = f.header
        crs = h.parse_crs()
        subs = crs.sub_crs_list if crs.is_compound else [crs]
        return {
            "tile": path.name,
            "points": h.point_count,
            "point_format": h.point_format.id,
            "las_version": str(h.version),
            "crs_name": crs.name,
            "horizontal_epsg": subs[0].to_epsg(),
            "vertical_epsg": subs[1].to_epsg() if len(subs) > 1 else None,
            "axis_units": [[a.name, a.unit_name] for a in crs.axis_info],
            "creation_date": str(h.creation_date),
            "mins": list(h.mins),
            "maxs": list(h.maxs),
        }


ARTIFACTS = ["heightmap.npz", "heightmap.tif", "mesh.obj", "mesh.glb",
             "slope_heatmap.png", "contours.png", "meta.json"]


def make_fake_export(out_dir, dirname, hole, **overrides):
    """A minimal outputs/greens/<dirname>/ dir that satisfies Stage 6/7 readers.

    The meta label defaults to the dir name; pass label=... to make them
    disagree (the Stage 6 mismatch scenario).
    """
    meta = {
        "hole": hole, "label": dirname, "needs_review": False,
        "hole_source": "hole_line" if hole else "unassigned",
        "source_work_units": ["USGS Lidar Point Cloud AZ_PimaCounty_2021_B21"],
        "acquisition_dates": ["2021-10-04"], "tiles": ["tile_a.laz"],
        "crs_horizontal": "EPSG:6341", "crs_vertical": "EPSG:5703",
        "cell_size_m": 0.25, "grid_shape": [40, 40],
        "grid_origin_north_up": [BASE_E, BASE_N],
        "local_origin_utm": [BASE_E, BASE_N, BASE_Z],
        "green_area_m2": 314.0, "class2_density_on_green_pts_m2": 5.4,
        "n_points_fit_region": 1500, "lambda": 100.0, "fit_rms_m": 0.035,
        "fit_band_note": "in_band", "slope_mean_pct": 2.2,
        "slope_max_pct": 4.0, "slope_max_sustained_pct": 3.5,
        "sustained_window_m": 1.0, "elevation_range_on_green_m": 0.4,
        "flags": [], "generated": "2026-07-10T00:00:00+00:00",
        "vertical_fidelity": "macro contours only; source RMSE ~5-10 cm; "
                             "micro-break below noise floor",
    }
    meta.update(overrides)
    d = out_dir / dirname
    d.mkdir(parents=True, exist_ok=True)
    for a in ARTIFACTS:
        if a != "meta.json":
            (d / a).write_bytes(b"x")
    (d / "meta.json").write_text(json.dumps(meta))
    return meta


def make_tiles_meta(raw_dir, tile_paths):
    meta = {
        "work_units": ["USGS Lidar Point Cloud AZ_PimaCounty_2021_B21"],
        "titles": [f"USGS Lidar Point Cloud AZ_PimaCounty_2021_B21 {p.stem[-6:]}"
                   for p in tile_paths],
        "publication_dates": ["2023-03-24"],
        "source_dates": ["2023-04-14T07:54:23.542-06:00"],
        "urls": [f"https://example.invalid/{p.name}" for p in tile_paths],
        "vendor_meta_urls": [],
        "tiles": [tile_header_meta(p) for p in tile_paths],
        "total_points": sum(tile_header_meta(p)["points"] for p in tile_paths),
    }
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "tiles_meta.json").write_text(json.dumps(meta, indent=1))
    return meta

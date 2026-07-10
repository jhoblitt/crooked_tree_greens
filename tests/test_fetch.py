"""Stage 2 plumbing: footprint, TNM cache, header inspection, tile checkpoint."""

import json

import pytest
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

from conftest import (BASE_E, BASE_N, load_script, make_greens_geojson,
                      make_hole_lines_geojson, make_tile, make_tiles_meta,
                      tile_header_meta)

mod = load_script("20_fetch_lidar")


def course_polygons(poly_dir, greens=None):
    greens = greens or [("hole_01", 1, BASE_E, BASE_N, 9),
                        ("hole_02", 2, BASE_E + 60, BASE_N + 40, 9)]
    make_greens_geojson(poly_dir / "greens.geojson", greens)
    make_hole_lines_geojson(poly_dir / "hole_lines.geojson", [
        (1, (BASE_E - 250, BASE_N), (BASE_E, BASE_N)),
        (2, (BASE_E - 250, BASE_N + 40), (BASE_E + 60, BASE_N + 40)),
        (3, (BASE_E - 250, BASE_N - 80), (BASE_E - 90, BASE_N - 80)),
    ])


def test_footprint_covers_greens_and_missing_hole_pins(sandbox):
    m = sandbox("20_fetch_lidar")
    course_polygons(m.POLY_DIR)
    fp = m.acquisition_footprint()
    fp_utm = shp_transform(m.TO_UTM.transform, fp)
    # buffered greens covered
    assert fp_utm.buffer(0.1).contains(shape({"type": "Point", "coordinates": (BASE_E, BASE_N)}).buffer(9 + 11))
    # hole 3 has no green: both its endpoints must be inside the footprint
    for pt in ((BASE_E - 250, BASE_N - 80), (BASE_E - 90, BASE_N - 80)):
        assert fp_utm.contains(shape({"type": "Point", "coordinates": pt}))


def test_tnm_products_uses_cache_without_network(sandbox, monkeypatch):
    m = sandbox("20_fetch_lidar")
    canned = {"items": [{"title": "cached"}]}
    (m.RAW / "tnm_products.json").write_text(json.dumps(canned))

    def boom(*a, **k):
        raise AssertionError("network hit despite cache")

    monkeypatch.setattr(m.requests, "get", boom)
    assert m.tnm_products((0, 0, 1, 1)) == canned


def test_inspect_headers_decomposes_compound_crs(sandbox, tmp_path):
    m = sandbox("20_fetch_lidar")
    tile = make_tile(m.RAW / "t.laz", BASE_E - 60, BASE_N - 60, size=50, density=2)
    meta, total = m.inspect_headers([tile])
    assert meta[0]["horizontal_epsg"] == 6341
    assert meta[0]["vertical_epsg"] == 5703
    assert total == meta[0]["points"] > 0
    units = {u.lower().replace("metre", "meter") for _, u in meta[0]["axis_units"]}
    assert units == {"meter"}


def test_verify_tiles_passes_on_full_coverage(sandbox, capsys):
    m = sandbox("20_fetch_lidar")
    course_polygons(m.POLY_DIR, greens=[("hole_01", 1, BASE_E, BASE_N, 9)])
    tile = make_tile(m.RAW / "t.laz", BASE_E - 60, BASE_N - 60, size=120, density=2)
    m.verify_tiles([tile_header_meta(tile)])
    assert "coverage: every buffered green" in capsys.readouterr().out


def test_verify_tiles_halts_on_coverage_gap(sandbox):
    m = sandbox("20_fetch_lidar")
    course_polygons(m.POLY_DIR, greens=[("hole_01", 1, BASE_E + 300, BASE_N, 9)])
    tile = make_tile(m.RAW / "t.laz", BASE_E - 60, BASE_N - 60, size=120, density=2)
    with pytest.raises(SystemExit, match="not covered"):
        m.verify_tiles([tile_header_meta(tile)])


def test_verify_tiles_halts_on_wrong_crs(sandbox):
    m = sandbox("20_fetch_lidar")
    course_polygons(m.POLY_DIR, greens=[("hole_01", 1, BASE_E, BASE_N, 9)])
    tile = make_tile(m.RAW / "t.laz", BASE_E - 60, BASE_N - 60, size=120, density=2)
    meta = tile_header_meta(tile)
    meta["horizontal_epsg"] = 3857
    with pytest.raises(SystemExit, match="unexpected horizontal CRS"):
        m.verify_tiles([meta])


def test_verify_tiles_halts_on_feet(sandbox):
    m = sandbox("20_fetch_lidar")
    course_polygons(m.POLY_DIR, greens=[("hole_01", 1, BASE_E, BASE_N, 9)])
    tile = make_tile(m.RAW / "t.laz", BASE_E - 60, BASE_N - 60, size=120, density=2)
    meta = tile_header_meta(tile)
    meta["axis_units"] = [["X", "US survey foot"], ["Y", "US survey foot"], ["Up", "meter"]]
    with pytest.raises(SystemExit, match="not uniformly meters"):
        m.verify_tiles([meta])

"""Stage 1 plumbing: hole assignment, feature building, caching, manual merge."""

import json

import pytest
from shapely.geometry import LineString, shape

from conftest import BASE_E, BASE_N, TO_LL, load_script, utm_disk

mod = load_script("10_green_polygons")


def green(cx, cy, r=9.0, tags=None, osm_id=1):
    return {"osm_id": osm_id, "poly": shape(utm_disk(cx, cy, r)), "tags": tags or {}}


def hole_line(ref, tee, pin):
    return {"osm_id": ref, "ref": ref,
            "line": LineString([TO_LL(*tee), TO_LL(*pin)])}


def test_way_polygon_closes_open_ring():
    el = {"geometry": [{"lon": 0.0, "lat": 0.0}, {"lon": 0.001, "lat": 0.0},
                       {"lon": 0.001, "lat": 0.001}]}
    poly = mod.way_polygon(el)
    assert poly.is_valid and poly.exterior.coords[0] == poly.exterior.coords[-1]


def test_assign_holes_from_pin_endpoint():
    g = [green(BASE_E, BASE_N, osm_id=10)]
    h = [hole_line(7, (BASE_E - 300, BASE_N), (BASE_E + 2, BASE_N + 1))]
    out = mod.assign_holes(g, h)
    assert out[0]["hole"] == 7 and out[0]["hole_source"] == "hole_line"


def test_assign_holes_tag_wins_over_line():
    g = [green(BASE_E, BASE_N, tags={"ref": "5"})]
    h = [hole_line(7, (BASE_E - 300, BASE_N), (BASE_E, BASE_N))]
    out = mod.assign_holes(g, h)
    assert out[0]["hole"] == 5 and out[0]["hole_source"] == "tag"


def test_assign_holes_far_green_stays_practice():
    g = [green(BASE_E, BASE_N)]
    h = [hole_line(3, (BASE_E + 500, BASE_N), (BASE_E + 200, BASE_N))]
    out = mod.assign_holes(g, h)
    assert out[0]["hole"] is None


def test_assign_holes_duplicate_claim_flags_both():
    g = [green(BASE_E, BASE_N, tags={"ref": "4"}, osm_id=1),
         green(BASE_E + 40, BASE_N, tags={"ref": "4"}, osm_id=2)]
    out = mod.assign_holes(g, [])
    assert all(x.get("needs_review") for x in out)


def test_green_feature_area_sanity_flag():
    tiny = green(BASE_E, BASE_N, r=3.0)  # ~28 m² — below the 250 m² floor
    tiny["hole"], tiny["hole_source"] = 1, "tag"
    f = mod.green_feature(tiny)
    assert f["properties"]["needs_review"] and "area_flag" in f["properties"]


def test_green_feature_labels():
    g = green(BASE_E, BASE_N)
    g["hole"], g["hole_source"] = 12, "hole_line"
    assert mod.green_feature(g)["properties"]["label"] == "hole_12"
    g["hole"] = None
    assert mod.green_feature(g)["properties"]["label"] == "practice"


def test_uniquify_practice_only_renames_when_multiple():
    def feat(hole):
        return {"properties": {"hole": hole, "label": "practice" if not hole else f"hole_{hole:02d}"}}

    two = [feat(0), feat(0), feat(1)]
    mod.uniquify_practice(two)
    assert [f["properties"]["label"] for f in two[:2]] == ["practice_1", "practice_2"]

    one = [feat(0), feat(1)]
    mod.uniquify_practice(one)
    assert one[0]["properties"]["label"] == "practice"


def test_cached_fetch_hits_cache(sandbox):
    m = sandbox("10_green_polygons")
    calls = []

    def fetch():
        calls.append(1)
        return {"n": len(calls)}

    assert m.cached_fetch("k", fetch) == {"n": 1}
    assert m.cached_fetch("k", fetch) == {"n": 1}
    assert len(calls) == 1


def test_load_manual_merges_polygons_and_skips_lines(sandbox):
    m = sandbox("10_green_polygons")
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": utm_disk(BASE_E, BASE_N, 8)},
        {"type": "Feature", "properties": {},
         "geometry": {"type": "LineString",
                      "coordinates": [TO_LL(BASE_E, BASE_N), TO_LL(BASE_E + 9, BASE_N)]}},
    ]}
    (m.POLY_DIR / "greens_manual.geojson").write_text(json.dumps(gj))
    out = m.load_manual()
    assert len(out) == 1 and out[0]["manual"] is True


def test_load_manual_absent_is_empty(sandbox):
    m = sandbox("10_green_polygons")
    assert m.load_manual() == []

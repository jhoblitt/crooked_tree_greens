"""Stage 1 plumbing: hole assignment, feature building, caching, manual merge."""

import json

import pytest
from conftest import BASE_E, BASE_N, TO_LL, load_script, utm_disk
from shapely.geometry import LineString, shape

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


def test_flatten_nines_chains_and_offsets():
    """Three interleaved nines with duplicate refs 1..3 chain into a=1-3,
    b=4-6, c=7-9 by spatial adjacency, ordered west to east."""
    holes = []
    for nine_i, x0 in enumerate((0.0, 500.0, 1000.0)):  # three east-offset loops
        for k in range(1, 4):
            # hole k runs from (x0 + k*60, nine_i*40) east 50 m: hole k's end
            # is 10 m from hole k+1's start within the same nine
            a = (BASE_E + x0 + k * 60, BASE_N + nine_i * 40)
            b = (BASE_E + x0 + k * 60 + 50, BASE_N + nine_i * 40)
            holes.append({"osm_id": nine_i * 10 + k, "ref": k, "name": "",
                          "line": LineString([TO_LL(*a), TO_LL(*b)])})
    out = mod.flatten_nines(holes, 3)
    assert sorted(h["ref"] for h in out) == list(range(1, 10))
    by_nine = {}
    for h in out:
        by_nine.setdefault(h["nine"], []).append(h)
    assert set(by_nine) == {"a", "b", "c"}
    for grp in by_nine.values():
        # all three holes of a group came from the same synthetic loop
        assert len({h["osm_id"] // 10 for h in grp}) == 1
        assert sorted(h["nine_ref"] for h in grp) == [1, 2, 3]
    # a is the westmost loop, c the eastmost
    assert {h["osm_id"] // 10 for h in by_nine["a"]} == {0}
    assert {h["osm_id"] // 10 for h in by_nine["c"]} == {2}


def test_flatten_nines_noop_without_config():
    holes = [{"osm_id": 1, "ref": 5, "line": LineString([TO_LL(BASE_E, BASE_N),
                                                         TO_LL(BASE_E + 50, BASE_N)])}]
    assert mod.flatten_nines(holes, 0) == holes


def test_flatten_nines_halts_on_wrong_multiplicity():
    holes = [{"osm_id": 1, "ref": 1, "name": "",
              "line": LineString([TO_LL(BASE_E, BASE_N), TO_LL(BASE_E + 50, BASE_N)])}]
    with pytest.raises(SystemExit, match="expected 3 lines per ref"):
        mod.flatten_nines(holes, 3)


def test_build_scorecard_maps_and_validates():
    table = {"Palmer": [26, 27, 1, 2, 3, 4, 5, 6, 7],
             "Pioneer": list(range(10, 19)),
             "Gambler": [19, 20, 21, 22, 23, 24, 25, 8, 9]}
    m = mod.build_scorecard(table, list(range(1, 28)))
    assert m[26] == ("Palmer", 1) and m[27] == ("Palmer", 2) and m[1] == ("Palmer", 3)
    assert m[10] == ("Pioneer", 1) and m[18] == ("Pioneer", 9)
    assert m[8] == ("Gambler", 8) and m[9] == ("Gambler", 9)
    assert mod.build_scorecard(None, [1, 2]) is None


def test_build_scorecard_halts_on_duplicate_and_gap():
    with pytest.raises(SystemExit, match="twice"):
        mod.build_scorecard({"A": [1, 2], "B": [2, 3]}, [1, 2, 3])
    with pytest.raises(SystemExit, match="expected holes"):
        mod.build_scorecard({"A": [1, 2]}, [1, 2, 3])


def test_green_feature_uses_scorecard(monkeypatch):
    monkeypatch.setattr(mod, "SCORECARD", {26: ("Palmer", 1)})
    g = green(BASE_E, BASE_N)
    g["hole"], g["hole_source"] = 26, "hole_line"
    p = mod.green_feature(g)["properties"]
    assert p["label"] == "palmer_01"
    assert p["display"] == "Palmer #1"
    assert p["nine"] == "Palmer" and p["nine_hole"] == 1
    monkeypatch.setattr(mod, "SCORECARD", None)
    p2 = mod.green_feature(g)["properties"]
    assert p2["label"] == "hole_26" and p2["display"] == "Hole 26"


def test_approach_azimuth_direction_and_orientation():
    from shapely.geometry import LineString as LS

    green_poly = shape(utm_disk(BASE_E, BASE_N, 9.0))
    green_utm = mod.utm(green_poly)
    # fairway due west of the green: play direction is due east (0 deg)
    line = LS([(BASE_E - 300, BASE_N), (BASE_E, BASE_N)])
    assert abs(mod.approach_azimuth(green_utm, line)) < 1.0
    # same hole digitized pin->tee: still due east
    assert abs(mod.approach_azimuth(green_utm, LS(list(line.coords)[::-1]))) < 1.0
    # fairway due south: play direction is due north (+90 deg math convention)
    line_s = LS([(BASE_E, BASE_N - 300), (BASE_E, BASE_N)])
    assert abs(mod.approach_azimuth(green_utm, line_s) - 90.0) < 1.0


def test_assign_holes_records_assigning_line():
    g = [green(BASE_E, BASE_N, osm_id=10)]
    h = [hole_line(7, (BASE_E - 300, BASE_N), (BASE_E + 2, BASE_N + 1))]
    out = mod.assign_holes(g, h)
    assert out[0]["hole_line"] is h[0]


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


def test_overview_tag_is_short_and_unambiguous():
    def props(**kw):
        base = {"hole": 0, "label": "practice", "nine": None, "nine_hole": None}
        base.update(kw)
        return base
    assert mod.overview_tag(props(hole=7, label="hole_07")) == "7"
    assert mod.overview_tag(props(hole=2, label="palmer_02",
                                  nine="Palmer", nine_hole=2)) == "Pa2"
    assert mod.overview_tag(props(hole=8, label="gambler_08",
                                  nine="Gambler", nine_hole=8)) == "Ga8"
    assert mod.overview_tag(props(hole=7, label="pioneer_07",
                                  nine="Pioneer", nine_hole=7)) == "Pi7"
    assert mod.overview_tag(props(hole=0, label="practice")) == "P"
    assert mod.overview_tag(props(hole=0, label="practice_2")) == "P2"


def test_overview_map_greens_are_clickable_and_uniform(sandbox):
    m = sandbox("10_green_polygons")
    review = m.green_feature({**green(BASE_E, BASE_N, osm_id=1),
                              "hole": 7, "hole_source": "hole_line"})
    manual = m.green_feature({**green(BASE_E + 40, BASE_N, osm_id=2),
                              "manual": True, "hole": 8, "hole_source": "manual"})
    course = shape(utm_disk(BASE_E, BASE_N, 200.0))
    m.overview_map(course, [review, manual], [], [])
    html_text = (m.REPORTS / "greens_overview.html").read_text()
    assert "window.location.href = 'greens/' + feature.properties.label" in html_text
    assert "hole_07" in html_text and "click to open" in html_text
    # uniform styling: no needs_review orange, labels click-through, deeper zoom
    assert "#ff9900" not in html_text
    assert "pointer-events:none" in html_text and "green-label" in html_text
    assert '"maxNativeZoom": 19' in html_text and '"maxZoom": 21' in html_text


def test_stage1_parsing_replays_committed_cache(sandbox, monkeypatch):
    """Course + greens + hole-line parsing against the real committed Overpass
    and Nominatim responses in data/polygons/cache — network hard-disabled."""
    from conftest import REPO

    m = sandbox("10_green_polygons")
    monkeypatch.setattr(m, "CACHE_DIR",
                        REPO / "courses" / "crooked_tree" / "polygons" / "cache")

    def no_network(*a, **k):
        raise AssertionError("cache miss: test tried to reach the network")

    monkeypatch.setattr(m.requests, "get", no_network)
    monkeypatch.setattr(m.requests, "post", no_network)

    course_el, course_poly = m.fetch_course()
    assert course_el["id"] == 263321891
    assert course_poly.is_valid

    greens, holes = m.fetch_course_features(course_poly)
    assert len(greens) == 8
    assert sorted(h["ref"] for h in holes) == list(range(1, 19))

    assigned = m.assign_holes(greens, holes)
    assert {g["hole"] for g in assigned if g["hole"]} == {1, 2, 9, 10, 11, 18}
    assert sum(1 for g in assigned if g["hole"] is None) == 2  # practice greens

#!/usr/bin/env python3
"""Stage 1: green polygons for one course (--course <slug>).

Primary source: OSM Overpass (golf=green within the course polygon), with hole
numbers assigned from golf=hole line pin endpoints. If OSM coverage is
incomplete, merges courses/<slug>/polygons/greens_manual.geojson
(user-digitized) when present; otherwise writes reports/digitize_map.html and
exits 2 so a human can draw the missing greens.

Outputs under courses/<slug>/: polygons/course.geojson, polygons/greens.geojson,
polygons/hole_lines.geojson, reports/greens_overview.html. All downloads cached
under polygons/cache/.
"""

import hashlib
import json
import sys
import time
import tomllib
from pathlib import Path

import folium
import folium.plugins
import requests
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import linemerge, polygonize, unary_union
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COURSE = "crooked_tree"

PIN_SNAP_M = 30.0  # max distance from a hole-line endpoint to its green

HDRS = {"User-Agent": "green-maps/0.1 (josh@hoblitt.com)"}
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def load_course(slug):
    with open(ROOT / "courses" / slug / "course.toml", "rb") as fh:
        cfg = tomllib.load(fh)
    cfg["slug"] = slug
    return cfg


def build_scorecard(table, expected_holes):
    """{pipeline hole -> (nine name, within-nine number)} from the
    human-confirmed [holes.scorecard] table; None when a course has none."""
    if not table:
        return None
    m = {}
    for nine, seq in table.items():
        for i, h in enumerate(seq, 1):
            if h in m:
                sys.exit(f"HALT: scorecard lists pipeline hole {h} twice")
            m[h] = (nine, i)
    if set(m) != set(expected_holes):
        sys.exit(f"HALT: scorecard covers {sorted(m)} but expected holes are "
                 f"{sorted(expected_holes)}")
    return m


def set_course(slug):
    global CFG, POLY_DIR, CACHE_DIR, REPORTS
    global COURSE_NAME_RE, SEARCH_BBOX, EXPECTED_HOLES, NOMINATIM_QUERY, COURSE_OSM_ID
    global TO_UTM, N_NINES, AREA_MIN, AREA_MAX, SCORECARD
    CFG = load_course(slug)
    base = ROOT / "courses" / slug
    POLY_DIR = base / "polygons"
    CACHE_DIR = POLY_DIR / "cache"
    REPORTS = base / "reports"
    COURSE_NAME_RE = CFG["osm"]["name_re"]
    SEARCH_BBOX = tuple(CFG["osm"]["search_bbox"])
    EXPECTED_HOLES = CFG["holes"].get("refs") or list(range(1, CFG["holes"]["count"] + 1))
    NOMINATIM_QUERY = CFG["osm"]["nominatim_query"]
    COURSE_OSM_ID = CFG["osm"].get("course_osm_id")
    N_NINES = CFG["holes"].get("nines", 0)
    AREA_MIN, AREA_MAX = CFG["holes"].get("area_m2", [250.0, 1200.0])
    SCORECARD = build_scorecard(CFG["holes"].get("scorecard"), EXPECTED_HOLES)
    TO_UTM = Transformer.from_crs("EPSG:4326", f"EPSG:{CFG['crs']['utm_epsg']}",
                                  always_xy=True).transform


set_course(DEFAULT_COURSE)


def utm(geom):
    return shp_transform(TO_UTM, geom)


def cached_fetch(key: str, fetch):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = fetch()
    path.write_text(json.dumps(data))
    return data


def overpass(query: str):
    key = "overpass_" + hashlib.sha256(query.encode()).hexdigest()[:16]

    def fetch():
        last = None
        for i in range(6):
            url = MIRRORS[i % len(MIRRORS)]
            try:
                r = requests.post(url, data={"data": query}, headers=HDRS, timeout=150)
                r.raise_for_status()
                return r.json()
            except Exception as exc:  # noqa: BLE001
                last = exc
                print(f"  overpass [{url.split('/')[2]}] {type(exc).__name__}, retrying")
                time.sleep(5 * (i + 1))
        raise last

    return cached_fetch(key, fetch)


def nominatim():
    def fetch():
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": NOMINATIM_QUERY, "format": "jsonv2", "limit": 3},
            headers=HDRS,
            timeout=60,
        )
        r.raise_for_status()
        return r.json()

    return cached_fetch("nominatim_course", fetch)


def way_polygon(el):
    coords = [(p["lon"], p["lat"]) for p in el["geometry"]]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)


def relation_polygon(el):
    """Assemble a (multi)polygon from a multipolygon relation's member ways.

    Outer ways commonly arrive as split segments, so rings are rebuilt with
    linemerge + polygonize rather than assuming each member closes on itself.
    """
    outers, inners = [], []
    for m in el.get("members", []):
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        coords = [(p["lon"], p["lat"]) for p in m["geometry"]]
        if len(coords) < 2:
            continue
        (inners if m.get("role") == "inner" else outers).append(LineString(coords))

    def rings_to_poly(lines):
        if not lines:
            return None
        merged = linemerge(unary_union(lines))
        polys = list(polygonize(merged))
        return unary_union(polys) if polys else None

    outer = rings_to_poly(outers)
    if outer is None:
        return None
    inner = rings_to_poly(inners)
    return outer.difference(inner) if inner is not None else outer


def element_polygon(el):
    return way_polygon(el) if el["type"] == "way" else relation_polygon(el)


def fetch_course():
    s, w, n, e = SEARCH_BBOX
    q = f"""[out:json][timeout:120];
(
  way["leisure"="golf_course"]["name"~"{COURSE_NAME_RE}",i]({s},{w},{n},{e});
  relation["leisure"="golf_course"]["name"~"{COURSE_NAME_RE}",i]({s},{w},{n},{e});
);
out geom;"""
    els = overpass(q)["elements"]
    if len(els) != 1:
        sys.exit(f"HALT: expected exactly 1 course way/relation matching "
                 f"{COURSE_NAME_RE!r}, got {len(els)}")
    el = els[0]
    poly = element_polygon(el)
    if poly is None or poly.is_empty:
        sys.exit(f"HALT: could not build a polygon from {el['type']} {el['id']}")
    if COURSE_OSM_ID is not None and el["id"] != COURSE_OSM_ID:
        sys.exit(f"HALT: course OSM id {el['id']} != configured {COURSE_OSM_ID}")

    hits = nominatim()
    match = next((h for h in hits if int(h.get("osm_id", 0)) == el["id"]), None)
    if match:
        print(f"  nominatim cross-check OK: {el['type']} {el['id']} "
              f"at ({match['lat']}, {match['lon']})")
    else:
        near = [
            h for h in hits
            if poly.buffer(0.01).contains(Point(float(h["lon"]), float(h["lat"])))
        ]
        if not near:
            sys.exit("HALT: Nominatim geocode does not match the OSM course polygon")
        print("  nominatim cross-check: geocode falls within course polygon (different OSM id)")
    return el, poly


def fetch_course_features(course_poly):
    b = course_poly.bounds  # w, s, e, n
    pad = 0.001
    s, w, n, e = b[1] - pad, b[0] - pad, b[3] + pad, b[2] + pad
    q = f"""[out:json][timeout:120];
(
  way["golf"="green"]({s},{w},{n},{e});
  relation["golf"="green"]({s},{w},{n},{e});
  way["golf"="hole"]({s},{w},{n},{e});
);
out geom;"""
    els = overpass(q)["elements"]

    course_utm = utm(course_poly).buffer(30)
    greens, holes = [], []
    for el in els:
        tags = el.get("tags", {})
        if tags.get("golf") == "green":
            poly = element_polygon(el)
            if poly is None or poly.is_empty:
                print(f"  WARNING: could not build green polygon "
                      f"({el['type']} {el['id']}), skipped")
                continue
            if utm(poly).intersects(course_utm):
                greens.append({"osm_id": el["id"], "poly": poly, "tags": tags})
        elif tags.get("golf") == "hole":
            line = LineString([(p["lon"], p["lat"]) for p in el["geometry"]])
            if utm(line).intersects(course_utm) and tags.get("ref", "").isdigit():
                holes.append({"osm_id": el["id"], "ref": int(tags["ref"]),
                              "name": tags.get("name", ""), "line": line})
    return greens, holes


def flatten_nines(holes, n_nines):
    """Courses built as N nines duplicate refs 1..k per nine. Chain each nine
    spatially (hole k's green end sits near hole k+1's tee), order the nines
    deterministically west-to-east, and offset refs so hole numbers are unique
    (nine 0 -> 1..k, nine 1 -> k+1..2k, ...). The chosen nine order is
    synthesized, not scorecard truth — greens keep a `nine` property and the
    QC notes must tell a human to confirm.
    """
    if not n_nines:
        return holes
    by_ref = {}
    for h in holes:
        by_ref.setdefault(h["ref"], []).append(h)
    per_nine = max(by_ref)
    bad = {k: len(v) for k, v in by_ref.items() if len(v) != n_nines}
    if bad or set(by_ref) != set(range(1, per_nine + 1)):
        sys.exit(f"HALT: expected {n_nines} lines per ref 1..{per_nine}, got "
                 f"{ {k: len(v) for k, v in sorted(by_ref.items())} }")

    def ends(h):
        c = utm(h["line"]).coords
        return Point(c[0]), Point(c[-1])

    chains = sorted(by_ref[1], key=lambda h: utm(h["line"]).centroid.x)
    groups = [[h] for h in chains]
    for k in range(2, per_nine + 1):
        cands = list(by_ref[k])
        pairs = []
        for gi, grp in enumerate(groups):
            tail = ends(grp[-1])
            for ci, cand in enumerate(cands):
                head = ends(cand)
                d = min(t.distance(hd) for t in tail for hd in head)
                pairs.append((d, gi, ci))
        taken_g, taken_c = set(), set()
        for _d, gi, ci in sorted(pairs):
            if gi in taken_g or ci in taken_c:
                continue
            groups[gi].append(cands[ci])
            taken_g.add(gi)
            taken_c.add(ci)

    out = []
    for gi, grp in enumerate(groups):
        nine = chr(ord("a") + gi)
        for h in grp:
            h = dict(h)
            h["nine"] = nine
            h["nine_ref"] = h["ref"]
            h["ref"] = h["ref"] + gi * per_nine
            out.append(h)
    print(f"  chained {n_nines} nines x {per_nine}: " +
          ", ".join(f"{chr(ord('a')+i)}=holes {i*per_nine+1}-{(i+1)*per_nine}"
                    for i in range(n_nines)))
    return out


def load_manual():
    path = POLY_DIR / "greens_manual.geojson"
    if not path.exists():
        return []
    gj = json.loads(path.read_text())
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    out = []
    for i, f in enumerate(feats):
        geom = shape(f["geometry"] if f.get("type") == "Feature" else f)
        if geom.geom_type != "Polygon":
            print(f"  WARNING: manual feature {i} is {geom.geom_type}, skipped")
            continue
        out.append({"osm_id": None, "poly": geom, "tags": {}, "manual": True})
    print(f"  merged {len(out)} manually digitized green(s) from {path.name}")
    return out


def assign_holes(greens, holes):
    """Attach hole numbers: explicit ref tag wins, else nearest hole-line endpoint."""
    greens_utm = [utm(g["poly"]) for g in greens]
    for g in greens:
        ref = g["tags"].get("ref") or g["tags"].get("name", "")
        g["hole"] = int(ref) if str(ref).isdigit() else None
        g["hole_source"] = "tag" if g["hole"] else None

    for h in holes:
        ends = [Point(utm(h["line"]).coords[0]), Point(utm(h["line"]).coords[-1])]
        best = None  # (dist, green_idx)
        for i, gu in enumerate(greens_utm):
            d = min(gu.distance(p) for p in ends)
            if d <= PIN_SNAP_M and (best is None or d < best[0]):
                best = (d, i)
        if best is None:
            continue
        g = greens[best[1]]
        if g["hole"] is None:
            g["hole"], g["hole_source"] = h["ref"], "hole_line"
            g["hole_line"] = h
        elif g["hole"] != h["ref"]:
            print(f"  WARNING: green osm={g['osm_id']} tag says hole {g['hole']} "
                  f"but hole line {h['ref']} terminates on it")

    by_ref = {h["ref"]: h for h in holes}
    for g in greens:
        if g["hole"] is not None and "hole_line" not in g and g["hole"] in by_ref:
            g["hole_line"] = by_ref[g["hole"]]

    claimed = {}
    for g in greens:
        if g["hole"] is not None and g["hole"] in claimed:
            print(f"  WARNING: holes duplicate — two greens claim hole {g['hole']}; "
                  f"flagging both for review")
            claimed[g["hole"]]["needs_review"] = True
            g["needs_review"] = True
        elif g["hole"] is not None:
            claimed[g["hole"]] = g
    return greens


APPROACH_LOOKBACK_M = 60.0


def approach_azimuth(green_poly_utm, line_utm):
    """Direction of play into the green, degrees CCW from east (math
    convention, same as aspect_deg). Taken along the hole line's last
    APPROACH_LOOKBACK_M into whichever endpoint sits at the green."""
    p_start, p_end = Point(line_utm.coords[0]), Point(line_utm.coords[-1])
    if green_poly_utm.distance(p_start) < green_poly_utm.distance(p_end):
        line_utm = line_utm.reverse()
    pin = line_utm.length
    back = line_utm.interpolate(max(0.0, pin - APPROACH_LOOKBACK_M))
    tip = line_utm.interpolate(pin)
    import math
    return math.degrees(math.atan2(tip.y - back.y, tip.x - back.x))


def green_feature(g):
    area = utm(g["poly"]).area
    hole = g["hole"]
    label, display, nine, nine_hole = (f"hole_{hole:02d}" if hole else "practice",
                                       f"Hole {hole}" if hole else "Practice",
                                       None, None)
    if hole and SCORECARD:
        nine, nine_hole = SCORECARD[hole]
        label = f"{nine.lower()}_{nine_hole:02d}"
        display = f"{nine} #{nine_hole}"
    props = {
        "hole": hole or 0,
        "label": label,
        "display": display,
        "nine": nine,
        "nine_hole": nine_hole,
        "osm_id": g["osm_id"],
        "area_m2": round(area, 1),
        "hole_source": g["hole_source"] or ("manual" if g.get("manual") else "unassigned"),
        "needs_review": bool(g.get("needs_review") or g.get("manual") or g["hole"] is None),
    }
    if g.get("hole_line") is not None:
        props["approach_deg"] = round(
            approach_azimuth(utm(g["poly"]), utm(g["hole_line"]["line"])), 1)
    if not (AREA_MIN <= area <= AREA_MAX):
        props["needs_review"] = True
        props["area_flag"] = f"area {area:.0f} m2 outside [{AREA_MIN:.0f}, {AREA_MAX:.0f}]"
    return {"type": "Feature", "properties": props, "geometry": mapping(g["poly"])}


def uniquify_practice(feats):
    """Practice greens share hole 0; give them collision-free output labels."""
    practice = [f for f in feats if f["properties"]["hole"] == 0]
    for i, f in enumerate(practice, 1):
        f["properties"]["label"] = f"practice_{i}" if len(practice) > 1 else "practice"


def overview_map(course_poly, feats, holes, missing):
    from folium.utilities import JsCode

    c = course_poly.centroid
    m = folium.Map(location=[c.y, c.x], zoom_start=16, tiles=None)
    folium.TileLayer("Esri.WorldImagery", name="Esri World Imagery").add_to(m)
    open_green = JsCode(
        """(feature, layer) => {
          layer.on('click', () => {
            window.location.href = 'greens/' + feature.properties.label + '/';
          });
        }""")
    folium.GeoJson(
        mapping(course_poly),
        style_function=lambda _: {"color": "#ffffff", "weight": 2, "fill": False, "dashArray": "5"},
    ).add_to(m)
    for h in holes:
        folium.PolyLine([(la, lo) for lo, la in h["line"].coords],
                        color="#66ccff", weight=1, opacity=0.6).add_to(m)
    for f in feats:
        p = f["properties"]
        color = "#ff9900" if p["needs_review"] else "#00e64d"
        folium.GeoJson(
            f,
            style_function=lambda _, color=color: {"color": color, "weight": 2, "fillOpacity": 0.25},
            tooltip=f"{p.get('display') or p['label']} · {p['area_m2']} m² · "
                    f"{p['hole_source']} · click to open",
            on_each_feature=open_green,
        ).add_to(m)
        cc = shape(f["geometry"]).centroid
        folium.Marker(
            [cc.y, cc.x],
            icon=folium.DivIcon(html=f"<div style='color:white;font-weight:bold;"
                                     f"text-shadow:0 0 3px black'>{p['label'].replace('hole_', '')}</div>"),
        ).add_to(m)
    if missing:
        folium.map.Marker(
            [c.y, c.x],
            icon=folium.DivIcon(html=f"<div style='background:#c00;color:#fff;padding:4px 8px;"
                                     f"border-radius:4px;white-space:nowrap'>missing greens: "
                                     f"{', '.join(map(str, missing))}</div>"),
        ).add_to(m)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "greens_overview.html"
    m.save(str(out))
    print(f"  wrote {out.relative_to(ROOT)}")


def digitize_map(course_poly, feats, holes, missing):
    c = course_poly.centroid
    m = folium.Map(location=[c.y, c.x], zoom_start=17, tiles=None, max_zoom=21)
    folium.TileLayer("Esri.WorldImagery", name="Esri World Imagery", max_native_zoom=19, max_zoom=21).add_to(m)

    existing = folium.FeatureGroup(name="existing greens (OSM)")
    for f in feats:
        folium.GeoJson(f, style_function=lambda _: {"color": "#00e64d", "weight": 2, "fillOpacity": 0.15}).add_to(existing)
    existing.add_to(m)

    for h in holes:
        folium.PolyLine([(la, lo) for lo, la in h["line"].coords],
                        color="#66ccff", weight=1, opacity=0.7).add_to(m)
        if h["ref"] in missing:
            lo, la = h["line"].coords[-1]
            folium.Marker(
                [la, lo],
                tooltip=f"hole {h['ref']}: draw this green",
                icon=folium.Icon(color="red", icon="flag"),
            ).add_to(m)
            folium.map.Marker(
                [la, lo],
                icon=folium.DivIcon(html=f"<div style='color:#ff4444;font-size:16px;font-weight:bold;"
                                         f"text-shadow:0 0 4px black'>{h['ref']}</div>"),
            ).add_to(m)

    drawn = folium.FeatureGroup(name="digitized greens")
    drawn.add_to(m)
    folium.plugins.Draw(
        export=True,
        feature_group=drawn,
        draw_options={"polyline": False, "rectangle": False, "circle": False,
                      "marker": False, "circlemarker": False},
    ).add_to(m)
    folium.LayerControl().add_to(m)

    manual_rel = f"courses/{CFG['slug']}/polygons/greens_manual.geojson"
    instructions = """
    <div style='position:fixed;top:10px;left:60px;z-index:9999;background:#fff;padding:10px 14px;
                border:2px solid #444;border-radius:6px;max-width:430px;font:13px sans-serif'>
    <b>Digitize missing greens</b><br>
    Red flags mark the pin end of each unmapped hole ({missing}).
    For each, zoom in and use the polygon tool (left toolbar) to trace the green's edge.
    Green outlines already in OSM are shown for reference. When done, click
    <b>Export</b> (top right) and save the download as
    <code>{manual}</code>, then rerun
    <code>uv run scripts/10_green_polygons.py --course {slug}</code>.
    </div>""".replace("{missing}", ", ".join(map(str, missing))) \
             .replace("{manual}", manual_rel).replace("{slug}", CFG["slug"])
    m.get_root().html.add_child(folium.Element(instructions))

    out = REPORTS / "digitize_map.html"
    m.save(str(out))
    print(f"  wrote {out.relative_to(ROOT)}")


def main(course=None) -> int:
    if course:
        set_course(course)
    POLY_DIR.mkdir(parents=True, exist_ok=True)

    print(f"course [{CFG['slug']}]:")
    course_el, course_poly = fetch_course()
    (POLY_DIR / "course.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature",
                      "properties": {"osm_id": course_el["id"], **course_el.get("tags", {})},
                      "geometry": mapping(course_poly)}],
    }))
    print(f"  {course_el['type']} {course_el['id']}: {course_el['tags'].get('name')} "
          f"({course_el['tags'].get('description', '')})")

    print("greens + hole lines:")
    greens, holes = fetch_course_features(course_poly)
    holes = flatten_nines(holes, N_NINES)
    (POLY_DIR / "hole_lines.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature",
                      "properties": {"hole": h["ref"], "osm_id": h["osm_id"],
                                     "name": h.get("name", ""),
                                     "nine": h.get("nine", ""),
                                     "nine_ref": h.get("nine_ref", h["ref"])},
                      "geometry": mapping(h["line"])} for h in sorted(holes, key=lambda h: h["ref"])],
    }))
    greens += load_manual()
    print(f"  {len(greens)} green(s), {len(holes)} hole line(s) inside course")

    greens = assign_holes(greens, holes)
    feats = sorted((green_feature(g) for g in greens),
                   key=lambda f: (f["properties"]["hole"] == 0, f["properties"]["label"],
                                  f["properties"]["osm_id"] or 0))
    uniquify_practice(feats)
    (POLY_DIR / "greens.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": feats}, indent=1))
    print(f"  wrote {(POLY_DIR / 'greens.geojson').relative_to(ROOT)}")

    have = {f["properties"]["hole"] for f in feats if f["properties"]["hole"]}
    missing = [h for h in EXPECTED_HOLES if h not in have]
    n_practice = sum(1 for f in feats if f["properties"]["hole"] == 0)

    for f in feats:
        p = f["properties"]
        flag = " REVIEW" if p["needs_review"] else ""
        print(f"    {p['label']:>12}  {p['area_m2']:7.1f} m²  src={p['hole_source']}{flag}"
              + (f"  [{p.get('area_flag')}]" if p.get("area_flag") else ""))

    overview_map(course_poly, feats, holes, missing)

    n_expected = len(EXPECTED_HOLES)
    bad_area = [f["properties"]["label"] for f in feats if f["properties"].get("area_flag")]
    if missing:
        digitize_map(course_poly, feats, holes, missing)
        print(f"\nCHECKPOINT FAILED: {len(have)}/{n_expected} hole greens in OSM "
              f"(+{n_practice} practice); missing holes: {missing}")
        print(f"Open courses/{CFG['slug']}/reports/digitize_map.html, trace the missing "
              f"greens, export to courses/{CFG['slug']}/polygons/greens_manual.geojson, "
              f"then rerun this script with --course {CFG['slug']}.")
        return 2
    if bad_area:
        print(f"\nCHECKPOINT FAILED: area sanity violations: {bad_area}")
        return 2
    print(f"\nCHECKPOINT OK: {len(have)}/{n_expected} hole greens (+{n_practice} practice), "
          f"all areas in [{AREA_MIN:.0f}, {AREA_MAX:.0f}] m²")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--course", default=DEFAULT_COURSE)
    raise SystemExit(main(parser.parse_args().course))

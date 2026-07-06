#!/usr/bin/env python3
"""Stage 2: acquire 3DEP LAZ tiles covering the greens via the TNM Access API.

Acquisition footprint = union of greens buffered 12 m, plus 40 m disks around
the pin end of any hole whose green is not yet digitized, so one download
session also covers greens added later. Tiles cached in data/raw/; never
re-fetched when present and complete. Headers are then verified (CRS,
horizontal/vertical units, point counts) and summarized in
data/raw/tiles_meta.json.
"""

import json
import sys
from pathlib import Path

import laspy
import requests
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Point, box, shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path(__file__).resolve().parent.parent
POLY_DIR = ROOT / "data" / "polygons"
RAW = ROOT / "data" / "raw"

GREEN_BUFFER_M = 12.0
MISSING_PIN_BUFFER_M = 40.0
TNM_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"
HDRS = {"User-Agent": "crooked-tree-greens/0.1 (josh@hoblitt.com)"}

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:6341", always_xy=True)
utm = lambda g: shp_transform(TO_UTM.transform, g)  # noqa: E731
unutm = lambda g: shp_transform(  # noqa: E731
    Transformer.from_crs("EPSG:6341", "EPSG:4326", always_xy=True).transform, g)


def acquisition_footprint():
    greens = json.loads((POLY_DIR / "greens.geojson").read_text())["features"]
    have = {f["properties"]["hole"] for f in greens if f["properties"]["hole"]}
    parts = [utm(shape(f["geometry"])).buffer(GREEN_BUFFER_M) for f in greens]

    holes = json.loads((POLY_DIR / "hole_lines.geojson").read_text())["features"]
    missing_pins = 0
    for h in holes:
        if h["properties"]["hole"] in have:
            continue
        line = utm(LineString(shape(h["geometry"]).coords))
        # pin end = endpoint farther from the clubhouse-side tee cluster is
        # unknowable here; cover BOTH endpoints (cheap, tiles are coarse)
        for c in (line.coords[0], line.coords[-1]):
            parts.append(Point(c).buffer(MISSING_PIN_BUFFER_M))
            missing_pins += 1
    fp_utm = unary_union(parts)
    print(f"footprint: {len(greens)} buffered greens + {missing_pins} endpoint disks "
          f"for {len(holes) - len(have)} undigitized holes")
    return unutm(fp_utm)


def tnm_products(bbox4326):
    cache = RAW / "tnm_products.json"
    if cache.exists():
        return json.loads(cache.read_text())
    params = {
        "datasets": "Lidar Point Cloud (LPC)",
        "bbox": ",".join(f"{v:.6f}" for v in bbox4326),
        "prodFormats": "LAS,LAZ",
        "outputFormat": "JSON",
        "max": 100,
    }
    r = requests.get(TNM_URL, params=params, headers=HDRS, timeout=120)
    r.raise_for_status()
    data = r.json()
    RAW.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, indent=1))
    return data


def download(url: str, dest: Path):
    if dest.exists():
        r = requests.head(url, headers=HDRS, timeout=60, allow_redirects=True)
        want = int(r.headers.get("Content-Length", -1))
        if dest.stat().st_size == want or want < 0:
            print(f"  cached   {dest.name} ({dest.stat().st_size/1e6:.1f} MB)")
            return
        print(f"  size mismatch, refetching {dest.name}")
    tmp = dest.with_suffix(".part")
    with requests.get(url, headers=HDRS, timeout=600, stream=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    tmp.rename(dest)
    print(f"  fetched  {dest.name} ({dest.stat().st_size/1e6:.1f} MB)")


def inspect_headers(paths):
    meta, total = [], 0
    for p in sorted(paths):
        with laspy.open(p) as f:
            h = f.header
            crs = h.parse_crs()
            n = h.point_count
            total += n
            axes = [(a.name, a.unit_name) for a in crs.axis_info] if crs else []
            horiz = vert = None
            if crs is not None:
                subs = crs.sub_crs_list if crs.is_compound else [crs]
                horiz = subs[0].to_epsg()
                vert = subs[1].to_epsg() if len(subs) > 1 else None
            m = {
                "tile": p.name,
                "points": n,
                "point_format": h.point_format.id,
                "las_version": str(h.version),
                "crs_name": crs.name if crs else None,
                "horizontal_epsg": horiz,
                "vertical_epsg": vert,
                "axis_units": axes,
                "creation_date": str(h.creation_date),
                "mins": list(h.mins),
                "maxs": list(h.maxs),
            }
            meta.append(m)
            print(f"  {p.name}: {n:,} pts, fmt {h.point_format.id}, "
                  f"CRS={crs.name if crs else 'MISSING'} (h=EPSG:{horiz}, v=EPSG:{vert}), units={axes}")
    return meta, total


def main() -> int:
    fp = acquisition_footprint()
    bbox = fp.bounds  # minx, miny, maxx, maxy in 4326
    print(f"query bbox (4326): {[round(v, 5) for v in bbox]}")

    data = tnm_products(bbox)
    items = data.get("items", [])
    print(f"TNM returned {len(items)} products")
    by_wu = {}
    for it in items:
        wu = it.get("title", "?")
        prefix = "_".join(wu.split("_")[:4]) if "_" in wu else wu
        by_wu.setdefault(prefix, []).append(it)
    for wu, its in sorted(by_wu.items()):
        print(f"  work unit group: {wu} × {len(its)}")

    pima = [it for it in items if "PimaCo" in it.get("title", "") and "2021" in it.get("title", "")]
    if not pima:
        sys.exit("HALT: no AZ_PimaCo 2021 products returned — inspect data/raw/tnm_products.json")

    keep = []
    for it in pima:
        bb = it["boundingBox"]
        tile_geom = box(bb["minX"], bb["minY"], bb["maxX"], bb["maxY"])
        if tile_geom.intersects(fp):
            keep.append(it)
    print(f"{len(pima)} PimaCo 2021 products, {len(keep)} intersect the footprint:")

    RAW.mkdir(parents=True, exist_ok=True)
    paths = []
    for it in keep:
        url = it.get("downloadLazURL") or it.get("downloadURL")
        name = url.rsplit("/", 1)[-1]
        dest = RAW / name
        download(url, dest)
        paths.append(dest)

    print("headers:")
    meta, total = inspect_headers(paths)

    tiles_meta = {
        "work_units": sorted({it["title"].rsplit(" ", 1)[0] for it in keep}),
        "titles": [it["title"] for it in keep],
        "publication_dates": sorted({it.get("publicationDate", "?") for it in keep}),
        "source_dates": sorted({str(it.get("dateCreated", "?")) for it in keep}),
        "urls": [it.get("downloadLazURL") or it.get("downloadURL") for it in keep],
        "vendor_meta_urls": sorted({it.get("metaUrl", "") for it in keep if it.get("metaUrl")}),
        "tiles": meta,
        "total_points": total,
    }
    (RAW / "tiles_meta.json").write_text(json.dumps(tiles_meta, indent=1))

    print(f"\nCHECKPOINT: {len(paths)} tiles, {total:,} points total")
    horiz = {m["horizontal_epsg"] for m in meta}
    units = {tuple(u for _, u in m["axis_units"]) for m in meta}
    print(f"horizontal CRS set: {horiz}, unit set: {units}")
    if len(horiz) != 1 or None in horiz:
        sys.exit("HALT: tiles disagree on horizontal CRS or CRS missing")
    if horiz - {6341, 26912}:
        sys.exit(f"HALT: unexpected horizontal CRS {horiz} — expected UTM 12N (6341/26912)")
    if units != {("meter", "meter", "meter")}:
        sys.exit(f"HALT: units are not uniformly meters: {units} — add ingest conversion")

    from shapely.ops import unary_union as uu
    cover = uu([box(m["mins"][0], m["mins"][1], m["maxs"][0], m["maxs"][1]).buffer(0.5)
                for m in meta])
    greens = json.loads((POLY_DIR / "greens.geojson").read_text())["features"]
    gaps = []
    for f in greens:
        g = utm(shape(f["geometry"])).buffer(GREEN_BUFFER_M)
        a = g.difference(cover).area
        if a > 1.0:
            gaps.append((f["properties"]["label"], a))
    if gaps:
        sys.exit(f"HALT: buffered greens not covered by downloaded tiles: {gaps}")
    print("coverage: every buffered green fully inside downloaded tiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

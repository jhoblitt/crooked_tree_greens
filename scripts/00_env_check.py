#!/usr/bin/env python3
"""Stage 0: verify all dependencies import and required endpoints are reachable."""

import importlib.metadata
import sys

MODULES = [
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("laspy", "laspy"),
    ("lazrs", "lazrs"),
    ("pyproj", "pyproj"),
    ("shapely", "shapely"),
    ("rasterio", "rasterio"),
    ("matplotlib", "matplotlib"),
    ("trimesh", "trimesh"),
    ("requests", "requests"),
    ("folium", "folium"),
]

ENDPOINTS = [
    "https://tnmaccess.nationalmap.gov/api/v1/products?datasets=Lidar%20Point%20Cloud%20(LPC)&bbox=-111.05,32.39,-111.04,32.40&outputFormat=JSON&max=1",
    "https://overpass-api.de/api/status",
]


def main() -> int:
    ok = True
    print(f"python {sys.version.split()[0]}")
    for mod_name, dist_name in MODULES:
        try:
            importlib.import_module(mod_name)
            version = importlib.metadata.version(dist_name)
            print(f"  {mod_name:<12} {version}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {mod_name:<12} FAILED: {exc}")
            ok = False

    import requests

    for url in ENDPOINTS:
        host = url.split("/")[2]
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "crooked-tree-greens/0.1"})
            print(f"  https {host:<32} HTTP {r.status_code}")
            if r.status_code >= 500:
                ok = False
        except Exception as exc:  # noqa: BLE001
            print(f"  https {host:<32} FAILED: {exc}")
            ok = False

    print("ENV OK" if ok else "ENV FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

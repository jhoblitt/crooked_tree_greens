"""Stage 5 plumbing: artifact correctness and atomic per-green publication."""

import json

import numpy as np
import pytest
import rasterio
import trimesh
from conftest import BASE_E, BASE_N


def test_export_writes_all_artifacts(staged_course):
    m30, m40, m50, m60 = staged_course
    assert m50.main() == 0
    d = m50.OUT / "hole_01"
    for a in ("heightmap.npz", "heightmap.tif", "mesh.obj", "mesh.glb",
              "slope_heatmap.png", "contours.png", "meta.json"):
        assert (d / a).exists(), a
    assert not (m50.OUT / "hole_01.tmp").exists()


def test_heightmap_is_north_up_masked_and_tif_matches(staged_course):
    m30, m40, m50, m60 = staged_course
    assert m50.main() == 0
    d = m50.OUT / "hole_01"
    h = np.load(d / "heightmap.npz")
    z = h["z"]

    # row 0 is the northern edge: y0 must be the max-y node
    grid = np.load(m40.INTERIM / "hole_01_grid.npz")
    ny = grid["z"].shape[0]
    assert float(h["y0"]) == pytest.approx(float(grid["y0"]) + (ny - 1) * 0.25)
    # synthetic plane falls to the north (-0.01*y): northern rows sit lower
    assert np.nanmean(z[:5]) < np.nanmean(z[-5:])
    # NaN outside the buffered polygon: corners of the bbox are masked
    assert np.isnan(z[0, 0]) and np.isnan(z[-1, -1])
    assert np.isnan(z).any() and np.isfinite(z).any()

    with rasterio.open(d / "heightmap.tif") as src:
        band = src.read(1)
        assert src.crs.to_epsg() == 6341
        assert src.res == (0.25, 0.25)
        assert src.tags()["AREA_OR_POINT"] == "Point"
        assert np.array_equal(np.isfinite(band), np.isfinite(z))
        assert np.nanmax(np.abs(band - z)) < 1e-6

    meta = json.loads((d / "meta.json").read_text())
    assert meta["grid_origin_north_up"] == [pytest.approx(float(h["x0"])),
                                            pytest.approx(float(h["y0"]))]
    assert meta["grid_shape"] == list(z.shape)


def test_mesh_is_local_and_well_formed(staged_course):
    m30, m40, m50, m60 = staged_course
    assert m50.main() == 0
    mesh = trimesh.load(m50.OUT / "hole_01" / "mesh.obj")
    assert len(mesh.vertices) > 100 and len(mesh.faces) > 100
    assert int(mesh.faces.max()) < len(mesh.vertices)
    # centroid-local coordinates: small numbers, Z spans well under a meter
    assert np.abs(mesh.vertices[:, :2]).max() < 40.0
    assert np.abs(mesh.vertices[:, 2]).max() < 2.0

    meta = json.loads((m50.OUT / "hole_01" / "meta.json").read_text())
    lo = meta["local_origin_utm"]
    assert abs(lo[0] - BASE_E) < 1.0 and abs(lo[1] - BASE_N) < 1.0


def test_interrupted_export_leaves_old_dir_and_tmp(staged_course):
    """Regression: a mid-export crash must not tear the published green."""
    m30, m40, m50, m60 = staged_course
    assert m50.main() == 0
    sentinel = (m50.OUT / "hole_01" / "meta.json").read_bytes()

    def boom(*a, **k):
        raise RuntimeError("disk full")

    orig = m50.contour_plot
    m50.contour_plot = boom
    try:
        with pytest.raises(RuntimeError):
            m50.main()
    finally:
        m50.contour_plot = orig

    # published dir untouched, torn attempt parked as .tmp
    assert (m50.OUT / "hole_01" / "meta.json").read_bytes() == sentinel
    assert (m50.OUT / "hole_01.tmp").exists()

    # and Stage 6 refuses to report over the torn state
    with pytest.raises(SystemExit, match="interrupted Stage 5"):
        m60.main()

    # rerunning Stage 5 heals: tmp replaced, report passes reconcile
    assert m50.main() == 0
    assert not (m50.OUT / "hole_01.tmp").exists()

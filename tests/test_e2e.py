"""Mini end-to-end: stages 3→7 on a synthetic 2-hole course, then the two
regression scenarios replayed against the finished tree."""

import json

import pytest
from conftest import BASE_E, BASE_N, make_greens_geojson, make_tile, make_tiles_meta


@pytest.mark.slow
def test_pipeline_end_to_end(sandbox, monkeypatch):
    m30, m40, m45, m50, m60, m70 = sandbox(
        "30_clip_clean", "40_fit_surface", "45_pin_zones",
        "50_export", "60_report", "70_site")
    monkeypatch.setattr(m40, "FIT_MAX_PTS", 1200)
    monkeypatch.setattr(m60, "EXPECTED_HOLES", {1, 2})

    greens = [("hole_01", 1, BASE_E, BASE_N, 7.0),
              ("hole_02", 2, BASE_E + 70, BASE_N + 50, 8.0),
              ("practice", 0, BASE_E - 60, BASE_N + 60, 7.0)]
    make_greens_geojson(m30.POLY_DIR / "greens.geojson", greens)
    # two abutting tiles so greens straddle a seam like the real course;
    # 0.04 m noise ≈ real LiDAR so the lambda sweep lands in the 3-6 cm band
    t1 = make_tile(m30.RAW / "tile_a.laz", BASE_E - 90, BASE_N - 40,
                   size=100, density=4.0, rng_seed=1, noise=0.04)
    t2 = make_tile(m30.RAW / "tile_b.laz", BASE_E + 10, BASE_N - 40,
                   size=100, density=4.0, rng_seed=2, noise=0.04)
    make_tiles_meta(m30.RAW, [t1, t2])

    assert m30.main() == 0
    assert m40.main() == 0
    assert m45.main() == 0
    assert m50.main() == 0
    assert m60.main() == 0
    assert m70.main() == 0

    idx = json.loads((m60.OUT / "index.json").read_text())
    assert idx["status"] == "complete"
    assert [g["label"] for g in idx["greens"]] == ["hole_01", "hole_02", "practice"]
    for g in idx["greens"]:
        meta = json.loads((m60.OUT / g["label"] / "meta.json").read_text())
        assert meta["fit_band_note"] == "in_band"
        assert 0.03 <= meta["fit_rms_m"] <= 0.06
        # pin zones flow all the way through to the site
        assert "legal_pin_area_m2" in g
        assert (m60.OUT / g["label"] / "pin_zones.tif").exists()
        assert (m70.SITE / "crooked_tree" / "greens" / g["label"] / "pin_zones.png").exists()
    assert 'data-kind="pins"' in (m70.SITE / "crooked_tree" / "index.html").read_text()
    assert "crooked_tree/" in (m70.SITE / "index.html").read_text()  # course picker
    # hole_01's buffer straddles the tile seam at BASE_E+10: both tiles feed it;
    # hole_02 sits entirely inside tile_b
    meta1 = json.loads((m60.OUT / "hole_01" / "meta.json").read_text())
    assert meta1["tiles"] == ["tile_a.laz", "tile_b.laz"]
    meta2 = json.loads((m60.OUT / "hole_02" / "meta.json").read_text())
    assert meta2["tiles"] == ["tile_b.laz"]
    assert (m70.SITE / "index.html").exists()

    # Regression 1: a stray LAZ appearing later must halt Stage 3
    make_tile(m30.RAW / "stray.laz", BASE_E - 90, BASE_N - 40, size=50,
              density=1.0, rng_seed=3)
    with pytest.raises(SystemExit, match="stray.laz"):
        m30.main()
    (m30.RAW / "stray.laz").unlink()

    # Regression 2: renaming a green in the manifest orphans its old outputs
    renamed = [("hole_01", 1, BASE_E, BASE_N, 7.0),
               ("hole_03", 3, BASE_E + 70, BASE_N + 50, 8.0),
               ("practice", 0, BASE_E - 60, BASE_N + 60, 7.0)]
    make_greens_geojson(m30.POLY_DIR / "greens.geojson", renamed)
    with pytest.raises(SystemExit, match="hole_02"):
        m60.main()

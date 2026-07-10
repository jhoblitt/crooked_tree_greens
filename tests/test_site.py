"""Stage 7 plumbing: the Pages gallery builds from index.json + metas alone."""

import json

from conftest import load_script, make_fake_export


def seed_outputs(m):
    metas = [make_fake_export(m.OUT, "hole_01", 1),
             make_fake_export(m.OUT, "hole_02", 2,
                              flags=["max_sustained_9.9%_gt_8%"]),
             make_fake_export(m.OUT, "practice", 0)]
    index = {
        "course": "Test Course & Park",  # ampersand exercises escaping
        "status": "complete", "missing_holes": [],
        "crs_horizontal": "EPSG:6341", "crs_vertical": "EPSG:5703",
        "cell_size_m": 0.25,
        "source_work_units": ["USGS Lidar Point Cloud AZ_PimaCounty_2021_B21"],
        "acquisition_dates": ["2021-10-04"],
        "vertical_fidelity": metas[0]["vertical_fidelity"],
        "generated": "2026-07-10T00:00:00+00:00",
        "greens": [{
            "label": mt["label"], "hole": mt["hole"],
            "dir": f"outputs/greens/{mt['label']}",
            "slope_mean_pct": mt["slope_mean_pct"],
            "elevation_range_m": mt["elevation_range_on_green_m"],
            "fit_rms_m": mt["fit_rms_m"], "flags": mt["flags"],
            "needs_review": mt["needs_review"],
        } for mt in metas],
    }
    (m.OUT / "index.json").write_text(json.dumps(index))


def test_site_builds_gallery(sandbox):
    m = sandbox("70_site")
    seed_outputs(m)
    assert m.main() == 0

    html = (m.SITE / "index.html").read_text()
    assert "Hole 1" in html and "Hole 2" in html and "Practice" in html
    assert "Test Course &amp; Park" in html
    assert "max_sustained_9.9%_gt_8%" in html
    for label in ("hole_01", "hole_02", "practice"):
        assert (m.SITE / "greens" / label / "slope_heatmap.png").exists()
        assert (m.SITE / "greens" / label / "contours.png").exists()


def test_site_rebuild_is_clean(sandbox):
    m = sandbox("70_site")
    seed_outputs(m)
    assert m.main() == 0
    (m.SITE / "stale.html").write_text("old")
    assert m.main() == 0
    assert not (m.SITE / "stale.html").exists()

"""Stage 7 plumbing: the multi-course Pages site builds from index.json + metas."""

import json

from conftest import make_fake_export


def seed_course(m, slug, course_name):
    out = m.COURSES / slug / "outputs" / "greens"
    metas = [make_fake_export(out, "hole_01", 1),
             make_fake_export(out, "hole_02", 2,
                              flags=["max_sustained_9.9%_gt_8%"]),
             make_fake_export(out, "practice", 0)]
    index = {
        "course": course_name,
        "status": "complete", "missing_holes": [],
        "crs_horizontal": "EPSG:6341", "crs_vertical": "EPSG:5703 NAVD88 height (m), GEOID18",
        "cell_size_m": 0.25,
        "source_work_units": ["USGS Lidar Point Cloud AZ_PimaCounty_2021_B21"],
        "acquisition_dates": ["2021-10-04"],
        "vertical_fidelity": metas[0]["vertical_fidelity"],
        "generated": "2026-07-19T00:00:00+00:00",
        "greens": [{
            "label": mt["label"], "hole": mt["hole"],
            "dir": f"courses/{slug}/outputs/greens/{mt['label']}",
            "slope_mean_pct": mt["slope_mean_pct"],
            "elevation_range_m": mt["elevation_range_on_green_m"],
            "fit_rms_m": mt["fit_rms_m"], "flags": mt["flags"],
            "needs_review": mt["needs_review"],
        } for mt in metas],
    }
    (out / "index.json").write_text(json.dumps(index))


def test_site_builds_multi_course_gallery(sandbox):
    m = sandbox("70_site")
    seed_course(m, "course_a", "Course A & Park")  # ampersand exercises escaping
    seed_course(m, "course_b", "Course B")
    assert m.main() == 0

    root = (m.SITE / "index.html").read_text()
    assert "Course A &amp; Park" in root and "Course B" in root
    assert 'href="course_a/"' in root and 'href="course_b/"' in root

    for slug in ("course_a", "course_b"):
        cpage = (m.SITE / slug / "index.html").read_text()
        assert "Hole 1" in cpage and "Practice" in cpage
        assert 'data-kind="pins"' in cpage
        assert "max_sustained_9.9%_gt_8%" in cpage
        for label in ("hole_01", "hole_02", "practice"):
            for png in ("slope_heatmap.png", "contours.png", "pin_zones.png"):
                assert (m.SITE / slug / "greens" / label / png).exists()


def test_green_pages_have_viewer_and_navigation(sandbox):
    m = sandbox("70_site")
    seed_course(m, "course_a", "Course A")
    assert m.main() == 0
    page = (m.SITE / "course_a" / "greens" / "hole_01" / "index.html").read_text()
    # view switcher over all three map kinds
    for kind in ("slope", "contours", "pins"):
        assert f'data-kind="{kind}"' in page
    # pan/zoom viewer with zoom + reset controls
    assert 'id="viewer"' in page and 'id="view"' in page
    assert "zoomBtn(1.3)" in page and "resetView()" in page
    # the pointerdown guard that lets the zoom buttons actually fire
    assert "e.target.closest('.vbtns')" in page
    # native image drag suppressed so pan doesn't cancel after a tiny move
    assert 'draggable="false"' in page
    assert "e.preventDefault()" in page and "dragstart" in page
    # return navigation + prev/next (wraps)
    assert 'href="../../"' in page
    assert 'href="../../greens_overview.html"' in page
    assert 'href="../practice/"' in page  # prev of first wraps to last
    assert 'href="../hole_02/"' in page
    # gallery card links to the page, not the raw png
    gal = (m.SITE / "course_a" / "index.html").read_text()
    assert 'href="greens/hole_01/"' in gal


def test_site_skips_courses_without_outputs(sandbox):
    m = sandbox("70_site")
    seed_course(m, "course_a", "Course A")
    (m.COURSES / "unbuilt" / "polygons").mkdir(parents=True)
    assert m.main() == 0
    assert not (m.SITE / "unbuilt").exists()
    assert "unbuilt" not in (m.SITE / "index.html").read_text()


def test_site_rebuild_is_clean(sandbox):
    m = sandbox("70_site")
    seed_course(m, "course_a", "Course A")
    assert m.main() == 0
    (m.SITE / "stale.html").write_text("old")
    assert m.main() == 0
    assert not (m.SITE / "stale.html").exists()

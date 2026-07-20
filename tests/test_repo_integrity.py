"""Integrity of the COMMITTED artifact trees, per course.

These run against the real repo (no network, no data/raw needed) and catch a
bad commit: outputs drifting from the polygon manifest, missing artifacts, or
an index that disagrees with what is on disk — for every course under
courses/ that has published outputs.
"""

import json
import tomllib

import pytest
from conftest import ARTIFACTS, REPO

COURSES = REPO / "courses"


def built_courses():
    return sorted(c.name for c in COURSES.iterdir()
                  if (c / "outputs" / "greens" / "index.json").exists())


def out_dir(slug):
    return COURSES / slug / "outputs" / "greens"


@pytest.fixture(params=built_courses(), scope="module")
def course(request):
    slug = request.param
    gj = json.loads((COURSES / slug / "polygons" / "greens.geojson").read_text())
    labels = {f["properties"]["label"] for f in gj["features"]}
    idx = json.loads((out_dir(slug) / "index.json").read_text())
    return slug, labels, idx


def test_course_has_config(course):
    slug, _, _ = course
    cfg = tomllib.loads((COURSES / slug / "course.toml").read_text())
    assert cfg["name"] and cfg["holes"]["count"] > 0
    assert cfg["crs"]["utm_epsg"] in cfg["crs"]["accept_horizontal_epsg"]


def test_outputs_match_polygon_manifest(course):
    slug, labels, _ = course
    dirs = {p.name for p in out_dir(slug).iterdir() if p.is_dir()}
    assert dirs == labels
    assert not any(d.endswith(".tmp") for d in dirs)


def test_every_green_has_all_artifacts(course):
    slug, labels, _ = course
    missing = [(label, a) for label in sorted(labels)
               for a in ARTIFACTS if not (out_dir(slug) / label / a).exists()]
    assert missing == []


def test_meta_labels_match_dirs(course):
    slug, labels, _ = course
    for label in sorted(labels):
        meta = json.loads((out_dir(slug) / label / "meta.json").read_text())
        assert meta["label"] == label


def test_index_agrees_with_disk(course):
    slug, labels, idx = course
    assert {g["label"] for g in idx["greens"]} == labels
    cfg = tomllib.loads((COURSES / slug / "course.toml").read_text())
    expected = set(cfg["holes"].get("refs") or range(1, cfg["holes"]["count"] + 1))
    holes = {g["hole"] for g in idx["greens"] if g["hole"]}
    if idx["status"] == "complete":
        assert holes == expected and idx["missing_holes"] == []
    else:
        assert sorted(expected - holes) == idx["missing_holes"]


def test_committed_fits_are_in_band(course):
    _, _, idx = course
    for g in idx["greens"]:
        assert 0.03 <= g["fit_rms_m"] <= 0.06, g["label"]


def test_committed_pin_zones_present_and_indexed(course):
    slug, _, idx = course
    for g in idx["greens"]:
        assert "legal_pin_area_m2" in g and "scarce_legal_area" in g
        meta = json.loads((out_dir(slug) / g["label"] / "meta.json").read_text())
        pz = meta["pin_zones"]
        assert (pz["tiers"]["premium"]["area_m2"] <= pz["tiers"]["standard"]["area_m2"]
                <= pz["tiers"]["traditional"]["area_m2"])
        assert pz["legal_area_m2"] == pz["tiers"]["standard"]["area_m2"]
        assert g["legal_pin_area_m2"] == pz["legal_area_m2"]


def test_crooked_tree_is_complete_with_known_steep_greens():
    """Course-specific regression pins for the original course."""
    idx = json.loads((out_dir("crooked_tree") / "index.json").read_text())
    assert idx["status"] == "complete"
    holes = sorted(g["hole"] for g in idx["greens"] if g["hole"])
    assert holes == list(range(1, 19))
    by = {g["label"]: g for g in idx["greens"]}
    for label in ("hole_13", "hole_18"):
        assert by[label]["legal_pin_area_m2"] == 0.0
        assert by[label]["scarce_legal_area"] is True

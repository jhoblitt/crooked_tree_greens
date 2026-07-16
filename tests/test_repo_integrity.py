"""Integrity of the COMMITTED artifact tree.

These run against the real repo (no network, no data/raw needed) and catch a
bad commit: outputs drifting from the polygon manifest, missing artifacts, or
an index that disagrees with what is on disk.
"""

import json

import pytest
from conftest import ARTIFACTS, REPO

POLY = REPO / "data" / "polygons"
OUT = REPO / "outputs" / "greens"


@pytest.fixture(scope="module")
def manifest_labels():
    gj = json.loads((POLY / "greens.geojson").read_text())
    return {f["properties"]["label"] for f in gj["features"]}


def test_outputs_match_polygon_manifest(manifest_labels):
    dirs = {p.name for p in OUT.iterdir() if p.is_dir()}
    assert dirs == manifest_labels
    assert not any(d.endswith(".tmp") for d in dirs)


def test_every_green_has_all_artifacts(manifest_labels):
    missing = [(label, a) for label in sorted(manifest_labels)
               for a in ARTIFACTS if not (OUT / label / a).exists()]
    assert missing == []


def test_meta_labels_match_dirs(manifest_labels):
    for label in sorted(manifest_labels):
        meta = json.loads((OUT / label / "meta.json").read_text())
        assert meta["label"] == label


def test_index_agrees_with_disk(manifest_labels):
    idx = json.loads((OUT / "index.json").read_text())
    assert {g["label"] for g in idx["greens"]} == manifest_labels
    holes = sorted(g["hole"] for g in idx["greens"] if g["hole"])
    assert holes == list(range(1, 19))
    assert idx["status"] == "complete" and idx["missing_holes"] == []


def test_committed_fits_are_in_band():
    idx = json.loads((OUT / "index.json").read_text())
    for g in idx["greens"]:
        assert 0.03 <= g["fit_rms_m"] <= 0.06, g["label"]


def test_committed_pin_zones_present_and_indexed(manifest_labels):
    idx = json.loads((OUT / "index.json").read_text())
    for g in idx["greens"]:
        assert "legal_pin_area_m2" in g and "scarce_legal_area" in g
        meta = json.loads((OUT / g["label"] / "meta.json").read_text())
        pz = meta["pin_zones"]
        # tiers nest and the headline area matches the standard tier
        assert (pz["tiers"]["premium"]["area_m2"] <= pz["tiers"]["standard"]["area_m2"]
                <= pz["tiers"]["traditional"]["area_m2"])
        assert pz["legal_area_m2"] == pz["tiers"]["standard"]["area_m2"]
        assert g["legal_pin_area_m2"] == pz["legal_area_m2"]


def test_steep_greens_have_scarce_or_zero_legal_area():
    """The known-steep greens must surface as scarce — a regression guard on
    both the fit and the pin-zone thresholds."""
    idx = json.loads((OUT / "index.json").read_text())
    by = {g["label"]: g for g in idx["greens"]}
    for label in ("hole_13", "hole_18"):
        assert by[label]["legal_pin_area_m2"] == 0.0
        assert by[label]["scarce_legal_area"] is True

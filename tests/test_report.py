"""Stage 6 plumbing: manifest reconciliation (Codex finding 2) and reporting."""

import json

import pytest
from conftest import BASE_E, BASE_N, load_script, make_fake_export, make_greens_geojson

mod = load_script("60_report")


def manifest(m, labels_holes):
    make_greens_geojson(
        m.POLY_DIR / "greens.geojson",
        [(label, hole, BASE_E + 30 * i, BASE_N, 9)
         for i, (label, hole) in enumerate(labels_holes)])


def test_complete_report_and_index(sandbox, monkeypatch):
    m = sandbox("60_report")
    monkeypatch.setattr(m, "EXPECTED_HOLES", {1, 2})
    manifest(m, [("hole_01", 1), ("hole_02", 2), ("practice", 0)])
    for label, hole in (("hole_01", 1), ("hole_02", 2), ("practice", 0)):
        make_fake_export(m.OUT, label, hole)

    assert m.main() == 0
    report = (m.REPORTS / "qc_report.md").read_text()
    assert "**COMPLETE**" in report
    idx = json.loads((m.OUT / "index.json").read_text())
    assert idx["status"] == "complete" and len(idx["greens"]) == 3
    assert [g["label"] for g in idx["greens"]][:2] == ["hole_01", "hole_02"]


def test_partial_when_manifest_green_unexported(sandbox, monkeypatch, capsys):
    m = sandbox("60_report")
    monkeypatch.setattr(m, "EXPECTED_HOLES", {1, 2})
    manifest(m, [("hole_01", 1), ("hole_02", 2)])
    make_fake_export(m.OUT, "hole_01", 1)

    assert m.main() == 0
    assert "no exports yet: ['hole_02']" in capsys.readouterr().out
    idx = json.loads((m.OUT / "index.json").read_text())
    assert idx["status"] == "partial" and idx["missing_holes"] == [2]


def test_orphan_output_dir_halts(sandbox, monkeypatch):
    """Regression: a stale dir from a renamed green must not satisfy the report."""
    m = sandbox("60_report")
    monkeypatch.setattr(m, "EXPECTED_HOLES", {1})
    manifest(m, [("hole_01", 1)])
    make_fake_export(m.OUT, "hole_01", 1)
    make_fake_export(m.OUT, "hole_99", 99)  # renamed/removed green's leftovers
    with pytest.raises(SystemExit, match="hole_99"):
        m.main()


def test_tmp_dir_halts(sandbox, monkeypatch):
    m = sandbox("60_report")
    monkeypatch.setattr(m, "EXPECTED_HOLES", {1})
    manifest(m, [("hole_01", 1)])
    make_fake_export(m.OUT, "hole_01", 1)
    (m.OUT / "hole_01.tmp").mkdir()
    with pytest.raises(SystemExit, match="interrupted Stage 5"):
        m.main()


def test_meta_label_dir_mismatch_halts(sandbox, monkeypatch):
    m = sandbox("60_report")
    monkeypatch.setattr(m, "EXPECTED_HOLES", {1, 2})
    manifest(m, [("hole_01", 1), ("hole_02", 2)])
    make_fake_export(m.OUT, "hole_01", 1)
    make_fake_export(m.OUT, "hole_02", 2, label="hole_01")  # hand-copied dir
    with pytest.raises(SystemExit, match="claims label"):
        m.main()


def test_missing_artifact_fails(sandbox, monkeypatch):
    m = sandbox("60_report")
    monkeypatch.setattr(m, "EXPECTED_HOLES", {1})
    manifest(m, [("hole_01", 1)])
    make_fake_export(m.OUT, "hole_01", 1)
    (m.OUT / "hole_01" / "mesh.glb").unlink()
    assert m.main() == 1


def test_report_and_index_include_pin_zones(sandbox, monkeypatch):
    m = sandbox("60_report")
    monkeypatch.setattr(m, "EXPECTED_HOLES", {1})
    manifest(m, [("hole_01", 1)])
    make_fake_export(m.OUT, "hole_01", 1)
    assert m.main() == 0
    report = (m.REPORTS / "qc_report.md").read_text()
    assert "legal pin m² (%)" in report
    assert "## Legal pin zones" in report
    assert "120" in report  # the fake export's standard legal area
    idx = json.loads((m.OUT / "index.json").read_text())
    g = idx["greens"][0]
    assert g["legal_pin_area_m2"] == 120.0 and g["scarce_legal_area"] is False


def test_report_flags_scarce_legal_area(sandbox, monkeypatch):
    m = sandbox("60_report")
    monkeypatch.setattr(m, "EXPECTED_HOLES", {1})
    manifest(m, [("hole_01", 1)])
    scarce = {
        "definition": "test", "edge_setback_m": 3.0, "cup_bench_radius_m": 0.5,
        "headline_tier": "standard", "legal_area_m2": 3.0, "legal_fraction": 0.01,
        "scarce_legal_area": True,
        "tiers": {
            "traditional": {"slope_max_pct": 3.0, "area_m2": 20.0,
                            "fraction_of_green": 0.07, "n_zones": 1},
            "standard": {"slope_max_pct": 2.0, "area_m2": 3.0,
                         "fraction_of_green": 0.01, "n_zones": 1},
            "premium": {"slope_max_pct": 1.5, "area_m2": 0.0,
                        "fraction_of_green": 0.0, "n_zones": 0},
        },
    }
    make_fake_export(m.OUT, "hole_01", 1, pin_zones=scarce)
    assert m.main() == 0
    report = (m.REPORTS / "qc_report.md").read_text()
    assert "Scarce legal area" in report and "hole_01" in report


def test_flags_surface_in_report(sandbox, monkeypatch):
    m = sandbox("60_report")
    monkeypatch.setattr(m, "EXPECTED_HOLES", {1})
    manifest(m, [("hole_01", 1)])
    make_fake_export(m.OUT, "hole_01", 1,
                     flags=["max_sustained_9.9%_gt_8%"], needs_review=True)
    assert m.main() == 0
    report = (m.REPORTS / "qc_report.md").read_text()
    assert "max_sustained_9.9%_gt_8%" in report
    assert "polygon needs human review" in report

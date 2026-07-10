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

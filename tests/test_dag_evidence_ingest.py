"""Unit tests for evidence file ingest, workspace sandboxing, and TS vibration validation."""

from pathlib import Path

import pytest

from cloudra.dag.evidence_ingest import (
    FileEvidenceSnapshot,
    snapshot_evidence_file,
    validate_species_minimum,
    validate_ts_mode,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_snapshot_evidence_file_success(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    test_file = ws / "data.txt"
    test_file.write_text("hello quantum world")

    snap = snapshot_evidence_file(test_file, workspace_root=ws)
    assert isinstance(snap, FileEvidenceSnapshot)
    assert snap.file_size == len("hello quantum world")
    assert snap.sha256
    assert Path(snap.snapshot_path).exists()
    assert snap.is_qm_log is False


def test_snapshot_evidence_file_traversal_blocked(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")

    with pytest.raises(ValueError, match="workspace"):
        snapshot_evidence_file(outside, workspace_root=ws)

    with pytest.raises(ValueError, match="workspace"):
        snapshot_evidence_file("../outside.txt", workspace_root=ws)


def test_snapshot_evidence_file_not_found(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    with pytest.raises(FileNotFoundError):
        snapshot_evidence_file(ws / "nonexistent.log", workspace_root=ws)


def test_snapshot_qm_log_xtb_ts(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    src = FIXTURES_DIR / "xtb" / "ts_hess_xtb.out"
    assert src.exists()
    dest = ws / "ts_hess_xtb.out"
    dest.write_text(src.read_text())

    snap = snapshot_evidence_file(dest, workspace_root=ws)
    assert snap.is_qm_log is True
    assert snap.imaginary_frequencies is not None
    assert len(snap.imaginary_frequencies) == 1
    assert snap.imaginary_frequencies[0] < 0
    assert snap.final_energy_hartree is not None


def test_snapshot_qm_log_water_minimum(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    src = FIXTURES_DIR / "gaussian" / "water_opt_freq_g16.out"
    assert src.exists()
    dest = ws / "water.out"
    dest.write_text(src.read_text())

    snap = snapshot_evidence_file(dest, workspace_root=ws)
    assert snap.is_qm_log is True
    assert snap.imaginary_frequencies is not None
    assert len(snap.imaginary_frequencies) == 0
    assert snap.final_energy_hartree is not None
    assert snap.final_energy_hartree == pytest.approx(
        -74.9659011806, rel=0, abs=1e-7,
    )


def test_validate_ts_mode():
    res = validate_ts_mode(freqs=[-521.21, 100.0, 500.0], normal_modes=None, description="C-C bond cleavage")
    assert res.frequency_count_valid is True
    assert res.frequency_data_present is True
    assert res.n_imag == 1
    assert res.imaginary_frequencies == [-521.21]
    assert res.mode_matched is False

    # 0 imaginary frequencies -> not a TS
    res_zero = validate_ts_mode(freqs=[100.0, 500.0], normal_modes=None, description="C-C bond cleavage")
    assert res_zero.frequency_count_valid is False
    assert res_zero.n_imag == 0

    # 2 imaginary frequencies -> second-order saddle point
    res_two = validate_ts_mode(freqs=[-521.21, -120.0, 100.0], normal_modes=None, description="C-C bond cleavage")
    assert res_two.frequency_count_valid is False
    assert res_two.n_imag == 2

    empty = validate_ts_mode(None, imaginary_freqs=[])
    assert empty.frequency_data_present is False
    assert empty.frequency_count_valid is False
    assert empty.mode_matched is False


def test_validate_species_minimum():
    res = validate_species_minimum(freqs=[100.0, 500.0, 1500.0])
    assert res.frequency_count_valid is True
    assert res.frequency_data_present is True
    assert res.n_imag == 0

    res_imag = validate_species_minimum(freqs=[-50.0, 100.0, 1500.0])
    assert res_imag.frequency_count_valid is False
    assert res_imag.n_imag == 1

    # A stale empty imaginary list must not override a negative full spectrum.
    inconsistent = validate_species_minimum(
        freqs=[-74.94, 108.03, 250.68], imaginary_freqs=[]
    )
    assert inconsistent.frequency_count_valid is False
    assert inconsistent.imaginary_frequencies == [-74.94]

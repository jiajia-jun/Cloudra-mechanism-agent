"""Gaussian archive separators must never become molecular identity text."""

import json
import tracemalloc
from pathlib import Path

import pytest

from cloudra.benchmark.graph_similarity import GedConfig, species_substitution_cost
from cloudra.benchmark.integrity import _smiles_in_native_log, scan_evidence_files

_NATIVE_WATER = Path(__file__).parent / "fixtures/gaussian/water_opt_freq_g16.out"
_ARCHIVE = (
    r"1\1\GINC-HOST\FOpt\RHF\STO-3G\C3H4O1\USER\19-Oct-2026\0"
    r"\\# opt\\smiles: C=CC=O\\0,1\C,0.,0.,0.\\Version=G16\\@"
)


@pytest.mark.parametrize("smiles", ["C=CC=O", r"F/C=C\F", "[OH-]", r"C=CC=O\0"])
def test_native_gaussian_archive_title_has_no_charge_suffix(tmp_path, smiles):
    native = _NATIVE_WATER.read_text()
    # Only the archive titles change; this test exercises discovery, not binding
    # these annotations to the water geometry in the captured native output.
    annotated = native.replace(r"\\Water\\", rf"\\smiles: {smiles}\\")
    assert annotated != native
    path = tmp_path / "species.log"
    path.write_text(annotated)

    evidence, = scan_evidence_files(tmp_path)

    assert evidence.kind == "gaussian"
    assert evidence.smiles_found == [smiles]
    assert path.read_text() == annotated


@pytest.mark.parametrize("wrap_marker", [None, "smiles", "C=CC=O", r"\\0", r"\\@"])
def test_gaussian_archive_annotation_survives_native_line_wrapping(tmp_path, wrap_marker):
    wrap_at = _ARCHIVE.index(wrap_marker) + len(wrap_marker) // 2 if wrap_marker else 0
    chunks = [_ARCHIVE] if not wrap_marker else [_ARCHIVE[:wrap_at], _ARCHIVE[wrap_at:]]
    (tmp_path / "species.log").write_text(
        "Entering Gaussian System\n" + "".join(f" {chunk}\n" for chunk in chunks)
    )

    evidence, = scan_evidence_files(tmp_path)

    assert evidence.smiles_found == ["C=CC=O"]


@pytest.mark.parametrize("ending", ["", "\n\n"])
def test_incomplete_gaussian_archive_never_becomes_a_smiles_annotation(tmp_path, ending):
    (tmp_path / "species.log").write_text(
        "Entering Gaussian System\n " + _ARCHIVE.removesuffix(r"\\@") + ending
    )

    evidence, = scan_evidence_files(tmp_path)

    assert evidence.smiles_found == []


@pytest.mark.parametrize("suffix", [".xyz", ".json", ".log"])
@pytest.mark.parametrize("smiles", [r"C=CC=O\0", r"F/C=C\F"])
def test_discovery_preserves_literal_smiles_outside_gaussian_archive(tmp_path, suffix, smiles):
    text = json.dumps({"smiles": smiles}) if suffix == ".json" else f"smiles: {smiles}\n"
    if suffix == ".log":
        text = "Entering Gaussian System\n" + text
    (tmp_path / f"species{suffix}").write_text(text)

    evidence, = scan_evidence_files(tmp_path)

    assert evidence.smiles_found == [smiles]


def test_archive_annotation_reaches_comparison_without_rdkit_parse_error(tmp_path, capfd):
    pytest.importorskip("rdkit")
    native = _NATIVE_WATER.read_text().replace(r"\\Water\\", r"\\smiles: C=CC=O\\")
    (tmp_path / "species.log").write_text(native)
    evidence, = scan_evidence_files(tmp_path)

    cost = species_substitution_cost(["C=CC=O"], evidence.smiles_found, GedConfig())

    assert cost == 0.0
    assert "SMILES Parse Error" not in capfd.readouterr().err


def test_gaussian_archive_body_does_not_accumulate_in_annotation_memory():
    def peak_for_body(body_lines):
        def lines():
            yield " " + _ARCHIVE.split(r"\\Version=", 1)[0] + "\n"
            for index in range(body_lines):
                # Generate Hessian-like native rows on demand; no full archive
                # or prebuilt body is counted as parser memory.
                yield f" {index * 1e-6:.8f}," + "0.00000000," * 6 + "\n"
            yield " " + r"\\@" + "\n"

        tracemalloc.start()
        try:
            identities = list(_smiles_in_native_log(lines(), "gaussian"))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert identities == ["C=CC=O"]
        return peak

    small_peak = peak_for_body(64)
    large_peak = peak_for_body(8192)

    assert large_peak < small_peak * 4

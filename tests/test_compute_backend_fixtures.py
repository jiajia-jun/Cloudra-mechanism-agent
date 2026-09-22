"""Validation for the minimal inputs used by the Agent scenario matrix."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from ase.calculators.vasp.create_input import GenerateVaspInput
from ase.io import read
from ase.io.gaussian import read_gaussian_in

FIXTURES = Path(__file__).parent / "fixtures" / "compute_backends"
GAUSSIAN = next(
    (path for name in ("g16", "g09", "g26") if (path := shutil.which(name))), None
)
CP2K = next(
    (
        path
        for name in ("cp2k.popt", "cp2k.ssmp", "cp2k.psmp", "cp2k")
        if (path := shutil.which(name))
    ),
    None,
)


def test_gaussian_fixture_is_parseable():
    with (FIXTURES / "gaussian" / "he.gjf").open(encoding="utf-8") as handle:
        atoms = read_gaussian_in(handle)

    assert atoms.get_chemical_symbols() == ["He"]


@pytest.mark.skipif(GAUSSIAN is None, reason="Gaussian is not installed")
def test_gaussian_fixture_is_accepted_by_the_engine(tmp_path):
    assert GAUSSIAN is not None
    source = FIXTURES / "gaussian" / "he.gjf"
    completed = subprocess.run(
        [GAUSSIAN],
        cwd=tmp_path,
        input=source.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Normal termination" in completed.stdout


@pytest.mark.skipif(shutil.which("orca") is None, reason="ORCA is not installed")
def test_orca_fixture_is_accepted_by_the_engine(tmp_path):
    source = FIXTURES / "orca" / "he.inp"
    target = tmp_path / source.name
    shutil.copy2(source, target)

    completed = subprocess.run(
        [shutil.which("orca"), target.name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "ORCA TERMINATED NORMALLY" in completed.stdout


@pytest.mark.skipif(shutil.which("xtb") is None, reason="xTB is not installed")
def test_xtb_fixture_is_accepted_by_the_engine(tmp_path):
    source = FIXTURES / "xtb" / "he.xyz"
    target = tmp_path / source.name
    shutil.copy2(source, target)

    completed = subprocess.run(
        [shutil.which("xtb"), target.name, "--sp"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "normal termination of xtb" in completed.stdout + completed.stderr


@pytest.mark.skipif(CP2K is None, reason="CP2K is not installed")
def test_cp2k_fixture_is_accepted_by_the_engine(tmp_path):
    assert CP2K is not None
    source = FIXTURES / "cp2k" / "he.inp"
    target = tmp_path / source.name
    output = tmp_path / "he.out"
    shutil.copy2(source, target)

    completed = subprocess.run(
        [CP2K, "-i", target.name, "-o", output.name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "PROGRAM ENDED AT" in output.read_text(encoding="utf-8", errors="replace")


def test_vasp_fixture_has_a_parseable_structure_and_required_control_files():
    fixture = FIXTURES / "vasp"
    atoms = read(fixture / "POSCAR", format="vasp")
    controls = GenerateVaspInput()
    controls.read_incar(fixture / "INCAR")
    controls.read_kpoints(fixture / "KPOINTS")

    assert atoms.get_chemical_symbols() == ["He"]
    assert atoms.cell.volume > 0
    assert controls.float_params["encut"] == 300.0
    assert controls.int_params["ibrion"] == -1
    assert controls.input_params["kpts"].tolist() == [1, 1, 1]
    assert controls.input_params["gamma"] is True
    assert not (fixture / "POTCAR").exists(), "licensed POTCAR must not be committed"

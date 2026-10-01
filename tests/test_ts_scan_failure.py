"""Offline boundaries for the observed ORCA PROPERTIES/SHARK failure."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_NATIVE_FAILURE = (
    "THE OPTIMIZATION HAS CONVERGED\n" * 8
    + "The optimization did not converge but reached the maximum number of optimization cycles.\n"
    + "ERROR (SHARK): Failed to read input file scan.SHARKINP.tmp\n"
    + "Primary job terminated normally, but 1 process returned a non-zero exit code.\n"
    + "ORCA finished by error termination in PROPERTIES\n"
)


def test_orca_runner_preserves_engine_temporary_file_on_properties_failure(tmp_path, monkeypatch):
    from cloudra.infra.platform_utils import get_bash_path, is_posix

    if not is_posix():
        pytest.skip("calculator requires POSIX bash")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    engine = binary_dir / "orca"
    engine.write_text(
        f"#!{sys.executable}\n"
        "from pathlib import Path\n"
        "import sys\n"
        "source = Path(sys.argv[1])\n"
        "assert source.parent.resolve() == Path.cwd()\n"
        "scratch = source.with_suffix('.SHARKINP.tmp')\n"
        "scratch.write_text('engine-owned temporary input')\n"
        "assert scratch.read_text() == 'engine-owned temporary input'\n"
        f"print({_NATIVE_FAILURE!r})\n"
        "sys.exit(4)\n"
    )
    engine.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary_dir) + os.pathsep + os.environ.get("PATH", ""))
    job = tmp_path / "scan"
    job.mkdir()
    source = job / "scan.inp"
    content = "! OPT b3lyp def2-SVP D3BJ RIJCOSX def2/J TightSCF\n"
    source.write_text(content)
    script = Path(__file__).resolve().parents[1] / "cloudra" / "calculator.sh"
    result = subprocess.run([get_bash_path(), str(script), str(source), "orca"],
                            cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 4
    assert "ORCA finished by error termination in PROPERTIES" in result.stdout
    assert source.read_text() == content
    assert source.with_suffix('.SHARKINP.tmp').read_text() == 'engine-owned temporary input'


@pytest.mark.asyncio
async def test_monitor_does_not_treat_mpi_primary_termination_as_orca_success(tmp_path, monkeypatch):
    from cloudra.runtime import monitor

    log = tmp_path / "scan.out"
    log.write_text(_NATIVE_FAILURE)
    async def unavailable_cclib(*_):
        return None
    monkeypatch.setattr(monitor, "_cclib_parse", unavailable_cclib)
    parsed, success = await monitor._parse_orca_log(log)
    assert success is False
    assert parsed["is_success"] is False

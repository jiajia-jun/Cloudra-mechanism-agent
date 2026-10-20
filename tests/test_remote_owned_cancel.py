"""The SSH runner must wait for the owned engine family, including new groups."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from cloudra.runtime.remote_compute import build_remote_runner_script


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix" or shutil.which("bash") is None, reason="POSIX runner")
async def test_remote_cancel_stops_term_ignoring_engine_in_its_new_group(tmp_path):
    engine = tmp_path / "engine.py"
    engine.write_text(
        "import os,pathlib,signal,subprocess,sys,time\n"
        "root=pathlib.Path(sys.argv[1]); role=sys.argv[2] if len(sys.argv)>2 else 'engine'\n"
        "if role=='link':\n"
        " os.setpgid(0,0)\n"
        " signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
        "else:\n"
        " subprocess.Popen([sys.executable,__file__,str(root),'link'],close_fds=True)\n"
        "(root/(role+'.ready')).write_text(str(os.getpid()))\n"
        "while not (root/'finish').exists():\n"
        " (root/(role+'.heartbeat')).write_text(str(time.monotonic_ns()))\n"
        " time.sleep(0.01)\n"
    )
    runtime = tmp_path / ".cloudra"
    runtime.mkdir()
    shutil.copyfile(Path(__file__).parents[1] / "cloudra/runtime/calc_lock_wrapper.py",
                    runtime / "calc_lock_wrapper.py")
    runner = tmp_path / "runner.sh"
    runner.write_text(build_remote_runner_script(
        "input.gjf", "gaussian", 7, {"type": "ssh_local"}, workdir=str(tmp_path),
        calculator_cmd=[sys.executable, str(engine), str(tmp_path)],
    ))
    proc = await asyncio.create_subprocess_exec(
        "bash", str(runner), cwd=tmp_path, start_new_session=True,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / "link.heartbeat").is_file():
            assert time.monotonic() < deadline, "owned engine did not start"
            await asyncio.sleep(0.02)
        # Both paths are written before the repair, to reproduce the old public
        # cancellation request and exercise the new shared-owner request.
        (tmp_path / ".cloudra-cancel-7").touch()
        (runtime / "calc-7.cancel").touch()
        await asyncio.wait_for(proc.wait(), 5)
        assert (tmp_path / ".cloudra-exit-7").is_file()
        heartbeat = (tmp_path / "link.heartbeat").read_text()
        await asyncio.sleep(0.1)
        assert (tmp_path / "link.heartbeat").read_text() == heartbeat, (
            "SSH exit receipt was published while a TERM-ignoring engine child still executed"
        )
    finally:
        (tmp_path / "finish").touch()
        if proc.returncode is None:
            proc.terminate()
        await proc.wait()
        await asyncio.sleep(0.05)

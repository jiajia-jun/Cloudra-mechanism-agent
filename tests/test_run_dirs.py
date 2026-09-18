"""run_dirs：crest_runner / xtb_path_runner 共用的运行现场件的单源行为。"""

import os
import stat
import subprocess

from cloudra.tools.core.run_dirs import (
    capture_versions,
    list_artifact_files,
    next_run_dir,
    terminate_process_group,
)


def test_next_run_dir_numbers_monotonically_and_sanitizes_label(tmp_path):
    first = next_run_dir(str(tmp_path), "runs", "my run/label")
    second = next_run_dir(str(tmp_path), "runs", "my run/label")
    assert os.path.basename(first) == "my_run_label_0001"
    assert os.path.basename(second) == "my_run_label_0002"
    assert os.path.isdir(first) and os.path.isdir(second)


def test_next_run_dir_ignores_unrelated_names(tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    (runs_root / "other_0001").mkdir()
    (runs_root / "run_abc").mkdir()
    (runs_root / "run_0007").mkdir()
    assert os.path.basename(next_run_dir(str(tmp_path), "runs", "run")) == "run_0001"
    # 已占用 1 与 7：下一个空号是 2，不覆盖已有的 7
    assert os.path.basename(next_run_dir(str(tmp_path), "runs", "run")) == "run_0002"


def test_capture_versions_records_missing_executable_as_failure():
    text = capture_versions(("definitely-not-a-real-binary-xyz",), ("version",))
    assert "definitely-not-a-real-binary-xyz --version failed:" in text


def test_capture_versions_keeps_only_marker_lines(tmp_path):
    script = tmp_path / "fakeengine"
    script.write_text(
        "#!/bin/sh\necho 'banner line'\necho 'fake version 9.9'\necho 'other noise'\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    text = capture_versions((str(script),), ("version",))
    assert "fake version 9.9" in text
    assert "banner line" not in text
    assert "other noise" not in text
    assert "returncode=0" in text


def test_list_artifact_files_lists_only_files_sorted(tmp_path):
    (tmp_path / "b.log").write_text("bb", encoding="utf-8")
    (tmp_path / "a.log").write_text("a", encoding="utf-8")
    (tmp_path / "subdir").mkdir()
    artifacts = list_artifact_files(str(tmp_path))
    assert [name for name, _path, _size in artifacts] == ["a.log", "b.log"]
    assert [size for _name, _path, size in artifacts] == [1, 2]
    for name, path, _size in artifacts:
        assert path == os.path.join(str(tmp_path), name)


def test_terminate_process_group_kills_and_reaps():
    proc = subprocess.Popen(
        ["sleep", "60"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    terminate_process_group(proc)
    assert proc.returncode is not None
    assert proc.poll() is not None


def test_terminate_process_group_windows_fallback(monkeypatch):
    """GH #40：Windows 没有 os.getpgid / os.killpg / signal.SIGKILL——
    降级为单进程 terminate → kill 并回收，绝不 AttributeError 炸穿调用方
    （Supervisor 曾在 Windows 上因此反复 failed）。"""
    import sys

    monkeypatch.delattr(os, "getpgid", raising=False)
    monkeypatch.delattr(os, "killpg", raising=False)
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        terminate_process_group(proc)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode is not None
    assert proc.poll() is not None

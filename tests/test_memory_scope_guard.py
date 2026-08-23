"""Memory scope guard: project-specific content must not reach global MEMORY.md."""

from __future__ import annotations

import pytest

from cloudra.tools.core.memory_scope_guard import find_project_specific_fragments


def test_detects_posix_absolute_path():
    fragments = find_project_specific_fragments("results live in /home/user/proj/out.log")
    assert any("/home/user/proj/out.log" in f for f in fragments)


def test_detects_windows_path():
    fragments = find_project_specific_fragments(r"see C:\work\proj\file.txt for details")
    assert any(f.startswith("C:") for f in fragments)


def test_detects_job_id():
    fragments = find_project_specific_fragments("Slurm job 12345678 finished with hints")
    assert any("12345678" in f for f in fragments)


def test_generic_lessons_pass():
    assert find_project_specific_fragments(
        "Before a Gaussian TS search, run a relaxed scan and save the guess geometry."
    ) == []
    assert find_project_specific_fragments(
        "When parsing a VASP OUTCAR, prefer the MAGMOM column to judge magnetism."
    ) == []


def test_empty_text_passes():
    assert find_project_specific_fragments("") == []


@pytest.mark.asyncio
async def test_update_memory_rejects_project_specific_lesson(mock_session):
    from cloudra.persistence.memory import get_memory_manager
    from cloudra.tools.Writetool.update_memory import UpdateMemory, UpdateMemory_input_schema

    tool = UpdateMemory()
    out = await tool.tool_call(
        UpdateMemory_input_schema(lesson="outputs are in /home/user/proj/result.gjf"),
        mock_session,
    )
    assert out.is_success is False
    assert "project-agnostic" in out.result
    assert "/home/user/proj/result.gjf" in out.result
    # Nothing reached the global memory file.
    assert not get_memory_manager().exists()


@pytest.mark.asyncio
async def test_update_memory_accepts_generic_lesson(mock_session):
    from cloudra.persistence.memory import get_memory_manager
    from cloudra.tools.Writetool.update_memory import UpdateMemory, UpdateMemory_input_schema

    tool = UpdateMemory()
    out = await tool.tool_call(
        UpdateMemory_input_schema(
            lesson="Run a relaxed scan before any TS search and keep the guess geometry."
        ),
        mock_session,
    )
    assert out.is_success is True
    assert "relaxed scan" in get_memory_manager().load()

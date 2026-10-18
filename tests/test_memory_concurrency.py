"""Global memory writes must survive another project's async compaction."""

import asyncio

import pytest

from cloudra.persistence.memory import MemoryManager


@pytest.mark.asyncio
async def test_compaction_keeps_lesson_saved_during_model_wait(monkeypatch):
    first = MemoryManager('first', word_limit=100)
    other = MemoryManager('other', word_limit=10000)
    first.memory_path.write_text('# Memory\n\n' + 'seed ' * 120 + '\n')
    waiting, finish = asyncio.Event(), asyncio.Event()

    async def compress(text):
        waiting.set()
        await finish.wait()
        return 'Condensed seed lessons.'

    monkeypatch.setattr(first, '_llm_compress', compress)
    task = asyncio.create_task(first.append_lesson('First project lesson.'))
    await waiting.wait()
    await other.append_lesson('Another project must remain in memory.')
    finish.set()
    await task
    assert 'Another project must remain in memory.' in first.load()
    assert 'First project lesson.' in first.memory_path.with_suffix('.archive.md').read_text()


@pytest.mark.asyncio
async def test_older_compaction_cannot_overwrite_newer_compaction(monkeypatch):
    first = MemoryManager('first', word_limit=100)
    other = MemoryManager('other', word_limit=100)
    first.memory_path.write_text('# Memory\n\n' + 'seed ' * 120 + '\n')
    waiting, finish = asyncio.Event(), asyncio.Event()

    async def delayed(text):
        waiting.set()
        await finish.wait()
        return 'Older summary.'

    async def immediate(text):
        return 'Newer summary including both projects.'

    monkeypatch.setattr(first, '_llm_compress', delayed)
    monkeypatch.setattr(other, '_llm_compress', immediate)
    task = asyncio.create_task(first.append_lesson('First project lesson.'))
    await waiting.wait()
    await other.append_lesson('Second project lesson.')
    finish.set()
    await task
    assert 'Newer summary including both projects.' in first.load()
    assert 'Older summary.' not in first.load()
    archived = first.memory_path.with_suffix('.archive.md').read_text()
    assert 'First project lesson.' in archived and 'Second project lesson.' in archived


@pytest.mark.asyncio
async def test_parallel_project_appends_preserve_every_lesson():
    managers = [MemoryManager(str(index), word_limit=10000) for index in range(8)]
    await asyncio.gather(*(manager.append_lesson(f'Lesson number {index}.')
                           for index, manager in enumerate(managers)))
    text = managers[0].load()
    assert all(f'Lesson number {index}.' in text for index in range(8))

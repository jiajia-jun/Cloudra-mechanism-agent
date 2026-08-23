"""General plugin mechanism: capability detection, event hooks, config load."""

from __future__ import annotations

import sys
import types

import pytest

from cloudra.runtime_v2 import plugins
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.knowledge import registered_providers
from cloudra.runtime_v2.plugins import (
    attach_plugins,
    clear_plugins,
    register_plugin,
    registered_plugins,
)
from cloudra.runtime_v2.schemas import EventEnvelope


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_plugins()
    yield
    clear_plugins()


class SearchOnly:
    name = "graph"

    def search(self, query, *, limit=5):
        return [{"title": "hit", "content": "c", "evidence_level": "L1"}]


class Observer:
    name = "observer"

    def __init__(self):
        self.seen: list[str] = []
        self.core = None

    def setup(self, core):
        self.core = core

    def on_event(self, envelope):
        self.seen.append(envelope.type)


class AsyncObserver:
    name = "async-observer"

    def __init__(self):
        self.seen: list[str] = []

    async def on_event(self, envelope):
        self.seen.append(envelope.type)


def _envelope(type: str = "run.finished") -> EventEnvelope:
    return EventEnvelope(
        stream="agent",
        project_id="prj",
        session_id="as_1",
        run_id="run_1",
        seq=1,
        type=type,
        data={},
    )


def test_register_detects_search_capability():
    register_plugin(SearchOnly())
    assert [p.name for p in registered_providers()] == ["graph"]
    # identity dedup
    plugin = Observer()
    register_plugin(plugin)
    register_plugin(plugin)
    assert registered_plugins().count(plugin) == 1


def test_register_requires_name():
    with pytest.raises(TypeError):
        register_plugin(object())


@pytest.mark.asyncio
async def test_attach_wires_setup_and_event_hooks():
    observer = Observer()
    async_observer = AsyncObserver()
    register_plugin(observer)
    register_plugin(async_observer)
    core = RuntimeCore(strict_events=True)
    assert attach_plugins(core) == 2
    assert observer.core is core

    await core.event_hub.publish(_envelope("run.finished"))
    assert observer.seen == ["run.finished"]
    assert async_observer.seen == ["run.finished"]


@pytest.mark.asyncio
async def test_broken_event_hook_does_not_propagate():
    class Exploding:
        name = "boom"

        def on_event(self, envelope):
            raise RuntimeError("plugin bug")

    register_plugin(Exploding())
    register_plugin(Observer())
    core = RuntimeCore(strict_events=True)
    attach_plugins(core)
    # EventHub isolates subscriber failures; the second plugin still runs.
    await core.event_hub.publish(_envelope())
    assert len(registered_plugins()) == 2


def test_import_plugin_instance_and_factory(monkeypatch):
    module = types.ModuleType("fake_plugin")
    module.plugin = Observer()
    monkeypatch.setitem(sys.modules, "fake_plugin", module)
    assert plugins._import_plugin("fake_plugin").name == "observer"

    module2 = types.ModuleType("fake_plugin2")
    module2.get_plugin = lambda: SearchOnly()
    monkeypatch.setitem(sys.modules, "fake_plugin2", module2)
    assert plugins._import_plugin("fake_plugin2").name == "graph"

    with pytest.raises(ValueError):
        plugins._import_plugin("json")  # no plugin attribute


def test_load_plugins_from_config(monkeypatch):
    module = types.ModuleType("cfg_plugin")
    module.plugin = SearchOnly()
    monkeypatch.setitem(sys.modules, "cfg_plugin", module)
    from cloudra.infra.config import get_config

    monkeypatch.setattr(get_config(), "plugins", ["cfg_plugin", "nonexistent_module_xyz"])
    loaded = plugins.load_plugins_from_config()
    assert loaded == 1  # the bad spec is skipped, not fatal
    assert registered_plugins()[0].name == "graph"
    assert [p.name for p in registered_providers()] == ["graph"]

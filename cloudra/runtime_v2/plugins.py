"""General plugin mechanism for runtime_v2.

A plugin is any object with a ``name``; all hooks are optional, so a plugin
shapes itself by which hooks it implements:

- ``search(query, *, limit)`` — knowledge/library provider: its entries ride
  back in ``agent_hub`` search results (see ``knowledge.py``).
- ``on_event(envelope)`` — event observer: receives every event the hub
  publishes (including transient ones like ``llm.chunk`` — filter what you
  need).  This is the generic reactive surface: key-node triggers, custom
  analytics, plugin-side store maintenance.  Never raises into the core —
  hub subscribers are error-isolated, and sync hooks are offloaded to a
  worker thread so they cannot block the event loop.
- ``setup(core)`` — called once at attach time with the RuntimeCore: the
  plugin gets a CommandBus (``context.inject`` for passive injection,
  ``agent.message`` for wakeups) and read access to live state.

The core never writes to plugin stores (no self-evolution): maintenance is
the plugin's own business, driven by ``on_event`` or external schedulers.

Registration: in-process via ``register_plugin`` / ``attach_plugins(core)``,
or declaratively through the ``plugins`` config list (``"pkg.module:attr"``
— attr is a plugin instance or a zero-arg factory), loaded and attached at
app startup.  Out-of-process plugins skip all of this and simply use the
HTTP API (``/context/inject``, ``/messages``, SSE event stream).
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
from typing import Any, Protocol, runtime_checkable

from cloudra.runtime_v2.knowledge import register_knowledge_provider

logger = logging.getLogger("runtime_v2.plugins")


@runtime_checkable
class CloudraPlugin(Protocol):
    name: str


_plugins: list[Any] = []


def register_plugin(plugin: Any) -> None:
    """Register a plugin instance (idempotent by identity)."""
    if not getattr(plugin, "name", None):
        raise TypeError(f"plugin {plugin!r} has no name")
    if any(existing is plugin for existing in _plugins):
        return
    _plugins.append(plugin)
    # Capability detection: a plugin with search() is also a library provider.
    if hasattr(plugin, "search"):
        register_knowledge_provider(plugin)


def registered_plugins() -> tuple[Any, ...]:
    return tuple(_plugins)


def clear_plugins() -> None:
    """Drop all registrations (test isolation).  Also clears the knowledge
    provider registry, since search-capable plugins land there."""
    from cloudra.runtime_v2.knowledge import clear_knowledge_providers

    _plugins.clear()
    clear_knowledge_providers()


def attach_plugins(core: Any) -> int:
    """Wire registered plugins into a live core.  Returns the attach count.

    - ``setup(core)`` is called immediately (sync or async def — async hooks
      must be awaited, so this runs inside ``create_default_v2_app`` where an
      event loop is available; a sync setup runs inline).
    - ``on_event`` is subscribed to the event hub, wrapped so sync hooks run
      in a worker thread and awaitables are awaited.
    """
    attached = 0
    for plugin in list(_plugins):
        setup = getattr(plugin, "setup", None)
        if callable(setup):
            try:
                result = setup(core)
                if inspect.isawaitable(result):
                    # setup() async hooks are rare; run them as a task so
                    # attach stays synchronous for the app factory.
                    asyncio.get_running_loop().create_task(result)
            except Exception:
                logger.exception("plugin %s setup failed", plugin.name)
        on_event = getattr(plugin, "on_event", None)
        if callable(on_event):
            core.event_hub.subscribe(_make_safe_handler(plugin, on_event))
        attached += 1
    if attached:
        logger.info("attached %d plugin(s)", attached)
    return attached


def _make_safe_handler(plugin: Any, on_event):
    async def handler(envelope) -> None:
        if asyncio.iscoroutinefunction(on_event):
            await on_event(envelope)
        else:
            await asyncio.to_thread(on_event, envelope)

    return handler


def load_plugins_from_config() -> int:
    """Import plugins listed in ``CloudraConfig.plugins``.

    Each spec is ``"pkg.module:attr"``; attr is a plugin instance or a
    zero-arg factory.  A failing spec is logged and skipped — plugin
    problems must never block app startup.
    """
    from cloudra.infra.config import get_config

    loaded = 0
    for spec in get_config().plugins:
        try:
            register_plugin(_import_plugin(str(spec)))
            loaded += 1
        except Exception:
            logger.exception("failed to load plugin %s", spec)
    return loaded


def _import_plugin(spec: str) -> Any:
    module_name, _, attr = spec.partition(":")
    module = importlib.import_module(module_name)
    target = getattr(module, attr) if attr else None
    if target is None:
        # Convention fallback: plugin instance or get_plugin() factory.
        target = getattr(module, "plugin", None) or getattr(module, "get_plugin", None)
    if target is None:
        raise ValueError(f"{spec!r}: no plugin attribute found")
    plugin = target() if callable(target) and not _looks_like_plugin(target) else target
    if not getattr(plugin, "name", None):
        raise TypeError(f"{spec!r}: object has no name")
    return plugin


def _looks_like_plugin(obj: Any) -> bool:
    return bool(getattr(obj, "name", None))

"""Ledger scope shared by synchronous TS workers and propagated by to_thread."""
from contextlib import contextmanager
from contextvars import ContextVar

from cloudra.persistence.database import ComputeDB

_current_ledger: ContextVar[ComputeDB | None] = ContextVar('ts_pipeline_ledger', default=None)


def pipeline_database() -> ComputeDB:
    return _current_ledger.get() or ComputeDB()


@contextmanager
def use_pipeline_database(db: ComputeDB):
    token = _current_ledger.set(db)
    try:
        yield db
    finally:
        _current_ledger.reset(token)


# The resolver is constructed by runtime code, never read from a tool argument.
# Resolving at every submit also observes revoked producer permissions/policies.
_current_authority: ContextVar[object | None] = ContextVar('ts_pipeline_authority', default=None)


@contextmanager
def use_pipeline_authority(resolver):
    token = _current_authority.set(resolver)
    try:
        yield
    finally:
        _current_authority.reset(token)


def require_pipeline_producer(project_id, owner_session_id):
    resolver = _current_authority.get()
    if resolver is None:
        raise ValueError('TS producer authorization source is unavailable')
    allowed, policy = resolver(project_id, owner_session_id)
    if not allowed:
        raise ValueError('Current TS owner lacks producer write permission')
    return policy


def require_pipeline_authority(project_id, owner_session_id):
    policy = require_pipeline_producer(project_id, owner_session_id)
    if policy is None:
        raise ValueError('Trusted TS method authorization is missing; configure the project MethodPolicy')
    return policy


@contextmanager
def use_runtime_authority(core):
    def resolve(project_id, owner_session_id):
        agent = core.agents.get(owner_session_id)
        project = core.projects.get(project_id)
        allowed = bool(agent and project and agent.project_id == project_id and agent.capabilities.permissions.write)
        return allowed, project.settings.method_policy if project else None
    with use_pipeline_authority(resolve):
        yield

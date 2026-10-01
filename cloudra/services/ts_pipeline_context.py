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

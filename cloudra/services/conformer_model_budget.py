"""Account physical provider requests during a scoped conformer decision turn."""
from __future__ import annotations

import asyncio
import uuid

from cloudra.persistence.database import ComputeDB
from cloudra.services.exploration_budget_store import (
    ActualCost,
    CostEstimate,
    release_unbound_actions,
    reserve_actions,
    settle_action,
)


class ModelRequestAccounting:
    def __init__(self, db: ComputeDB, process_ids: list[str]):
        self.db = db
        self.process_ids = process_ids
        self.call_id = uuid.uuid4().hex
        self.attempts: list[tuple[str, list[str]]] = []
        self.pending: list[tuple[str, list[str]]] = []

    @classmethod
    async def for_agent(cls, db: ComputeDB, project_id: str, owner_id: str):
        def scopes():
            import json
            with db.connect() as con:
                rows = con.execute('SELECT p.process_id,p.record FROM ts_pipeline_processes p '
                    'JOIN exploration_budgets b ON b.process_id=p.process_id '
                    'WHERE p.project_id=? AND p.owner_id=? AND p.status IN (?,?)',
                    (project_id, owner_id, 'blocked','failed')).fetchall()
            selected=[]
            for pid,record in rows:
                data=json.loads(record) if record else {}
                limits = data.get('input', {}).get('execution', {}).get('limits') or {}
                if (data.get('format_version') == 7 and (data.get('catalog_id') or limits.get('max_model_calls') is not None)
                        and (data.get('blocked') or data.get('terminal') in ('candidate_only','search_failed','invalid_input'))):
                    selected.append(pid)
            return selected
        processes = await asyncio.to_thread(scopes)
        return cls(db, processes) if processes else None

    async def before_request(self):
        key = f'model:{self.call_id}:{len(self.attempts)}'
        accepted = []
        def reserve():
            try:
                for pid in self.process_ids:
                    reserve_actions(self.db, process_id=pid, decision_id=key, estimates=[
                        CostEstimate(action_key=key, action_kind='model', source='runtime_provider_request')])
                    accepted.append(pid)
            except BaseException:
                for pid in accepted:
                    release_unbound_actions(self.db, process_id=pid, action_keys=[key],
                                            reason='Request not sent: another scoped budget rejected admission')
                raise
        await asyncio.to_thread(reserve)
        attempt = (key, accepted)
        self.attempts.append(attempt)
        self.pending.append(attempt)
        return attempt

    async def failed_request(self, attempt):
        await self._settle(attempt, False, None)
        self.pending.remove(attempt)

    async def _settle(self, attempt, success, tokens):
        key, processes = attempt
        actual = ActualCost(terminal_state='done' if success else 'failed',
            measurement_source='runtime_provider_request;tokens_from_provider_usage_if_available',
            model_calls=1, model_tokens=tokens)
        for pid in processes:
            await asyncio.to_thread(settle_action, self.db, process_id=pid, action_key=key, actual=actual)

    async def finish(self, *, success: bool, usage: dict | None):
        tokens = (usage or {}).get('total_tokens')
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
            tokens = None
        for index, attempt in enumerate(self.pending):
            await self._settle(attempt, success, tokens if index == len(self.pending)-1 else None)
        self.pending.clear()

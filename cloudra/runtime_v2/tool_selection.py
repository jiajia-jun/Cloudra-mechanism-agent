"""One bounded document choice, independent from executable authority."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictInt

from cloudra.infra.config import ToolDocumentLoadingConfig
from cloudra.runtime_v2.event_writer import EventPersistenceError
from cloudra.runtime_v2.schemas import AgentSession, RuntimeSettings
from cloudra.tools.documentation import ToolCapabilitySummary, catalog_revision, validate_tool_names


class ToolSelectionResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['selected', 'empty', 'failed']
    names: tuple[str, ...] = ()
    source: Literal['llm', 'jev', 'reranker']
    catalog_revision: str
    error_code: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0


class ToolSelectionRecord(ToolSelectionResult):
    status: Literal['started', 'selected', 'empty', 'failed']
    selection_id: str
    task_message_ids: tuple[str, ...] = ()
    model: str = ''
    document_revisions: dict[str, str] = Field(default_factory=dict)


class _Noul(BaseModel):
    model_config = ConfigDict(strict=True)
    noul: FiniteFloat = Field(ge=0, le=1)


class _Rank(BaseModel):
    model_config = ConfigDict(strict=True)
    index: StrictInt
    relevance_score: FiniteFloat


class _JevResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    answers: dict[str, _Noul]
    usage: dict[str, Any] = Field(default_factory=dict)


class _RerankResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    results: list[_Rank]
    usage: dict[str, Any] = Field(default_factory=dict)


def task_text(messages: list[dict]) -> str:
    parts = []
    for message in messages:
        content = message.get('content', '')
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    raise ValueError('Malformed task content')
                if part.get('type') == 'text':
                    parts.append(str(part.get('text', '')))
                elif part.get('type') in ('image_ref', 'image_url', 'image'):
                    parts.append('[An image is supplied for this task.]')
        else:
            raise ValueError('Malformed task content')
    return '\n'.join(parts)


class ToolDocumentSelector:
    def __init__(self, llm, *, transport: httpx.AsyncBaseTransport | None = None):
        self.llm = llm
        self.transport = transport

    async def select(self, *, agent: AgentSession, task_messages: list[dict],
            resolved_settings: RuntimeSettings, candidates: tuple[ToolCapabilitySummary, ...],
            config: ToolDocumentLoadingConfig) -> ToolSelectionResult:
        source = 'llm' if config.strategy == 'llm' else config.semantic_backend
        revision = catalog_revision(candidates)
        started = time.monotonic()
        usage = {}
        try:
            task = task_text(task_messages)
            names = [candidate.name for candidate in candidates]
            if not task.strip() or not candidates:
                selected = ()
            elif source == 'llm':
                directory = '\n'.join(f'- {item.name}: {item.summary}' for item in candidates)
                response = await asyncio.wait_for(self.llm.select_tool_names(agent, [
                    {'role':'system','content': 'Select tool documentation useful for the initial task. '
                        'Return only a JSON array of exact tool names, or []. Do not execute tools, '
                        'choose scientific methods or generate documentation.\nAvailable tools:\n'+directory},
                    {'role':'user','content':task}], resolved_settings=resolved_settings), timeout=resolved_settings.timeout or 300)
                usage = response.usage
                if response.tool_calls:
                    raise ValueError('Selection response attempted tool execution')
                selected = validate_tool_names(json.loads(response.content), allowed_names=names)
            else:
                selected, usage = await asyncio.wait_for(self._semantic(task, candidates, config, source),
                    timeout=resolved_settings.timeout or 300)
                selected = validate_tool_names(list(selected), allowed_names=names)
            return ToolSelectionResult(status='selected' if selected else 'empty', names=selected,
                source=source, catalog_revision=revision, usage=usage,
                duration_ms=int((time.monotonic()-started)*1000))
        except asyncio.CancelledError:
            raise
        except EventPersistenceError:
            raise
        except Exception as exc:
            return ToolSelectionResult(status='failed', source=source, catalog_revision=revision,
                error_code=type(exc).__name__, usage=usage, duration_ms=int((time.monotonic()-started)*1000))

    async def _semantic(self, task, candidates, config, source):
        backend = getattr(config, source)
        headers = {'Authorization': f'Bearer {backend.key}'} if backend.key else {}
        if source == 'jev':
            payload = {'model':backend.model, 'state':{'task':task}, 'questions':{
                item.name: {'type':'noul', 'instructions': 'Would this tool documentation help complete the current task? '
                    f'Tool {item.name}: {item.summary}'} for item in candidates}}
        else:
            payload = {'model':backend.model,'query':task,
                'documents':[f'Tool {item.name}: {item.summary}' for item in candidates]}
        async with httpx.AsyncClient(transport=self.transport, timeout=30) as client:
            response = await client.post(backend.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        if source == 'jev':
            envelope = _JevResponse.model_validate(data)
            answers = envelope.answers
            if set(answers) != {item.name for item in candidates}:
                raise ValueError('Incomplete Jev answers')
            ranked = [(index, answers[item.name].noul) for index,item in enumerate(candidates)]
            boundary = backend.min_probability
        else:
            envelope = _RerankResponse.model_validate(data)
            rows = envelope.results
            if len(rows) != len(candidates) or {row.index for row in rows} != set(range(len(candidates))):
                raise ValueError('Reranker indices must cover all candidates exactly once')
            ranked = [(row.index, row.relevance_score) for row in rows]
            boundary = backend.min_score
        ranked.sort(key=lambda item: (-item[1], item[0]))
        selected = [candidates[index].name for index,score in ranked if score >= boundary]
        if backend.max_tools is not None:
            selected = selected[:backend.max_tools]
        return tuple(selected), envelope.usage

"""Source-backed tool contracts; document selection never grants authority."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictStr, TypeAdapter

from cloudra.tools import ToolEntry

_NAMES = TypeAdapter(list[StrictStr])


class ToolCapabilitySummary(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    name: str
    summary: str


class ToolDocReference(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    skill_name: str
    reference: str


class ToolDocument(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    name: str
    revision: str
    content: str
    references: tuple[ToolDocReference, ...] = ()


def validate_tool_names(value: Any, *, allowed_names: Collection[str]) -> tuple[str, ...]:
    names = _NAMES.validate_python(value, strict=True)
    invalid = [name for name in names if name not in allowed_names]
    if invalid:
        raise ValueError(f'Unknown or unavailable tool names: {invalid}')
    return tuple(dict.fromkeys(names))


def tool_capability_summaries(names: Sequence[str], *, entries: Sequence[ToolEntry]) -> tuple[ToolCapabilitySummary, ...]:
    by_name = {entry.tool_name: entry for entry in entries}
    selected = validate_tool_names(list(names), allowed_names=by_name)
    result = []
    for name in sorted(selected):
        summary = by_name[name].summary
        if not summary.strip():
            raise ValueError(f'Tool {name!r} has no capability summary')
        result.append(ToolCapabilitySummary(name=name, summary=summary))
    return tuple(result)


def catalog_revision(summaries: Sequence[ToolCapabilitySummary]) -> str:
    payload = [item.model_dump(mode='json') for item in summaries]
    return _digest(payload)


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return 'sha256:' + hashlib.sha256(encoded).hexdigest()


def build_tool_documents(names: Sequence[str], *, allowed_names: Collection[str], entries: Sequence[ToolEntry]) -> tuple[ToolDocument, ...]:
    from cloudra.runtime_v2.tool_catalog import render_tool_declaration

    selected = validate_tool_names(list(names), allowed_names=allowed_names)
    by_name = {entry.tool_name: entry for entry in entries}
    validate_tool_names(list(selected), allowed_names=by_name)
    documents = []
    for name in selected:
        entry = by_name[name]
        refs = tuple(ToolDocReference(skill_name=skill, reference=reference)
                     for skill, reference in entry.skill_references)
        revision = _digest({'name': name, 'summary': entry.summary, 'description': entry.tool_description,
            'input': entry.input_schema.model_json_schema(), 'output': entry.output_schema.model_json_schema(),
            'references': [ref.model_dump() for ref in refs]})
        content = (f'# {name}\n\n{entry.tool_description}\n\n'
            f'## Input and result contract\n\n```typescript\n{render_tool_declaration(entry)}\n```\n\n'
            '## Calling pattern\n\nConstruct args from the contract and the actual task declarations. '
            'This pattern does not supply scientific methods or other task inputs.\n\n'
            f'```javascript\nconst r = await tools.{name}(args);\n'
            'if (r.is_success) text(r.data); else text(r.summary);\n```')
        documents.append(ToolDocument(name=name, revision=revision, content=content, references=refs))
    return tuple(documents)


def compact_document_outputs(outputs: Sequence[Any], documents: Sequence[dict]) -> list[Any]:
    """Replace only exact documents returned by a completed host reader."""
    def compact(value):
        for document in documents:
            if value == document or (isinstance(value, str) and value == document['content']):
                return {'tool_document':document['name'], 'revision':document['revision'],
                    'reload':'get_tool_docs'}
        if isinstance(value, list):
            return [compact(item) for item in value]
        if isinstance(value, dict):
            return {key:compact(item) for key,item in value.items()}
        return value
    return [compact(value) for value in outputs]

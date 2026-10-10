"""Tool documents must preserve contracts without expanding authority."""
import importlib
import importlib.util
from dataclasses import replace
from typing import Literal

import pytest
from pydantic import Field

from cloudra.base.tools_class import input_schema, output_schema
from cloudra.tools import ToolEntry


def docs():
    assert importlib.util.find_spec('cloudra.tools.documentation') is not None, 'Tool documentation API is missing'
    return importlib.import_module('cloudra.tools.documentation')


class Args(input_schema):
    mode: Literal['inspect', 'revise']
    atoms: tuple[int, int] = Field(description='Current structure atom order, 1-based.')
    expected_revision: int | None = Field(default=None, ge=0)


class Result(output_schema):
    is_success: bool = True
    verified: bool = False


def entry(name='inspect', **kwargs):
    return ToolEntry(cls=object, tool_name=name, tool_id=name,
        input_schema=Args, output_schema=Result,
        tool_description='Read current state without advancing a workflow.',
        summary='Inspect current state and missing inputs.', **kwargs)


@pytest.mark.parametrize('invalid', ['inspect', [1], [True], ['inspect', 'hidden'], ['*'], [' inspect']])
def test_invalid_selection_is_rejected_as_a_whole(invalid):
    with pytest.raises(ValueError):
        docs().validate_tool_names(invalid, allowed_names={'inspect'})


def test_empty_and_duplicate_selection_do_not_expand_names():
    mod = docs()
    assert mod.validate_tool_names([], allowed_names={'inspect'}) == ()
    assert mod.validate_tool_names(['inspect', 'inspect'], allowed_names={'inspect'}) == ('inspect',)


def test_summaries_are_sorted_without_full_contracts():
    mod = docs()
    summaries = mod.tool_capability_summaries(['revise', 'inspect'], entries=[entry('revise'), entry()])
    assert [(x.name, x.summary) for x in summaries] == [
        ('inspect', 'Inspect current state and missing inputs.'),
        ('revise', 'Inspect current state and missing inputs.')]


def test_document_preserves_actual_input_and_output_contract():
    mod = docs()
    document, = mod.build_tool_documents(['inspect'], allowed_names={'inspect'}, entries=[entry()])
    assert document.name == 'inspect'
    assert '[number, number]' in document.content
    assert 'expected_revision' in document.content
    assert '"inspect" | "revise"' in document.content
    assert '1-based' in document.content
    assert 'verified' in document.content
    assert 'await tools.inspect(args)' in document.content


def test_revision_changes_when_contract_description_or_reference_changes():
    mod = docs()
    original = entry()
    def revision(e):
        return mod.build_tool_documents(['inspect'], allowed_names={'inspect'}, entries=[e])[0].revision
    assert revision(original) == revision(original)
    assert revision(original) != revision(replace(original, tool_description='Different operation.'))
    assert revision(original) != revision(replace(original, skill_references=(('dft', 'guide.md'),)))
    class ChangedArgs(Args):
        reason: str
    assert revision(original) != revision(replace(original, input_schema=ChangedArgs))


def test_hidden_document_is_never_partially_returned():
    with pytest.raises(ValueError):
        docs().build_tool_documents(['inspect', 'hidden'], allowed_names={'inspect'}, entries=[entry(), entry('hidden')])

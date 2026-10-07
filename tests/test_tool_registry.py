"""The manifest loader rejects ambiguous or unusable tool implementations."""

import sys
from typing import Any

import pytest
from pydantic import create_model

import cloudra.tools as tools
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.tools.registry import ToolRegistration


class RegistryProbe(Tool):
    tool_id: str = "registry-probe"
    tool_name: str = "registry_probe"

    async def tool_call(self, user_input, session):
        return output_schema()


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    monkeypatch.setattr(tools, "TOOL_REGISTRY", ())
    monkeypatch.setattr(tools, "_TOOL_ENTRIES_CACHE", None)


def _manifest(monkeypatch, cls, *, name="registry_probe"):
    monkeypatch.setattr(sys.modules[__name__], "ManifestProbe", cls, raising=False)
    monkeypatch.setattr(tools, "TOOL_REGISTRY", (
        ToolRegistration(__name__, "ManifestProbe", tool_name=name),
    ))


@pytest.mark.parametrize("field", ["tool_name", "tool_id"])
def test_loader_rejects_duplicate_identity_and_can_reload_after_correction(monkeypatch, field):
    identities = {"tool_name": "second_probe", "tool_id": "second-probe"}
    identities[field] = RegistryProbe.model_fields[field].default
    second = create_model(
        "SecondProbe", __base__=RegistryProbe,
        **{name: (str, value) for name, value in identities.items()},
    )
    monkeypatch.setattr(sys.modules[__name__], "SecondProbe", second, raising=False)
    monkeypatch.setattr(tools, "TOOL_REGISTRY", (
        ToolRegistration(__name__, "RegistryProbe", tool_name="registry_probe"),
        ToolRegistration(__name__, "SecondProbe", tool_name=identities["tool_name"]),
    ))

    with pytest.raises(RuntimeError) as error:
        tools.get_tools_lst()
    assert field in str(error.value)
    _manifest(monkeypatch, RegistryProbe)
    assert [entry.tool_name for entry in tools.get_tools_lst()] == ["registry_probe"]


@pytest.mark.parametrize("field", ["tool_name", "tool_id"])
@pytest.mark.parametrize("value", ["", "   ", ...])
def test_loader_requires_nonempty_identity_defaults(monkeypatch, field, value):
    invalid = create_model("InvalidIdentity", __base__=RegistryProbe, **{field: (str, value)})
    _manifest(monkeypatch, invalid)

    with pytest.raises(RuntimeError) as error:
        tools.get_tools_lst()
    assert field in str(error.value)


@pytest.mark.parametrize("field", ["input_schema", "output_schema"])
@pytest.mark.parametrize("value", [None, dict, ...])
def test_loader_rejects_missing_or_nonmodel_schema_classes(monkeypatch, field, value):
    invalid = create_model("InvalidSchema", __base__=RegistryProbe, **{field: (Any, value)})
    _manifest(monkeypatch, invalid)

    with pytest.raises(RuntimeError) as error:
        tools.get_tools_lst()
    assert field in str(error.value)


@pytest.mark.parametrize("field,value", [
    ("input_schema", input_schema()),
    ("output_schema", output_schema()),
])
def test_loader_rejects_schema_instances(monkeypatch, field, value):
    invalid = create_model("SchemaInstance", __base__=RegistryProbe, **{field: (Any, value)})
    _manifest(monkeypatch, invalid)

    with pytest.raises(RuntimeError) as error:
        tools.get_tools_lst()
    assert field in str(error.value)


def test_loader_rejects_non_tool_class(monkeypatch):
    _manifest(monkeypatch, object)
    with pytest.raises(RuntimeError):
        tools.get_tools_lst()


def test_builtin_declared_name_must_match_the_implementation(monkeypatch):
    _manifest(monkeypatch, RegistryProbe, name="different_wire_name")

    with pytest.raises(RuntimeError) as error:
        tools.get_tools_lst()
    assert "different_wire_name" in str(error.value)
    assert "registry_probe" in str(error.value)

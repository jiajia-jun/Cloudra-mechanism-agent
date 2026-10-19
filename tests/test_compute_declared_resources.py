"""Native resource declarations must reach real admission and ledger reservations."""

import importlib
import json
from types import SimpleNamespace

import pytest

from cloudra.services.compute_admission import _read_declared_requirements, admit_job

submit = importlib.import_module("cloudra.tools.Chemtool.submit_compute_job")


@pytest.fixture
def submit_boundary(tmp_path, monkeypatch):
    """Replace only external effects; run the actual submit and admission code."""
    records = []
    resources = {"cpus": 64, "memory_mb": 65536, "max_concurrent": 16}
    node = SimpleNamespace(node_id="resource-node", scheduler={"type": "local"}, connection={})

    class Ledger:
        async def ainit(self):
            return self

    async def insert(db, **record):
        assert isinstance(db, Ledger)
        records.append(record)
        return len(records)

    async def progress(_event):
        pass

    monkeypatch.setattr(submit, "ComputeDB", Ledger)
    monkeypatch.setattr(submit, "ainsert_compute_job", insert)
    monkeypatch.setattr("cloudra.runtime_v2.invocation_context.report_tool_progress", progress)
    monkeypatch.setattr("cloudra.services.compute_admission._route_node", lambda _path: (node, ""))
    monkeypatch.setattr("cloudra.services.compute_admission.check_job_type", lambda *_args: (True, ""))
    monkeypatch.setattr("cloudra.services.host_capacity.effective_node_resources", lambda _node: dict(resources))
    tool = submit.SubmitComputeJob(subagent=SimpleNamespace(
        working_directory=str(tmp_path), conversation_id="resource-regression",
    ))
    return tool, records, resources, node


@pytest.mark.asyncio
@pytest.mark.parametrize(("engine", "declarations", "expected"), [
    ("orca", "! HF STO-3G PAL8\n%maxcore 1024\n", (8, 8192)),
    ("orca", "! HF STO-3G\n%maxcore 8192\n", (1, 8192)),
    ("orca", "! HF STO-3G\n%pal\n nprocs 8\nend\n%maxcore 1024\n", (8, 8192)),
    ("orca", "! HF STO-3G\n%pal# comment\n nprocs 8\nend\n%maxcore 1024\n", (8, 8192)),
    ("orca", "! HF STO-3G\n%pal nprocs 8 end %maxcore 1024\n", (8, 8192)),
    ("gaussian", "%nprocshared=8\n%mem=1000MW\n", (8, 8000)),
    ("gaussian", "%nprocshared = 8\n%mem = 8 GB\n", (8, 8192)),
])
async def test_submit_reserves_native_total_resources(tmp_path, submit_boundary, engine, declarations, expected):
    tool, records, _resources, _node = submit_boundary
    path = tmp_path / ("he.gjf" if engine == "gaussian" else "he.inp")
    path.write_text(declarations)
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=path.name, job_type=engine, is_async=True,
    ), None)
    assert result.is_success, result.message
    assert (records[0]["req_cpus"], records[0]["req_memory_mb"]) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(("allocation", "diagnostic"), [
    ({"cpus": 1}, "8 cores"),
    ({"memory_mb": 1}, "8192 MB total"),
])
async def test_submit_rejects_explicit_underreservation(tmp_path, submit_boundary, allocation, diagnostic):
    tool, records, _resources, _node = submit_boundary
    (tmp_path / "he.inp").write_text("! HF STO-3G PAL8\n%maxcore 1024\n")
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file="he.inp", job_type="orca", is_async=True, **allocation,
    ), None)
    assert not result.is_success
    assert diagnostic in result.message
    assert records == []


@pytest.mark.asyncio
async def test_native_total_memory_is_checked_against_node_capacity(tmp_path, submit_boundary):
    tool, records, resources, _node = submit_boundary
    resources["memory_mb"] = 4096
    (tmp_path / "he.inp").write_text("! HF STO-3G PAL8\n%maxcore 1024\n")
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file="he.inp", job_type="orca", is_async=True,
    ), None)
    assert not result.is_success
    assert "8192" in result.message and "capacity" in result.message
    assert records == []


@pytest.mark.parametrize(("declaration", "expected"), [
    ("%mem=8MB", 8), ("%mem=1.25MB", 2), ("%mem=1024KB", 1),
    ("%mem=1MW", 8), ("%mem=128KW", 1), ("%mem=1GW", 8192),
    ("%mem=1048576", 8),
])
def test_gaussian_memory_units_are_complete_and_rounded_up(tmp_path, declaration, expected):
    path = tmp_path / "he.gjf"
    path.write_text(declaration + "\n# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n")
    assert _read_declared_requirements("gaussian", str(path))[1] == expected


@pytest.mark.parametrize(("engine", "declarations"), [
    ("orca", "! PAL8\n%pal nprocs 2 end\n%maxcore 1024\n"),
    ("orca", "%pal nprocs 8 end\n%pal nprocs 2 end\n"),
    ("orca", "%maxcore 8192\n%maxcore 1\n"),
    ("orca", "%pal nprocs 0 end\n"),
    ("orca", "%pal nprocs eight end\n"),
    ("orca", "%pal nprocs 8\n"),
    ("orca", "%maxcore 1024oops\n"),
    ("gaussian", "%nprocshared=8\n%nproc=2\n"),
    ("gaussian", "%mem=8GB\n%mem=1MB\n"),
    ("gaussian", "%mem=1000MWjunk\n"),
    ("gaussian", "%mem=0GB\n"),
    ("gaussian", "%mem=1 2MB\n"),
])
@pytest.mark.asyncio
async def test_invalid_or_conflicting_resources_fail_before_ledger(
    tmp_path, submit_boundary, engine, declarations,
):
    tool, records, _resources, _node = submit_boundary
    path = tmp_path / "invalid.inp"
    path.write_text(declarations)
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=path.name, job_type=engine, is_async=True,
    ), None)
    assert not result.is_success
    assert "resource" in result.message.lower()
    assert records == []
    outcome = admit_job(input_file=str(path), job_type=engine, cpus=64, memory_mb=65536)
    assert not outcome.ok
    assert "resource" in outcome.message.lower()


def test_orca_comments_and_quoted_native_options_do_not_declare_resources(tmp_path):
    path = tmp_path / "he.inp"
    path.write_text(
        "# ! PAL64\n! HF STO-3G PAL8 # PAL64\n"
        '%method\n Ext_Params "--note %pal nprocs 64 %maxcore 99999"\nend\n'
        "%pal nprocs 8 end\n%maxcore 1024 # %maxcore 99999\n"
    )
    assert _read_declared_requirements("orca", str(path)) == (8, 8192)


def test_gaussian_title_and_geometry_do_not_declare_resources(tmp_path):
    path = tmp_path / "he.gjf"
    path.write_text("# HF/STO-3G\n\n%mem=500GB\n\n0 1\nHe 0 0 0\n\n")
    assert _read_declared_requirements("gaussian", str(path)) == (None, None)


def test_unknown_native_option_strings_are_outside_resource_validation(tmp_path):
    path = tmp_path / "he.inp"
    path.write_text('%method Ext_Params "unclosed scientific option\nend\n%maxcore 1024\n')
    assert _read_declared_requirements("orca", str(path)) == (None, 1024)


def test_unknown_simple_option_strings_are_outside_resource_validation(tmp_path):
    path = tmp_path / "he.inp"
    path.write_text('! HF PAL8 "unclosed scientific option\n%maxcore 1024\n')
    assert _read_declared_requirements("orca", str(path)) == (8, 8192)


@pytest.mark.parametrize("declarations", [
    '%pal nprocs 8 end %scf Extra "unclosed scientific option\n%maxcore 1024\n',
    '%pal nprocs 8 end\n%maxcore 1024 %scf Extra "unclosed scientific option\n',
])
@pytest.mark.asyncio
async def test_complete_resource_declarations_allow_malformed_scientific_suffix(
    tmp_path, submit_boundary, declarations,
):
    tool, records, _resources, _node = submit_boundary
    path = tmp_path / "he.inp"
    path.write_text(declarations)
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=path.name, job_type="orca", is_async=True,
    ), None)
    assert result.is_success, result.message
    assert (records[0]["req_cpus"], records[0]["req_memory_mb"]) == (8, 8192)


@pytest.mark.parametrize("declarations", [
    '%pal nprocs "unclosed\n',
    '%pal nprocs 8 "unclosed\n',
    '%maxcore "unclosed\n',
])
def test_incomplete_resource_declarations_remain_errors(tmp_path, declarations):
    path = tmp_path / "he.inp"
    path.write_text(declarations)
    with pytest.raises(ValueError, match="resource declaration"):
        _read_declared_requirements("orca", str(path))


@pytest.mark.asyncio
async def test_slurm_allocation_matches_native_reservation(tmp_path, submit_boundary, monkeypatch):
    tool, records, _resources, node = submit_boundary
    node.scheduler = {"type": "slurm"}
    monkeypatch.setattr("cloudra.infra.slurm.check_slurm_tools", lambda: (True, ""))
    (tmp_path / "he.inp").write_text("! HF STO-3G PAL8\n%maxcore 1024\n")
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file="he.inp", job_type="orca", is_async=True,
    ), None)
    assert result.is_success, result.message
    options = json.loads(records[0]["scheduler_options"])
    assert options["cpus"] == records[0]["req_cpus"] == 8
    assert options["memory"] == f"{records[0]['req_memory_mb']}M" == "8192M"


@pytest.mark.asyncio
async def test_sequential_gaussian_link1_reserves_each_resource_peak(tmp_path, submit_boundary):
    tool, records, _resources, _node = submit_boundary
    (tmp_path / "he.gjf").write_text(
        "%nprocshared=8\n%mem=1GB\n# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n"
        "--Link1--\n%nprocshared=2\n%mem=8GB\n# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n"
    )
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file="he.gjf", job_type="gaussian", is_async=True,
    ), None)
    assert result.is_success, result.message
    assert (records[0]["req_cpus"], records[0]["req_memory_mb"]) == (8, 8192)


@pytest.mark.parametrize(("declarations", "expected"), [
    ('! HF PAL8\n%maxcore 128\n$new_job\n! HF PAL2\n%maxcore 4096\n', (8, 8192)),
    ('! HF PAL2\n%maxcore 512\n$new_job\n! HF PAL8\n', (8, 4096)),
    ('! HF PAL8\n%maxcore 128\n$new_job # next job\n%maxcore 1024\n', (8, 8192)),
])
@pytest.mark.asyncio
async def test_sequential_orca_jobs_reserve_each_effective_resource_peak(
    tmp_path, submit_boundary, declarations, expected,
):
    tool, records, _resources, _node = submit_boundary
    (tmp_path / 'sequential.inp').write_text(declarations)
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file='sequential.inp', job_type='orca', is_async=True,
    ), None)
    assert result.is_success, result.message
    assert (records[0]['req_cpus'], records[0]['req_memory_mb']) == expected


def test_quoted_new_job_does_not_split_resource_declarations(tmp_path):
    path = tmp_path / 'he.inp'
    path.write_text('! HF PAL8\n%method Ext_Params "$new_job" end\n! HF PAL2\n')
    with pytest.raises(ValueError, match='Conflicting resource declarations'):
        _read_declared_requirements('orca', str(path))


def test_new_job_does_not_hide_unclosed_resource_block(tmp_path):
    path = tmp_path / 'he.inp'
    path.write_text('%pal nprocs 8\n$new_job\n%maxcore 1024\n')
    with pytest.raises(ValueError, match='resource declaration'):
        _read_declared_requirements('orca', str(path))

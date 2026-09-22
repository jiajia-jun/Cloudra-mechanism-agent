"""DAG test identities must retain the runtime's role capability boundaries."""

from cloudra.dag.models import OrchestrationMode
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import (
    InvocationProtocol,
    Project,
    RuntimeSettings,
)
from tests.dag_identity import make_session, projected_tool_names


def test_supervisor_test_identity_matches_live_restricted_tool_surface():
    core = RuntimeCore()
    role = core.roles.require("supervisor")
    live = core.agent_host.build(
        project=Project(id="dag-identity", name="DAG identity"),
        role=role,
        parent_session_id=None,
        display_name=None,
        settings=RuntimeSettings(
            orchestration_mode=OrchestrationMode.DAG_GUIDED,
            invocation_protocol=InvocationProtocol.TRADITIONAL,
        ),
    )
    fixture = make_session("dag-identity", "supervisor", protocol="traditional")

    assert set(fixture.capabilities.tools) == set(live.capabilities.tools)
    assert "*" not in fixture.capabilities.tools
    visible = projected_tool_names(fixture)
    assert {"dag_review_call", "read", "stop"} <= visible
    assert visible.isdisjoint(
        {"ask_user", "bash", "write", "submit_compute_job", "dag_add_species"}
    )

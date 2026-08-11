import pytest

from cloudra.services.nodes import NodeRegistry, NodeRegistryError


def test_node_registry_validates_and_resolves_workspace_routes(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    registry = NodeRegistry.from_dict(
        {
            "default_node_id": "local",
            "nodes": [
                {
                    "node_id": "local",
                    "display_name": "Local",
                    "workspaces": [
                        {"workspace_id": "default", "path": str(first)}
                    ],
                },
                {
                    "node_id": "hpc-login",
                    "display_name": "HPC",
                    "scheduler": {
                        "type": "slurm",
                        "partition": "compute",
                        "cpus": 8,
                    },
                    "workspaces": [
                        {
                            "workspace_id": "project-a",
                            "path": str(second),
                            "access": "read_only",
                        }
                    ],
                },
            ],
        }
    )

    assert registry.node(None).node_id == "local"
    route = registry.workspace("hpc-login", "project-a")
    assert route.path == second.resolve()
    assert route.access == "read_only"
    assert registry.node("hpc-login").scheduler["type"] == "slurm"
    assert "compute.slurm" in registry.node("hpc-login").capabilities
    assert {item["node_id"] for item in registry.public_nodes()} == {
        "local",
        "hpc-login",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"nodes": []},
        {
            "nodes": [
                {"node_id": "bad/id", "workspaces": [{"workspace_id": "x", "path": "."}]}
            ]
        },
        {
            "nodes": [
                {"node_id": "node", "workspaces": [{"workspace_id": "x", "path": "/definitely/missing"}]}
            ]
        },
    ],
)
def test_node_registry_rejects_invalid_or_unavailable_routes(payload):
    with pytest.raises(NodeRegistryError):
        NodeRegistry.from_dict(payload)


def test_node_capability_namespace_is_validated(tmp_path):
    payload = {
        "nodes": [
            {
                "node_id": "node-a",
                "scheduler": {"type": "slurm"},
                "capabilities": ["agent.session", "compute.local"],
                "workspaces": [{"workspace_id": "main", "path": str(tmp_path)}],
            }
        ]
    }
    with pytest.raises(NodeRegistryError, match="compute.slurm"):
        NodeRegistry.from_dict(payload)
    payload["nodes"][0]["capabilities"] = ["compute.slurm", "bad capability"]
    with pytest.raises(NodeRegistryError, match="invalid node capability"):
        NodeRegistry.from_dict(payload)

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
                        "modules": ["apps/orca/5.0.2"],
                        "environment": {"OMPI_MCA_rmaps_base_oversubscribe": "1"},
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
    assert registry.node("hpc-login").scheduler["modules"] == ["apps/orca/5.0.2"]
    assert registry.node("hpc-login").scheduler["environment"] == {
        "OMPI_MCA_rmaps_base_oversubscribe": "1"
    }
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


@pytest.mark.parametrize("modules", ["apps/orca/5.0.2", [], [""]])
def test_node_registry_rejects_invalid_scheduler_modules(tmp_path, modules):
    payload = {
        "nodes": [
            {
                "node_id": "hpc",
                "scheduler": {"type": "slurm", "modules": modules},
                "workspaces": [{"workspace_id": "main", "path": str(tmp_path)}],
            }
        ]
    }
    with pytest.raises(NodeRegistryError, match="modules"):
        NodeRegistry.from_dict(payload)


@pytest.mark.parametrize(
    "environment",
    [
        ["OMPI=value"],
        {"BAD-NAME": "1"},
        {"VALID_NAME": "line one\nline two"},
        {"VALID_NAME": 1},
    ],
)
def test_node_registry_rejects_invalid_scheduler_environment(tmp_path, environment):
    payload = {
        "nodes": [
            {
                "node_id": "hpc",
                "scheduler": {"type": "slurm", "environment": environment},
                "workspaces": [{"workspace_id": "main", "path": str(tmp_path)}],
            }
        ]
    }
    with pytest.raises(NodeRegistryError, match="environment"):
        NodeRegistry.from_dict(payload)


def _ssh_node_payload(tmp_path, connection):
    return {
        "nodes": [
            {
                "node_id": "remote-a",
                "scheduler": {"type": "slurm", "partition": "compute"},
                "connection": connection,
                "workspaces": [{"workspace_id": "staging", "path": str(tmp_path)}],
            }
        ]
    }


def test_node_registry_accepts_ssh_connection(tmp_path):
    identity = tmp_path / "id_ed25519"
    identity.write_text("placeholder", encoding="utf-8")
    registry = NodeRegistry.from_dict(
        _ssh_node_payload(
            tmp_path,
            {
                "type": "ssh",
                "host": "login.hpc.example.edu",
                "user": "cloudray",
                "port": 2222,
                "identity_file": str(identity),
                "remote_root": "/scratch/cloudray/cloudra/",
            },
        )
    )

    connection = registry.node("remote-a").connection
    assert connection["type"] == "ssh"
    assert connection["host"] == "login.hpc.example.edu"
    assert connection["port"] == 2222
    assert connection["identity_file"] == str(identity.resolve())
    # 尾斜杠归一化，远端作业目录拼接不产生双斜杠
    assert connection["remote_root"] == "/scratch/cloudray/cloudra"
    assert registry.node("remote-a").scheduler["type"] == "slurm"
    assert registry.public_nodes()[0]["connection"] == "ssh"


def test_node_registry_connection_defaults_to_local(tmp_path):
    registry = NodeRegistry.from_dict(
        {
            "nodes": [
                {
                    "node_id": "local",
                    "workspaces": [{"workspace_id": "main", "path": str(tmp_path)}],
                }
            ]
        }
    )
    assert registry.node("local").connection == {"type": "local"}
    assert registry.public_nodes()[0]["connection"] == "local"


@pytest.mark.parametrize(
    "connection,match",
    [
        ({"type": "telnet"}, "unsupported connection"),
        ({"type": "local", "host": "x"}, "no extra fields"),
        ({"type": "ssh", "user": "u", "remote_root": "/d"}, "host"),
        ({"type": "ssh", "host": "h", "remote_root": "/d"}, "user"),
        ({"type": "ssh", "host": "h", "user": "u"}, "remote_root"),
        ({"type": "ssh", "host": "h; rm -rf /", "user": "u", "remote_root": "/d"}, "host"),
        ({"type": "ssh", "host": "h", "user": "u\nk", "remote_root": "/d"}, "user"),
        (
            {"type": "ssh", "host": "h", "user": "u", "remote_root": "relative/dir"},
            "remote_root",
        ),
        (
            {"type": "ssh", "host": "h", "user": "u", "remote_root": "/d/../e"},
            "remote_root",
        ),
        (
            {"type": "ssh", "host": "h", "user": "u", "remote_root": "/d", "port": 0},
            "port",
        ),
        (
            {"type": "ssh", "host": "h", "user": "u", "remote_root": "/d", "port": 70000},
            "port",
        ),
        (
            {
                "type": "ssh", "host": "h", "user": "u", "remote_root": "/d",
                "identity_file": "/definitely/missing/key",
            },
            "identity_file",
        ),
        (
            {"type": "ssh", "host": "h", "user": "u", "remote_root": "/d", "extra": 1},
            "unknown connection fields",
        ),
    ],
)
def test_node_registry_rejects_invalid_connection(tmp_path, connection, match):
    with pytest.raises(NodeRegistryError, match=match):
        NodeRegistry.from_dict(_ssh_node_payload(tmp_path, connection))

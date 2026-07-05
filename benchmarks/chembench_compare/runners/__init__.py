"""
ChemBench comparison runners — package initialization.

Defines the output namespaces and runner registry used by the unified CLI.
"""

from __future__ import annotations

# Output namespaces under cloudra.config.data_dir / benchmarks
NAMESPACE_OPENCODE = "chembench-compare/opencode"
NAMESPACE_CLOUDRA_CLI = "chembench-compare/cloudra-cli"

RUNNER_NAMES = ["opencode", "cloudra-cli"]

NAMESPACE_MAP = {
    "opencode": NAMESPACE_OPENCODE,
    "cloudra-cli": NAMESPACE_CLOUDRA_CLI,
}

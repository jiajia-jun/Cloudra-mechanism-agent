"""Writable storage and workspace selection for packaged Flet apps."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppStorage:
    data_dir: Path
    config_file: Path
    workspace: Path
    packaged: bool


def configure_app_storage() -> AppStorage:
    """Point Cloudra at Flet's durable app storage when it is available.

    Packaged application code is read-only.  Databases, configuration, memory,
    and the default editable workspace therefore live under
    ``FLET_APP_STORAGE_DATA``.  Plain CLI/TUI launches retain their current
    platformdirs/cwd behavior.
    """

    storage_value = os.environ.get("FLET_APP_STORAGE_DATA")
    if not storage_value:
        cwd = Path.cwd().resolve()
        return AppStorage(
            data_dir=cwd,
            config_file=cwd / "config.yaml",
            workspace=cwd,
            packaged=False,
        )

    storage_root = Path(storage_value).expanduser().resolve()
    data_dir = storage_root / "cloudra-data"
    config_file = storage_root / "config.yaml"
    default_workspace = storage_root / "workspace"
    default_workspace.mkdir(parents=True, exist_ok=True)

    # Set these before reloading the singleton so database/path helpers all see
    # the writable application location.
    os.environ["CLOUDRA_DATA_DIR"] = str(data_dir)
    os.environ["CLOUDRA_CONFIG_FILE"] = str(config_file)

    # The Android package is a remote console and intentionally does not ship
    # Cloudra's server-side config stack. Its local state is limited to the
    # remote profile/cursor store managed by RemoteStateStore.
    from cloudra.infra.runtime_profile import is_mobile_runtime

    if is_mobile_runtime():
        return AppStorage(
            data_dir=data_dir,
            config_file=config_file,
            workspace=default_workspace.resolve(),
            packaged=True,
        )

    from cloudra.infra.config import reload_config

    config = reload_config()
    # A copied/stale YAML file must not redirect a packaged app into an
    # inaccessible desktop path.
    config.data_dir = data_dir
    config.config_file = config_file
    config._ensure_dirs()

    configured_workspace = getattr(config, "workspace_dir", None)
    workspace = Path(configured_workspace).expanduser() if configured_workspace else default_workspace
    if not workspace.is_dir():
        workspace = default_workspace

    return AppStorage(
        data_dir=data_dir,
        config_file=config_file,
        workspace=workspace.resolve(),
        packaged=True,
    )

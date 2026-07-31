"""Build the remote-console-only Android APK.

Flet normally consumes every dependency in the repository's root
``pyproject.toml``. That would put the server Agent, chemistry stack and API
server dependencies into the APK. This builder stages the deliberately small
Android runtime and then invokes Flet against that isolated project.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10：标准库 tomllib 于 3.11 引入
    import tomli as tomllib

ANDROID_RUNTIME_FILES = (
    "cloudra/__init__.py",
    "cloudra/backends.py",
    "cloudra/device/__init__.py",
    "cloudra/device/registry.py",
    "cloudra/device/runtime.py",
    "cloudra/mobile_storage.py",
    "cloudra/native_bridge.py",
    "cloudra/platform_utils.py",
    "cloudra/runtime_profile.py",
    "cloudra/ui/__init__.py",
    "cloudra/ui/app.py",
    "cloudra/workspace.py",
    "flet_app.py",
)

ANDROID_EXTENSION_DIRS = (
    "extensions/cloudra_native",
)


def _project_version(pyproject_path: Path) -> str:
    with pyproject_path.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def prepare_stage(project_root: Path, stage_dir: Path) -> Path:
    """Create a clean, auditable Android source stage and return its path."""

    project_root = project_root.resolve()
    stage_dir = stage_dir.resolve()
    if stage_dir == project_root or project_root not in stage_dir.parents:
        raise ValueError("Android stage must be a dedicated directory inside the project")

    stage_dir.mkdir(parents=True, exist_ok=True)
    # Keep Flet/Gradle's generated ``build`` directory so interrupted Android
    # builds can resume. Everything else is a controlled source stage and is
    # refreshed from the allowlist below.
    for child in stage_dir.iterdir():
        if child.name == "build":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    template = project_root / "android" / "pyproject.toml"
    if _project_version(template) != _project_version(project_root / "pyproject.toml"):
        raise RuntimeError("android/pyproject.toml version must match the root project")
    shutil.copy2(template, stage_dir / "pyproject.toml")

    for relative_name in ANDROID_RUNTIME_FILES:
        source = project_root / relative_name
        destination = stage_dir / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    for relative_name in ANDROID_EXTENSION_DIRS:
        source = project_root / relative_name
        destination = stage_dir / relative_name
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                "*.pyo",
                "build",
                "dist",
                "*.egg-info",
            ),
        )

    return stage_dir


def build_android(
    project_root: Path,
    *,
    stage_dir: Path | None = None,
    output_dir: Path | None = None,
    verbose: bool = False,
) -> Path:
    project_root = project_root.resolve()
    stage_dir = stage_dir or project_root / "build" / "android-source"
    output_dir = output_dir or project_root / "build" / "apk"
    prepare_stage(project_root, stage_dir)

    flet_executable = Path(sys.executable).with_name("flet")
    if not flet_executable.is_file():
        discovered = shutil.which("flet")
        if discovered is None:
            raise RuntimeError("Flet CLI was not found in the active Python environment")
        flet_executable = Path(discovered)

    command = [
        str(flet_executable),
        "build",
        "apk",
        str(stage_dir),
        "--output",
        str(output_dir),
        "--yes",
        "--no-rich-output",
    ]
    if verbose:
        command.append("-v")
    environment = os.environ.copy()
    # Flet's Android template currently asks Gradle for an 8 GiB heap. That can
    # be killed by the OS on common 8 GiB development machines during R8. An
    # ORG_GRADLE_PROJECT override has higher precedence than the generated
    # gradle.properties while remaining configurable for larger build hosts.
    environment.setdefault(
        "ORG_GRADLE_PROJECT_org.gradle.jvmargs",
        os.getenv(
            "CLOUDRA_GRADLE_JVMARGS",
            (
                "-Xmx4G -XX:MaxMetaspaceSize=1G "
                "-XX:ReservedCodeCacheSize=256m "
                "-XX:+HeapDumpOnOutOfMemoryError"
            ),
        ),
    )
    subprocess.run(
        command,
        cwd=project_root,
        check=True,
        env=environment,
    )
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Cloudra's remote-console-only Android APK"
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--stage-dir",
        type=Path,
        help="generated Android source stage (defaults to build/android-source)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="APK output directory (defaults to build/apk)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    build_android(
        root,
        stage_dir=args.stage_dir,
        output_dir=args.output,
        verbose=args.verbose,
    )
    return 0

"""
Cloudra CLI - 面向化学科研的 AI Agent 协作框架命令行工具。
"""

import asyncio
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cloudra import __version__, conversation_repo, paths
from cloudra.config import get_config
from cloudra.platform_utils import is_android, is_windows
from cloudra.service import CloudraService, validate_conversation_id

console = Console()
APP_NAME = "cloudra"
VERSION = __version__


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="显示版本信息")
@click.option("--coordinator-model", envvar="CLOUDRA_COORDINATOR_MODEL", help="覆盖 Coordinator 模型")
@click.option("--coordinator-url", envvar="CLOUDRA_COORDINATOR_URL", help="覆盖 Coordinator API 地址")
@click.option("--coordinator-key", envvar="CLOUDRA_COORDINATOR_KEY", help="覆盖 Coordinator API Key")
@click.option("--follower-model", envvar="CLOUDRA_FOLLOWER_MODEL", help="覆盖 Follower 模型")
@click.option("--follower-url", envvar="CLOUDRA_FOLLOWER_URL", help="覆盖 Follower API 地址")
@click.option("--follower-key", envvar="CLOUDRA_FOLLOWER_KEY", help="覆盖 Follower API Key")
@click.option("--yolo", is_flag=True, help="启动默认界面时启用 YOLO 全自动模式")
@click.option("--legacy-tui", is_flag=True, help="使用旧版 prompt_toolkit TUI（新 TUI 有问题时回退）")
@click.pass_context
def cli(ctx, version, coordinator_model, coordinator_url, coordinator_key,
        follower_model, follower_url, follower_key, yolo, legacy_tui):
    """Cloudra - AI 化学科研助手"""
    if version:
        console.print(f"[bold cyan]Cloudra[/bold cyan] version {VERSION}")
        sys.exit(0)

    if ctx.invoked_subcommand is None:
        # 无子命令时：Windows/Android 启动 GUI，Linux 进入交互式 TUI
        _apply_config_overrides(
            coordinator_model, coordinator_url, coordinator_key,
            follower_model, follower_url, follower_key,
        )
        if is_windows() or is_android():
            _launch_gui()
        else:
            _interactive_tui(yolo=yolo, legacy=legacy_tui)
        sys.exit(0)

    _apply_config_overrides(
        coordinator_model, coordinator_url, coordinator_key,
        follower_model, follower_url, follower_key,
    )


def _apply_config_overrides(coordinator_model, coordinator_url, coordinator_key,
                            follower_model, follower_url, follower_key):
    """把 CLI 覆盖项写入全局配置。"""
    config = get_config()
    if coordinator_model:
        config.coordinator.model = coordinator_model
    if coordinator_url:
        config.coordinator.url = coordinator_url
    if coordinator_key:
        config.coordinator.key = coordinator_key
    if follower_model:
        config.follower.model = follower_model
    if follower_url:
        config.follower.url = follower_url
    if follower_key:
        config.follower.key = follower_key


def _launch_gui():
    """启动 Flet GUI。"""
    from cloudra.ui import run_gui
    run_gui()


def _interactive_tui(yolo: bool = False, legacy: bool = False):
    """Linux 等终端环境下的交互式 TUI（默认 Textual 全屏，legacy 时回退 prompt_toolkit）。"""
    from cloudra.tui import run_tui
    run_tui(yolo=yolo, legacy=legacy)


@cli.command(name="gui")
def gui():
    """启动 Cloudra 原生 GUI（Windows/Android 默认入口）。"""
    _launch_gui()


@cli.command()
@click.argument("query")
@click.option("--conv-id", default=None, help="指定对话 ID")
@click.option("--new", is_flag=True, help="启动新对话，不自动恢复")
@click.option("--dry-run", is_flag=True, help="只显示配置，不实际执行")
@click.option("--yolo", is_flag=True, help="启用 YOLO 全自动模式（危险操作由 LLM 自动审批）")
@click.option(
    "--orchestration-mode",
    type=click.Choice(["standard", "dag_record", "dag_guided"]),
    default="standard",
    show_default=True,
    help="任务编排模式；DAG 模式按会话启用并持久化机理研究图。",
)
def run(query, conv_id, new, dry_run, yolo, orchestration_mode):
    """运行一个 Cloudra 任务。"""
    if yolo:
        os.environ["CLOUDRA_YOLO_MODE"] = "true"
        console.print("[bold yellow]YOLO 模式已启用：危险操作将由 LLM 自动审批[/bold yellow]")
    config = get_config()
    # Logic for sticky conversation
    if conv_id:
        active_conv_id = conv_id
    elif new:
        active_conv_id = None
    else:
        active_conv_id = config.last_conversation_id
        if active_conv_id:
            console.print(f"[dim]自动恢复上次对话: {active_conv_id}[/dim]")

    # Resolve actual ID (creates directory if new, but we need it for consistency)
    from cloudra.conversation_class import Conversation
    temp_conv = Conversation(active_conv_id)
    active_conv_id = temp_conv.id

    if dry_run:
        console.print(Panel("[bold]Dry Run 模式[/bold]", style="yellow"))
        console.print(f"Query: {query}")
        console.print(f"Conversation ID: {active_conv_id}")
        console.print(f"Data Dir: {config.data_dir}")
        console.print(f"Coordinator Model: {config.coordinator.model}")
        console.print(f"Follower Model: {config.follower.model}")
        console.print(f"Orchestration Mode: {orchestration_mode}")
        return


    # Validate API keys
    if not config.coordinator.key:
        console.print("[red]错误: Coordinator API Key 未设置。[/red]")
        console.print("请运行 `cloudra config init` 进行配置，或通过环境变量设置。")
        sys.exit(1)

    try:
        # CLI 和 HTTP API 共用同一个业务服务层；CLI 只负责终端输入输出。
        service = CloudraService()
        # 预生成 session_id，Ctrl+C 时才能定位 session 并请求优雅打断
        from datetime import datetime
        session_id = f"a-0_{datetime.now().isoformat()}"
        # CLI 有终端 stdin，显式启用交互式审批线程（service 层默认为 API 场景的 False）
        asyncio.run(service.run_task(
            query, conversation_id=active_conv_id, verbose=True, session_id=session_id,
            interactive_approval=not yolo,
            orchestration_mode=orchestration_mode,
        ))

        # Save the used ID as the last one
        config.last_conversation_id = active_conv_id
        config.save()

    except KeyboardInterrupt:
        # 先置 cancel_requested 让 Agent 优雅收尾（落 cancelled 终态），再退出
        try:
            from cloudra import session_store
            from cloudra.database import ConversationDB
            db = ConversationDB(active_conv_id)
            session_store.update_session_fields(db, session_id, {"state": "cancel_requested"})
        except Exception:
            pass
        console.print("\n[yellow]任务被用户中断。[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]任务执行失败: {e}[/red]")
        import traceback
        console.print(traceback.format_exc())
        sys.exit(1)


@cli.group(name="config")
def config_cmd():
    """配置管理（init, show, get, set）"""
    pass


@config_cmd.command(name="init")
@click.option("--force", is_flag=True, help="覆盖已有配置文件")
def config_init(force):
    """交互式初始化配置文件。"""
    cfg = get_config()
    cfg_path = cfg.config_file

    if cfg_path.exists() and not force:
        console.print(f"[yellow]配置文件已存在: {cfg_path}[/yellow]")
        console.print("使用 `--force` 覆盖，或直接编辑该文件。")
        return

    console.print("[bold]Cloudra 配置初始化[/bold]\n")

    # Prompt for values (use existing as defaults)
    coord_model = click.prompt("Coordinator 模型", default=cfg.coordinator.model)
    coord_url = click.prompt("Coordinator API 地址", default=cfg.coordinator.url)
    coord_key = click.prompt("Coordinator API Key", default="", hide_input=True)

    follower_model = click.prompt("Follower 模型", default=cfg.follower.model)
    follower_url = click.prompt("Follower API 地址", default=cfg.follower.url)
    follower_key = click.prompt("Follower API Key", default="", hide_input=True)

    cfg.coordinator.model = coord_model
    cfg.coordinator.url = coord_url
    cfg.coordinator.key = coord_key or cfg.coordinator.key
    cfg.follower.model = follower_model
    cfg.follower.url = follower_url
    cfg.follower.key = follower_key or cfg.follower.key

    cfg.save()
    console.print(f"[green]配置已保存至: {cfg_path}[/green]")


@config_cmd.command(name="show")
def config_show():
    """显示当前生效的配置（敏感信息脱敏）。"""
    cfg = get_config()
    display = cfg.to_display_dict()

    console.print(Panel("[bold]Cloudra 配置[/bold]", style="cyan"))
    console.print(f"[bold]Data Directory:[/bold] {display['data_dir']}")
    console.print(f"[bold]Config File:[/bold] {display['config_file']}")
    console.print()

    table = Table(title="LLM 配置", show_header=True, header_style="bold magenta")
    table.add_column("角色")
    table.add_column("模型")
    table.add_column("URL")
    table.add_column("Key")

    table.add_row(
        "Coordinator",
        display['llm']['coordinator']['model'],
        display['llm']['coordinator']['url'],
        display['llm']['coordinator']['key'],
    )
    table.add_row(
        "Follower",
        display['llm']['follower']['model'],
        display['llm']['follower']['url'],
        display['llm']['follower']['key'],
    )

    console.print(table)


def _resolve_config_attr(cfg, key: str):
    """Backward-compatible alias; 实现已下沉到 cloudra.config 供 API 复用。"""
    from cloudra.config import resolve_config_attr
    return resolve_config_attr(cfg, key)


@config_cmd.command(name="get")
@click.argument("key")
def config_get(key):
    """读取单个配置项。例如: cloudra config get coordinator.model"""
    cfg = get_config()

    target, final_key = _resolve_config_attr(cfg, key)
    if target is None:
        # Try without 'llm.' prefix for convenience
        target, final_key = _resolve_config_attr(cfg, f"coordinator.{key}")
    if target is None:
        target, final_key = _resolve_config_attr(cfg, f"follower.{key}")
    if target is None:
        console.print(f"[red]配置项不存在: {key}[/red]")
        sys.exit(1)

    value = getattr(target, final_key)

    # Mask keys
    if "key" in key.lower() and isinstance(value, str) and value:
        value = "***"

    console.print(value)


@config_cmd.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """设置单个配置项。例如: cloudra config set coordinator.model gpt-4o"""
    from cloudra.config import set_config_value

    try:
        set_config_value(key, value)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)
    console.print(f"[green]已设置 {key} = {value}[/green]")


@cli.command()
@click.option("--limit", default=20, help="最多显示多少条")
def history(limit):
    """查看历史对话列表。"""
    conversations = conversation_repo.list_conversations()
    if not conversations:
        console.print("[yellow]暂无历史对话。[/yellow]")
        return

    conversations = conversations[:limit]

    table = Table(title="历史对话", show_header=True, header_style="bold magenta")
    table.add_column("对话 ID", style="cyan")
    table.add_column("创建时间")
    table.add_column("最后活跃")
    table.add_column("状态")

    for conv in conversations:
        create_time = conv.get("create_time", "")
        last_active = conv.get("last_active", "")
        table.add_row(
            conv["id"],
            create_time[:19] if create_time else "",
            last_active[:19] if last_active else "",
            conv.get("state", "active"),
        )

    console.print(table)


@cli.command()
@click.argument("conv_id")
def logs(conv_id):
    """查看某个对话的日志。"""
    log_dir = paths.logs_dir(conv_id)

    if not log_dir.exists():
        console.print(f"[yellow]对话 {conv_id} 暂无日志。[/yellow]")
        return

    for log_file in sorted(log_dir.iterdir()):
        if log_file.is_file():
            console.print(Panel(f"[bold]{log_file.name}[/bold]", style="blue"))
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    content = f.read()
                console.print(content[:5000] if len(content) > 5000 else content)
                if len(content) > 5000:
                    console.print("[dim]... (日志过长，已截断)[/dim]")
            except Exception as e:
                console.print(f"[red]读取日志失败: {e}[/red]")
            console.print()


@cli.command()
def skills():
    """列出可用的 Skills。"""
    from cloudra.skill_class import skill_loader

    loader = skill_loader()
    skills_data = loader.skill_datas_get()

    if not skills_data:
        console.print("[yellow]暂无可用 Skills。[/yellow]")
        return

    table = Table(title="可用 Skills", show_header=True, header_style="bold green")
    table.add_column("名称", style="cyan")
    table.add_column("描述")

    for skill in skills_data:
        table.add_row(
            skill.get("name", "N/A"),
            skill.get("description", "")[:80],
        )

    console.print(table)


@cli.command()
@click.option("--state", default=None, help="按状态过滤 (sleeping, thinking, acting, killed)")
def sessions(state):
    """查看所有 Session 状态（跨 conversation 聚合，与 /api/sessions 一致）。"""
    service = CloudraService()
    rows = []
    for conversation in service.list_conversations():
        conversation_id = conversation.get("id", "")
        try:
            validate_conversation_id(conversation_id)
        except ValueError:
            continue
        for record in service.session_runner.list(conversation_id):
            row = record.to_dict()
            row["conversation_id"] = conversation_id
            rows.append(row)
    if state:
        rows = [row for row in rows if row["state"] == state]
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    rows = rows[:100]

    if not rows:
        console.print("[yellow]暂无 Session。[/yellow]")
        return

    table = Table(title="Sessions", show_header=True, header_style="bold magenta")
    table.add_column("Session ID", style="cyan")
    table.add_column("Conversation")
    table.add_column("State")
    table.add_column("Result", max_width=60)

    for row in rows:
        result = (row.get("result") or "")[:100]
        table.add_row(row["session_id"], row["conversation_id"], row["state"], result)
    console.print(table)


@cli.group(name="backup")
def backup_cmd():
    """创建、校验和恢复 Cloudra 数据备份。"""
    pass


@backup_cmd.command(name="create")
@click.argument("destination", type=click.Path(path_type=Path))
def backup_create(destination: Path):
    """在线快照 SQLite，并创建带 SHA-256 清单的备份。"""
    from cloudra.operations import BackupError, create_backup

    try:
        manifest = create_backup(Path(get_config().data_dir), destination)
    except BackupError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(
        f"[green]备份完成:[/green] {destination.resolve()} "
        f"({len(manifest['files'])} files)"
    )


@backup_cmd.command(name="verify")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def backup_verify(archive: Path):
    """校验备份清单、成员范围与全部 SHA-256。"""
    from cloudra.operations import BackupError, verify_backup

    try:
        manifest = verify_backup(archive)
    except BackupError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(f"[green]备份有效[/green] ({len(manifest['files'])} files)")


@backup_cmd.command(name="restore")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("destination", type=click.Path(path_type=Path))
def backup_restore(archive: Path, destination: Path):
    """恢复到不存在或空的目录；不会覆盖现有数据。"""
    from cloudra.operations import BackupError, restore_backup

    try:
        manifest = restore_backup(archive, destination)
    except BackupError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(
        f"[green]恢复完成:[/green] {destination.resolve()} "
        f"({len(manifest['files'])} files)"
    )


@cli.group(name="devices")
def devices_cmd():
    """列出或撤销已配对 Android 设备。"""
    pass


@devices_cmd.command(name="list")
@click.option("--all", "include_revoked", is_flag=True, help="包含已撤销设备")
def devices_list(include_revoked: bool):
    from cloudra.device_broker import DeviceBroker

    rows = DeviceBroker().list_devices(include_revoked=include_revoked)
    table = Table(title="Android Devices", show_header=True)
    table.add_column("Device ID", style="cyan")
    table.add_column("Name")
    table.add_column("State")
    table.add_column("Last seen")
    for row in rows:
        table.add_row(
            row["device_id"], row["display_name"], row["state"], row["last_seen_at"]
        )
    console.print(table if rows else "[yellow]暂无已配对设备。[/yellow]")


@devices_cmd.command(name="revoke")
@click.argument("device_id")
@click.option("--yes", is_flag=True, help="跳过确认")
def devices_revoke(device_id: str, yes: bool):
    """立即撤销设备 token；设备需要重新配对才能上线。"""
    from cloudra.device_broker import DeviceBroker

    if not yes and not click.confirm(f"撤销设备 {device_id}？"):
        return
    try:
        revoked = DeviceBroker().revoke(device_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if not revoked:
        raise click.ClickException("设备不存在或已经撤销")
    console.print(f"[green]设备已撤销:[/green] {device_id}")


@cli.group(name="android")
def android_cmd():
    """Android 构建和发布门禁。"""
    pass


@android_cmd.command(name="audit-apk")
@click.argument("apk", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--expected-cert-sha256",
    envvar="CLOUDRA_ANDROID_CERT_SHA256",
    help="生产签名证书 SHA-256 指纹；可通过环境变量提供",
)
@click.option("--allow-debug", is_flag=True, help="仅本地安装验证时允许 debug 证书")
def android_audit_apk(apk: Path, expected_cert_sha256: str | None, allow_debug: bool):
    from cloudra.android_build import audit_apk_signature

    try:
        result = audit_apk_signature(
            apk,
            expected_cert_sha256=expected_cert_sha256,
            allow_debug=allow_debug,
        )
    except (OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(
        f"[green]APK 签名验证通过[/green] SHA-256="
        f"{result['certificate_sha256']}"
    )


def main():
    """CLI 入口函数。"""
    cli()

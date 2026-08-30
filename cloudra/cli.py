"""
Cloudra CLI - 自主有机小分子机理计算 Agent 命令行工具。
"""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cloudra import __version__
from cloudra.infra.config import get_config
from cloudra.web_launcher import launch_browser

console = Console()
APP_NAME = "cloudra"
VERSION = __version__
_SENSITIVE_CONFIG_KEY_PARTS = {"key", "password", "secret", "token", "credential"}


def _is_sensitive_config_key(key: str) -> bool:
    """Return whether a dotted/underscored config path contains a secret field."""
    parts = key.lower().replace(".", "_").split("_")
    return any(part in _SENSITIVE_CONFIG_KEY_PARTS for part in parts)


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="显示版本信息")
@click.option("--coordinator-model", envvar="CLOUDRA_COORDINATOR_MODEL", help="覆盖 Coordinator 模型")
@click.option("--coordinator-url", envvar="CLOUDRA_COORDINATOR_URL", help="覆盖 Coordinator API 地址")
@click.option("--coordinator-key", envvar="CLOUDRA_COORDINATOR_KEY", help="覆盖 Coordinator API Key")
@click.option("--follower-model", envvar="CLOUDRA_FOLLOWER_MODEL", help="覆盖 Follower 模型")
@click.option("--follower-url", envvar="CLOUDRA_FOLLOWER_URL", help="覆盖 Follower API 地址")
@click.option("--follower-key", envvar="CLOUDRA_FOLLOWER_KEY", help="覆盖 Follower API Key")
@click.pass_context
def cli(ctx, version, coordinator_model, coordinator_url, coordinator_key,
        follower_model, follower_url, follower_key):
    """Cloudra - 自主有机小分子机理计算 Agent"""
    if version:
        console.print(f"[bold cyan]Cloudra[/bold cyan] version {VERSION}")
        sys.exit(0)

    if ctx.invoked_subcommand is None:
        _apply_config_overrides(
            coordinator_model, coordinator_url, coordinator_key,
            follower_model, follower_url, follower_key,
        )
        sys.exit(launch_browser(_frontend_or_exit(), rebuild=False, skip_build=False))

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


def _frontend_or_exit():
    from cloudra.web_launcher import _frontend_dir
    try:
        return _frontend_dir()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)


@cli.command(name="web")
@click.option("--rebuild", is_flag=True, help="强制重新构建前端")
@click.option("--skip-build", is_flag=True, help="复用已有 frontend/dist 构建")
def web(rebuild, skip_build):
    """启动 Web 前端（API + SPA 单端口服务）。"""
    sys.exit(launch_browser(_frontend_or_exit(), rebuild=rebuild, skip_build=skip_build))


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
    openalex_key = click.prompt(
        "OpenAlex API Key（可选，回车跳过；无 key 时匿名检索）",
        default="",
        hide_input=True,
    )
    openalex_mailto = click.prompt(
        "OpenAlex 礼貌池邮箱（可选，回车跳过）",
        default=cfg.openalex_mailto or "",
    )

    cfg.coordinator.model = coord_model
    cfg.coordinator.url = coord_url
    cfg.coordinator.key = coord_key or cfg.coordinator.key
    cfg.follower.model = follower_model
    cfg.follower.url = follower_url
    cfg.follower.key = follower_key or cfg.follower.key
    if openalex_key:
        cfg.openalex_api_key = openalex_key
    if openalex_mailto:
        cfg.openalex_mailto = openalex_mailto

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
    console.print()
    oa_key = display.get("openalex_api_key", "(not set)")
    oa_mail = display.get("openalex_mailto", "(not set)")
    console.print(f"[bold]OpenAlex API Key:[/bold] {oa_key}")
    console.print(f"[bold]OpenAlex mailto:[/bold] {oa_mail}")


def _resolve_config_attr(cfg, key: str):
    """Backward-compatible alias; 实现已下沉到 cloudra.infra.config 供 API 复用。"""
    from cloudra.infra.config import resolve_config_attr
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

    # Mask sensitive values
    if _is_sensitive_config_key(key) and isinstance(value, str) and value:
        value = "***"

    console.print(value)


@config_cmd.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """设置单个配置项。例如: cloudra config set coordinator.model gpt-4o"""
    from cloudra.infra.config import set_config_value

    try:
        set_config_value(key, value)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)
    display_value = "***" if _is_sensitive_config_key(key) else value
    console.print(f"[green]已设置 {key} = {display_value}[/green]")


@cli.group(name="knowledge")
def knowledge_cmd():
    """知识图谱（chem-kb）：导入 CSV、统计、检索与 provider 激活。"""
    pass


@knowledge_cmd.command(name="import")
@click.option("--entities", "entities_csv", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=Path("kg_data/kg-entities.csv"), show_default=True, help="实体 CSV（utf-8-sig）")
@click.option("--relations", "relations_csv", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=Path("kg_data/kg-relations.csv"), show_default=True, help="关系 CSV（utf-8-sig）")
@click.option("--db", "db_path", type=click.Path(path_type=Path), default=None,
              help="目标库路径（默认 data_dir/knowledge/chem_kg.db）")
def knowledge_import(entities_csv, relations_csv, db_path):
    """导入 KG CSV 到 chem_kg.db（幂等，可重复执行）。"""
    from cloudra.knowledge import store
    from cloudra.persistence.paths import knowledge_graph_db_path

    db = db_path or knowledge_graph_db_path()
    report = store.import_csv(db, entities_csv, relations_csv)
    console.print(f"[green]导入完成:[/green] {db}")
    console.print(f"  entities: {report['entities']}  relations: {report['relations']}  "
                  f"encoding: {report['encoding']['entities']}/{report['encoding']['relations']}")
    if report["bad_rows"]:
        console.print(f"[yellow]坏行 {len(report['bad_rows'])} 条（悬挂引用，已跳过）:[/yellow]")
        for bad in report["bad_rows"][:10]:
            console.print(f"    line {bad['line']}: {bad['reason']}")
    if report.get("smiles_invalid"):
        console.print(f"[yellow]SMILES 校验失败 {report['smiles_invalid']} 条（rdkit 软告警）[/yellow]")
    console.print(f"  耗时 {report['seconds']}s")


@knowledge_cmd.command(name="stats")
@click.option("--db", "db_path", type=click.Path(path_type=Path), default=None)
def knowledge_stats(db_path):
    """库概览：计数、类型/关系分布、corroborated 数。"""
    from cloudra.knowledge import store
    from cloudra.persistence.paths import knowledge_graph_db_path

    db = db_path or knowledge_graph_db_path()
    info = store.overview(db)
    if not info["db_present"]:
        console.print(f"[yellow]库不存在: {db}（先运行 cloudra knowledge import）[/yellow]")
        return
    console.print(Panel(f"[bold]chem_kg.db[/bold]  {db}", style="cyan"))
    console.print(f"实体 {info['entities']}  关系 {info['relations']}  corroborated {info['corroborated']}")
    table = Table(title="类型分布", show_header=True, header_style="bold magenta")
    table.add_column("type")
    table.add_column("count", justify="right")
    for k, v in info["type_dist"].items():
        table.add_row(k, str(v))
    console.print(table)
    table = Table(title="关系分布 (top 15)", show_header=True, header_style="bold magenta")
    table.add_column("rel_type")
    table.add_column("count", justify="right")
    for k, v in list(info["rel_dist"].items())[:15]:
        table.add_row(k, str(v))
    console.print(table)


@knowledge_cmd.command(name="search")
@click.argument("query")
@click.option("--limit", type=int, default=8, show_default=True)
@click.option("--db", "db_path", type=click.Path(path_type=Path), default=None)
def knowledge_search(query, limit, db_path):
    """图谱检索（FTS→LIKE 回退 + 1~2 跳邻域）。"""
    from cloudra.knowledge import store
    from cloudra.persistence.paths import knowledge_graph_db_path

    db = db_path or knowledge_graph_db_path()
    rows = store.search_graph(db, query, limit=limit)
    if not rows:
        console.print("[yellow]无命中。[/yellow]" if db.exists() else f"[yellow]库不存在: {db}[/yellow]")
        return
    table = Table(title=f"chem-kb 检索（{rows[0]['fallback']}）", show_header=True, header_style="bold magenta")
    table.add_column("hop", justify="right")
    table.add_column("label")
    table.add_column("type")
    table.add_column("source")
    table.add_column("score", justify="right")
    for r in rows:
        table.add_row(str(r["hop"]), r["label"], r["type"], r["source"], f"{r['score']:.3f}")
    console.print(table)


@knowledge_cmd.command(name="export")
@click.argument("out_dir", type=click.Path(file_okay=False, path_type=Path))
@click.option("--db", "db_path", type=click.Path(path_type=Path), default=None)
def knowledge_export(out_dir, db_path):
    """把库导出为 kg-entities.csv / kg-relations.csv。"""
    import csv

    from cloudra.knowledge import store
    from cloudra.persistence.paths import knowledge_graph_db_path

    db = db_path or knowledge_graph_db_path()
    if not db.exists():
        console.print(f"[yellow]库不存在: {db}[/yellow]")
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)
    con = store._open_ro(db)
    try:
        with (out_dir / "kg-entities.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "type", "label", "smiles", "props", "n_sources"])
            for row in con.execute("SELECT id, type, label, smiles, props, n_sources FROM kg_entities ORDER BY id"):
                w.writerow(row)
        with (out_dir / "kg-relations.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["src_id", "dst_id", "rel_type", "evidence_level", "source", "falsified", "note"])
            for row in con.execute("SELECT src_id, dst_id, rel_type, evidence_level, source, falsified, note "
                                   "FROM kg_relations ORDER BY id"):
                w.writerow(row)
    finally:
        con.close()
    console.print(f"[green]导出完成:[/green] {out_dir.resolve()}")


@knowledge_cmd.command(name="install")
def knowledge_install():
    """把 chem-kb 混合 provider 写进 config.yaml 的 plugins 列表（幂等）。"""
    from cloudra.knowledge.installer import install_plugin_spec

    cfg_path, added = install_plugin_spec()
    if added:
        console.print(f"[green]已写入 plugins:[/green] {cfg_path}")
    else:
        console.print(f"[yellow]已存在，跳过:[/yellow] {cfg_path}")
    console.print("重启 uvicorn 后生效（插件在 app 启动时加载）。")


@cli.command()
def skills():
    """列出可用的 Skills。"""
    from cloudra.base.skill_class import skill_loader

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


@cli.group(name="backup")
def backup_cmd():
    """创建、校验和恢复 Cloudra 数据备份。"""
    pass


@backup_cmd.command(name="create")
@click.argument("destination", type=click.Path(path_type=Path))
def backup_create(destination: Path):
    """在线快照 SQLite，并创建带 SHA-256 清单的备份。"""
    from cloudra.infra.operations import BackupError, create_backup

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
    from cloudra.infra.operations import BackupError, verify_backup

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
    from cloudra.infra.operations import BackupError, restore_backup

    try:
        manifest = restore_backup(archive, destination)
    except BackupError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(
        f"[green]恢复完成:[/green] {destination.resolve()} "
        f"({len(manifest['files'])} files)"
    )


def main():
    """CLI 入口函数。"""
    cli()

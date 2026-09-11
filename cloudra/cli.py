"""
Cloudra CLI - 自主有机小分子机理计算 Agent 命令行工具。
"""

import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cloudra import __version__
from cloudra.infra.config import get_config
from cloudra.infra.logging_setup import setup_logging
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
    # CLI 场景只让 warning+ 上屏（stderr）；面向用户的输出仍走 rich Console。
    setup_logging("cloudra", stream=sys.stderr, level=os.environ.get("CLOUDRA_LOG_LEVEL", "WARNING"))
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

    from cloudra.infra.providers import detect_provider_from_url, get_provider_preset, list_provider_presets
    presets = list_provider_presets()

    def _prompt_slot(role_name: str, current_cfg, allow_same: bool = False):
        console.print(f"[bold cyan]--- 配置 {role_name} ---[/bold cyan]")
        if allow_same:
            console.print("  [bold]0[/bold]) 同 Coordinator 配置")
        for idx, p in enumerate(presets, 1):
            console.print(f"  [bold]{idx}[/bold]) {p.name}")

        default_idx = 1
        detected = None
        if current_cfg.provider:
            detected = get_provider_preset(current_cfg.provider)
        if not detected and current_cfg.url:
            detected = detect_provider_from_url(current_cfg.url)
        if detected:
            for idx, p in enumerate(presets, 1):
                if p.id == detected.id:
                    default_idx = idx
                    break

        choice = click.prompt("供应商序号", default=0 if allow_same else default_idx, type=int)
        if allow_same and choice == 0:
            return None

        if 1 <= choice <= len(presets):
            chosen = presets[choice - 1]
        else:
            chosen = presets[-1]

        default_url = chosen.default_url or current_cfg.url
        default_model = chosen.default_model or current_cfg.model
        url = click.prompt(f"{role_name} API 地址", default=default_url)
        if chosen.models:
            console.print(f"[dim]常见模型候选: {', '.join(chosen.models[:5])}[/dim]")
        model = click.prompt(f"{role_name} 模型", default=default_model)

        key = ""
        if chosen.id == "openrouter":
            console.print("[cyan]OpenRouter 账号授权方式:[/cyan]")
            console.print("  [bold]1[/bold]) 浏览器一键授权 (OAuth PKCE 自动重定向捕获 - 推荐)")
            console.print("  [bold]2[/bold]) 手工输入已有 API Key (sk-or-v1-...)")
            auth_way = click.prompt("选择授权方式", default=1, type=int)
            if auth_way == 1:
                import urllib.parse

                from cloudra.infra.providers import (
                    exchange_openrouter_code,
                    generate_pkce_pair,
                    run_local_auth_listener,
                )
                verifier, challenge = generate_pkce_pair()
                callback_url, wait_for_code = run_local_auth_listener(timeout=90.0)
                params = {
                    "callback_url": callback_url,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
                auth_url = f"https://openrouter.ai/auth?{urllib.parse.urlencode(params)}"
                console.print("[bold green]正在打开浏览器进行 OpenRouter 账号授权...[/bold green]")
                console.print(f"[dim]授权链接: {auth_url}[/dim]")
                try:
                    click.launch(auth_url)
                except Exception:
                    pass
                console.print("[dim]本地重定向回调服务已就绪，等待浏览器授权完成...[/dim]")
                captured = wait_for_code(90.0)
                if captured:
                    try:
                        key = exchange_openrouter_code(captured.strip(), verifier)
                        console.print("[green]✓ OpenRouter 账号授权成功，已自动获得 API Key！[/green]")
                    except Exception as exc:
                        console.print(f"[red]授权交换失败 ({exc})，请改用手动输入 Key[/red]")
                else:
                    console.print("[yellow]等待重定向超时，未能自动捕获授权码。[/yellow]")

        if not key:
            key_hint = f" ({chosen.key_hint})" if chosen.key_hint else ""
            key = click.prompt(f"{role_name} API Key{key_hint}", default="", hide_input=True)

        return chosen.id, model, url, key

    coord_res = _prompt_slot("Coordinator", cfg.coordinator, allow_same=False)
    coord_provider, coord_model, coord_url, coord_key = coord_res

    console.print()
    foll_res = _prompt_slot("Follower", cfg.follower, allow_same=True)
    if foll_res is None:
        foll_provider, foll_model, foll_url, foll_key = coord_provider, coord_model, coord_url, coord_key
    else:
        foll_provider, foll_model, foll_url, foll_key = foll_res

    console.print()
    openalex_key = click.prompt(
        "OpenAlex API Key（可选，回车跳过；无 key 时匿名检索）",
        default="",
        hide_input=True,
    )
    openalex_mailto = click.prompt(
        "OpenAlex 礼貌池邮箱（可选，回车跳过）",
        default=cfg.openalex_mailto or "",
    )

    from cloudra.infra.config import mutate_config
    from cloudra.infra.providers import apply_provider_preset

    def _apply(work):
        if coord_provider and coord_provider != "custom":
            apply_provider_preset(work.coordinator, coord_provider)
        work.coordinator.model = coord_model
        work.coordinator.url = coord_url
        if coord_key:
            work.coordinator.key = coord_key

        if foll_provider and foll_provider != "custom":
            apply_provider_preset(work.follower, foll_provider)
        work.follower.model = foll_model
        work.follower.url = foll_url
        if foll_key:
            work.follower.key = foll_key

        if openalex_key:
            work.openalex_api_key = openalex_key
        if openalex_mailto:
            work.openalex_mailto = openalex_mailto

    mutate_config(_apply)
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
    table.add_column("供应商")
    table.add_column("模型")
    table.add_column("URL")
    table.add_column("Key")

    table.add_row(
        "Coordinator",
        display['llm']['coordinator'].get('provider', 'custom'),
        display['llm']['coordinator']['model'],
        display['llm']['coordinator']['url'],
        display['llm']['coordinator']['key'],
    )
    table.add_row(
        "Follower",
        display['llm']['follower'].get('provider', 'custom'),
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
@click.option("--tag", "tag_filters", multiple=True,
              help="标签过滤，格式 facet:tag（可多次，如 --tag error:err_l502 --tag problem:ts_search）")
@click.option("--type", "entity_type", default=None,
              help="实体类型过滤（concept/method/software/pitfall/...）")
@click.option("--db", "db_path", type=click.Path(path_type=Path), default=None)
def knowledge_search(query, limit, tag_filters, entity_type, db_path):
    """图谱检索（FTS→LIKE 回退 + 1~2 跳邻域，支持标签/类型分面）。"""
    from cloudra.knowledge import store
    from cloudra.persistence.paths import knowledge_graph_db_path

    facets: dict[str, list[str]] = {}
    for item in tag_filters:
        facet, _, tag = str(item).partition(":")
        facet, tag = facet.strip(), tag.strip()
        if facet and tag:
            facets.setdefault(facet, []).append(tag)
        elif tag:  # 裸 tag 无 facet 前缀：按 error 惯例放行报错签名检索
            facets.setdefault("error", []).append(tag)
    db = db_path or knowledge_graph_db_path()
    rows = store.search_graph(db, query, limit=limit,
                              facets=facets or None, entity_type=entity_type)
    if not rows:
        console.print("[yellow]无命中。[/yellow]" if db.exists() else f"[yellow]库不存在: {db}[/yellow]")
        return
    table = Table(title=f"chem-kb 检索（{rows[0]['fallback']}）", show_header=True, header_style="bold magenta")
    table.add_column("hop", justify="right")
    table.add_column("label")
    table.add_column("type")
    table.add_column("tags")
    table.add_column("source")
    table.add_column("score", justify="right")
    for r in rows:
        tags = ",".join(t for vals in (r.get("tags") or {}).values() for t in vals)
        table.add_row(str(r["hop"]), r["label"], r["type"], tags, r["source"], f"{r['score']:.3f}")
    console.print(table)


@knowledge_cmd.group(name="tag")
def tag_cmd():
    """卡片标签（v13）：LLM 打标 → 实体反贴 → 覆盖率统计。"""
    pass


@tag_cmd.command(name="build")
@click.option("--limit", type=int, default=0, help="只打前 N 张卡（0=全部；试跑/控费用用）")
@click.option("--batch-size", type=int, default=15, show_default=True, help="每次 LLM 请求的卡片数")
@click.option("--concurrency", type=int, default=4, show_default=True, help="并发 LLM 请求数")
@click.option("--refresh", is_flag=True, help="忽略缓存，全部重打（内容未变的卡也会重调 LLM）")
@click.option("--dry-run", is_flag=True, help="只调 LLM 并报告，不写 cards.jsonl / 缓存 / pending")
@click.option("--model", default=None, help="覆盖 config.coordinator.model")
@click.option("--url", "base_url", default=None, help="覆盖 config.coordinator.url")
@click.option("--key", "api_key", default=None, help="覆盖 config.coordinator.key（不会回显）")
def tag_build(limit, batch_size, concurrency, refresh, dry_run, model, base_url, api_key):
    """LLM 批量打标：cards.jsonl 加 tags 字段（行对齐，向量库无需重编码）。

    断点安全：已打过的卡（内容哈希命中缓存）自动跳过。词表外的 LLM 提议
    进 vector_store/_tag_state/pending_tags.json，人工审核后补进词表。
    """
    from cloudra.knowledge import tagging

    if not (api_key or get_config().coordinator.key):
        console.print("[red]未配置 LLM key：先 cloudra config set coordinator.key …"
                      "（或用 --key/--url/--model 覆盖）[/red]")
        sys.exit(1)
    report = tagging.tag_cards(
        model=model, base_url=base_url, api_key=api_key,
        batch_size=batch_size, concurrency=concurrency,
        limit=limit, refresh=refresh, dry_run=dry_run,
    )
    mode = "（dry-run，未写盘）" if dry_run else ""
    console.print(Panel(f"[bold]打标完成[/bold] {mode}", style="cyan"))
    console.print(f"卡片 {report['cards_total']}  本次打标 {report['cards_with_tags']}  "
                  f"缓存命中 {report['from_cache']}  LLM 调用 {report['llm_batches']} 批"
                  f"/{report['llm_called']} 卡  耗时 {report['seconds']}s")
    if report["llm_errors"]:
        console.print(f"[yellow]LLM 失败 {len(report['llm_errors'])} 批（下轮重跑自动补）:[/yellow]")
        for err in report["llm_errors"][:5]:
            console.print(f"  {err}")
    if report["pending"]:
        console.print(f"[yellow]词表外提议 {len(report['pending'])} 条 → "
                      f"vector_store/_tag_state/pending_tags.json（审核后补进 tag_vocab.yaml）[/yellow]")
    if report["write"]:
        console.print(f"写回: {report['write']['cards']}/{report['write']['rows']} 行携带 tags")


@tag_cmd.command(name="apply-db")
@click.option("--db", "db_path", type=click.Path(path_type=Path), default=None)
@click.option("--cards", "cards_path", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None, help="cards.jsonl 路径（默认仓库内 vector_store/cards.jsonl）")
def tag_apply_db(db_path, cards_path):
    """把卡片 tags 经 relations.source 反贴到实体（整表重建，幂等）。"""
    from cloudra.knowledge import store, tagging
    from cloudra.persistence.paths import knowledge_graph_db_path

    rows = tagging.read_cards(cards_path)
    source_map = tagging.source_tag_map(rows)
    if not source_map:
        console.print("[yellow]cards.jsonl 里还没有 tags——先跑 cloudra knowledge tag build。[/yellow]")
        return
    report = store.rebuild_entity_tags(db_path or knowledge_graph_db_path(), source_map)
    console.print(f"[green]实体标签已重建:[/green] 来源 {report['sources']} 个博客 → "
                  f"{report['entities']} 实体 / {report['rows']} 行标签（{report['seconds']}s）")


@tag_cmd.command(name="stats")
@click.option("--db", "db_path", type=click.Path(path_type=Path), default=None)
def tag_stats(db_path):
    """打标覆盖率（卡片侧）与标签分布（图谱侧）。"""
    from cloudra.knowledge import store, tagging
    from cloudra.persistence.paths import knowledge_graph_db_path

    cov = tagging.coverage_report()
    console.print(Panel("[bold]卡片覆盖率（cards.jsonl）[/bold]", style="cyan"))
    console.print(f"已打 {cov['tagged_cards']}/{cov['cards']} 卡（{cov['coverage_pct']}%）  "
                  f"维度覆盖: " + "  ".join(f"{f} {pct}%" for f, pct in cov["facet_cards"].items()))
    for facet, top in cov["top"].items():
        if top:
            tops = "  ".join(f"{t}×{n}" for t, n in top[:8])
            console.print(f"  [dim]{facet}[/dim] {tops}")
    dist = store.tag_distribution(db_path or knowledge_graph_db_path())
    if not dist.get("db_present"):
        console.print("[yellow]chem_kg.db 不存在（先 cloudra knowledge import）。[/yellow]")
        return
    console.print(Panel("[bold]图谱实体标签（kg_entity_tags）[/bold]", style="cyan"))
    if not dist.get("rows"):
        console.print("库内暂无实体标签（先 cloudra knowledge tag apply-db）。")
        return
    console.print(f"{dist['entities']} 实体 / {dist['rows']} 行标签")
    for facet, items in dist.get("facets", {}).items():
        tops = "  ".join(f"{t}×{n}" for t, n in items[:8])
        console.print(f"  [dim]{facet}[/dim] {tops}")


@knowledge_cmd.command(name="tags")
@click.option("--facet", "facet_filter", default=None, help="只列某个维度（method/software/problem/error/domain）")
def knowledge_tags(facet_filter):
    """列出标签词表（vector_store/tag_vocab.yaml）。"""
    import yaml

    from cloudra.knowledge.tagging import TAG_FACETS, VOCAB_FILE

    raw = yaml.safe_load(VOCAB_FILE.read_text(encoding="utf-8"))
    facets = raw.get("facets") or {}
    wanted = [facet_filter] if facet_filter else list(facets)
    console.print(f"[bold]词表 v{raw.get('version', 1)}[/bold]  {VOCAB_FILE}")
    for facet in wanted:
        items = facets.get(facet) or []
        console.print(Panel(f"[bold]{facet}[/bold]（{len(items)} 个值"
                            + ("，继承字段不打标" if facet not in TAG_FACETS else "，LLM 打标")
                            + "）", style="cyan"))
        for item in items:
            aliases = "/".join(str(a) for a in (item.get("aliases") or [])[:5])
            line = f"{item.get('id')}: {item.get('label')}"
            if aliases:
                line += f"  [dim]({aliases})[/dim]"
            console.print(f"  {line}")


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


@knowledge_cmd.command(name="status")
def knowledge_status():
    """三通道健康：语义（kg_vec 微服务）/ 图谱库 / 模糊兜底卡片。"""
    from cloudra.knowledge.health import knowledge_health

    health = knowledge_health()
    sem, graph, fuzzy = health["semantic"], health["graph"], health["fuzzy"]
    if sem["ok"]:
        model = sem.get("model") or sem.get("library_model") or "(模型预热中)"
        sem_detail = f"model={model}  cards={sem.get('count', '?')}"
    else:
        sem_detail = sem.get("error") or "不可用"
    graph_detail = (f"实体 {graph.get('entities')}  关系 {graph.get('relations')}"
                    if graph["ok"] else graph.get("error") or "不可用")
    fuzzy_detail = (f"{fuzzy.get('cards')} 卡"
                    if fuzzy["ok"] else fuzzy.get("error") or "不可用")

    def _row(name: str, ok: bool, detail: str) -> None:
        mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"  {mark} {name}: {detail}")

    console.print("[bold]chem-kb 通道健康[/bold]")
    _row(f"语义（{sem['url']}）", sem["ok"], sem_detail)
    _row("图谱（chem_kg.db）", graph["ok"], graph_detail)
    _row("模糊兜底（cards.jsonl）", fuzzy["ok"], fuzzy_detail)
    if not sem["ok"]:
        console.print("[yellow]语义通道不可用：cloudra web 启动时会自动拉起 kg_vec"
                      "（CLOUDRA_KG_VEC=off 已禁用或服务异常时见 data_dir/logs/kg_vec.log）。[/yellow]")


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


@knowledge_cmd.command(name="uninstall")
def knowledge_uninstall():
    """把 chem-kb 混合 provider 从 config.yaml 的 plugins 列表移除（幂等）。"""
    from cloudra.knowledge.installer import uninstall_plugin_spec

    cfg_path, removed = uninstall_plugin_spec()
    if removed:
        console.print(f"[green]已从 plugins 移除:[/green] {cfg_path}")
    else:
        console.print(f"[yellow]不存在，跳过:[/yellow] {cfg_path}")
    console.print("重启 uvicorn 后生效（插件在 app 启动时加载）。")


@cli.command(name="scheduler")
def scheduler_cmd():
    """前台运行计算调度守护进程（排队/容量/对账；单实例 flock）。"""
    from cloudra.scheduler.daemon import main as scheduler_main

    sys.exit(scheduler_main())


@cli.command(name="stop")
@click.option("--timeout", default=20.0, show_default=True, help="等待各部件退出的总时限（秒）")
def stop_cmd(timeout):
    """显式停止全部 Cloudra 服务（API 控制面 + scheduler/kg_vec 守护）。

    只回收有明确归属的执行：API 进程走优雅关停（取消推理/收尾、关流、
    回收 JS host），守护进程看到 daemons.stop marker 后自行退出。在跑的
    计算作业（guard/calculator/QM）不会被杀——它们跑到终态自行收尾；
    Slurm 作业的取消走现有的 cancel_requested → scancel 路径。
    再次运行 `cloudra`/`cloudra web` 会清除 marker 并重新拉起守护。
    """
    from cloudra.services.shutdown import stop_all

    console.print("[cyan]正在停止 Cloudra（写入关停标志并通知各部件）...[/cyan]")
    report = stop_all(timeout=timeout)
    port = report["api_port"]
    if port is None:
        console.print("  API: 未发现运行中的实例")
    elif report["api_stopped"]:
        console.print(f"  API: 已停止（端口 {port}）")
    else:
        console.print(f"[yellow]  API: {timeout}s 内未确认退出（端口 {port}），请检查进程[/yellow]")
    for name, state in report["daemons"].items():
        mark = "[green]已停止[/green]" if state == "stopped" else "[yellow]仍在运行[/yellow]"
        console.print(f"  {name}: {mark}")
    running = report["compute_jobs_running"]
    if running:
        console.print(
            f"[yellow]  注意：仍有 {running} 个计算作业在跑；按可靠性铁律它们不被 kill，"
            "会运行到终态自行收尾。[/yellow]"
        )
    console.print("[green]关停标志已生效：守护进程不会被自动重新拉起；下次 `cloudra` 启动时清除。[/green]")


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

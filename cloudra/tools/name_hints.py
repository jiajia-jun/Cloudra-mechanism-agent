"""Retired wire names → hint only. Never executed."""

_RETIRED: dict[str, str] = {
    "text_reader": "read",
    "image_reader": "read",
    "pdf2md": "read",
    "pdf2image": "read",
    "read_file": "read",
    "web_search": "search (source=web)",
    "paper_searcher": "search (source=arxiv)",
    "openalex_searcher": "search (source=openalex)",
    "bashtools": "bash",
    "shell": "bash",
    "text_writer": "write",
    "write_file": "write",
    "edit_file": "edit",
    "str_replace": "edit",
    "getskill": "get_skill",
    "web_fetcher": "browser",
    "web_fetch": "browser",
    "headless_browser": "browser",
    "SubAgentLauncher": "subagent_launcher",
    "SubAgentSwarm": "subagent_swarm",
}


def hint_unknown_tool(name: str) -> str:
    target = _RETIRED.get(name)
    if target:
        return (
            f"[Tool error] unknown tool {name!r}. "
            f"Use `{target}` instead."
        )
    return (
        f"[Tool error] unknown tool {name!r}. "
        "Choose an available tool and retry."
    )


def is_retired_tool_name(name: str) -> bool:
    return name in _RETIRED

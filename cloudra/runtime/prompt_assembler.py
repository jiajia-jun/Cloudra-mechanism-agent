"""Deterministic, request-time system prompt assembly.

Identity and policy sources are re-validated for every model request via file
mtime/size signatures: unchanged files are served from a module-level cache,
changed files are re-read immediately. Conversation history never owns these
messages, so an existing conversation can pick up a changed role prompt,
MEMORY.md, AGENTS.md, or capability manifest immediately.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml

from cloudra.infra.config import get_config
from cloudra.persistence.memory import get_memory_manager
from cloudra.runtime.environment_observer import observe_workspace

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"

# 有联网搜索能力（原生搜索或 web_search 工具）时注入的引导，防止模型凭记忆作答
_WEB_SEARCH_GUIDANCE = (
    "## 联网搜索（重要）\n"
    "你具备联网搜索能力。当任务依赖**实时/最新或外部**信息时，**必须先联网搜索**，"
    "不要凭训练记忆作答。典型场景：\n"
    "- 近期新闻、最新软件/模型版本、当前价格/参数、榜单/政策/规范；\n"
    "- 官方文档、论坛讨论、数据库页面、具体机构/产品的最新信息；\n"
    "- 你的知识可能过时或不确定，而答案会影响结论或决策。\n"
    "搜索后基于结果作答，并附来源 URL。联网搜索不是可选项——只要任务需要当前/"
    "外部事实，就先搜再答。"
)

# 有 agent_hub 工具（所有并行 Agent）时注入的引导，鼓励主动共享/复用
_AGENT_HUB_GUIDANCE = (
    "## AgentHub 协作（并行共享）\n"
    "系统提供 `agent_hub` 工具：所有并行 Agent 共享的论坛，是彼此间唯一的横向信道。"
    "使用纪律：\n"
    "- 开工前先 `browse`/`search` 看别人是否已做过相关主题，避免重复劳动；"
    "与其他 Agent 并行、可能重叠的任务**尤其要主动查**。\n"
    "- 拿到可复用的关键结论（参数、数据、坑）后，用 `post` 发布到对应主题；"
    "帖子要自包含——别人没有你的上下文。\n"
    "- 其他 Agent 的帖子是你结论的交叉验证来源：遇到可疑/矛盾的发现时，"
    "`read`/`search` 查一下 hub 是否有相关记录再下结论。"
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# 按 (mtime_ns, size) 签名的文件内容缓存：签名不变直接复用，变了立即重读。
# assemble 已移入工作线程，多 Agent 并发时靠锁保证缓存读写一致。
_FILE_CACHE_LOCK = threading.Lock()
_FILE_CONTENT_CACHE: dict[str, tuple[tuple[int, int], str]] = {}
# skills 目录签名 -> (manifest, source)；签名含每个 SKILL.md 的 mtime/size。
_SKILL_MANIFEST_CACHE: dict[
    str, tuple[tuple[tuple[str, int, int], ...], tuple[list[dict], "PromptSource"]]
] = {}


def _read_file_cached(path: Path) -> str:
    """读取文本文件，(mtime_ns, size) 签名不变时复用缓存内容。"""
    stat = path.stat()
    signature = (stat.st_mtime_ns, stat.st_size)
    key = str(path)
    with _FILE_CACHE_LOCK:
        cached = _FILE_CONTENT_CACHE.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1]
    content = path.read_text(encoding="utf-8")
    with _FILE_CACHE_LOCK:
        _FILE_CONTENT_CACHE[key] = (signature, content)
    return content


@dataclass(frozen=True)
class PromptSource:
    kind: str
    revision: str
    path: Optional[str] = None

    def to_dict(self) -> dict[str, str]:
        data = {"kind": self.kind, "revision": self.revision}
        if self.path is not None:
            data["path"] = self.path
        return data


@dataclass(frozen=True)
class PromptAssembly:
    prompt_revision: str
    capability_revision: str
    identity_messages: tuple[dict, ...]
    observation_messages: tuple[dict, ...]
    sources: tuple[PromptSource, ...]
    tool_names: tuple[str, ...]
    working_directory: str
    environment_revisions: dict[str, object]

    def diagnostics(self) -> dict:
        return {
            "prompt_revision": self.prompt_revision,
            "capability_revision": self.capability_revision,
            "prompt_sources": [source.to_dict() for source in self.sources],
            "tool_names": list(self.tool_names),
            "working_directory": self.working_directory,
            "environment_revisions": self.environment_revisions,
        }


def load_role_prompt(prompt_name: str) -> str:
    prompt_path = PROMPTS_DIR / f"{prompt_name}.md"
    if not prompt_path.is_file():
        raise FileNotFoundError(f"找不到 prompt 文件: {prompt_path}")
    return _read_file_cached(prompt_path)


class PromptAssembler:
    """Assemble current identity, capability, and workspace observation layers."""

    def __init__(
        self,
        *,
        prompt_name: Optional[str],
        custom_prompt: Optional[str],
        conversation_id: str,
        working_directory: Optional[str],
        include_memory: bool,
        observer_id: str = "",
    ):
        self.prompt_name = prompt_name
        self.custom_prompt = custom_prompt
        self.conversation_id = conversation_id
        self.working_directory = str(
            Path(working_directory or os.getcwd()).resolve()
        )
        self.include_memory = include_memory
        self.observer_id = observer_id or conversation_id

    @staticmethod
    def _source(kind: str, content: str, path: Optional[Path] = None) -> PromptSource:
        return PromptSource(
            kind=kind,
            revision=f"sha256:{_sha256_text(content)}",
            path=str(path) if path is not None else None,
        )

    def _base_prompt(self) -> tuple[str, PromptSource]:
        if self.custom_prompt is not None:
            content = self.custom_prompt
            return content, self._source("custom_role", content)
        if not self.prompt_name:
            raise ValueError("Agent 未声明 prompt_name，也没有提供自定义 prompt")
        prompt_path = PROMPTS_DIR / f"{self.prompt_name}.md"
        content = load_role_prompt(self.prompt_name)
        return content, self._source("role", content, prompt_path)

    def _agents_md_sections(self) -> list[tuple[str, str, PromptSource]]:
        cfg = get_config()
        candidates = (
            ("global_agents_md", "全局", Path(cfg.config_file).parent / "AGENTS.md"),
            ("workspace_agents_md", "项目", Path(self.working_directory) / "AGENTS.md"),
        )
        sections = []
        seen_paths: set[Path] = set()
        for kind, label, path in candidates:
            resolved = path.resolve()
            if resolved in seen_paths or not resolved.is_file():
                continue
            seen_paths.add(resolved)
            try:
                content = _read_file_cached(resolved)
            except Exception as exc:
                print(f"[PromptAssembler] 读取 {label} AGENTS.md 失败: {exc}")
                continue
            if content.strip():
                sections.append(
                    (label, content.strip(), self._source(kind, content, resolved))
                )
        return sections

    def _memory_section(self) -> tuple[str, PromptSource] | None:
        if not self.include_memory:
            return None
        manager = get_memory_manager(conversation_id=self.conversation_id)
        if not manager.memory_path.exists():
            return None
        try:
            content = _read_file_cached(manager.memory_path)
        except Exception as exc:
            print(f"[PromptAssembler] 读取 MEMORY.md 失败: {exc}")
            return None
        if not content.strip():
            return None
        return content.strip(), self._source("memory", content, manager.memory_path)

    def _skill_manifest(self) -> tuple[list[dict], PromptSource] | None:
        """Read skill metadata at request time and revision the full SKILL.md files.

        逐个 read_text + YAML 解析 + sha256 开销大，按目录签名缓存：
        任一 SKILL.md 的 (path, mtime_ns, size) 变化才重新解析。
        """

        if not SKILLS_DIR.is_dir():
            return None
        signature_entries = []
        for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            try:
                stat = skill_file.stat()
            except OSError:
                continue
            signature_entries.append(
                (
                    skill_file.relative_to(SKILLS_DIR).as_posix(),
                    stat.st_mtime_ns,
                    stat.st_size,
                )
            )
        signature = tuple(signature_entries)
        cache_key = str(SKILLS_DIR)
        with _FILE_CACHE_LOCK:
            cached = _SKILL_MANIFEST_CACHE.get(cache_key)
            if cached is not None and cached[0] == signature:
                return cached[1]
        result = self._build_skill_manifest()
        if result is not None:
            with _FILE_CACHE_LOCK:
                _SKILL_MANIFEST_CACHE[cache_key] = (signature, result)
        return result

    def _build_skill_manifest(self) -> tuple[list[dict], PromptSource] | None:
        """逐文件解析 skills 目录，构建 manifest 与 revision source。"""
        manifest = []
        revision_inputs = []
        for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            try:
                raw = skill_file.read_text(encoding="utf-8")
            except OSError:
                continue
            metadata: dict = {}
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) == 3:
                    try:
                        parsed = yaml.safe_load(parts[1]) or {}
                    except yaml.YAMLError:
                        parsed = {}
                    if isinstance(parsed, dict):
                        metadata = parsed
            name = str(metadata.get("name") or skill_file.parent.name).strip()
            description = str(metadata.get("description") or "").strip()
            manifest.append(
                {
                    "name": name,
                    "description": description,
                }
            )
            revision_inputs.append(
                {
                    "path": skill_file.relative_to(SKILLS_DIR).as_posix(),
                    "sha256": _sha256_text(raw),
                }
            )
        if not manifest:
            return None
        payload = json.dumps(
            revision_inputs,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return manifest, self._source("skills", payload, SKILLS_DIR)

    @staticmethod
    def _normalize_device_snapshot(devices: Iterable[dict]) -> tuple[list[dict], list[dict]]:
        capabilities = []
        environment = []
        for raw in devices:
            if not isinstance(raw, dict):
                continue
            capability_items = []
            for item in raw.get("capabilities", []):
                if not isinstance(item, dict) or not item.get("available", True):
                    continue
                capability_items.append(
                    {
                        "name": str(item.get("name", "")),
                        "schema_version": int(item.get("schema_version", 1)),
                        "risk": str(item.get("risk", "read")),
                        "requires_approval": bool(
                            item.get("requires_approval", False)
                        ),
                    }
                )
            capability_items.sort(key=lambda item: item["name"])
            capabilities.append(
                {
                    "device_id": str(raw.get("device_id", "")),
                    "display_name": str(raw.get("display_name", ""))[:100],
                    "state": str(raw.get("state", "offline")),
                    "capability_revision": int(
                        raw.get("capability_revision", 0)
                    ),
                    "capabilities": capability_items,
                }
            )
            environment.append(
                {
                    "device_id": str(raw.get("device_id", "")),
                    "workspace_revision": int(
                        raw.get("workspace_revision", 0)
                    ),
                    "config_revision": int(raw.get("config_revision", 0)),
                    "last_seen_at": str(raw.get("last_seen_at", "")),
                    "recent_observations": list(
                        raw.get("recent_observations", [])
                    )[-20:],
                }
            )
        capabilities.sort(key=lambda item: item["device_id"])
        environment.sort(key=lambda item: item["device_id"])
        return capabilities, environment

    def _workspace_observation(
        self,
        device_environment: list[dict],
    ) -> tuple[dict, str]:
        root = Path(self.working_directory)
        try:
            observation = observe_workspace(
                root,
                observer_id=self.observer_id,
            )
            listing = (
                "\n".join(observation.top_level_entries)
                if observation.top_level_entries
                else "<空目录>"
            )
            change_lines = [
                f"- {item['change']}: {item['path']}"
                for item in observation.changes
            ]
            recent_changes = (
                "\n".join(change_lines) if change_lines else "<本进程内未观察到新变化>"
            )
            scan_note = (
                f"扫描条目={observation.entry_count}"
                + ("（已截断）" if observation.truncated else "")
            )
            workspace_revision = observation.revision
        except Exception:
            listing = "<无法读取目录内容>"
            recent_changes = "<无法计算>"
            scan_note = "扫描失败"
            workspace_revision = "unavailable"
        device_section = ""
        if device_environment:
            rendered = json.dumps(
                device_environment,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            device_section = (
                "\n\n【Android Device environment observation】\n"
                f"{rendered}"
            )
        return (
            {
                "role": "system",
                "content": (
                "【当前工作区 observation】\n"
                f"workspace_revision={workspace_revision}\n"
                f"working_directory={self.working_directory}\n"
                f"{scan_note}\n"
                f"顶层内容:\n{listing}\n"
                f"最近变化:\n{recent_changes}\n"
                "任务描述可以引用绝对路径；text_reader、edit_file、text_writer "
                "的 filepath 必须相对此工作目录。"
                f"{device_section}"
                ),
            },
            workspace_revision,
        )

    def assemble(
        self,
        capability_names: Iterable[str] = (),
        *,
        capability_schemas: Iterable[dict] | None = None,
        device_snapshot: Iterable[dict] = (),
        web_search_available: bool = False,
    ) -> PromptAssembly:
        tool_names = tuple(sorted({name for name in capability_names if name}))
        normalized_schemas = list(capability_schemas or ())
        capability_source = normalized_schemas if normalized_schemas else tool_names
        capability_payload = json.dumps(
            capability_source,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        capability_revision = f"sha256:{_sha256_text(capability_payload)}"
        device_capabilities, device_environment = (
            self._normalize_device_snapshot(device_snapshot)
        )

        base_prompt, base_source = self._base_prompt()
        identity_sections = [base_prompt.strip()]
        sources = [base_source]

        memory = self._memory_section()
        if memory is not None:
            memory_text, memory_source = memory
            identity_sections.append(
                "## 长期记忆（从过往任务中积累的经验）\n\n"
                "以下经验来自 MEMORY.md，在执行任务时优先遵循：\n\n"
                f"{memory_text}\n\n"
                "如果从这些经验中学到了新的可复用原则，请调用 "
                "`update_memory` 工具更新记忆。"
            )
            sources.append(memory_source)

        agents_sections = self._agents_md_sections()
        if agents_sections:
            rendered_agents = []
            for label, content, source in agents_sections:
                rendered_agents.append(f"### {label} AGENTS.md\n\n{content}")
                sources.append(source)
            identity_sections.append(
                "## 用户自定义指令（AGENTS.md）\n\n"
                "以下内容来自用户编写的 AGENTS.md，在执行任务时优先遵循：\n\n"
                + "\n\n".join(rendered_agents)
            )

        skills = self._skill_manifest()
        if skills is not None:
            skill_manifest, skill_source = skills
            identity_sections.append(
                "## 当前 skill manifest\n\n"
                + "\n".join(
                    f"- {item['name']}: {item['description']}"
                    for item in skill_manifest
                )
            )
            sources.append(skill_source)

        if device_capabilities:
            rendered_devices = []
            for device in device_capabilities:
                names = ", ".join(
                    item["name"] for item in device["capabilities"]
                ) or "<无>"
                rendered_devices.append(
                    f"- {device['device_id']} ({device['display_name']}, "
                    f"{device['state']}): {names}"
                )
            identity_sections.append(
                "## 当前 Android device capability snapshot\n\n"
                + "\n".join(rendered_devices)
            )
            device_payload = json.dumps(
                device_capabilities,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            sources.append(
                PromptSource(
                    kind="device_capabilities",
                    revision=f"sha256:{_sha256_text(device_payload)}",
                )
            )

        identity_sections.append(
            "## 当前可用工具\n\n"
            + (
                "\n".join(f"- {name}" for name in tool_names)
                if tool_names
                else "本次请求没有可用工具。"
            )
        )
        sources.append(
            PromptSource(
                kind="capabilities",
                revision=capability_revision,
            )
        )

        if web_search_available:
            identity_sections.append(_WEB_SEARCH_GUIDANCE)
            sources.append(
                PromptSource(
                    kind="web_search_guidance",
                    revision=f"sha256:{_sha256_text(_WEB_SEARCH_GUIDANCE)}",
                )
            )

        if "agent_hub" in tool_names:
            identity_sections.append(_AGENT_HUB_GUIDANCE)
            sources.append(
                PromptSource(
                    kind="agent_hub_guidance",
                    revision=f"sha256:{_sha256_text(_AGENT_HUB_GUIDANCE)}",
                )
            )

        revision_payload = json.dumps(
            [source.to_dict() for source in sources],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        prompt_revision = f"sha256:{_sha256_text(revision_payload)}"
        identity_message = {
            "role": "system",
            "content": "\n\n".join(identity_sections),
        }
        workspace_observation, workspace_revision = (
            self._workspace_observation(device_environment)
        )
        config_path = Path(get_config().config_file)
        try:
            config_revision = (
                f"sha256:{_sha256_text(_read_file_cached(config_path))}"
            )
        except OSError:
            config_revision = "missing"

        return PromptAssembly(
            prompt_revision=prompt_revision,
            capability_revision=capability_revision,
            identity_messages=(identity_message,),
            observation_messages=(workspace_observation,),
            sources=tuple(sources),
            tool_names=tool_names,
            working_directory=self.working_directory,
            environment_revisions={
                "workspace": workspace_revision,
                "server_config": config_revision,
                "devices": [
                    {
                        "device_id": item["device_id"],
                        "workspace_revision": item["workspace_revision"],
                        "config_revision": item["config_revision"],
                    }
                    for item in device_environment
                ],
            },
        )

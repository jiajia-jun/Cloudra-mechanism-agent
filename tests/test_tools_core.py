import ast
import os
from pathlib import Path

import pytest

from cloudra.subagents.registry import SUBAGENT_REGISTRY
from cloudra.tools import get_tools_lst
from cloudra.tools.registry import TOOL_REGISTRY


def _modules_with_get_class(package_dir: Path) -> set[str]:
    project_root = package_dir.parents[1]
    modules = set()
    for source_file in package_dir.rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "get_class"
            for node in tree.body
        ):
            relative = source_file.relative_to(project_root).with_suffix("")
            modules.add(".".join(relative.parts))
    return modules


def test_explicit_builtin_registries_are_complete_and_unique():
    tool_targets = [(entry.module, entry.class_name) for entry in TOOL_REGISTRY]
    subagent_ids = [entry.agent_id for entry in SUBAGENT_REGISTRY]
    subagent_targets = [
        (entry.module, entry.class_name) for entry in SUBAGENT_REGISTRY
    ]

    assert len(tool_targets) == len(set(tool_targets))
    assert len(subagent_ids) == len(set(subagent_ids))
    assert len(subagent_targets) == len(set(subagent_targets))

    project_root = Path(__file__).resolve().parents[1]
    assert {target[0] for target in tool_targets} == _modules_with_get_class(
        project_root / "cloudra" / "tools"
    )
    assert {target[0] for target in subagent_targets} == _modules_with_get_class(
        project_root / "cloudra" / "subagents"
    )


def test_tool_loading():
    """测试工具加载机制和缓存。"""
    tools = get_tools_lst()
    assert len(tools) > 0
    assert any(t.tool_name == 'bash' for t in tools)
    assert any(t.tool_name == 'edit' for t in tools)

    # 测试缓存
    tools_again = get_tools_lst()
    assert tools is tools_again


def test_skill_loader_cache_invalidates_when_manifest_changes(
    tmp_path,
    monkeypatch,
):
    from cloudra.base import skill_class

    skills = tmp_path / "skills"
    skill_file = skills / "live" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: live\ndescription: v1\n---\ncontent-v1",
        encoding="utf-8",
    )
    monkeypatch.setattr(skill_class.skill_loader, "base_path", str(skills))
    skill_class._SKILL_DATAS_CACHE.clear()

    assert skill_class.skill_loader().get_content("live") == "content-v1"
    skill_file.write_text(
        "---\nname: live\ndescription: v2\n---\ncontent-v2",
        encoding="utf-8",
    )
    assert skill_class.skill_loader().get_content("live") == "content-v2"

@pytest.mark.asyncio
async def test_bash_permission():
    """测试 bash 的权限识别。"""
    from cloudra.tools.Bashtool.bash import Bash
    tool = Bash()

    # review 修复：subagent 为 None 时不再默认放行全部权限，只允许只读命令，
    # 防止注入空子 Agent 获得完整执行权限。
    assert tool.has_command_permission("ls -la") is True
    assert tool.has_command_permission("rm -rf /") is False

def test_write_schema():
    """测试 Write 的 Schema 校验。"""
    from cloudra.tools.Writetool.write import Write, Write_input_schema
    tool = Write()

    # 正确参数
    input_data = Write_input_schema(path="test.txt", content="hello")
    assert input_data.path == "test.txt"
    assert input_data.expected_sha256 == "missing"

    # 验证 tool 属性
    assert tool.tool_name == 'write'
    assert tool.is_write() is True


def test_edit_schema_keeps_nested_operation_definition():
    from cloudra.tools.Writetool.edit import Edit_input_schema

    parameters = Edit_input_schema.to_parameters_schema()
    assert parameters["properties"]["edits"]["items"]["$ref"] == "#/$defs/EditOperation"
    assert parameters["$defs"]["EditOperation"]["additionalProperties"] is False


def test_write_multiline_parsing():
    """回归测试：LLM 返回的含未转义换行符的 JSON 参数应能被正确解析并保留换行。"""
    import json

    from cloudra.tools.Writetool.write import Write_input_schema

    # 模拟 LLM 生成的 arguments 中直接包含换行符（未转义）
    raw_args = '{"path": "multi.txt", "content": "line1\nline2\nline3"}'
    parsed = json.loads(raw_args, strict=False)
    input_data = Write_input_schema(**parsed)
    assert input_data.content == "line1\nline2\nline3"


def test_subagent_hash_caching():
    """测试 Subagent_hash 在同进程内复用缓存。"""
    from cloudra.subagents import Subagent_hash

    h1 = Subagent_hash()
    h2 = Subagent_hash()
    # 复用缓存，字典对象应为同一个
    assert h1.subagents_dict is h2.subagents_dict
    assert hasattr(h1, 'a-1') or 'a-1' in h1.subagents_dict


def test_web_fetch_schema():
    """测试 WebFetcher 工具 Schema 与 HTML 文本提取。"""
    from cloudra.tools.Browsertool.web_fetch import WebFetcher, WebFetcher_input_schema, _HTMLTextExtractor

    tool = WebFetcher()
    assert tool.tool_name == 'web_fetch'
    assert tool.is_read() is True

    inp = WebFetcher_input_schema(url='https://example.com')
    assert inp.url == 'https://example.com'
    assert inp.extract_text is True

    html = '<html><head><title>Test Page</title></head><body><p>Hello</p><script>alert(1)</script></body></html>'
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    assert extractor.get_title() == 'Test Page'
    assert extractor.get_text() == 'Hello'


def test_browser_schema():
    """测试 HeadlessBrowser 工具 Schema。"""
    from cloudra.tools.Browsertool.browser import HeadlessBrowser, HeadlessBrowser_input_schema

    tool = HeadlessBrowser()
    assert tool.tool_name == 'browser'
    assert tool.is_read() is True

    inp = HeadlessBrowser_input_schema(url='https://example.com', action='fetch')
    assert inp.url == 'https://example.com'
    assert inp.action == 'fetch'
    assert inp.max_length == 0


class TestWebFetcherGuards:
    """web_fetch 的 PDF 防护；正文不截断。"""

    @staticmethod
    def _resp(content: bytes, content_type: str, status: int = 200):
        import types
        return types.SimpleNamespace(
            content=content,
            text=content.decode("utf-8", errors="replace"),
            headers={"content-type": content_type},
            status_code=status,
            raise_for_status=lambda: None,
        )

    @staticmethod
    def _client(resp):
        class _C:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def request(self, **kwargs):
                return resp

        return _C

    @pytest.mark.asyncio
    async def test_pdf_rejected_with_guidance(self, monkeypatch):
        from cloudra.tools.Browsertool.web_fetch import WebFetcher, WebFetcher_input_schema

        resp = self._resp(b"%PDF-1.7 fake\n" + b"\x00" * 100, "application/pdf")
        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: self._client(resp)())
        result = await WebFetcher().tool_call(
            WebFetcher_input_schema(url="https://x.com/a.pdf"), None
        )
        assert result.is_success is False
        assert "pdf2md" in result.error and "download_path" in result.error

    @pytest.mark.asyncio
    async def test_pdf_detected_by_magic_bytes(self, monkeypatch):
        resp = self._resp(b"%PDF-1.3 xxx\n" + b"0" * 50, "application/octet-stream")
        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: self._client(resp)())
        from cloudra.tools.Browsertool.web_fetch import WebFetcher, WebFetcher_input_schema
        result = await WebFetcher().tool_call(
            WebFetcher_input_schema(url="https://x.com/download?id=1"), None
        )
        assert result.is_success is False and "pdf2md" in result.error

    @pytest.mark.asyncio
    async def test_giant_html_not_truncated(self, monkeypatch):
        html = ("<html><body><p>" + "x" * 250_000 + "</p></body></html>").encode()
        resp = self._resp(html, "text/html; charset=utf-8")
        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: self._client(resp)())
        from cloudra.tools.Browsertool.web_fetch import WebFetcher, WebFetcher_input_schema
        result = await WebFetcher().tool_call(
            WebFetcher_input_schema(url="https://x.com/page"), None
        )
        assert result.is_success is True
        assert result.content.count("x") == 250_000
        assert "已截断" not in result.content


@pytest.mark.asyncio
async def test_bash_oversized_output_offloads_to_workspace(tmp_path, mock_session):
    """超大 stdout 落盘到 .cloudra/tool_output/，observation 只回截断摘要 + 路径。"""
    from types import SimpleNamespace

    from cloudra.tools.Bashtool.bash import Bash, Bash_input_schema
    from cloudra.tools.core.observation_offload import MAX_OBSERVATION_CHARS, TOOL_OUTPUT_DIR
    from cloudra.tools.core.permission_model import Permission

    big = "x" * (MAX_OBSERVATION_CHARS + 5_000) + "\n"
    (tmp_path / "big.txt").write_text(big, encoding="utf-8")

    subagent = SimpleNamespace(
        working_directory=str(tmp_path),
        permission_all=lambda: (
            Permission.READ | Permission.WRITE | Permission.SCRIPT | Permission.DESTRUCTIVE
        ),
    )
    tool = Bash(subagent=subagent)
    result = await tool.tool_call(
        Bash_input_schema(command="cat big.txt", task_description="read big file"),
        mock_session,
    )

    assert result.exit_code == 0
    assert len(result.result) < MAX_OBSERVATION_CHARS
    assert "`read`" in result.result
    assert "offset" in result.result
    assert TOOL_OUTPUT_DIR.replace(os.sep, "/") in result.result

    dumped = list((tmp_path / TOOL_OUTPUT_DIR).glob("bash-*.log"))
    assert len(dumped) == 1
    assert dumped[0].read_text(encoding="utf-8") == big


@pytest.mark.asyncio
async def test_bash_oversized_output_fallback_truncates(tmp_path, mock_session, monkeypatch):
    """落盘失败时优雅降级为纯截断并注明，工具本身不炸。"""
    from types import SimpleNamespace

    import cloudra.tools.core.observation_offload as offload_mod
    from cloudra.tools.Bashtool.bash import Bash, Bash_input_schema
    from cloudra.tools.core.observation_offload import MAX_OBSERVATION_CHARS
    from cloudra.tools.core.permission_model import Permission

    (tmp_path / "big.txt").write_text("y" * (MAX_OBSERVATION_CHARS + 5_000), encoding="utf-8")

    def _failing_write(path, content, encoding="utf-8"):
        raise OSError("disk full")

    monkeypatch.setattr(offload_mod, "atomic_write_text", _failing_write)
    subagent = SimpleNamespace(
        working_directory=str(tmp_path),
        permission_all=lambda: (
            Permission.READ | Permission.WRITE | Permission.SCRIPT | Permission.DESTRUCTIVE
        ),
    )
    tool = Bash(subagent=subagent)
    result = await tool.tool_call(
        Bash_input_schema(command="cat big.txt", task_description="read big file"),
        mock_session,
    )

    assert result.exit_code == 0
    assert len(result.result) < MAX_OBSERVATION_CHARS
    assert "could not be saved" in result.result


@pytest.mark.asyncio
async def test_bash_small_output_untouched(tmp_path, mock_session):
    """阈值以下的输出原样返回，不触发落盘。"""
    from types import SimpleNamespace

    from cloudra.tools.Bashtool.bash import Bash, Bash_input_schema
    from cloudra.tools.core.permission_model import Permission

    subagent = SimpleNamespace(
        working_directory=str(tmp_path),
        permission_all=lambda: Permission.READ,
    )
    tool = Bash(subagent=subagent)
    result = await tool.tool_call(
        Bash_input_schema(command="ls", task_description="list files"),
        mock_session,
    )

    assert result.exit_code == 0
    assert "Full output" not in result.result
    assert not (tmp_path / ".cloudra").exists()

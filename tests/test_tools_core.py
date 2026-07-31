import ast
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
    assert any(t.tool_name == 'bashtools' for t in tools)
    assert any(t.tool_name == 'edit_file' for t in tools)

    # 测试缓存
    tools_again = get_tools_lst()
    assert tools is tools_again


def test_skill_loader_cache_invalidates_when_manifest_changes(
    tmp_path,
    monkeypatch,
):
    from cloudra import skill_class

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
async def test_bashtools_permission():
    """测试 bashtools 的权限识别。"""
    from cloudra.tools.Bashtool.bashtools import Bashtools
    tool = Bashtools()

    # review 修复：subagent 为 None 时不再默认放行全部权限，只允许只读命令，
    # 防止注入空子 Agent 获得完整执行权限。
    assert tool.has_command_permission("ls -la") is True
    assert tool.has_command_permission("rm -rf /") is False

def test_text_writer_schema():
    """测试 TextWriter 的 Schema 校验。"""
    from cloudra.tools.Writetool.text_writer import TextWriter, TextWriter_input_schema
    tool = TextWriter()

    # 正确参数
    input_data = TextWriter_input_schema(filepath="test.txt", content="hello")
    assert input_data.filepath == "test.txt"
    assert input_data.expected_sha256 == "missing"

    # 验证 tool 属性
    assert tool.tool_name == 'text_writer'
    assert tool.is_write() is True


def test_edit_file_schema_keeps_nested_operation_definition():
    from cloudra.tools.Writetool.edit_file import EditFile_input_schema

    parameters = EditFile_input_schema.to_parameters_schema()
    assert parameters["properties"]["edits"]["items"]["$ref"] == "#/$defs/EditOperation"
    assert parameters["$defs"]["EditOperation"]["additionalProperties"] is False


def test_text_writer_multiline_parsing():
    """回归测试：LLM 返回的含未转义换行符的 JSON 参数应能被正确解析并保留换行。"""
    import json

    from cloudra.tools.Writetool.text_writer import TextWriter_input_schema

    # 模拟 LLM 生成的 arguments 中直接包含换行符（未转义）
    raw_args = '{"filepath": "multi.txt", "content": "line1\nline2\nline3"}'
    parsed = json.loads(raw_args, strict=False)
    input_data = TextWriter_input_schema(**parsed)
    assert input_data.content == "line1\nline2\nline3"


def test_subagent_hash_caching():
    """测试 Subagent_hash 在同进程内复用缓存。"""
    from cloudra.subagents import Subagent_hash

    h1 = Subagent_hash()
    h2 = Subagent_hash()
    # 复用缓存，字典对象应为同一个
    assert h1.subagents_dict is h2.subagents_dict
    assert hasattr(h1, 'a-1') or 'a-1' in h1.subagents_dict


def test_web_fetcher_schema():
    """测试 WebFetcher 工具 Schema 与 HTML 文本提取。"""
    from cloudra.tools.Browsertool.web_fetcher import WebFetcher, WebFetcher_input_schema, _HTMLTextExtractor

    tool = WebFetcher()
    assert tool.tool_name == 'web_fetcher'
    assert tool.is_read() is True

    inp = WebFetcher_input_schema(url='https://example.com')
    assert inp.url == 'https://example.com'
    assert inp.extract_text is True

    html = '<html><head><title>Test Page</title></head><body><p>Hello</p><script>alert(1)</script></body></html>'
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    assert extractor.get_title() == 'Test Page'
    assert extractor.get_text() == 'Hello'


def test_headless_browser_schema():
    """测试 HeadlessBrowser 工具 Schema。"""
    from cloudra.tools.Browsertool.headless_browser import HeadlessBrowser, HeadlessBrowser_input_schema

    tool = HeadlessBrowser()
    assert tool.tool_name == 'headless_browser'
    assert tool.is_read() is True

    inp = HeadlessBrowser_input_schema(url='https://example.com', action='fetch')
    assert inp.url == 'https://example.com'
    assert inp.action == 'fetch'


class TestWebFetcherGuards:
    """web_fetcher 的 PDF/体积防护。"""

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
        from cloudra.tools.Browsertool.web_fetcher import WebFetcher, WebFetcher_input_schema

        resp = self._resp(b"%PDF-1.7 fake\n" + b"\x00" * 100, "application/pdf")
        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: self._client(resp)())
        result = await WebFetcher().tool_call(
            WebFetcher_input_schema(url="https://x.com/a.pdf"), None
        )
        assert result.success is False
        assert "pdf2md" in result.error and "download_path" in result.error

    @pytest.mark.asyncio
    async def test_pdf_detected_by_magic_bytes(self, monkeypatch):
        resp = self._resp(b"%PDF-1.3 xxx\n" + b"0" * 50, "application/octet-stream")
        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: self._client(resp)())
        from cloudra.tools.Browsertool.web_fetcher import WebFetcher, WebFetcher_input_schema
        result = await WebFetcher().tool_call(
            WebFetcher_input_schema(url="https://x.com/download?id=1"), None
        )
        assert result.success is False and "pdf2md" in result.error

    @pytest.mark.asyncio
    async def test_giant_html_truncated(self, monkeypatch):
        html = ("<html><body><p>" + "内容 " * 300000 + "</p></body></html>").encode()
        resp = self._resp(html, "text/html; charset=utf-8")
        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: self._client(resp)())
        from cloudra.tools.Browsertool.web_fetcher import WebFetcher, WebFetcher_input_schema
        result = await WebFetcher().tool_call(
            WebFetcher_input_schema(url="https://x.com/page"), None
        )
        assert result.success is True
        assert len(result.content) <= 210_000
        assert "已截断" in result.content

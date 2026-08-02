"""harness 健壮性加固的钉板测试（对应后端审计 Top 6 修复）：

1. context_window / timeout 进 config，废除 1,000,000 硬编码（agent.py / config.py）
2. 工具参数 Pydantic 校验失败回喂 LLM，不再穿透主循环（react.py act_result）
3. LLM 传输层：AsyncOpenAI 传 timeout + max_retries=0；重试/fallback 触发 on_status 事件
4. bashtools 返回 exit_code，超长输出首尾保留截断
5. 主循环死循环检测（相同签名连续调用先警告后终止）+ 步数预算
6. 上下文压缩持久化：梗概写回存储，不再每轮重摘要；旧梗概折叠进新梗概

全部使用临时 DB / mock LLM，禁止真实网络。
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest

from cloudra.config import get_config
from cloudra.database import ConversationDB
from cloudra.llm_client import LLMClient
from cloudra.react import AgentStuckLoop, MaxStepsExceeded
from cloudra.tools import ToolEntry
from cloudra.tools_class import Tool, input_schema, output_schema

# ---------------------------------------------------------------------------
# react 测试夹具（与 test_react_dispatch 同模式）
# ---------------------------------------------------------------------------

class _EchoInput(input_schema):
    text: str


class _CountInput(input_schema):
    count: int


class _EchoOutput(output_schema):
    message: str
    is_success: bool = True


class _EchoTool(Tool):
    tool_id: str = "t-echo"
    tool_name: str = "echo_tool"
    tool_description: str = "回显输入文本"
    input_schema: Any = _EchoInput
    output_schema: Any = _EchoOutput

    async def tool_call(self, user_input, session):
        return _EchoOutput(message=f"echo:{user_input.text}")


class _CountTool(Tool):
    tool_id: str = "t-count"
    tool_name: str = "count_tool"
    tool_description: str = "要求整数参数"
    input_schema: Any = _CountInput
    output_schema: Any = _EchoOutput

    async def tool_call(self, user_input, session):
        return _EchoOutput(message=f"count:{user_input.count}")


def _make_react(tmp_path, monkeypatch, tool_classes, conv_id="test-hardening"):
    from cloudra.agent import Follower
    from cloudra.react import reAct

    db_path = str(tmp_path / "test.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr("cloudra.react.get_database_path", lambda _cid: db_path)
    monkeypatch.setattr("cloudra.react.get_tools_lst", lambda: [ToolEntry(
        cls=cls,
        tool_name=cls._get_field_default("tool_name") or "",
        tool_id=cls._get_field_default("tool_id") or "",
        input_schema=cls._get_field_default("input_schema"),
    ) for cls in tool_classes])

    agent = Follower(
        id="a-test",
        name="tester",
        prompt="测试",
        query="测试问题",
        conversation_id=conv_id,
    )
    return reAct(agent), agent


def _tc(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


# ---------------------------------------------------------------------------
# 1. context_window / timeout 配置化
# ---------------------------------------------------------------------------

class TestContextWindowConfig:
    def test_window_and_timeout_come_from_config(self, monkeypatch):
        from cloudra.agent import Coordinator, Follower

        cfg = get_config()
        monkeypatch.setattr(cfg.coordinator, "context_window", 64000)
        monkeypatch.setattr(cfg.coordinator, "timeout", 77)
        monkeypatch.setattr(cfg.follower, "context_window", 32000)

        coordinator = Coordinator(prompt="p", query="q", conversation_id="t-cfg")
        follower = Follower(id="a-x", name="x", prompt="p", query="q", conversation_id="t-cfg")

        assert coordinator.context_window == 64000
        assert follower.context_window == 32000
        assert coordinator._get_llm_client().timeout == 77

    def test_explicit_window_overrides_config(self, monkeypatch):
        from cloudra.agent import Follower

        monkeypatch.setattr(get_config().follower, "context_window", 32000)
        follower = Follower(
            id="a-x", name="x", prompt="p", query="q",
            conversation_id="t-cfg", context_window=999,
        )
        assert follower.context_window == 999

    def test_yaml_roundtrip_keeps_new_fields(self, tmp_path, monkeypatch):
        import cloudra.config as config_mod

        monkeypatch.setenv("CLOUDRA_CONFIG_FILE", str(tmp_path / "config.yaml"))
        cfg = config_mod.reload_config()
        cfg.coordinator.context_window = 200000
        cfg.coordinator.timeout = 45
        cfg.save()

        reloaded = config_mod.reload_config()
        assert reloaded.coordinator.context_window == 200000
        assert reloaded.coordinator.timeout == 45

    @pytest.mark.asyncio
    async def test_half_window_budget_includes_tools_and_observations(
        self, monkeypatch
    ):
        """Schema/observation 必须在 50% 自动压缩阈值内，而非事后追加。"""
        from types import SimpleNamespace

        from cloudra.agent import Coordinator
        from cloudra.token_estimator import TokenEstimator

        agent = Coordinator(
            prompt="p",
            query="q",
            conversation_id="budget-overhead",
            context_window=20_000,
        )
        schemas = [{"type": "function", "function": {"description": "s" * 4_000}}]
        observations = ({"role": "system", "content": "o" * 4_000},)
        assembly = SimpleNamespace(
            identity_messages=({"role": "system", "content": "identity"},),
            observation_messages=observations,
        )
        captured = {}

        class FakeCM:
            async def build_messages(self, **kwargs):
                captured.update(kwargs)
                return list(assembly.identity_messages)

        monkeypatch.setattr(type(agent), "_get_tools_schema", lambda self: schemas)
        monkeypatch.setattr(
            type(agent),
            "_prompt_assembler",
            lambda self: SimpleNamespace(assemble=lambda *args, **kwargs: assembly),
        )
        monkeypatch.setattr(type(agent), "_ensure_context_manager", lambda self: FakeCM())

        messages = await agent._build_messages()
        overhead = TokenEstimator.estimate_text(json.dumps(schemas, ensure_ascii=False))
        overhead += TokenEstimator.estimate_messages(list(observations))
        assert captured["max_context_tokens"] == 10_000 - overhead
        assert messages[-1] == observations[0]


# ---------------------------------------------------------------------------
# 2. 参数校验失败回喂 LLM
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestValidationErrorFeedback:
    async def test_schema_validation_error_fed_back_not_raised(self, tmp_path, monkeypatch):
        """LLM 传错参数类型：错误作为 tool 消息回喂，任务不崩。"""
        react, agent = _make_react(tmp_path, monkeypatch, [_CountTool])

        stopped = await react.act_result([_tc("c1", "count_tool", '{"count": "not-a-number"}')])

        assert stopped is False
        assert react._continue is True
        context = await agent.get_context()
        tool_msgs = [m for m in context if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "c1"
        assert "参数校验失败" in tool_msgs[0]["content"]
        assert "count_tool" in tool_msgs[0]["content"]

    async def test_valid_call_alongside_invalid_still_runs(self, tmp_path, monkeypatch):
        """一个调用参数非法不影响同批其他调用执行。"""
        react, agent = _make_react(tmp_path, monkeypatch, [_CountTool, _EchoTool])

        await react.act_result([
            _tc("c1", "count_tool", '{"count": "bad"}'),
            _tc("c2", "echo_tool", '{"text": "ok"}'),
        ])

        context = await agent.get_context()
        tool_msgs = [m for m in context if m.get("role") == "tool"]
        assert len(tool_msgs) == 2
        assert "参数校验失败" in tool_msgs[0]["content"]
        assert "echo:ok" in tool_msgs[1]["content"]


# ---------------------------------------------------------------------------
# 3. LLM 传输层 timeout 与状态事件
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTransportStatus:
    async def test_openai_client_constructed_with_timeout_and_no_sdk_retry(self, monkeypatch):
        """AsyncOpenAI 必须显式传 timeout（不再落到 SDK 默认 600s），
        且关掉 SDK 静默重试（统一由 create_with_retry 处理，保证重试可见）。"""
        captured = {}

        def _fake_openai(**kwargs):
            captured.update(kwargs)
            client = MagicMock()
            client.chat.completions.create = AsyncMock(return_value=MagicMock(usage=None))
            return client

        monkeypatch.setattr("cloudra.llm_client.AsyncOpenAI", _fake_openai)
        client = LLMClient(api_key="sk-x", base_url="https://example.invalid/v1", timeout=123)
        await client.create(model="m", messages=[{"role": "user", "content": "hi"}])

        assert captured["timeout"] == 123
        assert captured["max_retries"] == 0

    async def test_retry_emits_status_event(self, monkeypatch):
        """瞬时错误重试时触发 on_status('llm_retry')，携带次数与延迟信息。"""
        monkeypatch.setattr("cloudra.llm_client.asyncio.sleep", AsyncMock())
        client = LLMClient(api_key="sk-x", base_url="https://example.invalid/v1", max_retries=1)
        statuses = []
        client.on_status = lambda event, data: statuses.append((event, data))

        conn_err = openai.APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
        client.create = AsyncMock(side_effect=[conn_err, "OK"])

        result = await client.create_with_retry(model="m", messages=[])

        assert result == "OK"
        assert len(statuses) == 1
        event, data = statuses[0]
        assert event == "llm_retry"
        assert data["attempt"] == 1
        assert data["max_retries"] == 1
        assert "delay" in data

    async def test_status_hook_exception_swallowed(self):
        """遥测回调自身抛异常绝不能影响传输层。"""
        client = LLMClient(api_key="sk-x", base_url="https://example.invalid/v1")

        def _boom(event, data):
            raise RuntimeError("hook 炸了")

        client.on_status = _boom
        await client._emit_status("llm_error", error="x")  # 不抛异常即通过


# ---------------------------------------------------------------------------
# 4. bashtools exit_code 与输出截断
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestBashExitCode:
    async def test_success_command_exit_code_zero(self):
        from cloudra.tools.Bashtool.bashtools import Bashtools, Bashtools_input_schema

        tool = Bashtools()  # subagent=None：仅只读命令
        out = await tool.tool_call(Bashtools_input_schema(command="echo hello"), session=None)
        assert out.exit_code == 0
        assert "hello" in out.result

    async def test_failing_command_exit_code_nonzero(self):
        from cloudra.tools.Bashtool.bashtools import Bashtools, Bashtools_input_schema

        tool = Bashtools()
        out = await tool.tool_call(
            Bashtools_input_schema(command="ls /nonexistent_dir_xyz_123"), session=None,
        )
        assert out.exit_code != 0
        assert "【命令失败】" in out.result

    async def test_permission_denied_exit_code_126(self):
        from cloudra.tools.Bashtool.bashtools import Bashtools, Bashtools_input_schema

        tool = Bashtools()  # 无 subagent：rm 属于 DESTRUCTIVE，无权执行
        out = await tool.tool_call(Bashtools_input_schema(command="rm some_file"), session=None)
        assert out.exit_code == 126
        assert "没有权限" in out.result

class TestTruncateOutput:
    def test_truncate_output_keeps_head_and_tail(self):
        from cloudra.tools.Bashtool.bashtools import MAX_OUTPUT_CHARS, truncate_output

        text = "头" * (MAX_OUTPUT_CHARS // 2) + "中" * MAX_OUTPUT_CHARS + "尾" * 100
        truncated = truncate_output(text)

        assert len(truncated) < len(text)
        assert truncated.startswith("头")
        assert truncated.endswith("尾" * 100)
        assert "中间省略" in truncated

    def test_truncate_output_short_text_untouched(self):
        from cloudra.tools.Bashtool.bashtools import truncate_output

        assert truncate_output("短文本") == "短文本"


# ---------------------------------------------------------------------------
# 5. 死循环检测与步数预算
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLoopDetection:
    async def test_warn_on_third_identical_call(self, tmp_path, monkeypatch):
        """相同（工具名+参数）签名连续第 3 次调用时注入系统警告。"""
        react, agent = _make_react(tmp_path, monkeypatch, [_EchoTool])
        call = _tc("c1", "echo_tool", '{"text": "same"}')

        for _ in range(react.LOOP_WARN_THRESHOLD):
            await react.act_result([call])

        context = await agent.get_context()
        system_msgs = [m for m in context if m.get("role") == "system"]
        assert any("陷入循环" in str(m.get("content", "")) for m in system_msgs)

    async def test_abort_on_fifth_identical_call(self, tmp_path, monkeypatch):
        """连续第 5 次相同调用直接抛 AgentStuckLoop（在执行前拦截）。"""
        react, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        call = _tc("c1", "echo_tool", '{"text": "same"}')

        with pytest.raises(AgentStuckLoop, match="死循环"):
            for _ in range(react.LOOP_ABORT_THRESHOLD):
                await react.act_result([call])

    async def test_different_args_not_flagged(self, tmp_path, monkeypatch):
        """参数不同的连续调用不算循环。"""
        react, agent = _make_react(tmp_path, monkeypatch, [_EchoTool])

        for i in range(react.LOOP_ABORT_THRESHOLD + 2):
            await react.act_result([_tc(f"c{i}", "echo_tool", json.dumps({"text": f"v{i}"}))])

        context = await agent.get_context()
        system_msgs = [m for m in context if m.get("role") == "system"]
        assert not any("陷入循环" in str(m.get("content", "")) for m in system_msgs)

    async def test_max_steps_raises(self, tmp_path, monkeypatch):
        """步数超过预算上限时抛 MaxStepsExceeded。"""
        react, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        react.step_count = react.MAX_STEPS

        with pytest.raises(MaxStepsExceeded, match="最大步数"):
            await react._run_loop()

    async def test_steps_warning_injected_once(self, tmp_path, monkeypatch):
        """接近预算上限时注入一次收敛警告（不重复）。"""
        react, agent = _make_react(tmp_path, monkeypatch, [_EchoTool])
        react.step_count = react.MAX_STEPS  # 下一步即触发警告 + 超限

        with pytest.raises(MaxStepsExceeded):
            await react._run_loop()

        context = await agent.get_context()
        warnings = [
            m for m in context
            if m.get("role") == "system" and "步数预算" in str(m.get("content", ""))
        ]
        assert len(warnings) == 1


# ---------------------------------------------------------------------------
# 6. 上下文压缩持久化
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPersistentCompression:
    @staticmethod
    def _make_cm(tmp_path):
        from cloudra.context_manager import ContextManager

        cm = ContextManager(
            agent_id="test-agent",
            conversation_id="test-conv-persist",
            prompt="你是一个测试助手。",
            query="初始问题",
        )
        cm.context_file = str(tmp_path / "context.json")
        return cm

    @staticmethod
    def _mock_summary_llm(monkeypatch, text="压缩梗概"):
        from types import SimpleNamespace

        follower = get_config().follower
        monkeypatch.setattr(follower, "model", "fake-model")
        monkeypatch.setattr(follower, "url", "http://fake-llm")
        monkeypatch.setattr(follower, "key", "fake-key")

        create = AsyncMock(return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
        ))
        monkeypatch.setattr("cloudra.context_manager.LLMClient", MagicMock(
            return_value=SimpleNamespace(create=create),
        ))
        return create

    @staticmethod
    async def _fill(cm, long_rounds=12, recent_rounds=10, tag="历史"):
        """填充 long_rounds 轮长历史 + recent_rounds 轮短近期对话。"""
        for i in range(long_rounds):
            await cm.append({"role": "user", "content": f"{tag}问题 {i}: " + "这是历史消息。" * 30})
            await cm.append({"role": "assistant", "content": f"{tag}回复 {i}: " + "这是历史回复。" * 30})
        for i in range(recent_rounds):
            await cm.append({"role": "user", "content": f"{tag}最近问题 {i}: 短"})
            await cm.append({"role": "assistant", "content": f"{tag}最近回复 {i}: 短"})

    async def test_summary_persisted_and_not_resummarized(self, tmp_path, monkeypatch):
        """超预算触发压缩后：梗概写回存储；下一轮 build 不再重复调用 LLM 摘要。"""
        cm = self._make_cm(tmp_path)
        create = self._mock_summary_llm(monkeypatch)
        await self._fill(cm)

        msgs = await cm.build_messages(max_context_tokens=1000)
        assert create.call_count == 1
        contents = [str(m.get("content", "")) for m in msgs]
        assert any("[上下文压缩提示]" in c for c in contents)
        assert not any("历史问题 0" in c for c in contents)

        # 存储中的上下文已是梗概形态（持久化，而非仅当次请求生效）
        stored = await cm.load()
        stored_contents = [str(m.get("content", "")) for m in stored]
        assert any("[上下文压缩提示]" in c for c in stored_contents)
        assert not any("历史问题 0" in c for c in stored_contents)

        # 再次 build：压缩后的上下文已在预算内，不再调 LLM
        await cm.build_messages(max_context_tokens=1000)
        assert create.call_count == 1

    async def test_old_summary_folded_into_next_compression(self, tmp_path, monkeypatch):
        """第二次压缩时，旧梗概被折叠进新梗概的输入，而不是并行累积。"""
        cm = self._make_cm(tmp_path)
        create = self._mock_summary_llm(monkeypatch)
        await self._fill(cm, tag="第一批")

        await cm.build_messages(max_context_tokens=1000)
        assert create.call_count == 1

        # 塞入第二批长历史，再次触发压缩
        await self._fill(cm, tag="第二批")
        await cm.build_messages(max_context_tokens=1000)
        assert create.call_count == 2

        # 第二次梗概的输入包含旧梗概内容（折叠），存储里仍只有一条梗概消息
        second_prompt = create.call_args.kwargs["messages"][1]["content"]
        assert "[上下文压缩提示]" in second_prompt
        stored = await cm.load()
        summaries = [
            m for m in stored
            if m.get("role") == "system"
            and str(m.get("content", "")).startswith("[上下文压缩提示]")
        ]
        assert len(summaries) == 1


# ---------------------------------------------------------------------------
# 7. token usage 聚合事件
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTokenUsageEvents:
    @staticmethod
    def _fake_response():
        """非流式假响应：content 完整、无 tool_calls。"""
        message = MagicMock()
        message.content = "最终答案"
        message.reasoning_content = None
        message.tool_calls = None
        message.model_dump = lambda **_: {"role": "assistant", "content": "最终答案"}
        choice = MagicMock()
        choice.message = message
        choice.finish_reason = "stop"
        response = MagicMock()
        response.choices = [choice]
        return response

    async def test_token_usage_event_emitted_with_running_total(self, tmp_path, monkeypatch):
        """每轮推理后广播 token_usage 事件，total 为跨轮累计值。"""
        import sqlite3
        from types import SimpleNamespace

        react, agent = _make_react(tmp_path, monkeypatch, [_EchoTool])
        agent.is_stream = False
        agent._tools_schema_cache = []
        cm = MagicMock()
        cm.build_messages = AsyncMock(return_value=[{"role": "user", "content": "hi"}])
        cm.load = AsyncMock(return_value=[])
        cm.append = AsyncMock()
        agent.context_manager = cm

        fake_client = SimpleNamespace(
            last_usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
        )
        monkeypatch.setattr(type(agent), "_get_llm_client", lambda self: fake_client)
        monkeypatch.setattr(type(agent), "llm_call", AsyncMock(return_value=self._fake_response()))

        await react._reasoning_once()
        await react._reasoning_once()

        db_path = react.database_path
        with sqlite3.connect(db_path) as con:
            rows = con.execute(
                "SELECT data FROM session_events WHERE session_id=? AND event_type='token_usage'",
                (react.session.id,),
            ).fetchall()
        assert len(rows) == 2
        first = json.loads(rows[0][0])
        second = json.loads(rows[1][0])
        assert first["total"]["total_tokens"] == 120
        assert second["total"]["total_tokens"] == 240  # 累计
        assert second["agent_id"] == "a-test"

    async def test_no_usage_no_event(self, tmp_path, monkeypatch):
        """provider 不返回 usage 时不发事件、不报错。"""
        import sqlite3
        from types import SimpleNamespace

        react, agent = _make_react(tmp_path, monkeypatch, [_EchoTool])
        agent.is_stream = False
        agent._tools_schema_cache = []
        cm = MagicMock()
        cm.build_messages = AsyncMock(return_value=[{"role": "user", "content": "hi"}])
        cm.load = AsyncMock(return_value=[])
        cm.append = AsyncMock()
        agent.context_manager = cm

        monkeypatch.setattr(
            type(agent), "_get_llm_client", lambda self: SimpleNamespace(last_usage=None)
        )
        monkeypatch.setattr(type(agent), "llm_call", AsyncMock(return_value=self._fake_response()))

        await react._reasoning_once()

        with sqlite3.connect(react.database_path) as con:
            rows = con.execute(
                "SELECT COUNT(*) FROM session_events WHERE session_id=? AND event_type='token_usage'",
                (react.session.id,),
            ).fetchone()
        assert rows[0] == 0


# ---------------------------------------------------------------------------
# 8. Supervisor 读取 goal 锚点
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSupervisorGoalAnchor:
    def test_build_prompt_includes_goal_anchor(self):
        """有锚点时 prompt 以锚点为主要审查基准；无锚点时不含该块。"""
        from cloudra.supervisor import Supervisor

        supervisor = Supervisor()
        prompt = supervisor.build_prompt(
            "用户目标", "时间线", [], goal_anchor="【任务目标】完成 DFT 计算\n完成判据: 能量收敛"
        )
        assert "【任务目标】完成 DFT 计算" in prompt
        assert "主要审查基准" in prompt

        prompt_without = supervisor.build_prompt("用户目标", "时间线", [])
        assert "主要审查基准" not in prompt_without

    async def test_review_extracts_anchor_from_context(self, tmp_path, monkeypatch):
        """_supervisor_review 从上下文提取最新 GOAL_MARKER 消息传给 Supervisor。"""
        from types import SimpleNamespace

        from cloudra.tools.Plantool.goal import GOAL_MARKER

        react, agent = _make_react(tmp_path, monkeypatch, [_EchoTool])
        await agent.get_context()
        await agent.update_context({"role": "system", "content": f"{GOAL_MARKER} 旧目标"})
        await agent.update_context({"role": "user", "content": "干活"})
        await agent.update_context({"role": "system", "content": f"{GOAL_MARKER} 新目标"})

        captured = {}

        async def fake_review(user_goal, messages, cases=None, goal_anchor=""):
            captured["goal_anchor"] = goal_anchor
            return SimpleNamespace(verdict="proceed", reasoning="ok", advice=[])

        monkeypatch.setattr(react.supervisor, "review", fake_review)
        monkeypatch.setattr(react.supervisor, "format_advice", lambda review: "建议")

        await react._supervisor_review()

        assert captured["goal_anchor"].startswith(GOAL_MARKER)
        assert "新目标" in captured["goal_anchor"]
        assert "旧目标" not in captured["goal_anchor"]

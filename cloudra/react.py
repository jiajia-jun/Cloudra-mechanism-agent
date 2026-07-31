import asyncio
import json
import os
from datetime import datetime

import numpy as np

from cloudra import events, session_store
from cloudra.agent import Agent
from cloudra.case_bank import get_case_bank
from cloudra.config import get_config
from cloudra.database import ConversationDB, get_database_path
from cloudra.log_class import Log
from cloudra.presentation import Color
from cloudra.session_class import Session
from cloudra.streaming import _aiter_chunks, _ChunkPumper, dynamic_deep_merge
from cloudra.supervisor import get_supervisor
from cloudra.tools import get_tools_lst
from cloudra.tools.Plantool.goal import GOAL_MARKER


class AgentCancelled(Exception):
    """用户请求打断（cancel_requested）时由 Agent 主动抛出。

    executor 捕获后把任务标记为 cancelled 而非 failed。
    """


class LLMOutputTruncated(Exception):
    """模型输出连续被 max_tokens 截断（thinking 过长/tool_call 被拦腰截断）。

    截断的输出绝不能被当成"正常说完"：否则上一条工具结果会被误存为最终答案，
    session 表现为"调用完工具就提前结束"。
    """


class AgentStuckLoop(Exception):
    """检测到死循环：同一工具以完全相同的参数连续调用多次仍无进展。

    与 LLMOutputTruncated 一样落库 failed，防止无意义重复调用烧 token。
    """


class MaxStepsExceeded(Exception):
    """超过最大步数预算，强制终止任务，避免主循环失控。"""


class _TruncationRetry(Exception):
    """内部信号：本轮输出被 max_tokens 截断，注入收敛提示后重试（有界循环）。"""


class _StreamRetry(Exception):
    """内部信号：流式消费过程中网络抖动，需要重试整轮推理。"""


class reAct:
    session: Session
    agent: Agent
    prompt: str
    log: Log
    _continue: bool
    database_path: str
    undos: list

    def __init__(
        self,
        agent: Agent,
        query: str = "",
        session_id: str = None,
        parent_session_id: str = None,
    ):
        self.agent = agent
        self.parent_session_id = parent_session_id
        # query 是本次任务要求，应该作为 user 消息进入上下文，
        # 绝不能覆盖 agent.prompt（身份 prompt）。
        if query:
            agent.query = query
        self.log = Log(agent.name)
        self.log.session = None

        data_dir = get_config().data_dir
        conv_id = getattr(agent, 'conversation_id', 'default')
        if conv_id and conv_id != 'default':
            log_path = os.path.join(data_dir, 'conversations', conv_id, 'logs', agent.name)
        else:
            log_path = os.path.join(data_dir, 'logs', agent.name)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        # 按 conversation 隔离 SQLite，避免并发 benchmark 时全局锁竞争。
        self.database_path = get_database_path(conv_id)

        self.log = Log(agent.name, log_path=log_path)
        self.log.session = None
        self.session_create(session_id)

        # 运行状态标志与缓冲区：必须是实例字段，避免多个 reAct 实例共享类级可变对象
        self._continue = True
        self.undos = []

        # 每轮 ReAct 的步数计数，用于触发 Supervisor 定期审查
        self.step_count = 0
        # 科学督导模块：默认每 15 轮审查一次方向
        self.supervisor = get_supervisor(interval=15)
        # tool_call 反查表缓存：仅当真的出现空 name 时才惰性构建（见 _normalize_tool_calls）
        self._tool_arg_maps = None
        # 输出被 max_tokens 截断的重试计数（见 _retry_on_truncation）
        self._truncation_retries = 0
        # 死循环检测：最近若干次工具调用的签名（tool_name + 稳定序列化参数）
        self._recent_tool_sigs: list[str] = []
        # 步数预算耗尽警告只注入一次
        self._steps_warned = False
        # 本 session 的累计 token usage（真实 usage 逐轮累加，供前端展示成本）
        self._usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        # 打断（cancel）信号：通过 IPC 订阅 cancel_requested 事件直接置位
        self._cancel_event = asyncio.Event()
        self._cancel_queue: asyncio.Queue | None = None
        self._cancel_task: asyncio.Task | None = None
        # 外部事件队列：通过 IPC 订阅后实时投递
        self._external_queue: asyncio.Queue | None = None

    async def _setup_event_subscriptions(self) -> None:
        """订阅本 session 的 cancel 与外部事件（幂等：只订阅一次）。"""
        conv_id = getattr(self.agent, "conversation_id", "default") or "default"
        if self._cancel_queue is None:
            await events.ensure_listener(conv_id)
            self._cancel_queue = await events.subscribe_async(conv_id, "cancel_requested")
            self._external_queue = await events.subscribe_async(conv_id, "external_event")
        if self._cancel_task is None or self._cancel_task.done():
            self._cancel_task = asyncio.create_task(self._cancel_consumer())

    async def _cancel_consumer(self) -> None:
        """等待属于本 session 的 cancel_requested 事件并置位。"""
        if self._cancel_queue is None:
            return
        while True:
            msg = await self._cancel_queue.get()
            if msg.get("session_id") == self.session.id:
                self._cancel_event.set()
                return

    def _check_cancel_event(self) -> None:
        """检查 IPC 投递的 cancel 信号。"""
        if self._cancel_event.is_set():
            raise AgentCancelled()

    @staticmethod
    async def _close_response(response) -> None:
        """尽力关闭底层流响应。"""
        close = getattr(response, "close", None)
        if close is not None:
            try:
                maybe_awaitable = close()
                if asyncio.iscoroutine(maybe_awaitable):
                    await maybe_awaitable
            except Exception:
                pass

    async def _consume_external_events(self) -> int:
        """Drain IPC 队列 + 持久化 pending 事件并注入上下文；返回注入条数。"""
        if self.agent.context_manager is None:
            return 0

        raw_events: list[dict] = []
        if self._external_queue is not None:
            while not self._external_queue.empty():
                raw_events.append(self._external_queue.get_nowait())

        # 同时补拉离线期间落到 DB 的事件
        persisted = await self.agent.context_manager.drain_pending_events()

        # inject_event 会先持久化、再广播同一事件。在线状态下两条通道会同时
        # 命中，按内容消掉 IPC 副本；仅广播、未持久化的外部事件仍会保留。
        persisted_counts: dict[tuple[str, str], int] = {}
        for event in persisted:
            key = (event.get("event_type", "external"), event.get("content", ""))
            persisted_counts[key] = persisted_counts.get(key, 0) + 1
        deduplicated_raw = []
        for event in raw_events:
            key = (event.get("event_type", "external"), event.get("content", ""))
            if persisted_counts.get(key, 0) > 0:
                persisted_counts[key] -= 1
            else:
                deduplicated_raw.append(event)

        injected = 0
        for event in deduplicated_raw + persisted:
            # IPC 事件 payload 包含 agent_id/event_type/content
            agent_id = event.get("agent_id")
            if agent_id is not None and agent_id != self.agent.id:
                continue
            event_type = event.get("event_type", "external")
            content = event.get("content", "")
            await self.agent.update_context({
                "role": "system",
                "content": f"【{event_type}】{content}",
            })
            self.log.update_content(
                f"{Color.YELLOW}[外部事件] {event_type}: {self._truncate(content, 200)}{Color.END}\n"
            )
            injected += 1
        return injected

    async def drain_pending_external_events(self) -> bool:
        """供 runner 在等待后台任务后调用：一次性消费所有外部事件。"""
        await self._setup_event_subscriptions()
        return await self._consume_external_events() > 0

    def _should_use_supervisor(self) -> bool:
        """判断是否启用 Supervisor。

        默认启用；如果 Supervisor 未配置有效 LLM，则后续 review 会退化，
        这里仍保留实例以便统一日志。
        """
        return getattr(self.agent, 'type', '') != 'yolo_guard'

    async def _supervisor_review(self) -> None:
        """调用 Supervisor 审查当前方向，并将建议写入上下文。"""
        if not self.supervisor or not self.agent.context_manager:
            return

        try:
            user_goal = self.agent.query or ""
            messages = await self.agent.get_context()

            # 提取最新的 goal 锚点（goal_set 工具写入），让审查对准可验证的完成判据
            goal_anchor = ""
            for msg in reversed(messages):
                content = str(msg.get("content", ""))
                if msg.get("role") == "system" and content.startswith(GOAL_MARKER):
                    goal_anchor = content
                    break

            # 从全局 Case Bank 检索历史经验（跨 conversation 共享）
            case_bank = get_case_bank()
            cases = case_bank.get_cases(limit=50)

            review = await self.supervisor.review(
                user_goal=user_goal,
                messages=messages,
                cases=cases,
                goal_anchor=goal_anchor,
            )
            advice_text = self.supervisor.format_advice(review)
            await self.agent.context_manager.set_supervisor_advice(advice_text)
            # 遥测事件：前端边栏据此展示当前阶段的 Supervisor 意见
            await self._record_event("supervisor_review", {
                "verdict": review.verdict,
                "reasoning": review.reasoning,
                "advice": [str(item) for item in review.advice],
            })

            if review.verdict in ('redirect', 'pause_and_reflect'):
                self.log.update_content(
                    f"{Color.YELLOW}[Supervisor] {review.verdict.upper()}: {review.reasoning}{Color.END}\n"
                )
                for item in review.advice:
                    self.log.update_content(f"{Color.YELLOW}  - {item}{Color.END}\n")
            else:
                self.log.update_content(
                    f"{Color.BLUE}[Supervisor] 审查通过: {review.reasoning}{Color.END}\n"
                )
        except Exception as e:
            print(f"[reAct] Supervisor 审查失败: {e}")

    async def _persist_case(self) -> None:
        """任务结束时把 trajectory 沉淀为结构化 case 到全局 Case Bank。"""
        if not self.supervisor or not self.agent.context_manager:
            return

        try:
            messages = await self.agent.get_context()
            if not messages or len(messages) < 3:
                return

            case_data = await self.supervisor.extract_case(messages)
            task_summary = case_data.get("task_summary", "")
            if not task_summary:
                return

            embedding = await self.supervisor.embed_text(task_summary)
            embedding_bytes = embedding.astype(np.float32).tobytes()

            case_bank = get_case_bank()
            case_bank.add_case(
                session_id=self.session.id,
                task_summary=task_summary,
                outcome=case_data.get("outcome", "unknown"),
                outcome_reason=case_data.get("outcome_reason", ""),
                lesson=case_data.get("lesson", ""),
                embedding=embedding_bytes,
            )
            self.log.update_content(
                f"{Color.BLUE}[系统] 已沉淀任务经验到全局 Case Bank。{Color.END}\n"
            )
        except Exception as e:
            print(f"[reAct] Case 沉淀失败: {e}")

    async def run(self):
        '''
        reAct的核心方法，执行agent的任务。
        '''
        # 确保上下文管理器已初始化，并加载初始上下文
        await self.agent.get_context()
        await self._setup_event_subscriptions()
        # 把 LLM 传输层状态（重试/fallback/异常）桥接为 session 事件：
        # 全屏 TUI 下 print 不可见，没有这些事件用户只能看到"卡住"
        self.agent._get_llm_client().on_status = (
            lambda event, data: self._record_event("llm_status", {"kind": event, **data})
        )

        try:
            return await self._run_loop()
        except AgentCancelled:
            # 用户打断：落库 cancelled 状态后向上抛，由 executor 统一收尾
            self.session.state = 'cancelled'
            db = ConversationDB.from_path(self.database_path)
            try:
                await session_store.afinalize_session(db, self.session.id, 'cancelled')
            except Exception as e:
                print(f"[reAct] cancelled 状态写入失败: {e}")
            self.log.update_content(f"{Color.YELLOW}[系统] 任务已被用户打断。{Color.END}\n")
            raise
        except (LLMOutputTruncated, AgentStuckLoop, MaxStepsExceeded) as exc:
            # 输出反复被 max_tokens 截断 / 死循环 / 超步数预算：
            # 明确落库 failed，绝不让工具结果误当最终答案
            self.session.state = 'failed'
            error_msg = str(exc)
            db = ConversationDB.from_path(self.database_path)
            try:
                await session_store.afinalize_session(db, self.session.id, 'failed', error=error_msg)
            except Exception as e:
                print(f"[reAct] failed 状态写入失败: {e}")
            await self._record_event("task_aborted", {"reason": error_msg})
            self.log.update_content(f"{Color.RED}[系统] {exc}{Color.END}\n")
            raise
        finally:
            if self._cancel_task is not None and not self._cancel_task.done():
                self._cancel_task.cancel()
                try:
                    await self._cancel_task
                except asyncio.CancelledError:
                    pass

    # 步数预算：防止主循环失控空转烧 token（对齐 OpenHands 默认的 100 步）
    MAX_STEPS = 100
    # 预算接近耗尽时提前警告一次，让模型收敛到结论而不是被硬切断
    STEPS_WARN_AT = 80
    # 死循环检测阈值：相同（工具名+参数）签名连续出现次数，先警告、再终止
    LOOP_WARN_THRESHOLD = 3
    LOOP_ABORT_THRESHOLD = 5

    async def _run_loop(self):
        '''reAct 的主循环（从 run 拆出以便统一捕获 AgentCancelled）。'''
        while self._continue:
            self.session.state = 'thinking'
            await self._record_phase('thinking')
            self.step_count += 1

            # 步数预算：接近上限时注入一次收敛提示，超限则硬终止
            if self.step_count >= self.STEPS_WARN_AT and not self._steps_warned:
                self._steps_warned = True
                await self.agent.update_context({
                    "role": "system",
                    "content": (
                        f"【系统提示】步数预算即将耗尽（{self.step_count}/{self.MAX_STEPS}）。"
                        "请停止扩展新的调查方向，基于已获得的信息收敛并给出最终结论。"
                    ),
                })
            if self.step_count > self.MAX_STEPS:
                raise MaxStepsExceeded(
                    f"已达到最大步数 {self.MAX_STEPS}，任务被强制终止以避免失控空转。"
                )

            # 每轮循环边界检查一次打断请求（流式期间也逐 chunk 检查 _cancel_event）
            self._check_cancel_event()

            # 每轮推理前，消费 IPC 与持久化外部事件并注入上下文
            await self._consume_external_events()

            # 每 15 轮触发一次 Supervisor 方向审查
            if self._should_use_supervisor() and self.supervisor and self.supervisor.should_review(self.step_count):
                await self._supervisor_review()

            tool_calls = await self.reasoning()

            # 如果没有工具调用且有内容，或者已经停止
            if not tool_calls:
                # 检查最后一条消息内容
                context = await self.agent.get_context()
                content = context[-1].get('content', '') if context else ''
                if content:
                    self.session.state = 'completed'
                    # 更新数据库结果
                    db = ConversationDB.from_path(self.database_path)
                    await session_store.afinalize_session(db, self.session.id, 'completed', result=content)
                    # 任务结束前沉淀经验 case
                    await self._persist_case()
                    return content

            self.session.state = 'acting'
            await self._record_phase('acting')
            stopped = await self.act_result(tool_calls)

            if stopped:
                self.session.state = 'completed'
                # result 取最后一条 assistant 正文：stop 调用后 context[-1] 是工具返回
                # （{"stopped": true, ...} 的原始 JSON），不能直接当最终总结。
                context = await self.agent.get_context()
                content = ''
                for msg in reversed(context):
                    if msg.get('role') == 'assistant' and msg.get('content'):
                        content = str(msg['content'])
                        break
                if not content:
                    content = context[-1].get('content', '任务已完成') if context else '任务已完成'
                db = ConversationDB.from_path(self.database_path)
                await session_store.afinalize_session(db, self.session.id, 'completed', result=content)
                # 任务结束前沉淀经验 case
                await self._persist_case()
                if self.agent.id != 'a-0':
                    await self.agent.clear_context()
                    print(f"Agent {self.agent.name}上下文已释放！")
                return content

    MAX_STREAM_RETRIES = 2

    async def reasoning(self) -> list:
        '''
        reAct的推理方法，分析agent的上下文和工具，决定下一步行动。

        输出被 max_tokens 截断时通过有界循环重试（不再递归自调用）；
        流式消费遇到网络抖动时丢弃部分输出并重试整轮推理。
        '''
        stream_errors = 0
        while True:
            try:
                return await self._reasoning_once()
            except _TruncationRetry:
                # 注入收敛提示；重试次数耗尽时抛 LLMOutputTruncated
                await self._retry_on_truncation()
            except _StreamRetry as exc:
                stream_errors += 1
                if stream_errors > self.MAX_STREAM_RETRIES:
                    raise exc.__cause__ or exc
                self.log.update_content(
                    f"{Color.YELLOW}[系统] 流式连接抖动，重试整轮推理 "
                    f"({stream_errors}/{self.MAX_STREAM_RETRIES}){Color.END}\n"
                )

    async def _reasoning_once(self) -> list:
        '''单轮推理：调用 LLM 并消费响应。输出被截断时抛 _TruncationRetry。'''
        agent = self.agent
        # 身份 prompt 在 Agent.llm_call 内按当前文件与策略动态装配。
        try:
            response = await agent.llm_call()
        except Exception:
            diagnostics = agent.get_runtime_diagnostics()
            if diagnostics:
                await self._record_event(
                    "llm_request_diagnostics",
                    {**diagnostics, "request_state": "transport_error"},
                )
            raise
        diagnostics = agent.get_runtime_diagnostics()
        if diagnostics:
            await self._record_event(
                "llm_request_diagnostics",
                {**diagnostics, "request_state": "response_received"},
            )
        # 累计真实 token usage 并广播：前端据此展示成本，不再完全黑盒
        usage = agent._get_llm_client().last_usage
        if usage:
            for key in self._usage_totals:
                self._usage_totals[key] += int(usage.get(key) or 0)
            await self._record_event(
                "token_usage",
                {
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "last": usage,
                    "total": dict(self._usage_totals),
                },
            )
        final_response = ''
        reasoning_content = ''
        tool_calls = []
        message = None

        if agent.is_stream:
            tool_call_buffer = {}
            self.log.update_content(f'{Color.CYAN}{agent.name}[reasoning]:{Color.END}\n')

            reasoning_buffer = ""
            last_finish_reason = None
            # token 级流式事件：节流后写入 session_events，供前端实时渲染
            pumper = _ChunkPumper(
                lambda event_type, data: self._record_event(
                    event_type,
                    {**data, "agent_id": agent.id, "agent_name": agent.name},
                )
            )
            self.log.begin_stream()
            try:
                async for chunk in _aiter_chunks(response):
                    if self._cancel_event.is_set():
                        raise AgentCancelled()
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta
                    finish_reason = choice.finish_reason
                    if finish_reason:
                        last_finish_reason = finish_reason
                    token = delta.content

                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        reasoning_buffer += delta.reasoning_content
                        await pumper.add("reasoning", delta.reasoning_content)

                    if token:
                        final_response += token
                        self.log.update_content(token)
                        await pumper.add("content", token)

                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            tc_idx = tc_chunk.index
                            chunk_dict = tc_chunk.model_dump(exclude_none=True)

                            if tc_idx not in tool_call_buffer:
                                tool_call_buffer[tc_idx] = {}

                            tool_call_buffer[tc_idx] = dynamic_deep_merge(
                                tool_call_buffer[tc_idx],
                                chunk_dict
                            )

                    if finish_reason == 'tool_calls' or (finish_reason == 'stop' and tool_call_buffer):
                        if reasoning_buffer:
                            self.log.update_content(f"{Color.DARKCYAN}[thinking]{reasoning_buffer}{Color.END}\n")
                            reasoning_content = reasoning_buffer
                            reasoning_buffer = ""

                        # 部分中转站/模型会返回 function.name 为空的 tool_call，
                        # 但 arguments 里保留了工具特有参数。这里根据参数签名反推工具名，
                        # 对自定义工具也生效，因为映射是从 input_schema 自动生成的。
                        normalized_tcs = self._normalize_tool_calls(list(tool_call_buffer.values()))
                        tool_call_buffer.clear()

                        for tc_data in normalized_tcs:
                            tool_calls.append(tc_data)
                            func_name = tc_data.get('function', {}).get('name', 'Unknown')
                            self.log.update_content(new_content=f"{Color.GREEN}工具调用: {func_name}{Color.END}\n")

                # 流结束时 tool_call_buffer 仍有内容：tool_call 的 JSON 被拦腰截断
                leftover_tool_calls = bool(tool_call_buffer)
                tool_call_buffer.clear()
                # 流式输出结束时，如果还有未打印的 reasoning_content，补打出来
                if reasoning_buffer:
                    self.log.update_content(f"{Color.DARKCYAN}[thinking]{reasoning_buffer}{Color.END}\n")
                # 冲刷残余增量并标记流结束
                await pumper.flush()
                await self._record_event(
                    "llm_stream_end",
                    {
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "has_tool_calls": bool(tool_calls),
                    },
                )
            except AgentCancelled:
                # 打断请求：关闭底层流，向上传播由 run() 统一落库 cancelled
                await self._close_response(response)
                raise
            except Exception as e:
                # 流式消费出现网络/解析等异常：关闭流并请求重试整轮推理，
                # 避免单次抖动直接打崩主进程。
                await self._close_response(response)
                self.log.update_content(new_content=f"{Color.RED}[reasoning步骤]流式消费错误：{e}{Color.END}")
                raise _StreamRetry() from e
            finally:
                self.log.end_stream()

            # 输出被 max_tokens 截断：finish_reason=='length'，或 tool_call 被拦腰截断。
            # 截断的输出不能按"正常说完"处理（否则上一条工具结果会被误存为最终答案）。
            if last_finish_reason == 'length' or leftover_tool_calls:
                raise _TruncationRetry()

        else:
            message = response.choices[0].message
            if response.choices[0].finish_reason == 'length':
                raise _TruncationRetry()
            final_response = message.content
            if hasattr(message, 'reasoning_content') and message.reasoning_content:
                reasoning_content = message.reasoning_content
            # 非流式模式下，模型返回的 reasoning_content 也打印出来
            if reasoning_content:
                self.log.update_content(f"{Color.DARKCYAN}[thinking]{reasoning_content}{Color.END}\n")
            self.log.update_content(f'{Color.CYAN}{agent.name}[reasoning]:{Color.END}\n{final_response}\n')

            if message.tool_calls:
                raw_tool_calls = []
                for tool_call in message.tool_calls:
                    raw_tool_calls.append(tool_call.model_dump(exclude_none=True))
                tool_calls = self._normalize_tool_calls(raw_tool_calls)

        # 输出完整生成：重置截断重试计数
        self._truncation_retries = 0

        # 构建完整的 assistant 消息写入上下文
        if message:  # 非stream模式
            new_block = message.model_dump(exclude_none=True)
        else:  # stream模式
            new_block = {'role': 'assistant'}
            if reasoning_content:
                new_block['reasoning_content'] = reasoning_content
            if final_response:
                new_block['content'] = final_response
            else:
                new_block['content'] = None

            if tool_calls:
                new_block['tool_calls'] = tool_calls

        # 延迟加载逻辑：如果有 tool_calls，先存入 undos 缓冲区
        if tool_calls:
            self.undos.append(new_block)
        elif not self._is_empty_assistant_block(new_block):
            await agent.update_context(new_block)

        return tool_calls

    MAX_TRUNCATION_RETRIES = 2

    async def _retry_on_truncation(self) -> None:
        """输出被 max_tokens 截断时的处理：注入收敛提示；反复截断则抛 LLMOutputTruncated。"""
        if self._truncation_retries >= self.MAX_TRUNCATION_RETRIES:
            raise LLMOutputTruncated(
                f"模型输出连续 {self.MAX_TRUNCATION_RETRIES + 1} 次被 max_tokens 截断"
                f"（当前上限 {self.agent.max_tokens} tokens）。"
                "这通常意味着 thinking 过长，请增大 max_tokens 或拆分任务。"
            )
        self._truncation_retries += 1
        self.log.update_content(
            f"{Color.YELLOW}[系统] 模型输出被 max_tokens 截断，"
            f"注入收敛提示后重试 ({self._truncation_retries}/{self.MAX_TRUNCATION_RETRIES}){Color.END}\n"
        )
        await self.agent.update_context({
            "role": "system",
            "content": (
                "【系统提示】你上一条输出因 max_tokens 限制被截断，结论或 tool_call 没有完整生成。"
                "请立即收敛思考长度，用简洁形式直接给出最终结论，或重新发起必要的工具调用。"
            ),
        })

    @staticmethod
    def _is_empty_assistant_block(block: dict) -> bool:
        """判断一条消息是否为没有有效载荷的 assistant 空消息。"""
        if block.get("role") != "assistant":
            return False
        has_content = bool(block.get("content"))
        has_reasoning = bool(block.get("reasoning_content"))
        has_tool_calls = bool(block.get("tool_calls"))
        return not (has_content or has_reasoning or has_tool_calls)

    def _build_tool_arg_maps(self) -> tuple[dict[frozenset, str], dict[frozenset, str]]:
        """根据每个工具的 input_schema 自动建立参数→工具名的反查表。

        返回两个映射：
        - required_map: required 字段集合 → 工具名
        - full_map: 全部参数字段集合 → 工具名

        对自定义工具生效：只要新工具遵循 input_schema 规范，就会在这里自动出现，
        不需要改 reAct.py。
        """
        required_map: dict[frozenset, str] = {}
        full_map: dict[frozenset, str] = {}
        for entry in self.agent.get_available_tools(get_tools_lst()):
            try:
                schema_cls = entry.input_schema
                if schema_cls is None:
                    continue
                schema = schema_cls.to_parameters_schema()
            except Exception:
                continue
            props = schema.get("properties", {})
            required = frozenset(schema.get("required", []))
            full_keys = frozenset(props.keys())
            if required:
                required_map.setdefault(required, entry.tool_name)
            if full_keys:
                full_map.setdefault(full_keys, entry.tool_name)
        return required_map, full_map

    def _normalize_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """对 tool_calls 做后处理：当 function.name 为空时，根据 arguments 反推工具名。"""
        if not tool_calls:
            return tool_calls

        # 只有真的出现空 name 的 tool_call 时才需要反查表，
        # 避免每个推理步骤都无条件重建全部工具的参数 schema。
        def _has_empty_name(tc: dict) -> bool:
            func = tc.get("function") or {}
            return not (func.get("name") if isinstance(func, dict) else None)

        if not any(_has_empty_name(tc) for tc in tool_calls):
            return tool_calls

        if self._tool_arg_maps is None:
            self._tool_arg_maps = self._build_tool_arg_maps()
        required_map, full_map = self._tool_arg_maps

        for tc in tool_calls:
            func = tc.get("function") or {}
            name = func.get("name") if isinstance(func, dict) else None
            args_raw = func.get("arguments") if isinstance(func, dict) else None

            if name:
                continue

            args = args_raw
            if isinstance(args_raw, str):
                try:
                    args = json.loads(args_raw, strict=False)
                except Exception:
                    args = {}
            if not isinstance(args, dict):
                args = {}

            arg_keys = frozenset(args.keys())
            inferred = None

            # 1) 精确匹配全部字段集合（能抓到 stop 等 required 为空但签名独特的工具）
            if arg_keys in full_map:
                inferred = full_map[arg_keys]
            # 2) 精确匹配 required 字段集合
            elif arg_keys in required_map:
                inferred = required_map[arg_keys]
            else:
                # 3) 模糊匹配：找 required 是 args 子集且重合度最高的工具
                candidates = [
                    (req, tname) for req, tname in required_map.items() if req.issubset(arg_keys)
                ]
                if candidates:
                    candidates.sort(key=lambda item: (-len(item[0]), item[1]))
                    inferred = candidates[0][1]

            if inferred:
                func["name"] = inferred
                tc["function"] = func
                print(
                    f"\033[93m[reAct] tool_call name 为空，根据参数推断为 '{inferred}'\033[0m"
                )

        return tool_calls

    async def _commit_undos(self):
        '''将缓冲区中的消息提交到上下文。'''
        while self.undos:
            await self.agent.update_context(self.undos.pop(0))

    @staticmethod
    def _truncate(text: str, max_len: int = 200) -> str:
        '''截断长文本，用于日志展示。'''
        if not text:
            return text
        if len(text) > max_len:
            return text[:max_len] + '...'
        return text

    def _summarize_args(self, tool_name: str, args: dict) -> str:
        '''生成工具参数的可读摘要，避免把完整大文件内容打印到日志。'''
        if not args:
            return ''
        # 对常见大字段做截断
        display = {}
        for k, v in args.items():
            s = str(v)
            display[k] = self._truncate(s, max_len=300)
        summary = json.dumps(display, ensure_ascii=False)
        return self._truncate(summary, max_len=600)

    def _summarize_result(self, tool_name: str, result: dict) -> str:
        '''生成工具结果的可读摘要。'''
        # 优先取常用字段
        text = (
            result.get('message')
            or result.get('result')
            or result.get('content')
            or json.dumps(result, ensure_ascii=False)
        )
        return self._truncate(str(text), max_len=400)

    async def act_result(self, tool_calls: list):
        '''
        并发执行 reasoning 阶段收集到的 tool_calls。
        tool_calls 为标准 OpenAI 格式的 dict 列表。
        返回 bool：是否检测到 stop 工具并请求终止循环。
        '''
        session = self.session
        # Enforce the same permission/runtime boundary used to build the LLM
        # schema.  A hallucinated tool name must never bypass a hidden tool.
        tool_entries = self.agent.get_available_tools(get_tools_lst())

        # 并发执行所有工具调用
        acts = []
        tool_call_ids = []
        tool_names = []
        stop_requested = False

        for tool_call in tool_calls:
            tool_name = tool_call.get('function', {}).get('name', '')
            tool_call_id = tool_call.get('id')
            tool_args_raw = tool_call.get('function', {}).get('arguments', {})

            # 空 tool name 直接提醒 LLM，避免进入无意义的工具查找/循环
            if not tool_name:
                available_names = sorted({e.tool_name for e in tool_entries})
                example = '{"name": "getskill", "arguments": {"skill_name": "subagent-prompting"}}'
                err_msg = (
                    "【系统错误】工具调用缺少 function.name。"
                    "OpenAI function calling 要求必须提供准确的工具名，"
                    f"例如：{example}。"
                    f"当前可用工具：{', '.join(available_names)}。"
                    "请重新调用，并确保 `name` 字段非空。"
                )
                result_block = {
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'content': err_msg,
                }
                await self._commit_undos()
                await self.agent.update_context(result_block)
                self.log.update_content(f"{Color.RED}工具名缺失，已提醒 LLM 补全。{Color.END}\n")
                continue

            try:
                if isinstance(tool_args_raw, str):
                    # strict=False 允许 JSON 字符串中出现未转义的换行/控制字符，
                    # 这是 LLM 生成 text_writer 等多行参数时的常见情况。
                    tool_args = json.loads(tool_args_raw, strict=False)
                else:
                    tool_args = tool_args_raw
            except json.JSONDecodeError as e:
                # 如果 JSON 解析失败，将错误作为工具结果返回给 Agent
                result_block = {
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'content': f"【系统错误】工具参数解析失败 (JSON Error): {str(e)}。请确保参数格式正确。"
                }
                await self._commit_undos()
                await self.agent.update_context(result_block)
                self.log.update_content(f"{Color.RED}参数解析失败: {tool_name}{Color.END}\n")
                continue

            # 死循环检测：记录调用签名（工具名 + 稳定序列化参数），
            # 同一签名连续出现 LOOP_WARN_THRESHOLD 次注入警告，
            # 达到 LOOP_ABORT_THRESHOLD 次直接终止任务（在本次调用执行前拦截）。
            sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True, ensure_ascii=False, default=str)}"
            self._recent_tool_sigs.append(sig)
            del self._recent_tool_sigs[:-20]
            repeat = 0
            for recent_sig in reversed(self._recent_tool_sigs):
                if recent_sig == sig:
                    repeat += 1
                else:
                    break
            if repeat >= self.LOOP_ABORT_THRESHOLD:
                raise AgentStuckLoop(
                    f"检测到死循环：工具 `{tool_name}` 以完全相同的参数连续调用 {repeat} 次，"
                    "任务被强制终止。"
                )
            if repeat == self.LOOP_WARN_THRESHOLD:
                warn_msg = (
                    f"【系统提示】检测到你可能陷入循环：工具 `{tool_name}` 已连续 {repeat} 次"
                    "以完全相同的参数被调用。请先仔细阅读前几次的返回结果，改变策略或参数；"
                    "如果目的是等待/轮询，请说明原因并换用更长间隔的方式。不要无意义地重复相同调用。"
                )
                await self._commit_undos()
                await self.agent.update_context({"role": "system", "content": warn_msg})
                await self._record_event("loop_detected", {"tool": tool_name, "repeat": repeat})
                self.log.update_content(
                    f"{Color.YELLOW}[系统] 检测到重复工具调用: {tool_name} x{repeat}{Color.END}\n"
                )

            if tool_name == 'stop':
                self._continue = False
                stop_requested = True

            args_summary = self._summarize_args(tool_name, tool_args)
            await self._record_event("tool_started", {"tool": tool_name, "arguments": args_summary})
            self.log.update_content(
                f"{Color.YELLOW}执行工具: {tool_name}{Color.END}"
                f"{(' 参数: ' + args_summary) if args_summary else ''}\n"
            )

            found = False
            for entry in tool_entries:
                if entry.tool_name == tool_name:
                    found = True
                    tool_instance = entry.instantiate(subagent=self.agent)

                    input_schema_class = tool_instance.input_schema
                    try:
                        input_instance = input_schema_class(**tool_args)
                    except Exception as e:
                        # 参数通不过 Pydantic 校验（类型错误/缺必填字段等）：
                        # 把校验错误作为工具结果回喂 LLM 让它自行修正，
                        # 绝不能让 ValidationError 穿透主循环直接打崩整个任务。
                        err_msg = (
                            f"【系统错误】工具 `{tool_name}` 参数校验失败: {e}。"
                            "请对照该工具的参数 schema 修正参数类型与必填字段后重新调用。"
                        )
                        await self._commit_undos()
                        await self.agent.update_context({
                            'role': 'tool',
                            'tool_call_id': tool_call_id,
                            'content': err_msg,
                        })
                        await self._record_event(
                            "tool_finished",
                            {"tool": tool_name, "result": err_msg},
                        )
                        self.log.update_content(
                            f"{Color.RED}参数校验失败: {tool_name}: {e}{Color.END}\n"
                        )
                        break

                    session.state = 'waiting'
                    acts.append(tool_instance.safe_call(input_instance, session))
                    tool_call_ids.append(tool_call_id)
                    tool_names.append(tool_name)
                    break

            if not found:
                result_block = {
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'content': f"【系统错误】找不到工具: {tool_name}。请检查工具名称是否正确。"
                }
                await self._commit_undos()
                await self.agent.update_context(result_block)
                await self._record_event(
                    "tool_finished",
                    {"tool": tool_name, "result": result_block["content"]},
                )

        # 记录 tool_call_id 到工具名的映射，方便结果日志展示
        id_to_name = dict(zip(tool_call_ids, tool_names))

        if acts:
            # 使用 return_exceptions=True，确保单个工具崩溃不影响其他工具，且能捕获异常
            tool_results = await asyncio.gather(*acts, return_exceptions=True)
            await self._commit_undos()

            # 每个工具结果单独作为一条消息
            for tool_result, tool_call_id in zip(tool_results, tool_call_ids):
                tool_name = id_to_name.get(tool_call_id, 'Unknown')
                image_path = None
                if isinstance(tool_result, Exception):
                    # 如果工具执行抛出了异常，将错误信息反馈给 Agent
                    content = f"【系统错误】工具执行发生异常: {str(tool_result)}"
                    self.log.update_content(f"{Color.RED}工具异常: {tool_name}: {str(tool_result)}{Color.END}\n")
                else:
                    result_dict = tool_result.toJson()
                    content = json.dumps(result_dict)
                    # 自动提取图片路径（如果工具输出中包含该字段）
                    if result_dict.get('image_path'):
                        image_path = result_dict.get('image_path')
                    summary = self._summarize_result(tool_name, result_dict)
                    status_color = Color.GREEN if result_dict.get('is_success', result_dict.get('is_written', result_dict.get('stopped', True))) else Color.RED
                    self.log.update_content(
                        f"{status_color}工具完成: {tool_name} -> {summary}{Color.END}\n"
                    )

                result_block = {
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'content': content
                }
                if image_path:
                    result_block['image_path'] = image_path

                await self.agent.update_context(result_block)
                await self._record_event(
                    "tool_finished",
                    {"tool": tool_name, "result": self._truncate(content, 800)},
                )

            session.state = 'thinking'

        return stop_requested

    async def _record_phase(self, phase: str) -> None:
        """刷新心跳并记录可供前端消费的 Session 阶段事件。"""
        await self._record_event("phase", {"phase": phase})

    async def _record_event(self, event_type: str, data: dict) -> None:
        """写入 session_events 遥测事件（经 session_store，附带心跳刷新）。

        遥测写入是可丢弃的：多进程并发时 SQLite 写锁竞争激烈，
        重试耗尽后只记录日志，绝不能让日志/事件写入杀死 Agent 主流程。
        使用异步连接 + aretry_on_locked，避免同步 busy_timeout 等待冻结事件循环。
        """
        db = ConversationDB.from_path(self.database_path)
        try:
            await session_store.arecord_event(db, self.session.id, event_type, data)
        except Exception as e:
            self.log.update_content(
                f"{Color.YELLOW}[reAct] 事件写入失败（已忽略）: {event_type}: {e}{Color.END}\n"
            )

    def session_create(self, session_id: str = None) -> None:
        '''
        创建session，记录agent的整个生命周期。
        数据库是唯一事实来源；per-session JSON 快照仅在
        CLOUDRA_DEBUG_SESSION_JSON=1 时由 Session 自行写出（调试用途）。
        '''
        data_dir = get_config().data_dir
        if not self.database_path:
            self.database_path = get_database_path(getattr(self.agent, 'conversation_id', 'default'))
        conv_id = getattr(self.agent, 'conversation_id', 'default')
        # 如果调用方指定了 session_id（如 SubAgentLauncher），则直接使用；否则按时间生成。
        session_id = session_id if session_id else f'{self.agent.id}_{datetime.now().isoformat()}'
        if conv_id and conv_id != 'default':
            _path = os.path.join(data_dir, 'conversations', conv_id, 'sessions', session_id + '.json')
        else:
            _path = os.path.join(data_dir, 'sessions', session_id + '.json')
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        session_ = Session(id=session_id, path=_path)
        self.session = session_
        self.log.session = session_

        # 数据库为单一事实来源：创建即入库
        db = ConversationDB.from_path(self.database_path)
        session_store.create_session_record(
            db,
            session_id=session_.id,
            agent_id=getattr(self.agent, 'id', None),
            agent_type=getattr(self.agent, 'type', None),
            parent_session_id=self.parent_session_id,
            query=getattr(self.agent, 'query', ''),
            created_at=session_.create_time.isoformat(),
        )
        return


class Coordinator_reAct(reAct):
    '''
    协调者agent的react进程
    '''
    session: Session

    def __init__(self, agent: Agent, session_id: str = None):
        # Coordinator 的身份 prompt 已包含 ReAct 工作指南，
        # 这里不再传入额外 query，让 agent.query（用户原始输入）作为第一条 user 消息。
        super().__init__(agent=agent, session_id=session_id)
        self.log.is_main = True

    async def run(self):
        result = await super().run()
        return result

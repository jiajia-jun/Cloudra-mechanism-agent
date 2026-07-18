import asyncio
import json
import os
import time
from datetime import datetime, timezone

import httpx
import numpy as np
import openai

from cloudra.agent import Agent
from cloudra.case_bank import get_case_bank
from cloudra.config import get_config
from cloudra.database import ConversationDB, aretry_on_locked, get_database_path, retry_on_locked
from cloudra.log_class import Log
from cloudra.session_class import Session
from cloudra.supervisor import get_supervisor
from cloudra.tools import get_tools_lst

# 每次 reasoning 前等待外部事件的最长时间（秒）
EXTERNAL_EVENT_POLL_INTERVAL = 0.5


def dynamic_deep_merge(buffer_dict: dict, delta_dict: dict) -> dict:
    """通用动态拼接工具：不硬编码任何字段名，自动合并字符串，自动递归字典。

    注意：tool_call 中的 'type' 和 'name' 是固定枚举值，收到重复 chunk 时应
    直接覆盖，而不是字符串累加；否则会出现 'functionfunction...' 这种非法值，
    导致部分 provider（如 Xiaomi token-plan）返回 400。
    """
    # 这些字段在 OpenAI tool_call chunk 中是固定值，不应累加。
    overwrite_fields = {"type", "name"}

    for key, value in delta_dict.items():
        if isinstance(value, dict):
            # 如果是嵌套字典（比如 'function'），递归进去拼接
            if key not in buffer_dict:
                buffer_dict[key] = {}
            dynamic_deep_merge(buffer_dict[key], value)

        elif isinstance(value, str):
            # 固定值字段直接覆盖，其余字符串字段累加。
            if key in overwrite_fields:
                buffer_dict[key] = value
            else:
                if key not in buffer_dict:
                    buffer_dict[key] = ""
                buffer_dict[key] += value

        else:
            # 如果是数字或其他类型（比如 'index'），直接覆盖/初始化
            buffer_dict[key] = value

    return buffer_dict


class AgentCancelled(Exception):
    """用户请求打断（cancel_requested）时由 Agent 主动抛出。

    executor 捕获后把任务标记为 cancelled 而非 failed。
    """


class LLMOutputTruncated(Exception):
    """模型输出连续被 max_tokens 截断（thinking 过长/tool_call 被拦腰截断）。

    截断的输出绝不能被当成"正常说完"：否则上一条工具结果会被误存为最终答案，
    session 表现为"调用完工具就提前结束"。
    """


_STREAM_SENTINEL = object()


async def _aiter_chunks(response):
    """统一异步迭代 LLM chunk。

    AsyncStream（AsyncOpenAI）直接 async 迭代；requests fallback 返回的
    同步生成器用线程拉取 next()，避免网络阻塞冻结事件循环。
    """
    if hasattr(response, "__aiter__"):
        async for chunk in response:
            yield chunk
        return
    iterator = iter(response)
    while True:
        chunk = await asyncio.to_thread(next, iterator, _STREAM_SENTINEL)
        if chunk is _STREAM_SENTINEL:
            break
        yield chunk


class _ChunkPumper:
    """把 LLM token 增量节流落库为 llm_chunk 事件。

    节流规则：单流缓冲满 80 字符，或距上次落库满 0.4s，即flush。
    目标是兼顾前端流式观感和 SQLite 写入压力（约 2.5 写/秒/Agent）。
    """

    FLUSH_INTERVAL = 0.4
    FLUSH_SIZE = 80

    def __init__(self, record):
        # record: async callable(event_type: str, data: dict)，由 reAct._record_event 提供
        self._record = record
        self._buffers: dict[str, list[str]] = {"content": [], "reasoning": []}
        self._sizes: dict[str, int] = {"content": 0, "reasoning": 0}
        self._last_flush = time.monotonic()

    async def add(self, stream: str, delta: str) -> None:
        if not delta:
            return
        self._buffers[stream].append(delta)
        self._sizes[stream] += len(delta)
        if (
            self._sizes[stream] >= self.FLUSH_SIZE
            or (time.monotonic() - self._last_flush) >= self.FLUSH_INTERVAL
        ):
            await self.flush(stream)

    async def flush(self, stream: str = None) -> None:
        targets = (stream,) if stream else ("content", "reasoning")
        for name in targets:
            if not self._buffers[name]:
                continue
            delta = "".join(self._buffers[name])
            self._buffers[name].clear()
            self._sizes[name] = 0
            await self._record("llm_chunk", {"stream": name, "delta": delta})
        self._last_flush = time.monotonic()


class Color:
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

class reAct:
    session: Session
    agent: Agent
    prompt: str
    log: Log
    _continue : bool = True
    database_path: str = ''
    undos: list = []
    _reset_count: int = 0

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

        # 每轮 ReAct 的步数计数，用于触发 Supervisor 定期审查
        self.step_count = 0
        # 科学督导模块：默认每 15 轮审查一次方向
        self.supervisor = get_supervisor(interval=15)
        # tool_call 反查表缓存：仅当真的出现空 name 时才惰性构建（见 _normalize_tool_calls）
        self._tool_arg_maps = None
        # 输出被 max_tokens 截断的重试计数（见 _retry_on_truncation）
        self._truncation_retries = 0
        # 打断（cancel）信号：由 _cancel_watcher 轮询 DB 置位，流式消费循环逐 chunk 检查
        self._cancel_event = asyncio.Event()

    async def _check_cancellation(self) -> None:
        """检查本 session 是否被请求打断；命中则抛出 AgentCancelled。"""
        db = ConversationDB.from_path(self.database_path)

        async def read_state():
            async with db.aconnect() as con:
                cur = await con.execute(
                    "SELECT state FROM session WHERE session_id=?", (self.session.id,)
                )
                row = await cur.fetchone()
                return row[0] if row else None

        state = await aretry_on_locked(read_state)
        if state == 'cancel_requested':
            raise AgentCancelled()

    async def _cancel_watcher(self) -> None:
        """后台轮询 cancel_requested（1s 间隔），命中时置位 _cancel_event。

        流式 LLM 消费循环逐 chunk 检查该事件，实现流式期间的秒级打断。
        """
        while True:
            await asyncio.sleep(1)
            try:
                await self._check_cancellation()
            except AgentCancelled:
                self._cancel_event.set()
                return
            except Exception:
                # 检查本身失败（如锁竞争）不影响主流程，下轮再查
                continue

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

            # 从全局 Case Bank 检索历史经验（跨 conversation 共享）
            case_bank = get_case_bank()
            cases = case_bank.get_cases(limit=50)

            review = await self.supervisor.review(
                user_goal=user_goal,
                messages=messages,
                cases=cases,
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

    async def _poll_and_inject_external_events(self):
        """轮询外部事件并注入到当前 Agent 上下文。"""
        if self.agent.context_manager is None:
            return
        events = await self.agent.context_manager.poll_external_events()
        for event in events:
            await self.agent.update_context({
                "role": "system",
                "content": f"【{event['event_type']}】{event['content']}"
            })
            self.log.update_content(
                f"{Color.YELLOW}[外部事件] {event['event_type']}: {self._truncate(event['content'], 200)}{Color.END}\n"
            )

    async def run(self):
        '''
        reAct的核心方法，执行agent的任务。
        '''
        # 确保上下文管理器已初始化，并加载初始上下文
        await self.agent.get_context()

        try:
            return await self._run_loop()
        except AgentCancelled:
            # 用户打断：落库 cancelled 状态后向上抛，由 executor 统一收尾
            self.session.state = 'cancelled'
            db = ConversationDB.from_path(self.database_path)

            async def mark_cancelled() -> None:
                async with db.aconnect() as con:
                    await con.execute(
                        "UPDATE session SET state='cancelled', finished_at=? WHERE session_id=?",
                        (datetime.now(timezone.utc).isoformat(), self.session.id),
                    )
                    await con.commit()

            try:
                await aretry_on_locked(mark_cancelled)
            except Exception as e:
                print(f"[reAct] cancelled 状态写入失败: {e}")
            self.log.update_content(f"{Color.YELLOW}[系统] 任务已被用户打断。{Color.END}\n")
            raise
        except LLMOutputTruncated as exc:
            # 输出反复被 max_tokens 截断：明确落库 failed，绝不让工具结果误当最终答案
            self.session.state = 'failed'
            db = ConversationDB.from_path(self.database_path)

            async def mark_truncated() -> None:
                async with db.aconnect() as con:
                    await con.execute(
                        "UPDATE session SET state='failed', error=?, finished_at=? WHERE session_id=?",
                        (str(exc), datetime.now(timezone.utc).isoformat(), self.session.id),
                    )
                    await con.commit()

            try:
                await aretry_on_locked(mark_truncated)
            except Exception as e:
                print(f"[reAct] truncated 状态写入失败: {e}")
            self.log.update_content(f"{Color.RED}[系统] {exc}{Color.END}\n")
            raise

    async def _run_loop(self):
        '''reAct 的主循环（从 run 拆出以便统一捕获 AgentCancelled）。'''
        while self._continue:
            self.session.state = 'thinking'
            await self._record_phase('thinking')
            self.step_count += 1

            # 每轮循环边界检查一次打断请求（流式期间的打断由 _cancel_watcher 负责）
            await self._check_cancellation()

            # 每轮推理前，轮询并注入外部事件
            await self._poll_and_inject_external_events()

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

                    async def mark_completed() -> None:
                        async with db.aconnect() as con:
                            await con.execute(
                                "UPDATE session SET state = ?, result = ?, finished_at = ? WHERE session_id = ?",
                                ('completed', content, datetime.now(timezone.utc).isoformat(), self.session.id)
                            )
                            await con.commit()

                    await aretry_on_locked(mark_completed)
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

                async def mark_stopped() -> None:
                    async with db.aconnect() as con:
                        await con.execute(
                            "UPDATE session SET state = ?, result = ?, finished_at = ? WHERE session_id = ?",
                            ('completed', content, datetime.now(timezone.utc).isoformat(), self.session.id),
                        )
                        await con.commit()

                await aretry_on_locked(mark_stopped)
                # 任务结束前沉淀经验 case
                await self._persist_case()
                if self.agent.id != 'a-0':
                    await self.agent.clear_context()
                    print(f"Agent {self.agent.name}上下文已释放！")
                return content

    async def reasoning(self) -> list:
        '''
        reAct的推理方法，分析agent的上下文和工具，决定下一步行动。
        '''
        agent = self.agent
        # agent.prompt 是身份 prompt，必须保留，不允许被任务要求覆盖。
        response = await agent.llm_call()
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
            # 流式期间的打断监视：cancel_requested 时置位 _cancel_event
            watcher = asyncio.create_task(self._cancel_watcher())
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
            except (httpx.HTTPError, openai.APIConnectionError) as e:
                self.log.update_content(
                        new_content=f"{Color.RED}[reasoning步骤]出现网络错误：{e}，{2 ** (self._reset_count+1)}秒后重试"
                        )
                self._reset_count += 1
                await asyncio.sleep(2 ** self._reset_count)
                # 重试，只是网络问题的话让用户自行等待或者切断程序
                return await self.reasoning()
            except AgentCancelled:
                # 打断请求：关闭底层流，向上传播由 run() 统一落库 cancelled
                close = getattr(response, "close", None)
                if close is not None:
                    try:
                        maybe_awaitable = close()
                        if asyncio.iscoroutine(maybe_awaitable):
                            await maybe_awaitable
                    except Exception:
                        pass
                raise
            except Exception as e:
                self.log.update_content(new_content=f"{Color.RED}[reasoning步骤]未知的错误：{e}")
                raise e
            finally:
                watcher.cancel()
                self.log.end_stream()

            # 输出被 max_tokens 截断：finish_reason=='length'，或 tool_call 被拦腰截断。
            # 截断的输出不能按"正常说完"处理（否则上一条工具结果会被误存为最终答案）。
            if last_finish_reason == 'length' or leftover_tool_calls:
                return await self._retry_on_truncation()

        else:
            message = response.choices[0].message
            if response.choices[0].finish_reason == 'length':
                return await self._retry_on_truncation()
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

    async def _retry_on_truncation(self) -> list:
        """输出被 max_tokens 截断时的处理：注入收敛提示重试，反复截断则抛 LLMOutputTruncated。"""
        if self._truncation_retries < self.MAX_TRUNCATION_RETRIES:
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
            return await self.reasoning()
        raise LLMOutputTruncated(
            f"模型输出连续 {self.MAX_TRUNCATION_RETRIES + 1} 次被 max_tokens 截断"
            f"（当前上限 {self.agent.max_tokens} tokens）。"
            "这通常意味着 thinking 过长，请增大 max_tokens 或拆分任务。"
        )

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
        for tool in get_tools_lst():
            try:
                schema = tool.input_schema.to_parameters_schema()
            except Exception:
                continue
            props = schema.get("properties", {})
            required = frozenset(schema.get("required", []))
            full_keys = frozenset(props.keys())
            if required:
                required_map.setdefault(required, tool.tool_name)
            if full_keys:
                full_map.setdefault(full_keys, tool.tool_name)
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
        tools_list = get_tools_lst()

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
                available_names = sorted({t.tool_name for t in tools_list})
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
            for tool in tools_list:
                # NOTE: get_tools_lst() 现在返回实例对象（不再是类），因此直接用 tool.tool_name 匹配。
                if tool.tool_name == tool_name:
                    # 统一注入当前 agent 到工具实例中，以便工具内部获取上下文和进行安全审计
                    # 我知道这是很粗糙的设计，因为Agent不应该承载这么多的上下文信息，但不妨把
                    # Agent看成一个运行状态机，reAct专注过程，Agent专注状态
                    tool_instance = tool.__class__(subagent=self.agent)

                    input_schema_class = tool_instance.input_schema
                    input_instance = input_schema_class(**tool_args)
                    session.state = 'waiting'
                    acts.append(tool_instance.safe_call(input_instance, session))
                    tool_call_ids.append(tool_call_id)
                    tool_names.append(tool_name)
                    found = True
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
        """写入 session_events 遥测事件。

        遥测写入是可丢弃的：多进程并发时 SQLite 写锁竞争激烈，
        重试耗尽后只记录日志，绝不能让日志/事件写入杀死 Agent 主流程。
        使用异步连接 + aretry_on_locked，避免同步 busy_timeout 等待冻结事件循环。
        """
        now = datetime.now(timezone.utc).isoformat()
        db = ConversationDB.from_path(self.database_path)

        async def write_event() -> None:
            async with db.aconnect() as con:
                await con.execute(
                    "UPDATE session SET heartbeat_at=? WHERE session_id=?",
                    (now, self.session.id),
                )
                await con.execute(
                    "INSERT INTO session_events (session_id, event_type, data, created_at) VALUES (?, ?, ?, ?)",
                    (self.session.id, event_type, json.dumps(data, ensure_ascii=False), now),
                )
                await con.commit()

        try:
            await aretry_on_locked(write_event)
        except Exception as e:
            self.log.update_content(
                f"{Color.YELLOW}[reAct] 事件写入失败（已忽略）: {event_type}: {e}{Color.END}\n"
            )

    def session_create(self, session_id: str = None) -> None:
        '''
        创建session，记录agent的整个生命周期。
        Session 文件放在 agent 所属 conversation 的 sessions/ 目录下。
        同时写入数据库作为单一事实来源。
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
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        session_ = Session(id=session_id, path=_path)
        self.session = session_
        self.log.session = session_

        # 数据库为单一事实来源：创建即入库
        db = ConversationDB.from_path(self.database_path)

        def create_session_record() -> None:
            with db.connect() as con:
                con.execute(
                    """INSERT OR IGNORE INTO session
                    (session_id, agent_id, agent_type, parent_session_id, query, state, result, pid,
                     worker_id, created_at, started_at, heartbeat_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_.id,
                        getattr(self.agent, 'id', None),
                        getattr(self.agent, 'type', None),
                        self.parent_session_id,
                        getattr(self.agent, 'query', ''),
                        'running',
                        '',
                        os.getpid(),
                        f'process:{os.getpid()}',
                        session_.create_time.isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                con.execute(
                    """UPDATE session SET
                    agent_id = COALESCE(agent_id, ?),
                    agent_type = COALESCE(agent_type, ?),
                    parent_session_id = COALESCE(parent_session_id, ?),
                    query = COALESCE(query, ?),
                    state = 'running',
                    pid = ?,
                    worker_id = ?,
                    started_at = COALESCE(started_at, ?)
                    WHERE session_id = ?""",
                    (
                        getattr(self.agent, 'id', None),
                        getattr(self.agent, 'type', None),
                        self.parent_session_id,
                        getattr(self.agent, 'query', ''),
                        os.getpid(),
                        f'process:{os.getpid()}',
                        datetime.now(timezone.utc).isoformat(),
                        session_.id,
                    ),
                )
                con.commit()

        retry_on_locked(create_session_record)
        return

    def kill(self):
        session = self.session
        session.state = 'killed'
        session.upload_json()
        self._continue = False
        # 同步数据库
        db = ConversationDB.from_path(self.database_path)
        with db.connect() as con:
            cur = con.cursor()
            cur.execute(
                "UPDATE session SET state = ? WHERE session_id = ?",
                ('killed', session.id)
            )
            con.commit()


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

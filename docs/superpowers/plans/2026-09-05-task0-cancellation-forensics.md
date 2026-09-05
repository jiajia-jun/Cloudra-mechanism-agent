# Task 0 — 停止失效取证（cancellation forensics）

> 2026-09-06。配套计划：`2026-09-05-event-driven-supervisor.md` 的 Task 0 / Task 5。
> 本文只记录取证结论与为 Task 5 定的接口命名；实现代码零改动。
> 回归测试：`tests/test_llm_cancellation.py`、`tests/test_runtime_v2_cancellation.py`（本地 fake HTTP/SSE，不触真实 provider）。

## 1. LLM 请求入口与后台 task 创建点枚举

### LLM 请求入口（全部最终汇入 `cloudra/infra/llm_client.py`）

| # | 入口 | 调用链 | 传输形态 |
| --- | --- | --- | --- |
| E1 | 轮次推理（TurnPipeline） | `runtime_v2/adapters.py:280` `LegacyLLMProvider.complete` → `_make_client`（:261-268，**每次 complete 新建 LLMClient**）→ `create_with_retry`（:352）或 `create_responses_with_retry`（:350，DeepSeek 原生搜索） | Chat SSE 流式 / Responses 流式 |
| E2 | run 收尾摘要（finalize） | `runtime_v2/agent_runner.py:747-751` `_finalize_run_context` → `run_summarizer` → `runtime_v2/compaction.py:173-196` `summarize_with_agent_settings`（**每次新建 LLMClient**）→ `create_with_retry` | Chat 非流式 |
| E3 | compaction 摘要 | `agent_runner.py:561-562` `_apply_compaction` → 同一个 `summarize_with_agent_settings`（触发点：手动 `agent.compact`、stop 且末指令为 `[Reminder]`（:298-301）、400/413 超窗两阶段（:234-263）） | Chat 非流式 |
| E4 | Supervisor 裁决循环 | `core/supervisor.py:358` `GraphSupervisor.run` → `agent.llm_call()`（`core/agent.py`，底层同为 LLMClient）；空回复强制收尾 :285 | Chat 非流式 |
| E5 | `chat_json` 结构化结论 | `llm_client.py:448-494`（Supervisor / YoloGuard 用；截断自动翻倍重试一次 :487-488） | Chat 非流式 |
| E6 | retry / fallback 内部增发 | `create_with_retry`（:407-431，指数退避 ≤60s×4）、`create_responses_with_retry`（:610-639）、三级 fallback（Level1 :367-377 → Level2 :346-362 → Level3 requests shim :337-343，触发判据 `is_fallback_trigger` :87-90 按异常文本匹配） | 全部 |

### 后台 task / 线程 / 子进程创建点

| # | 创建点 | 归属与回收现状 |
| --- | --- | --- |
| T1 | `agent_runner.py:128` runner 主任务 `agent:<sid>` | 登记在 `AgentRunner._tasks`，`cancel()`（:149-154）只取消它 |
| T2 | `agent_runner.py:678` `_schedule_run_finalize`：**裸 `asyncio.create_task`，不存引用、无 done callback、不可取消**；succeeded/cancelled/failed 三结局都调度（:328-330、:366、:373） | **无登记**，任何取消/shutdown 都碰不到 |
| T3 | `llm_client.py:522/:526` Responses 非流式/流式经 `asyncio.to_thread`；:592 逐 chunk `to_thread(next, ...)`；:647-652 Level3 `run_in_executor`；`streaming.py` 同步生成器逐块 to_thread | **工作线程不可取消**，取消 await 线程照跑（T7 实证） |
| T4 | `js_runtime.py:173-190` 每程序一个 node 宿主，`start_new_session=True`（:188）；`_terminate_process`（:192-218）单次执行内完整（SIGTERM→2s→SIGKILL→reap） | **无全局活动 host 登记表**；父猝死即成孤儿 |
| T5 | `services/api_v2/app.py:128-154` lifespan 管理 watchdog / compute_notify / review_worker / email_listener / reminders | **不回收** runner 任务、finalize、JS host、LLM 客户端、launch_groups |
| T6 | `services/daemon_supervisor.py` 拉起链（ensure_scheduler / ensure_kg_vec / ensure_daemons） | **无关停全局标志**：watchdog 只认 flock/端口，无"显式全停后不再拉起"语义 |
| T7 | `adapters.py:402-404`：SSE 消费循环只有 `except Exception` 才 `_close_stream`；**CancelledError 时流被遗弃**（`AsyncOpenAI` 实例缓存 `_openai_client` :161-162 从不关闭，LLMClient 无 close/aclose） | 连接泄漏实证见 R4/R5 |

## 2. 归属表：session/run → task → request

| 资源 | 作用域键 | 创建者 | 现有回收者 | 缺口 |
| --- | --- | --- | --- | --- |
| run task | session_id | `AgentRunner.schedule` | `CancelRunner` effect → `runner.cancel` | 无（覆盖良好） |
| finalize task | session_id + run_id | `_schedule_run_finalize` | **无** | 不在 `_tasks`；cancel/shutdown 均遗漏 |
| turn LLM 请求 | run_id（事件 `llm.request_started`） | pipeline → LLMClient | 随 run task 取消 | 已发出的请求远端不可撤销；本地 SSE 连接不关闭（R4/R5） |
| finalize/compaction 摘要请求 | session_id + run_id | `_finalize_run_context` / `_apply_compaction` → 新建 LLMClient | compaction 随 run task 取消（R9 证绿）；finalize **无**（R1/R2 证红） | finalize 无准入检查：取消后仍可**新发**摘要请求（R2 实证） |
| retry/fallback 增发 | 单次请求内部 | `create_with_retry` / `create` | CancelledError 不被吞（只捕 `Exception` 子类）——退避中取消有效（R6/R8 证绿） | 无发送前准入检查；to_thread/executor 段取消无效（R7） |
| requests 工作线程 | 无 | `to_thread` / `run_in_executor` | **无** | 取消后线程仍阻塞在 `requests.post`/`iter_content`（R7 实证） |
| JS host 进程 | execution_id | `JavaScriptRuntime._launch` | `_terminate_process`（取消路径完整） | 无全局登记；父死即孤儿 |
| Supervisor LLM 循环 | 项目（shell session） | `GraphSupervisor.run`（经 review_worker / DagController） | review_worker 生命周期 | 壳取消 ≠ 执行取消（事故基线：23:36:27 取消后 23:36:34 仍输出） |

## 3. 已证实的停止失效路径（测试实证）

测试运行：`pytest -q tests/test_llm_cancellation.py tests/test_runtime_v2_cancellation.py` → **5 failed, 7 passed**（全红或全绿都算未完成；以下为逐条记录）。

| ID | 路径 | 证据（测试） | 结果 |
| --- | --- | --- | --- |
| R1 | succeeded run 的 finalize（LLM 摘要进行中）遇用户取消：finalize 任务**不被取消**，继续占用 LLM | `test_cancel_cancels_inflight_finalize_summary`：取消完成后 `finalize:<sid>` 仍 pending（assert not survivors 失败） | **红（行为不符）** |
| R2 | finalize 已调度但尚未发请求时取消：取消完成后释放门闩，finalize **照常新发摘要请求**（实测 summarizer.calls 0→1） | `test_cancel_before_finalize_starts_blocks_summary_request`：assert calls == 0 失败 | **红（行为不符）** |
| R3 | 服务关闭无入口：runner/finalize 活动时无统一回收 API | `test_core_aclose_cancels_runners_and_finalizes`：`AttributeError: 'RuntimeCore' object has no attribute 'aclose'` | **红（未来 API，预期失败方式 = AttributeError）** |
| R4 | Chat SSE 流中途取消：底层连接**不关闭**（adapters :402-404 只在 `except Exception` 时 `_close_stream`）；释放门闩后服务端尾块仍写入成功 | `test_cancel_mid_sse_stream_closes_connection`：write_failures 为空，assert 失败 | **红（行为不符）** |
| R5 | Responses 流式（`asyncio.to_thread` 逐块拉）中途取消：孤儿工作线程在门闩释放后**继续消费**流 | `test_cancel_mid_responses_stream_closes_connection`：同上，assert 失败 | **红（行为不符）** |

证绿（守护用例，当前已通过）：

| ID | 路径 | 测试 |
| --- | --- | --- |
| R6 | 请求发出前取消 → 计数恒 0 | `test_cancel_before_request_sends_nothing` |
| R7 | **characterization**：asyncio task 被取消后 requests 工作线程仍存活（子进程自报 `WORKER_THREADS_ALIVE` 非空，随后自释门闩收束）——文档化限制，不断言修复 | `test_requests_worker_thread_survives_task_cancellation`（独立子进程，绿色即"限制存在"） |
| R8 | 重试退避（`asyncio.sleep`）中取消 → 不再增发（传输层 + runner 层各一） | `test_cancel_during_retry_backoff_stops_new_attempts` / `test_cancel_during_retry_backoff_stops_retries` |
| R9 | cancelled 结局的 finalize 走确定性 fallback，**不发** LLM 摘要；compaction 摘要 await 在 runner 任务内，取消即中断且不重发 | `test_cancelled_run_finalize_uses_deterministic_fallback` / `test_cancel_during_compaction_stops_summary_request` |
| R10 | fallback 切换前取消 → Level2/Level3 请求不出现（CancelledError 不被 `except Exception` 吞入 fallback） | `test_cancel_before_fallback_switch_blocks_level2_request` |

排除/澄清：

- "所有僵尸进程都在调 LLM"不成立：OS defunct 已退出不能发请求；本取证证实的失效是**取消后新建/继续的 LLM 请求**（R1/R2/R4/R5）与**不可取消的传输线程**（R7），加上无回收入口（R3）。
- retry 退避与 fallback 判定本身的取消语义是健康的（R8/R10）；失效集中在 finalize 所有权与流/线程关闭。
- 一个额外发现（已写进测试注释）：429 响应体若含 "rate limit"/"too many requests" 等词会被 `is_fallback_trigger` 当中转站拦截而直接降级到 requests shim，**绕过** `create_with_retry` 的退避（shim 抛 `requests.HTTPError`，chat 路径重试只捕 openai 异常）。测试构造时需避开这些关键词；是否算 bug 留给 Task 5 判定。

## 4. 给 Task 5 的最小新 API（命名即契约，照此实现）

命名贴合现有风格（`AgentRunner.schedule/cancel`、`compute_notify.close()` 等协作者均为 `async close()`；httpx/openai 侧为 `aclose()`）：

```python
class AgentRunner:
    def track_background(self, session_id: str, task: asyncio.Task, *, label: str) -> asyncio.Task:
        """登记 session 作用域的后台任务（finalize 等）；完成自动出登记。
        _schedule_run_finalize 必须改走这里，禁止裸 create_task。"""

    async def cancel(self, session_id: str) -> None:
        """语义扩展：取消 run task + 该 session 全部已登记后台任务并 await。
        签名不变；作用域为 session（取消任一 run 即收掉该 session 的未完成收尾）。"""

    async def cancel_all(self) -> None:
        """shutdown 用：取消全部 session 的 run/background 任务并 await。"""

class RuntimeCore:
    async def aclose(self) -> None:
        """服务关闭唯一入口（Task 5）：停止准入 → runner.cancel_all() →
        回收本 core 拥有的 JS host → 供 api_v2 lifespan 调用。
        注：测试 test_core_aclose_cancels_runners_and_finalizes 以此名为准。"""

class LLMClient:
    def __init__(self, ..., abort_event: asyncio.Event | None = None): ...
    def _raise_if_aborted(self) -> None:
        """每次实际发送前、每次 retry 退避后、每次 fallback 切换前调用；
        abort_event 置位即抛 CancelledError。"""
    async def aclose(self) -> None:
        """关闭缓存的 _openai_client / _openai_client_custom（AsyncOpenAI.aclose）。
        对已发出的请求：本地停止读取/重试/新请求并尽量关连接；
        远端计算与账单不可撤销（契约第 4 条），aclose 不承诺撤回。"""

class JavaScriptRuntime:
    def active_executions(self) -> dict[str, asyncio.subprocess.Process]: ...
    async def aclose(self) -> None:
        """终止并 reap 全部登记 host（走既有 _terminate_process）。"""

# daemon_supervisor.py
def request_daemons_shutdown() -> None:
    """置全局关停标志：ensure_* 自此拒绝拉起（watchdog 自愈同步失效）。
    用于显式"停止全部 Cloudra"，普通 agent.cancel 不触此。"""
```

实施要点（测试已锁定的断言）：取消完成后 finalize 任务必须 done（R1）；取消前已 armed 的 finalize 在门闩释放后不得新发请求（R2）；`core.aclose()` 返回后 runner/background 登记全空且无新增请求（R3）；SSE 取消必须关闭连接（R4/R5，Level1 靠 aclose 流，to_thread 路径需要可关闭的 `requests.Response` 句柄或受控隔离——若保留同步路径，提供有界退出，不允许无限悬挂线程）。

## 5. 建议（记录备查，本任务不改实现）

1. `_schedule_run_finalize`（agent_runner.py:662-681）改走 `track_background`；cancelled/failed 结局保持确定性 fallback 不动（R9 已是绿守护）。
2. `adapters.py:402` 的 `except Exception` 改为同时 `except asyncio.CancelledError`（先 `_close_stream` 再 re-raise），配合 `LLMClient.aclose`。
3. `summarize_with_agent_settings`（compaction.py:173-196）每次新建 LLMClient 且从不关闭——Task 5 应让它接受调用方传入的 client/abort_event，而不是自建无回收传输。
4. `api_v2/app.py:144-154` lifespan 收尾追加 `await core.aclose()`，顺序：停止准入/watchdog → 取消推理与收尾任务 → 关客户端/流 → 回收 JS host。
5. R7 的线程悬挂如不能在传输层根治，按 Task 0 计划改用受控隔离进程承载 requests shim，不留无限悬挂线程。

## 6. Task 5 落地结论补记（2026-09-06，替代 §5 第 5 条的受控隔离进程方案）

Task 5 实施时发现在传输层可以根治流式悬挂，**未采用受控隔离进程**：

- **流式路径（R4/R5 的修复）**：`LLMClient` 为每个 requests 流式响应登记 `_StreamHandle`（创建时捕获底层 TCP socket，预设 `SO_LINGER(1,0)` 中止式关闭）；取消/aclose 时 `abort()` 直接对 socket 做 `shutdown(SHUT_RDWR)` + `close`——shutdown 不受 urllib3 `BufferedReader` 跨线程锁影响，立即唤醒 to_thread 里的阻塞读线程并 RST 对端（高层 `resp.close()` 跨线程会卡锁到读超时，实测 30s，已明文禁止走该路径）。OpenAI SDK 流（Level1/2）走 `_abort_stream_connection` 同款 socket 层断开。取消后服务端尾块写入失败（fake 服务断言 `write_failures` 非空），R4/R5 转绿。
- **非流式 requests shim 的残余限制**：非流式 `requests.post` 没有可关闭句柄（响应未返回前无 socket 暴露），取消 asyncio task 后工作线程仍阻塞在 `requests.post` 里——但退出以 `timeout=self.timeout`（读超时）为上界，不是无限悬挂，因此不引入隔离进程。R7（`test_requests_worker_thread_survives_task_cancellation`）保留为 characterization 守护：子进程自报 `WORKER_THREADS_ALIVE` 非空即"限制仍存在"，防止未来有人误以为该路径已可即时取消。
- **准入检查**：`abort_event`/`aclose` 后的 `_raise_if_aborted` 在每次实际发送前、retry 退避后、fallback 切换前抛 CancelledError（R2/R6/R10 语义固化）；`core.aclose()` 为服务关闭唯一入口（R3）。
- 进程回收侧：JS host 登记 `active_executions()` + `aclose()` 终止并 reap；父进程被 SIGKILL 时 host 靠 stdin EOF 自清理（finally 不执行，测试实证）；`cloudra stop` 写 `daemons.stop` marker 令守护自检退出并禁止自愈拉起。

# Harness 缓存连续性与全历史压缩 — 实测验收报告

计划：`docs/superpowers/plans/2026-09-13-harness-cache-continuity.md`（Task 6）
日期：2026-09-13
基线夹具：`tests/test_runtime_v2_context_cache.py`；旧版基线：
`docs/superpowers/reports/2026-09-13-harness-cache-baseline.json`

## 交付内容（Task 1–5 回顾）

- **Task 1**：最终请求回归夹具 + Responses usage 缓存细项保真修复
  （`_translate_responses_usage` 保留 `input_tokens_details.cached_tokens`，
  缺失不记 0）+ 请求指纹/首差异日志诊断（主 agent 与摘要请求分组标记）。
- **Task 2**：静态前缀固定——`LegacyContextPrefix` 上下文前缀 owner；
  MEMORY/AGENTS.md/工作区观察改为带来源的动态快照，跨轮变化只追加
  替代消息；JS instructions 初始化时安装一次，adapter 不再尾部追加。
- **Task 3**：通知真实进入历史——NoticeManager 批次/游标模型
  （`collect_batch`/`confirm_consumed`，`context.notices_consumed` 事件），
  LLM 重试逐字节重发同一批；GoalStage 不再过滤重写历史 goal 消息。
- **Task 4**：会话级上下文投影——`core.session_contexts` +
  `ContextBroker`（`context.prefix_installed`/`context.appended`/
  `context.compacted` 事件，apply_event 唯一应用）；run 只是执行生命周期；
  per-run 自动摘要/handover 管线与 `context_tree.py`（build_seed_context 等）
  全部删除；快照载荷携带投影；恢复路径不执行任何工具/JS/计算。
- **Task 5**：统一全轮次压缩——逐字指令区（用户原文按消息身份完整保留）
  + 结构化 JSON 摘要（pydantic 校验 + 来源序号）+ 按容量分段（现有
  context_window/输出预算，85% 余量）；触发只有手动/预算/overflow；
  schedule stop 不再自动 compact；版本不符放弃候选。

## 实测设置（同条件对照）

- provider/model/路由：两版同为 DeepSeek `deepseek-v4-flash`（真实用户配置
  槽位），chat completions 流式，`native_search=off`，`max_tokens=256`，
  traditional 调用协议，温度默认。usage 缓存字段：
  `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`。
- 固定回放场景（两版逐字节相同输入与工具结果；工具执行本地打桩，只有
  LLM 调用真实）：7 步——用户工具轮（写文件指令）、工作区写入 + MEMORY
  更新 + 用户纠正、schedule 唤醒、pin + push、unpin + schedule 唤醒、
  显式 compact、最终状态轮。驱动：`scripts/replay_cache_probe.py`；
  汇总：`scripts/analyze_cache_probe.py`（公式与计划逐字一致）。
- 采样：3 个独立重复任务组 × 2 版本，组间交错执行（new→old、old→new、
  new→old），压缩网络与缓存预热差异的影响。DeepSeek 缓存 TTL 为分钟级，
  组内轮次紧贴；两版提示词头部内容高度相同，提供方内容寻址缓存对两版
  同等加温——差异因此偏保守（见「局限」）。

## 实测结果

原始逐请求计量 JSON：`/tmp/cache-probe/*2_g*.json`（驱动
`scripts/replay_cache_probe.py`，汇总 `scripts/analyze_cache_probe.py`，
公式与计划逐字一致；可重算）。聚合结果随报告归档：
`docs/superpowers/reports/2026-09-13-harness-cache-validation-data.json`。

聚合（3 组独立重复，组间交错 new→old / old→new / new→old）：

| 指标 | 旧版（HEAD） | 新版（工作树） | 变化 |
| --- | --- | --- | --- |
| 总体 token 加权命中率 | 97.56%（组：97.85/97.35/97.47，stdev 0.26pp） | **98.84%**（98.82/98.86/98.86，stdev 0.02pp） | **+1.28pp** |
| 稳定区间命中率（去冷启动） | 97.58% | **99.20%** | **+1.62pp** |
| 未缓存输入 token（主流程合计） | 34,787 | **15,052** | **−56.7%** |
| prefix_mutations（非边界请求改写旧前缀） | 30（8/12/10 每组） | **0（0/0/0）** | 消除 |
| 摘要调用次数 | 27（9/组：每 run 收尾 finalize + schedule stop compact） | **3（1/组：仅显式 compact）** | −89% |
| 摘要输入/输出 token | 10,449 / 8,918 | **5,186 / 7,821** | 输入 −50% |
| 首 token 延迟（均值/最大，秒） | 0.464 / 1.958 | **0.439 / 1.070** | 无回归（略降） |
| usage 缺失计数 | 0 | 0 | provider 数据齐全 |

冷启动边界（单列、不隐藏）：两版各组均为「首请求」+「compact 后首请求」
（新版 2 个/组：首请求 + 显式 compact 后首请求；旧版 3 个/组：首请求 +
两次 schedule stop 自动 compact 后的首请求）。旧版的显式 compact 命令在
idle agent 上被 run.started 过期吞掉（pending_compactions 旧语义）——实测
到的旧行为，报告如实标注；新版的显式 compact 真实生效（trigger=manual，
分段 1 段 + 结构化校验通过）。

结论：**效果验收通过**——新版实测命中率更高（总体 +1.28pp、稳定区间
+1.62pp）、主流程未缓存输入 token 下降 56.7%、prefix_mutations 实测为 0，
且摘要调用成本大幅下降、TTFT 无回归。

## 硬门禁核对

- `prefix_mutations == 0`（新版）：实测 0/0/0（三组）；结构证据：
  `tests/test_runtime_v2_context_cache.py` 17/17 绿——固定协议且未 compact
  的场景序列中，两轮工具调用、pin/push、工作区变更、MEMORY/AGENTS.md
  更新、schedule 唤醒、跨 run 唤醒的实际发送请求全部满足
  `current[:len(previous)] == previous` 且 tools 不变；重试逐字节重发
  （`test_retry_reuses_identical_prepared_request`）；取消不提前确认消费
  （`test_cancel_never_confirms_notice_consumption`）。旧版基线（同夹具在
  HEAD 上的首处分歧位置与完整计数）：
  `docs/superpowers/reports/2026-09-13-harness-cache-baseline.json`。
- 新版命中率提高、未缓存输入 token 下降：上表。
- 用户原文与授权边界回归：
  `tests/test_runtime_v2_compaction_integrity.py` 21/21（三轮目标+纠正、
  两轮 reminder、>12,000 字符轨迹、>4,000 字符用户消息逐字保留、超长
  消息分段全覆盖、空输出/结构错误/区段失败/不缩短/容量不足/取消全部
  拒替换、版本守卫放弃过期候选）。
- 摘要调用次数/成本、TTFT：上表（新版摘要调用 1 次/组，仅为显式 compact）。
- 工具历史配对 / 事件恢复 / 取消语义无回归：`tests/test_runtime_v2_runner.py`
  、`_recovery.py`、`_persistence.py`、`_replay_equivalence.py`（三路径逐
  字段全等含 session_contexts）、`_cancellation.py`、`_shutdown.py` 全绿；
  回放场景全部 run 以 succeeded 收尾（任务完成质量无回归）；
  全套测试套件：`uv run pytest -q tests/` → 2,211 项，退出码 0（日志
  /tmp/pytest_full.log，进度 100% 无 F/E）。

## 局限与剩余风险

- **提供方内容寻址缓存的加温效应**：两版提示词头部内容高度相同，
  DeepSeek 缓存按内容寻址且 TTL 为分钟级——交错执行让两版同等受益，
  因此命中率差距（+1.28pp）是保守下界；结构性差异更真实的口径是
  未缓存输入 token（−56.7%）与 prefix_mutations（30 → 0）。
- 实测模型合规性：回放场景的工具轮依赖真实模型按指令调用 write 等工具；
  各组轮次数有小幅波动（12–16 请求/组），已在样本数与波动中如实呈现。
- 缓存 TTL 之外的长期行为（跨小时级会话）未测；预算触发压缩的估算用
  chars/4 近似 token，真实 token 数以 provider 拒绝（overflow）为准——
  overflow 路径有独立测试覆盖。
- 摘要语义质量：fake 摘要测试只证明输入覆盖与原文保留；真实摘要的语义
  完整性需人工/真实模型抽查（本报告未做语义评分）。
- 旧版对照取自 HEAD 工作树（`.worktrees/head-old`），未修改任何源码回退
  用户改动。


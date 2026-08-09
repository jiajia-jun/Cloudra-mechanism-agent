# `ts_guess` 严格验证模式设计

日期：2026-08-10

## 目标与边界

`ts_guess` 的主要职责仍是向 agent 提供过渡态搜索方向。`interpolate`、`scan_prepare` 和 `scan_parse` 都是探索性功能，不承担 SI 级证据判定，也不受严格模式影响。

本次只调整 `mode="verify"`：新增可选的 `strict` 模式，让调用者在已经取得 TS 频率、部分 IRC 路径以及两侧优化中间体后，检查 IRC 两端是否沿正确方向离开 TS，并在几何上位于 TS 与对应中间体之间。

严格模式不宣称 TS “100% 正确”，不管理端点优化任务，不保存工作流状态，也不要求 IRC 自身完整走到极小值。

## 接口

在 `TsGuess_input_schema` 中新增：

```python
strict: bool = False
```

该参数仅在 `mode="verify"` 时生效。现有 `reactant_path/reactant_text` 与 `product_path/product_text` 在严格模式中表示 IRC 两侧经普通几何优化得到的预期中间体；二者顺序不作要求。现有 `watch_pairs` 可显式指定用于判断反应进程的原子对。

不新增持久状态字段或端点优化日志字段。结果继续使用现有 `verdict`、`checks`、`irc_end_a_path` 和 `irc_end_b_path`。

非严格模式的正向结论使用 `candidate`，避免把启发式检查写成正式的 `pass`。严格模式的 `verdict` 使用 `pass`、`fail` 或 `inconclusive` 前缀：`pass` 表示现有证据与预期路径一致，`fail` 表示存在明确的反证，`inconclusive` 表示材料不足或无法稳定判断。三者只是本次纯函数调用的结果，不是持久化工作流状态。

## 严格验证算法

工具首先解析 `freq_log`。频率作业正常完成且恰好一个虚频时继续；正常完成但虚频数为零或大于一时返回 `fail`；作业未收敛、结构无法提取或日志不足时返回 `inconclusive`。

TS 几何取自频率日志的最终坐标。IRC 日志不要求自然终止或到达极小值，只要求能从 TS 两侧各提取至少一个有效路径点。工具分别选取反应坐标负侧和正侧距离 TS 最远的有效帧，写出当前已有的 `irc_end_a.xyz` 与 `irc_end_b.xyz`。缺少任一方向时返回 `inconclusive`，而不是把未完成计算当成错误机理。

严格模式要求提供两个优化中间体结构。TS、IRC 帧与优化中间体必须具有相同的元素序列；无法确认原子映射时返回 `inconclusive`。

几何关系在原子对距离空间中判断，以避免平移、旋转和弯曲反应路径对 Cartesian RMSD 的干扰。若调用者提供 `watch_pairs`，直接使用这些原子对。否则，对每个候选中间体计算全部原子对相对于 TS 的距离变化，选取变化最大的至多五对，并忽略绝对变化小于 0.15 Å 的原子对。没有任何信息性原子对时返回 `inconclusive`。

对某个 TS—IRC 端点—优化中间体组合，每个信息性原子对均计算距离进度：

```text
p_i = (q_end,i - q_TS,i) / (q_intermediate,i - q_TS,i)
```

对每个原子对，把 `q_TS` 与 `q_intermediate` 构成的闭区间两端各扩展 0.10 Å；`q_end` 必须落在扩展后的区间内。同时，端点在所选距离向量空间中必须比 TS 更接近该中间体。该检查证明的是路径方向与几何插值关系，不要求原始 IRC 端点已经形成中间体的完整键连通性。

工具尝试两种无序指派：A→反应物且 B→产物，以及 A→产物且 B→反应物。若存在一组一一对应指派使两侧都满足中间值条件，严格验证返回 `pass`；如果材料完整但两种指派均明确朝错方向或越过容差范围，返回 `fail`；若原子映射、有效坐标或信息性反应坐标不足，则返回 `inconclusive`。

IRC 是否因 `maxpoints` 停止只写入 `checks` 作为背景信息，不参与严格模式的通过条件。

## 非严格模式

`strict=False` 时保持启发式定位用途。工具报告频率数量、可用 IRC 端点及粗略连通性信息，但不要求 IRC、优化中间体或中间值证明。恰好一个虚频时使用 `candidate` 措辞；明显不是一阶鞍点时使用 `unlikely`；缺少可解析材料时使用 `inconclusive`。`is_success` 只表示工具是否正常执行，不表示化学结论正确。

## 错误处理

文件不存在、输入 schema 非法等调用错误仍通过现有工具错误机制返回 `is_success=False`。化学证据不足不视为工具执行错误，返回 `is_success=True` 与 `verdict="inconclusive: ..."`。明确的频率或路径反证返回 `is_success=True` 与 `verdict="fail: ..."`。

严格模式不得因为 IRC 未完整收敛、优化中间体顺序相反或原始 IRC 端点尚未改变键连通性而误判失败。

## 测试

测试覆盖以下行为：非严格模式下单虚频且无 IRC 返回 `candidate`；严格模式缺少 IRC 或优化中间体返回 `inconclusive`；未完整 IRC 的两侧帧只要分别处于 TS 与优化中间体之间即可返回 `pass`；预期中间体顺序交换不改变结果；一侧明确朝相反方向时返回 `fail`；元素序列不一致、缺少双向 IRC 帧或没有信息性距离变化时返回 `inconclusive`；零虚频与多虚频的正常作业返回 `fail`；现有 `scan_parse` 测试与输出保持不变。

实现后运行 `tests/test_ts_guess.py`，并运行相关 Gaussian 帧解析测试，确认不破坏 IRC 帧提取与扫描解析。

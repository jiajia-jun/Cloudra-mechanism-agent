# 评分公平性修复（P1b 重算依据）

> 日期：2026-10-24
> 缘起：P1b 四臂 48 个 run 完成后，发现部分"算对了却被重罚"的案例；不重跑任务，只修评分器并离线重算。
> 数据：`/home/ly/cloudra-p1b-20261024`（48 个沙箱，四臂 × 四题 × 三轮）；重算结果 `/home/ly/cloudra-p1b-rescore/results.csv`。

## 1. 三处缺陷

### 1.1 JSON schema 过严（整图作废）

`cloudra/benchmark/schema.py`

- `MechanismNode.properties` 只允许 `dict[str, float | str]`：agent 写
  `"evidence_log": ["a.log"]`、`"imaginary_frequency_cm": [-633.3]` 即校验失败；
- 节点/边 `extra="forbid"`：多写 `note`、`overall`、`barrier_definition` 等就整图作废；
- 逐图作废后走"无可解析机理图"分支 → `-no_evidence_penalty` = **−1.0**。

证据：48 个交付图中 **19 个**违反旧严格 schema；其中 **8 个**是 `evidence_log`
写成列表，全部 −1.0。

### 1.2 evidence_log 只取第一个路径

`cloudra/benchmark/integrity.py`

TS 节点通常同时给出三份原生日志：

```
properties.evidence_log = [
  "ts/ts_0005/jobs/declaration_0001/ts_opt/refine.log",
  "ts/ts_0005/jobs/declaration_0001/frequency/frequency.log",
  "ts/ts_0005/jobs/declaration_0002/irc/irc.log",
]
```

旧实现只取第一个（opt 日志，没有频率块）→ `collect_barrier_evidence` 里
"saddles = 空" → accuracy=0。频率日志明明就在列表里。

### 1.3 hard 档选择性按 channel 字符串比较

`cloudra/benchmark/accuracy.py::score_qualitative_selectivity`

旧实现要求交付边的 `channel` **字符串等于** gold 内部标签
（`outward_rotation`、`double_outward_rotation`、`directed_face`），
但这些词在任务文本里从不出现，agent 只能写出 `E_channel`、`conrotatory-E`
这类等价标签——因此 hard 档 accuracy 恒为 0。

## 2. 修复

| 文件 | 修复 |
|---|---|
| `schema.py` | `properties: dict[str, Any]`；节点/边/图 `extra="ignore"` |
| `integrity.py` | `_evidence_paths()` 规范化单/多路径；物种按序尝试直到绑定成功；TS 绑定列表里全部可用原生日志；证据扫描先按后缀过滤（跳过 `.chk/.fchk` 等二进制）再解析路径 |
| `accuracy.py` | 选择性改为**按产物物种**比对：favored 边指向的产物 vs gold favored 通道的产物（`species_substitution_cost`），channel 字符串仅作向后兼容的快速通道 |
| `runner.py` | 传入 `gold_graph` / `cfg` / `match_threshold` 给选择性评分 |

## 3. 验证

单例（record/r1 HA1）：

| 阶段 | final | graph | selfc | accuracy |
|---|---|---|---|---|
| 原始 | −1.000 | 0 | 0 | 0 |
| 修 schema | +0.362 | 1.000 | 0.875 | 0 |
| 修多路径 | +0.362 | 1.000 | 0.875 | 0 |
| 修选择性 | **+0.963** | 1.000 | 0.875 | **1.0** |

全量离线重算（48/48）：

| 臂 | 旧 mean | 新 mean | 旧 sd | 新 sd |
|---|---|---|---|---|
| guided | 0.829 | **0.979** | 0.291 | 0.032 |
| brief-errors | 0.100 | **0.907** | 0.947 | 0.224 |
| record | 0.190 | **0.729** | 0.871 | 0.365 |
| standard | 0.245 | **0.534** | 0.778 | 0.574 |

| 臂 | easy | normal | hard | impossible |
|---|---|---|---|---|
| guided | 1.000 | 0.991 | 0.925 | 1.000 |
| brief | 1.000 | 0.960 | 0.943 | 0.724 |
| record | 0.972 | 0.914 | 0.929 | 0.102 |
| standard | 0.853 | 0.940 | 0.243 | 0.102 |

## 4. 仍然低分的情况（正确惩罚，不是缺陷）

- **impossible 误报**：`record`/`standard` 的 IA1 声明了"有机理"（barrier 18.6–25.4），
  按契约判 0 accuracy，只剩图分+自洽 ≈ 0.07–0.17；
- **无图交付**：`standard/r2 HA1` 没写 `mechanism_graph.json` → −1.0；
- **agent 未按契约声明**：`guided` 的 HA1 图把能量写进 `description` 散文、
  TS 节点没有 `energy_hartree`/`evidence_log`——这类 accuracy=0 是 agent 违规。

## 5. 复现

```bash
# 用修复后的评分器重算 48 个沙箱（不重跑任务）
/home/ly/cloudra-bench-20261019/.venv/bin/python /home/ly/bin/rescore.py
# 新旧对照
/home/ly/cloudra-bench-20261019/.venv/bin/python /home/ly/bin/compare_rescore.py
```

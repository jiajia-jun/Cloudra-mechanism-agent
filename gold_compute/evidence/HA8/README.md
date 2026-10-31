# HA8 · (2E,4Z,6E)-octa-2,4,6-triene thermal 6-pi electrocyclization: determine the stereochemical outcome

正式定义：[HA8.json](../../../ideapool/tasks/hard/HA8.json) · 档位：hard · 旧题最终原件；未重新科学验收。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../REPRODUCE.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| HA8_E1 | 29.48 | numeric_reference |

## 证据与限定

按历史最终回填表选取输入、原生日志和必要附件；本轮整理不重新裁决科学验收，也不把正常终止当作完整 IRC 证明。


## 复跑所需的外部文件

只在工作副本重定位文件路径；原输入和原日志保留原样。缺失 Hessian 的条目先复跑对应 TS/Freq，禁止拿其他驻点 Hessian 顶替。

| 输入及行号 | 原始读取路径 | 当前文件 / 操作 |
|---|---|---|
| [legacy/job081/input.inp](legacy/job081/input.inp):8 | `/data/cloudra/workspace/hard_resume_20260930/hard_replacements_20261001/H6PI/orca_inputs/04_ts_optfreq.hess` | [legacy/job077/04_ts_optfreq.hess](legacy/job077/04_ts_optfreq.hess) |

## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [legacy/job077/raw_output.log](legacy/job077/raw_output.log) | [legacy/job077/input.inp](legacy/job077/input.inp) | 频率 + TS优化 |
| [legacy/job080/raw_output.log](legacy/job080/raw_output.log) | [legacy/job080/input.inp](legacy/job080/input.inp) | 频率 + 极小值优化 |
| [legacy/job081/raw_output.log](legacy/job081/raw_output.log) | [legacy/job081/input.inp](legacy/job081/input.inp) | IRC |
| [legacy/job089/raw_output.log](legacy/job089/raw_output.log) | [legacy/job089/input.inp](legacy/job089/input.inp) | 频率 + 极小值优化 |
| [legacy/job090/raw_output.log](legacy/job090/raw_output.log) | [legacy/job090/input.inp](legacy/job090/input.inp) | 频率 + 极小值优化 |

本题登记 28 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

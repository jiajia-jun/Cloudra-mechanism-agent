# HB10 · cyclopentadiene + acrylonitrile Diels-Alder reaction: determine both stereochemical pathways

正式定义：[HB10.json](../../../ideapool/tasks/hard/HB10.json) · 档位：hard · 旧题最终原件；未重新科学验收。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../DELIVERY.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| HB10_E1 | 14.34 | numeric_reference |
| HB10_EM1 | 14.12 | numeric_reference |

## 证据与限定

按历史最终回填表选取输入、原生日志和必要附件；本轮整理不重新裁决科学验收，也不把正常终止当作完整 IRC 证明。


## 复跑所需的外部文件

只在工作副本重定位文件路径；原输入和原日志保留原样。缺失 Hessian 的条目先复跑对应 TS/Freq，禁止拿其他驻点 Hessian 顶替。

| 输入及行号 | 原始读取路径 | 当前文件 / 操作 |
|---|---|---|
| [legacy/job078/input.inp](legacy/job078/input.inp):9 | `/data/cloudra/workspace/hard_resume_20260930/hard_replacements_20261001/HDA_CN/orca_inputs_ready/02_ts_endo_optts.hess` | [legacy/job075/02_ts_endo_optts.hess](legacy/job075/02_ts_endo_optts.hess) |
| [legacy/job079/input.inp](legacy/job079/input.inp):9 | `/data/cloudra/workspace/hard_resume_20260930/hard_replacements_20261001/HDA_CN/orca_inputs_ready/03_ts_exo_optts.hess` | [legacy/job076/03_ts_exo_optts.hess](legacy/job076/03_ts_exo_optts.hess) |

## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [legacy/job075/raw_output.log](legacy/job075/raw_output.log) | [legacy/job075/input.inp](legacy/job075/input.inp) | 频率 + TS优化 |
| [legacy/job076/raw_output.log](legacy/job076/raw_output.log) | [legacy/job076/input.inp](legacy/job076/input.inp) | 频率 + TS优化 |
| [legacy/job078/raw_output.log](legacy/job078/raw_output.log) | [legacy/job078/input.inp](legacy/job078/input.inp) | IRC |
| [legacy/job079/raw_output.log](legacy/job079/raw_output.log) | [legacy/job079/input.inp](legacy/job079/input.inp) | IRC |
| [legacy/job084/raw_output.log](legacy/job084/raw_output.log) | [legacy/job084/input.inp](legacy/job084/input.inp) | 频率 + 极小值优化 |
| [legacy/job085/raw_output.log](legacy/job085/raw_output.log) | [legacy/job085/input.inp](legacy/job085/input.inp) | 频率 + 极小值优化 |
| [legacy/job086/raw_output.log](legacy/job086/raw_output.log) | [legacy/job086/input.inp](legacy/job086/input.inp) | 频率 + 极小值优化 |
| [legacy/job087/raw_output.log](legacy/job087/raw_output.log) | [legacy/job087/input.inp](legacy/job087/input.inp) | 频率 + 极小值优化 |

本题登记 46 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

# NU6 · Staudinger beta-lactam synthesis: ketene + methanimine -> 2-azetidinone

正式定义：[NU6.json](../../../ideapool/tasks/normal/NU6.json) · 档位：normal · 旧题最终原件；未重新科学验收。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../DELIVERY.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| NU6_E1 | 2.66 | numeric_reference |
| NU6_E2 | 15.72 | numeric_reference |

## 证据与限定

按历史最终回填表选取输入、原生日志和必要附件；本轮整理不重新裁决科学验收，也不把正常终止当作完整 IRC 证明。

- 历史验收保留项（非本轮复核）：已回填 2.66，但本地旧验收树注明 RC 有 −24.32 软虚频；本次未找到该起点零虚频修正记录，不能把旧源的 verified 当作严格最小值全过。

## 复跑所需的外部文件

只在工作副本重定位文件路径；原输入和原日志保留原样。缺失 Hessian 的条目先复跑对应 TS/Freq，禁止拿其他驻点 Hessian 顶替。

| 输入及行号 | 原始读取路径 | 当前文件 / 操作 |
|---|---|---|
| [legacy/edges/NU6_E1/IRC.recovered.inp](legacy/edges/NU6_E1/IRC.recovered.inp):9 | `e1ts.hess` | 原 Hessian 未归档；先运行同一步 TS.recovered.inp 的 OptTS+Freq 生成，再交给 IRC |
| [legacy/edges/NU6_E2/IRC.recovered.inp](legacy/edges/NU6_E2/IRC.recovered.inp):9 | `e2ts.hess` | 原 Hessian 未归档；先运行同一步 TS.recovered.inp 的 OptTS+Freq 生成，再交给 IRC |

## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [legacy/edges/NU6_E1/IRC.log](legacy/edges/NU6_E1/IRC.log) | [legacy/edges/NU6_E1/IRC.recovered.inp](legacy/edges/NU6_E1/IRC.recovered.inp) | IRC |
| [legacy/edges/NU6_E1/TS.log](legacy/edges/NU6_E1/TS.log) | [legacy/edges/NU6_E1/TS.recovered.inp](legacy/edges/NU6_E1/TS.recovered.inp) | 频率 + TS优化 |
| [legacy/edges/NU6_E2/IRC.log](legacy/edges/NU6_E2/IRC.log) | [legacy/edges/NU6_E2/IRC.recovered.inp](legacy/edges/NU6_E2/IRC.recovered.inp) | IRC |
| [legacy/edges/NU6_E2/TS.log](legacy/edges/NU6_E2/TS.log) | [legacy/edges/NU6_E2/TS.recovered.inp](legacy/edges/NU6_E2/TS.recovered.inp) | 频率 + TS优化 |
| [legacy/edges/NU6_E2/min_product_side.log](legacy/edges/NU6_E2/min_product_side.log) | [legacy/edges/NU6_E2/min_product_side.recovered.inp](legacy/edges/NU6_E2/min_product_side.recovered.inp) | 频率 + 极小值优化 |
| [legacy/edges/NU6_E2/min_reactant_side.log](legacy/edges/NU6_E2/min_reactant_side.log) | [legacy/edges/NU6_E2/min_reactant_side.recovered.inp](legacy/edges/NU6_E2/min_reactant_side.recovered.inp) | 频率 + 极小值优化 |
| [legacy/species/I1.log](legacy/species/I1.log) | [legacy/species/I1.recovered.inp](legacy/species/I1.recovered.inp) | 频率 + 极小值优化 |
| [legacy/species/P.log](legacy/species/P.log) | [legacy/species/P.recovered.inp](legacy/species/P.recovered.inp) | 频率 + 极小值优化 |
| [legacy/species/RC.log](legacy/species/RC.log) | [legacy/species/RC.recovered.inp](legacy/species/RC.recovered.inp) | 频率 + 极小值优化 |

本题登记 18 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

# NU3 · H3P=CH2 ylide + formaldehyde -> ethylene + H3P=O

正式定义：[NU3.json](../../../ideapool/tasks/normal/NU3.json) · 档位：normal · 旧题最终原件；未重新科学验收。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../REPRODUCE.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| NU3_E1 | 1.7 | numeric_reference |
| NU3_E2 | 55.81 | numeric_reference |
| NU3_E3 | 23.76 | numeric_reference |

## 证据与限定

按历史最终回填表选取输入、原生日志和必要附件；本轮整理不重新裁决科学验收，也不把正常终止当作完整 IRC 证明。


## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [legacy/edges/NU3_E1/IRC.log](legacy/edges/NU3_E1/IRC.log) | [legacy/edges/NU3_E1/IRC.recovered.inp](legacy/edges/NU3_E1/IRC.recovered.inp) | IRC |
| [legacy/edges/NU3_E1/TS.log](legacy/edges/NU3_E1/TS.log) | [legacy/edges/NU3_E1/TS.recovered.inp](legacy/edges/NU3_E1/TS.recovered.inp) | 频率 + TS优化 |
| [legacy/edges/NU3_E2a/IRC.log](legacy/edges/NU3_E2a/IRC.log) | [legacy/edges/NU3_E2a/IRC.recovered.inp](legacy/edges/NU3_E2a/IRC.recovered.inp) | IRC |
| [legacy/edges/NU3_E2a/TS.log](legacy/edges/NU3_E2a/TS.log) | [legacy/edges/NU3_E2a/TS.recovered.inp](legacy/edges/NU3_E2a/TS.recovered.inp) | 频率 + TS优化 |
| [legacy/edges/NU3_E2b/IRC.log](legacy/edges/NU3_E2b/IRC.log) | [legacy/edges/NU3_E2b/IRC.recovered.inp](legacy/edges/NU3_E2b/IRC.recovered.inp) | IRC |
| [legacy/edges/NU3_E2b/TS.log](legacy/edges/NU3_E2b/TS.log) | [legacy/edges/NU3_E2b/TS.recovered.inp](legacy/edges/NU3_E2b/TS.recovered.inp) | 频率 + TS优化 |
| [legacy/species/I1_adduct.log](legacy/species/I1_adduct.log) | [legacy/species/I1_adduct.recovered.inp](legacy/species/I1_adduct.recovered.inp) | 频率 + 极小值优化 |
| [legacy/species/I2_oxaphosphetane.log](legacy/species/I2_oxaphosphetane.log) | [legacy/species/I2_oxaphosphetane.recovered.inp](legacy/species/I2_oxaphosphetane.recovered.inp) | 频率 + 极小值优化 |
| [legacy/species/P_C2H4.log](legacy/species/P_C2H4.log) | [legacy/species/P_C2H4.recovered.inp](legacy/species/P_C2H4.recovered.inp) | 频率 + 极小值优化 |
| [legacy/species/P_H3P_O.log](legacy/species/P_H3P_O.log) | [legacy/species/P_H3P_O.recovered.inp](legacy/species/P_H3P_O.recovered.inp) | 频率 + 极小值优化 |
| [legacy/species/RC.log](legacy/species/RC.log) | [legacy/species/RC.recovered.inp](legacy/species/RC.recovered.inp) | 频率 + 极小值优化 |

本题登记 22 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

# NR1 · formamide dehydration: formamide -> hydrogen cyanide + water

正式定义：[NR1.json](../../../ideapool/tasks/normal/NR1.json) · 档位：normal · E1–E3 原件；E4 成功 run 缺件。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../REPRODUCE.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| NR1_E1 | 46.32 | numeric_reference |
| NR1_E2 | 22.8 | numeric_reference |
| NR1_E3 | 7.25 | numeric_reference |
| NR1_E4 | 68.85 | numeric_reference |

## 证据与限定

| 步骤 | TS 日志 | 稳定参照日志 |
|---|---|---|
| NR1_E1 | [E1/frequency.log](E1/frequency.log) | [references/formamide/formamide_frequency.log](references/formamide/formamide_frequency.log) |
| NR1_E2 | [E2/frequency.log](E2/frequency.log) | [E2/reactant_frequency.log](E2/reactant_frequency.log) |
| NR1_E3 | [E3/frequency.log](E3/frequency.log) | [E3/reactant_frequency.log](E3/reactant_frequency.log) |
| NR1_E4 | 成功原件缺失 | [references/INT1a/INT1a_frequency.log](references/INT1a/INT1a_frequency.log) |

### NR1_E1

- Latest decl11/12 independent reference minima reproduce the same accepted energies. Canonical older TS opt/frequency have exactly the same TS energy -169.699169421 Ha.
- Only archived true IRC1170 A outer-frame chain reaches INT-1a. Formamide minimum is independently seeded; do not label both true-arm chains complete.

| 计算链阶段 | 文件 |
|---|---|
| ts_optimization/input | [E1/ts_opt.gjf](E1/ts_opt.gjf) |
| ts_optimization/log | [E1/ts_opt.log](E1/ts_opt.log) |
| ts_frequency/input | [E1/frequency.gjf](E1/frequency.gjf) |
| ts_frequency/log | [E1/frequency.log](E1/frequency.log) |
| ts_frequency/final_xyz | [E1/frequency.xyz](E1/frequency.xyz) |
| irc/input | [E1/irc.gjf](E1/irc.gjf) |
| irc/log | [E1/irc.log](E1/irc.log) |
| actual_irc_product/optimization/input | [E1/irc_product_opt.gjf](E1/irc_product_opt.gjf) |
| actual_irc_product/optimization/log | [E1/irc_product_opt.log](E1/irc_product_opt.log) |
| actual_irc_product/optimization/source_record | [E1/irc_product_opt_source.json](E1/irc_product_opt_source.json) |
| actual_irc_product/optimization/source_xyz | [E1/irc_product_opt_source.xyz](E1/irc_product_opt_source.xyz) |
| actual_irc_product/frequency/input | [E1/irc_product_frequency.gjf](E1/irc_product_frequency.gjf) |
| actual_irc_product/frequency/log | [E1/irc_product_frequency.log](E1/irc_product_frequency.log) |
| actual_irc_product/frequency/final_xyz | [E1/irc_product_frequency.xyz](E1/irc_product_frequency.xyz) |

### NR1_E2

- Conformational transition; reference is its own starting INT-1a.

| 计算链阶段 | 文件 |
|---|---|
| ts_optimization/input | [E2/ts_opt.gjf](E2/ts_opt.gjf) |
| ts_optimization/log | [E2/ts_opt.log](E2/ts_opt.log) |
| ts_frequency/input | [E2/frequency.gjf](E2/frequency.gjf) |
| ts_frequency/log | [E2/frequency.log](E2/frequency.log) |
| ts_frequency/final_xyz | [E2/frequency.xyz](E2/frequency.xyz) |
| irc/input | [E2/irc.gjf](E2/irc.gjf) |
| irc/log | [E2/irc.log](E2/irc.log) |
| reactant/optimization/input | [E2/reactant_opt.gjf](E2/reactant_opt.gjf) |
| reactant/optimization/log | [E2/reactant_opt.log](E2/reactant_opt.log) |
| reactant/optimization/source_record | [E2/reactant_opt_source.json](E2/reactant_opt_source.json) |
| reactant/optimization/source_xyz | [E2/reactant_opt_source.xyz](E2/reactant_opt_source.xyz) |
| reactant/frequency/input | [E2/reactant_frequency.gjf](E2/reactant_frequency.gjf) |
| reactant/frequency/log | [E2/reactant_frequency.log](E2/reactant_frequency.log) |
| reactant/frequency/final_xyz | [E2/reactant_frequency.xyz](E2/reactant_frequency.xyz) |
| product/optimization/input | [E2/product_opt.gjf](E2/product_opt.gjf) |
| product/optimization/log | [E2/product_opt.log](E2/product_opt.log) |
| product/optimization/source_record | [E2/product_opt_source.json](E2/product_opt_source.json) |
| product/optimization/source_xyz | [E2/product_opt_source.xyz](E2/product_opt_source.xyz) |
| product/frequency/input | [E2/product_frequency.gjf](E2/product_frequency.gjf) |
| product/frequency/log | [E2/product_frequency.log](E2/product_frequency.log) |
| product/frequency/final_xyz | [E2/product_frequency.xyz](E2/product_frequency.xyz) |

### NR1_E3

- Conformational transition; reference is its own starting INT-1b, not INT-1a.

| 计算链阶段 | 文件 |
|---|---|
| ts_optimization/input | [E3/ts_opt.gjf](E3/ts_opt.gjf) |
| ts_optimization/log | [E3/ts_opt.log](E3/ts_opt.log) |
| ts_frequency/input | [E3/frequency.gjf](E3/frequency.gjf) |
| ts_frequency/log | [E3/frequency.log](E3/frequency.log) |
| ts_frequency/final_xyz | [E3/frequency.xyz](E3/frequency.xyz) |
| irc/input | [E3/irc.gjf](E3/irc.gjf) |
| irc/log | [E3/irc.log](E3/irc.log) |
| reactant/optimization/input | [E3/reactant_opt.gjf](E3/reactant_opt.gjf) |
| reactant/optimization/log | [E3/reactant_opt.log](E3/reactant_opt.log) |
| reactant/optimization/source_record | [E3/reactant_opt_source.json](E3/reactant_opt_source.json) |
| reactant/optimization/source_xyz | [E3/reactant_opt_source.xyz](E3/reactant_opt_source.xyz) |
| reactant/frequency/input | [E3/reactant_frequency.gjf](E3/reactant_frequency.gjf) |
| reactant/frequency/log | [E3/reactant_frequency.log](E3/reactant_frequency.log) |
| reactant/frequency/final_xyz | [E3/reactant_frequency.xyz](E3/reactant_frequency.xyz) |
| product/optimization/input | [E3/product_opt.gjf](E3/product_opt.gjf) |
| product/optimization/log | [E3/product_opt.log](E3/product_opt.log) |
| product/optimization/source_record | [E3/product_opt_source.json](E3/product_opt_source.json) |
| product/optimization/source_xyz | [E3/product_opt_source.xyz](E3/product_opt_source.xyz) |
| product/frequency/input | [E3/product_frequency.gjf](E3/product_frequency.gjf) |
| product/frequency/log | [E3/product_frequency.log](E3/product_frequency.log) |
| product/frequency/final_xyz | [E3/product_frequency.xyz](E3/product_frequency.xyz) |

### NR1_E4

- Accepted reference uses reported E(TS4)=-169.641371451 Ha relative stable INT-1a=-169.751090026 Ha.
- No native ts_0042 TS optimization, frequency, IRC, endpoint Opt/Freq, or source records in supplied branch/ZIP. Preserve missing status; ts_0035 stale rotor attempts are excluded.

| 计算链阶段 | 文件 |
|---|---|
| stable_reference/optimization/input | [references/INT1a/INT1a_opt.gjf](references/INT1a/INT1a_opt.gjf) |
| stable_reference/optimization/log | [references/INT1a/INT1a_opt.log](references/INT1a/INT1a_opt.log) |
| stable_reference/optimization/source_record | [references/INT1a/INT1a_opt_source.json](references/INT1a/INT1a_opt_source.json) |
| stable_reference/optimization/source_xyz | [references/INT1a/INT1a_opt_source.xyz](references/INT1a/INT1a_opt_source.xyz) |
| stable_reference/frequency/input | [references/INT1a/INT1a_frequency.gjf](references/INT1a/INT1a_frequency.gjf) |
| stable_reference/frequency/log | [references/INT1a/INT1a_frequency.log](references/INT1a/INT1a_frequency.log) |
| stable_reference/frequency/final_xyz | [references/INT1a/INT1a_frequency.xyz](references/INT1a/INT1a_frequency.xyz) |
| independent_product_reference/input | [references/HCN_water/opt_freq.gjf](references/HCN_water/opt_freq.gjf) |
| independent_product_reference/log | [references/HCN_water/opt_freq.log](references/HCN_water/opt_freq.log) |

- 历史验收保留项（非本轮复核）：已回填旧 Gaussian 自算 5.74，旧边 NR1_E3 现对应去质子步 E4；原证据记录替代质子接力拓扑及一点评 IRC，仅按 supervisor-supported 接受，须保留身份/拓扑 caveat。

## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [E1/frequency.log](E1/frequency.log) | [E1/frequency.gjf](E1/frequency.gjf) | 见原生 route / 所在阶段 |
| [E1/irc.log](E1/irc.log) | [E1/irc.gjf](E1/irc.gjf) | 见原生 route / 所在阶段 |
| [E1/irc_product_frequency.log](E1/irc_product_frequency.log) | [E1/irc_product_frequency.gjf](E1/irc_product_frequency.gjf) | 见原生 route / 所在阶段 |
| [E1/irc_product_opt.log](E1/irc_product_opt.log) | [E1/irc_product_opt.gjf](E1/irc_product_opt.gjf) | 见原生 route / 所在阶段 |
| [E1/ts_opt.log](E1/ts_opt.log) | [E1/ts_opt.gjf](E1/ts_opt.gjf) | 见原生 route / 所在阶段 |
| [E2/frequency.log](E2/frequency.log) | [E2/frequency.gjf](E2/frequency.gjf) | 见原生 route / 所在阶段 |
| [E2/irc.log](E2/irc.log) | [E2/irc.gjf](E2/irc.gjf) | 见原生 route / 所在阶段 |
| [E2/product_frequency.log](E2/product_frequency.log) | [E2/product_frequency.gjf](E2/product_frequency.gjf) | 见原生 route / 所在阶段 |
| [E2/product_opt.log](E2/product_opt.log) | [E2/product_opt.gjf](E2/product_opt.gjf) | 见原生 route / 所在阶段 |
| [E2/reactant_frequency.log](E2/reactant_frequency.log) | [E2/reactant_frequency.gjf](E2/reactant_frequency.gjf) | 见原生 route / 所在阶段 |
| [E2/reactant_opt.log](E2/reactant_opt.log) | [E2/reactant_opt.gjf](E2/reactant_opt.gjf) | 见原生 route / 所在阶段 |
| [E2/ts_opt.log](E2/ts_opt.log) | [E2/ts_opt.gjf](E2/ts_opt.gjf) | 见原生 route / 所在阶段 |
| [E3/frequency.log](E3/frequency.log) | [E3/frequency.gjf](E3/frequency.gjf) | 见原生 route / 所在阶段 |
| [E3/irc.log](E3/irc.log) | [E3/irc.gjf](E3/irc.gjf) | 见原生 route / 所在阶段 |
| [E3/product_frequency.log](E3/product_frequency.log) | [E3/product_frequency.gjf](E3/product_frequency.gjf) | 见原生 route / 所在阶段 |
| [E3/product_opt.log](E3/product_opt.log) | [E3/product_opt.gjf](E3/product_opt.gjf) | 见原生 route / 所在阶段 |
| [E3/reactant_frequency.log](E3/reactant_frequency.log) | [E3/reactant_frequency.gjf](E3/reactant_frequency.gjf) | 见原生 route / 所在阶段 |
| [E3/reactant_opt.log](E3/reactant_opt.log) | [E3/reactant_opt.gjf](E3/reactant_opt.gjf) | 见原生 route / 所在阶段 |
| [E3/ts_opt.log](E3/ts_opt.log) | [E3/ts_opt.gjf](E3/ts_opt.gjf) | 见原生 route / 所在阶段 |
| [references/HCN_water/opt_freq.log](references/HCN_water/opt_freq.log) | [references/HCN_water/opt_freq.gjf](references/HCN_water/opt_freq.gjf) | 见原生 route / 所在阶段 |
| [references/INT1a/INT1a_frequency.log](references/INT1a/INT1a_frequency.log) | [references/INT1a/INT1a_frequency.gjf](references/INT1a/INT1a_frequency.gjf) | 见原生 route / 所在阶段 |
| [references/INT1a/INT1a_opt.log](references/INT1a/INT1a_opt.log) | [references/INT1a/INT1a_opt.gjf](references/INT1a/INT1a_opt.gjf) | 见原生 route / 所在阶段 |
| [references/formamide/formamide_frequency.log](references/formamide/formamide_frequency.log) | [references/formamide/formamide_frequency.gjf](references/formamide/formamide_frequency.gjf) | 见原生 route / 所在阶段 |
| [references/formamide/formamide_opt.log](references/formamide/formamide_opt.log) | [references/formamide/formamide_opt.gjf](references/formamide/formamide_opt.gjf) | 见原生 route / 所在阶段 |

本题登记 72 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

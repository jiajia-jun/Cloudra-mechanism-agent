# NY3 · isocyanic acid hydrolysis: HNCO + one water -> ammonia + carbon dioxide

正式定义：[NY3.json](../../../ideapool/tasks/normal/NY3.json) · 档位：normal · 三步原件；端点来源限制。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../DELIVERY.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| NY3_E1 | 36.79 | numeric_reference |
| NY3_E2 | 11.06 | numeric_reference |
| NY3_E3 | 43.13 | numeric_reference |

## 证据与限定

| 步骤 | TS 日志 | 稳定参照日志 |
|---|---|---|
| NY3_E1 | [E1/frequency.log](E1/frequency.log) | [references/RC/RC_frequency.log](references/RC/RC_frequency.log) |
| NY3_E2 | [E2/frequency.log](E2/frequency.log) | [references/syn_carbamic_acid/opt_freq.log](references/syn_carbamic_acid/opt_freq.log) |
| NY3_E3 | [E3/frequency.log](E3/frequency.log) | [references/syn_carbamic_acid/opt_freq.log](references/syn_carbamic_acid/opt_freq.log) |

### NY3_E1

- Stable RC is the energy denominator; direct opposite endpoint is a higher water rotamer.
- Eigenvector plus/minus jobs1293/1294 are not actual IRC outer frames. Rotamer-to-RC profile ends at stable RC but has no independent conformational TS/Freq/IRC.

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

### NY3_E2

- Conformational syn-to-anti step; source is stable syn. Later duplicated independent seeds and byte-identical reused IRC logs are discarded.

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

### NY3_E3

- Actual graph anti-to-product; energy denominator remains stable syn by user decision.
- Product minimum is independent species_reference. Supplied originals do not establish true product IRC outer-frame optimization linkage.

| 计算链阶段 | 文件 |
|---|---|
| ts_optimization/input | [E3/ts_opt.gjf](E3/ts_opt.gjf) |
| ts_optimization/log | [E3/ts_opt.log](E3/ts_opt.log) |
| ts_frequency/input | [E3/frequency.gjf](E3/frequency.gjf) |
| ts_frequency/log | [E3/frequency.log](E3/frequency.log) |
| ts_frequency/final_xyz | [E3/frequency.xyz](E3/frequency.xyz) |
| irc/input | [E3/irc.gjf](E3/irc.gjf) |
| irc/log | [E3/irc.log](E3/irc.log) |
| actual_irc_reactant/optimization/input | [E3/irc_reactant_opt.gjf](E3/irc_reactant_opt.gjf) |
| actual_irc_reactant/optimization/log | [E3/irc_reactant_opt.log](E3/irc_reactant_opt.log) |
| actual_irc_reactant/optimization/source_record | [E3/irc_reactant_opt_source.json](E3/irc_reactant_opt_source.json) |
| actual_irc_reactant/optimization/source_xyz | [E3/irc_reactant_opt_source.xyz](E3/irc_reactant_opt_source.xyz) |
| actual_irc_reactant/frequency/input | [E3/irc_reactant_frequency.gjf](E3/irc_reactant_frequency.gjf) |
| actual_irc_reactant/frequency/log | [E3/irc_reactant_frequency.log](E3/irc_reactant_frequency.log) |
| actual_irc_reactant/frequency/final_xyz | [E3/irc_reactant_frequency.xyz](E3/irc_reactant_frequency.xyz) |
| independent_product/optimization/input | [E3/product_opt.gjf](E3/product_opt.gjf) |
| independent_product/optimization/log | [E3/product_opt.log](E3/product_opt.log) |
| independent_product/optimization/source_record | [E3/product_opt_source.json](E3/product_opt_source.json) |
| independent_product/optimization/source_xyz | [E3/product_opt_source.xyz](E3/product_opt_source.xyz) |
| independent_product/frequency/input | [E3/product_frequency.gjf](E3/product_frequency.gjf) |
| independent_product/frequency/log | [E3/product_frequency.log](E3/product_frequency.log) |
| independent_product/frequency/final_xyz | [E3/product_frequency.xyz](E3/product_frequency.xyz) |


## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [E1/conformer_profile/rotamer_to_RC_scan.log](E1/conformer_profile/rotamer_to_RC_scan.log) | [E1/conformer_profile/rotamer_to_RC_scan.gjf](E1/conformer_profile/rotamer_to_RC_scan.gjf) | 见原生 route / 所在阶段 |
| [E1/eigenvector_endpoints/minus.log](E1/eigenvector_endpoints/minus.log) | [E1/eigenvector_endpoints/minus.gjf](E1/eigenvector_endpoints/minus.gjf) | 见原生 route / 所在阶段 |
| [E1/eigenvector_endpoints/plus.log](E1/eigenvector_endpoints/plus.log) | [E1/eigenvector_endpoints/plus.gjf](E1/eigenvector_endpoints/plus.gjf) | 见原生 route / 所在阶段 |
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
| [E3/irc_reactant_frequency.log](E3/irc_reactant_frequency.log) | [E3/irc_reactant_frequency.gjf](E3/irc_reactant_frequency.gjf) | 见原生 route / 所在阶段 |
| [E3/irc_reactant_opt.log](E3/irc_reactant_opt.log) | [E3/irc_reactant_opt.gjf](E3/irc_reactant_opt.gjf) | 见原生 route / 所在阶段 |
| [E3/product_frequency.log](E3/product_frequency.log) | [E3/product_frequency.gjf](E3/product_frequency.gjf) | 见原生 route / 所在阶段 |
| [E3/product_opt.log](E3/product_opt.log) | [E3/product_opt.gjf](E3/product_opt.gjf) | 见原生 route / 所在阶段 |
| [E3/ts_opt.log](E3/ts_opt.log) | [E3/ts_opt.gjf](E3/ts_opt.gjf) | 见原生 route / 所在阶段 |
| [references/RC/RC_frequency.log](references/RC/RC_frequency.log) | [references/RC/RC_frequency.gjf](references/RC/RC_frequency.gjf) | 见原生 route / 所在阶段 |
| [references/RC/RC_opt.log](references/RC/RC_opt.log) | [references/RC/RC_opt.gjf](references/RC/RC_opt.gjf) | 见原生 route / 所在阶段 |
| [references/syn_carbamic_acid/opt_freq.log](references/syn_carbamic_acid/opt_freq.log) | [references/syn_carbamic_acid/opt_freq.gjf](references/syn_carbamic_acid/opt_freq.gjf) | 见原生 route / 所在阶段 |

本题登记 73 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

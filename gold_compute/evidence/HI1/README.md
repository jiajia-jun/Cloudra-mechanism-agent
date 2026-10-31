# HI1 · Cope elimination of threo/erythro N,N-dimethyl-3-phenyl-2-butylamine oxide: determine the stereochemical mapping

正式定义：[HI1.json](../../../ideapool/tasks/hard/HI1.json) · 档位：hard · 两条 syn 完整链。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../REPRODUCE.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| HI1_e1_erythro_syn | 16.62 | numeric_reference |
| HI1_e2_threo_syn | 15.85 | numeric_reference |

## 证据与限定

| 步骤 | TS 日志 | 稳定参照日志 |
|---|---|---|
| HI1_e1_erythro_syn | [erythro_syn/frequency/frequency.log](erythro_syn/frequency/frequency.log) | [erythro_syn/reactant_frequency/reactant_frequency.log](erythro_syn/reactant_frequency/reactant_frequency.log) |
| HI1_e2_threo_syn | [threo_syn/frequency/frequency.log](threo_syn/frequency/frequency.log) | [threo_syn/reactant_frequency/reactant_frequency.log](threo_syn/reactant_frequency/reactant_frequency.log) |

### HI1_e1_erythro_syn

- Barrier denominator is the stable minimum of this stereochemical substrate, not the other substrate.
- Short IRC is 10 points per direction; its actual outer frames are followed by converged Opt/Freq endpoint calculations.
- Original endpoint_source JSON and native input/log bytes are retained unchanged.
- TS优化：[erythro_syn/ts_opt/refine.log](erythro_syn/ts_opt/refine.log)
- 真实IRC：[erythro_syn/irc/irc.log](erythro_syn/irc/irc.log)
- 参照优化：[erythro_syn/reactant_opt/reactant_opt.log](erythro_syn/reactant_opt/reactant_opt.log)
- 产物优化：[erythro_syn/product_opt/product_opt.log](erythro_syn/product_opt/product_opt.log)
- 产物频率：[erythro_syn/product_frequency/product_frequency.log](erythro_syn/product_frequency/product_frequency.log)
- 反应物来源JSON：[erythro_syn/reactant_opt/endpoint_source.json](erythro_syn/reactant_opt/endpoint_source.json)
- 产物来源JSON：[erythro_syn/product_opt/endpoint_source.json](erythro_syn/product_opt/endpoint_source.json)
- 反应物输入来源坐标：[erythro_syn/reactant_opt/reactant_source.xyz](erythro_syn/reactant_opt/reactant_source.xyz)
- 产物输入来源坐标：[erythro_syn/product_opt/product_source.xyz](erythro_syn/product_opt/product_source.xyz)
- 预期振动模式数：93
- 产物立体身份：Z

### HI1_e2_threo_syn

- Barrier denominator is the stable minimum of this stereochemical substrate, not the other substrate.
- Short IRC is 10 points per direction; its actual outer frames are followed by converged Opt/Freq endpoint calculations.
- Original endpoint_source JSON and native input/log bytes are retained unchanged.
- TS优化：[threo_syn/ts_opt/refine.log](threo_syn/ts_opt/refine.log)
- 真实IRC：[threo_syn/irc/irc.log](threo_syn/irc/irc.log)
- 参照优化：[threo_syn/reactant_opt/reactant_opt.log](threo_syn/reactant_opt/reactant_opt.log)
- 产物优化：[threo_syn/product_opt/product_opt.log](threo_syn/product_opt/product_opt.log)
- 产物频率：[threo_syn/product_frequency/product_frequency.log](threo_syn/product_frequency/product_frequency.log)
- 反应物来源JSON：[threo_syn/reactant_opt/endpoint_source.json](threo_syn/reactant_opt/endpoint_source.json)
- 产物来源JSON：[threo_syn/product_opt/endpoint_source.json](threo_syn/product_opt/endpoint_source.json)
- 反应物输入来源坐标：[threo_syn/reactant_opt/reactant_source.xyz](threo_syn/reactant_opt/reactant_source.xyz)
- 产物输入来源坐标：[threo_syn/product_opt/product_source.xyz](threo_syn/product_opt/product_source.xyz)
- 预期振动模式数：93
- 产物立体身份：E


## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [erythro_syn/frequency/frequency.log](erythro_syn/frequency/frequency.log) | [erythro_syn/frequency/frequency.gjf](erythro_syn/frequency/frequency.gjf) | 见原生 route / 所在阶段 |
| [erythro_syn/irc/irc.log](erythro_syn/irc/irc.log) | [erythro_syn/irc/irc.gjf](erythro_syn/irc/irc.gjf) | 见原生 route / 所在阶段 |
| [erythro_syn/product_frequency/product_frequency.log](erythro_syn/product_frequency/product_frequency.log) | [erythro_syn/product_frequency/product_frequency.gjf](erythro_syn/product_frequency/product_frequency.gjf) | 见原生 route / 所在阶段 |
| [erythro_syn/product_opt/product_opt.log](erythro_syn/product_opt/product_opt.log) | [erythro_syn/product_opt/product_opt.gjf](erythro_syn/product_opt/product_opt.gjf) | 见原生 route / 所在阶段 |
| [erythro_syn/reactant_frequency/reactant_frequency.log](erythro_syn/reactant_frequency/reactant_frequency.log) | [erythro_syn/reactant_frequency/reactant_frequency.gjf](erythro_syn/reactant_frequency/reactant_frequency.gjf) | 见原生 route / 所在阶段 |
| [erythro_syn/reactant_opt/reactant_opt.log](erythro_syn/reactant_opt/reactant_opt.log) | [erythro_syn/reactant_opt/reactant_opt.gjf](erythro_syn/reactant_opt/reactant_opt.gjf) | 见原生 route / 所在阶段 |
| [erythro_syn/ts_opt/refine.log](erythro_syn/ts_opt/refine.log) | [erythro_syn/ts_opt/refine.gjf](erythro_syn/ts_opt/refine.gjf) | 见原生 route / 所在阶段 |
| [identity_references/E_alkene.log](identity_references/E_alkene.log) | [identity_references/E_alkene.gjf](identity_references/E_alkene.gjf) | 见原生 route / 所在阶段 |
| [identity_references/Z_alkene.log](identity_references/Z_alkene.log) | [identity_references/Z_alkene.gjf](identity_references/Z_alkene.gjf) | 见原生 route / 所在阶段 |
| [threo_syn/frequency/frequency.log](threo_syn/frequency/frequency.log) | [threo_syn/frequency/frequency.gjf](threo_syn/frequency/frequency.gjf) | 见原生 route / 所在阶段 |
| [threo_syn/irc/irc.log](threo_syn/irc/irc.log) | [threo_syn/irc/irc.gjf](threo_syn/irc/irc.gjf) | 见原生 route / 所在阶段 |
| [threo_syn/product_frequency/product_frequency.log](threo_syn/product_frequency/product_frequency.log) | [threo_syn/product_frequency/product_frequency.gjf](threo_syn/product_frequency/product_frequency.gjf) | 见原生 route / 所在阶段 |
| [threo_syn/product_opt/product_opt.log](threo_syn/product_opt/product_opt.log) | [threo_syn/product_opt/product_opt.gjf](threo_syn/product_opt/product_opt.gjf) | 见原生 route / 所在阶段 |
| [threo_syn/reactant_frequency/reactant_frequency.log](threo_syn/reactant_frequency/reactant_frequency.log) | [threo_syn/reactant_frequency/reactant_frequency.gjf](threo_syn/reactant_frequency/reactant_frequency.gjf) | 见原生 route / 所在阶段 |
| [threo_syn/reactant_opt/reactant_opt.log](threo_syn/reactant_opt/reactant_opt.log) | [threo_syn/reactant_opt/reactant_opt.gjf](threo_syn/reactant_opt/reactant_opt.gjf) | 见原生 route / 所在阶段 |
| [threo_syn/ts_opt/refine.log](threo_syn/ts_opt/refine.log) | [threo_syn/ts_opt/refine.gjf](threo_syn/ts_opt/refine.gjf) | 见原生 route / 所在阶段 |

本题登记 46 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

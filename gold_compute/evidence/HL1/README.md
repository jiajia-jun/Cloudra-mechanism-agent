# HL1 · formonitrile oxide + norbornene [3+2] cycloaddition: determine both facial pathways

正式定义：[HL1.json](../../../ideapool/tasks/hard/HL1.json) · 档位：hard · 两通道原件；endo 来源限制。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../DELIVERY.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| e_exo | 16.18 | numeric_reference |
| e_endo | 10.77 | numeric_reference |

## 证据与限定

| 步骤 | TS 日志 | 稳定参照日志 |
|---|---|---|
| e_exo | [exo/frequency/frequency.log](exo/frequency/frequency.log) | [exo/reactant_frequency/reactant_frequency.log](exo/reactant_frequency/reactant_frequency.log) |
| e_endo | [endo/frequency/frequency.log](endo/frequency/frequency.log) | [endo/reactant_frequency/reactant_frequency.log](endo/reactant_frequency/reactant_frequency.log) |

### e_exo

- Reference is this channel stable contact minimum. Keep separate from endo contact minimum; no favored-channel scoring is inferred from these two differently referenced barriers.
- TS优化：[exo/ts_opt/refine.log](exo/ts_opt/refine.log)
- 真实IRC：[exo/irc/irc.log](exo/irc/irc.log)
- 参照优化：[exo/reactant_opt/reactant_opt.log](exo/reactant_opt/reactant_opt.log)
- 产物优化：[exo/product_opt/product_opt.log](exo/product_opt/product_opt.log)
- 产物频率：[exo/product_frequency/product_frequency.log](exo/product_frequency/product_frequency.log)
- 反应物来源JSON：[exo/reactant_opt/endpoint_source.json](exo/reactant_opt/endpoint_source.json)
- 产物来源JSON：[exo/product_opt/endpoint_source.json](exo/product_opt/endpoint_source.json)
- 反应物输入来源坐标：[exo/reactant_opt/reactant_source.xyz](exo/reactant_opt/reactant_source.xyz)
- 产物输入来源坐标：[exo/product_opt/product_source.xyz](exo/product_opt/product_source.xyz)
- 预期振动模式数：57

### e_endo

- Stable contact energy reference is valid independent of whether it is the directly reached IRC conformer.
- Retained successful reactant endpoint_source is species_reference with null IRC id/hash; do not label it an IRC outer-frame relaxation.
- Earlier actual IRC-frame reactant optimization fails (Bend failed/FormBX/Error termination); retain this one log, input, source XYZ, and provenance JSON solely to substantiate the audit limitation.
- Product combined Opt+Freq job1324 uses the endo product-side outer frame; input vs archived frame Kabsch RMSD=0.000148565 A, max raw coordinate difference=0.000234 A, so do not claim byte-identical seed coordinates.
- No separation-reference monomer energies are substituted for the channel contact minimum.
- TS优化：[endo/ts_opt/refine.log](endo/ts_opt/refine.log)
- 真实IRC：[endo/irc/irc.log](endo/irc/irc.log)
- 参照优化：[endo/reactant_opt/reactant_opt.log](endo/reactant_opt/reactant_opt.log)
- 产物优化：[endo/product_optfreq/product_optfreq.log](endo/product_optfreq/product_optfreq.log)
- 产物频率：[endo/product_optfreq/product_optfreq.log](endo/product_optfreq/product_optfreq.log)
- 反应物来源JSON：[endo/reactant_opt/endpoint_source.json](endo/reactant_opt/endpoint_source.json)
- 反应物输入来源坐标：[endo/reactant_opt/reactant_source.xyz](endo/reactant_opt/reactant_source.xyz)
- 产物输入来源坐标：[endo/irc/product_outer.xyz](endo/irc/product_outer.xyz)
- 预期振动模式数：57

- 历史验收保留项（非本轮复核）：保留旧 23.13，一阶迁移鞍点存在，但 IRC 反向未回声明 I1 的 partial caveat；本轮没有重新验证 E2。

## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [endo/audit_limit/reactant_opt/reactant_opt.log](endo/audit_limit/reactant_opt/reactant_opt.log) | [endo/audit_limit/reactant_opt/reactant_opt.gjf](endo/audit_limit/reactant_opt/reactant_opt.gjf) | 限制证据：原生失败输出 |
| [endo/frequency/frequency.log](endo/frequency/frequency.log) | [endo/frequency/frequency.gjf](endo/frequency/frequency.gjf) | 见原生 route / 所在阶段 |
| [endo/irc/irc.log](endo/irc/irc.log) | [endo/irc/irc.gjf](endo/irc/irc.gjf) | 见原生 route / 所在阶段 |
| [endo/product_optfreq/product_optfreq.log](endo/product_optfreq/product_optfreq.log) | [endo/product_optfreq/product_optfreq.gjf](endo/product_optfreq/product_optfreq.gjf) | 见原生 route / 所在阶段 |
| [endo/reactant_frequency/reactant_frequency.log](endo/reactant_frequency/reactant_frequency.log) | [endo/reactant_frequency/reactant_frequency.gjf](endo/reactant_frequency/reactant_frequency.gjf) | 见原生 route / 所在阶段 |
| [endo/reactant_opt/reactant_opt.log](endo/reactant_opt/reactant_opt.log) | [endo/reactant_opt/reactant_opt.gjf](endo/reactant_opt/reactant_opt.gjf) | 见原生 route / 所在阶段 |
| [endo/ts_opt/refine.log](endo/ts_opt/refine.log) | [endo/ts_opt/refine.gjf](endo/ts_opt/refine.gjf) | 见原生 route / 所在阶段 |
| [exo/frequency/frequency.log](exo/frequency/frequency.log) | [exo/frequency/frequency.gjf](exo/frequency/frequency.gjf) | 见原生 route / 所在阶段 |
| [exo/irc/irc.log](exo/irc/irc.log) | [exo/irc/irc.gjf](exo/irc/irc.gjf) | 见原生 route / 所在阶段 |
| [exo/product_frequency/product_frequency.log](exo/product_frequency/product_frequency.log) | [exo/product_frequency/product_frequency.gjf](exo/product_frequency/product_frequency.gjf) | 见原生 route / 所在阶段 |
| [exo/product_opt/product_opt.log](exo/product_opt/product_opt.log) | [exo/product_opt/product_opt.gjf](exo/product_opt/product_opt.gjf) | 见原生 route / 所在阶段 |
| [exo/reactant_frequency/reactant_frequency.log](exo/reactant_frequency/reactant_frequency.log) | [exo/reactant_frequency/reactant_frequency.gjf](exo/reactant_frequency/reactant_frequency.gjf) | 见原生 route / 所在阶段 |
| [exo/reactant_opt/reactant_opt.log](exo/reactant_opt/reactant_opt.log) | [exo/reactant_opt/reactant_opt.gjf](exo/reactant_opt/reactant_opt.gjf) | 见原生 route / 所在阶段 |
| [exo/ts_opt/refine.log](exo/ts_opt/refine.log) | [exo/ts_opt/refine.gjf](exo/ts_opt/refine.gjf) | 见原生 route / 所在阶段 |

本题登记 42 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

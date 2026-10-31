# NU5 · Passerini reaction: formaldehyde + formic acid + methyl isocyanide -> N-methyl-alpha-formyloxyacetamide

正式定义：[NU5.json](../../../ideapool/tasks/normal/NU5.json) · 档位：normal · 仅 E2 原件，E1/E3 缺件。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../REPRODUCE.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| NU5_E1 | 8.21 | numeric_reference |
| NU5_E2 | 1.544 | numeric_reference |
| NU5_E3 | 31.7 | numeric_reference |

## 证据与限定

| 步骤 | TS 日志 | 稳定参照日志 |
|---|---|---|
| NU5_E2 | [E2/frequency/output.log](E2/frequency/output.log) | [E2/reactant_frequency/output.log](E2/reactant_frequency/output.log) |

### NU5_E2

- Same-composition 15-atom stable nitrilium/formate contact-ion-pair minimum; reactant opt used prior verified reference93 rather than the true IRC outer frame. Historical acceptance and this limitation are preserved.

- 仅选定现行 E2；E1/E3 尚无对应原件包。旧四步 NU5、6.54 等旧定义不沿用。

## 复跑所需的外部文件

只在工作副本重定位文件路径；原输入和原日志保留原样。缺失 Hessian 的条目先复跑对应 TS/Freq，禁止拿其他驻点 Hessian 顶替。

| 输入及行号 | 原始读取路径 | 当前文件 / 操作 |
|---|---|---|
| [E2/irc/irc.inp](E2/irc/irc.inp):8 | `/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/.cloudra/local-20261005/workspace/NU5_E2/ts/ts_0001/jobs/declaration_0001/frequency/frequency.hess` | [E2/frequency/frequency.hess](E2/frequency/frequency.hess) |

## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [E2/frequency/output.log](E2/frequency/output.log) | [E2/frequency/frequency.inp](E2/frequency/frequency.inp) | 频率 |
| [E2/irc/output.log](E2/irc/output.log) | [E2/irc/irc.inp](E2/irc/irc.inp) | IRC |
| [E2/product_frequency/output.log](E2/product_frequency/output.log) | [E2/product_frequency/product_frequency.inp](E2/product_frequency/product_frequency.inp) | 频率 |
| [E2/product_opt/output.log](E2/product_opt/output.log) | [E2/product_opt/product_opt.inp](E2/product_opt/product_opt.inp) | 极小值优化 |
| [E2/reactant_frequency/output.log](E2/reactant_frequency/output.log) | [E2/reactant_frequency/reactant_frequency.inp](E2/reactant_frequency/reactant_frequency.inp) | 频率 |
| [E2/reactant_opt/output.log](E2/reactant_opt/output.log) | [E2/reactant_opt/reactant_opt.inp](E2/reactant_opt/reactant_opt.inp) | 极小值优化 |
| [E2/ts_opt/output.log](E2/ts_opt/output.log) | [E2/ts_opt/refine.inp](E2/ts_opt/refine.inp) | TS优化 |

本题登记 30 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

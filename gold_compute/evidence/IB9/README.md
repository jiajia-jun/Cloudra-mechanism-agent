# IB9 · diazomethane and ethylene to cyclopropane via 1-pyrazoline

正式定义：[IB9.json](../../../ideapool/tasks/impossible/IB9.json) · 档位：impossible · 人工采信；接触体两软虚频。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../REPRODUCE.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| IB9_E1 | 5.65 | numeric_reference |
| IB9_E2 | — | negative_target |

## 证据与限定

| 步骤 | TS 日志 | 稳定参照日志 |
|---|---|---|
| IB9_E1 | [E1/frequency/output.log](E1/frequency/output.log) | [reference_contact/output.log](reference_contact/output.log) |

### IB9_E1

- 纯电子能；接触体保留2个软虚频，工具inconclusive。E2为负例无能垒。

- 历史验收保留项（非本轮复核）：已回填 14.74；9/26 复盘记录第一阶段产物 IRC 再优化仍有浅环翻转虚频。本次未见该端点后续零虚频修复证明，列为待复核旧限制；不据此自动撤回数值。

## 复跑所需的外部文件

只在工作副本重定位文件路径；原输入和原日志保留原样。缺失 Hessian 的条目先复跑对应 TS/Freq，禁止拿其他驻点 Hessian 顶替。

| 输入及行号 | 原始读取路径 | 当前文件 / 操作 |
|---|---|---|
| [E1/irc/input.inp](E1/irc/input.inp):8 | `/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/ts/ts_0005/jobs/declaration_0006/frequency/frequency.hess` | [E1/frequency/frequency.hess](E1/frequency/frequency.hess) |

## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [E1/contact_refinement/output.log](E1/contact_refinement/output.log) | [E1/contact_refinement/input.inp](E1/contact_refinement/input.inp) | 频率 + 极小值优化 |
| [E1/contact_relaxation/output.log](E1/contact_relaxation/output.log) | [E1/contact_relaxation/input.inp](E1/contact_relaxation/input.inp) | 频率 + 极小值优化 |
| [E1/frequency/output.log](E1/frequency/output.log) | [E1/frequency/input.inp](E1/frequency/input.inp) | 频率 |
| [E1/irc/output.log](E1/irc/output.log) | [E1/irc/input.inp](E1/irc/input.inp) | IRC |
| [E1/product/output.log](E1/product/output.log) | [E1/product/input.inp](E1/product/input.inp) | 频率 + 极小值优化 |
| [E1/ts_opt/output.log](E1/ts_opt/output.log) | [E1/ts_opt/input.inp](E1/ts_opt/input.inp) | TS优化 |
| [comparison_fragments/c2h4/output.log](comparison_fragments/c2h4/output.log) | [comparison_fragments/c2h4/input.inp](comparison_fragments/c2h4/input.inp) | 频率 + 极小值优化 |
| [comparison_fragments/ch2n2/output.log](comparison_fragments/ch2n2/output.log) | [comparison_fragments/ch2n2/input.inp](comparison_fragments/ch2n2/input.inp) | 频率 + 极小值优化 |
| [reference_contact/output.log](reference_contact/output.log) | [reference_contact/input.inp](reference_contact/input.inp) | 频率 + 极小值优化 |

本题登记 38 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

历史原始采信记录中的 `new_verification_review/ACTUAL_VERIFICATION.json` 对应本包 `verification_record.json`；原记录保持原文，来源映射见MANIFEST。

# M17 · methyl isocyanide -> acetonitrile rearrangement

正式定义：[M17.json](../../../ideapool/tasks/easy/M17.json) · 档位：easy · 旧题最终原件；未重新科学验收。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../DELIVERY.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| M17_E1 | 44.5 | numeric_reference |

## 证据与限定

按历史最终回填表选取输入、原生日志和必要附件；本轮整理不重新裁决科学验收，也不把正常终止当作完整 IRC 证明。


## 复跑所需的外部文件

只在工作副本重定位文件路径；原输入和原日志保留原样。缺失 Hessian 的条目先复跑对应 TS/Freq，禁止拿其他驻点 Hessian 顶替。

| 输入及行号 | 原始读取路径 | 当前文件 / 操作 |
|---|---|---|
| [legacy/irc/irc.inp](legacy/irc/irc.inp):7 | `/public/home/yyywaa/cloudra_workspace/candidate_methyl_isocyanide_20260924/ts_lit_seed/ts_lit_seed.hess` | [legacy/ts_lit_seed/ts_lit_seed.hess](legacy/ts_lit_seed/ts_lit_seed.hess) |

## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [legacy/irc/output.log](legacy/irc/output.log) | [legacy/irc/irc.inp](legacy/irc/irc.inp) | IRC |
| [legacy/irc_backward_opt/output.log](legacy/irc_backward_opt/output.log) | [legacy/irc_backward_opt/irc_backward_opt.inp](legacy/irc_backward_opt/irc_backward_opt.inp) | 频率 + 极小值优化 |
| [legacy/irc_forward_opt/output.log](legacy/irc_forward_opt/output.log) | [legacy/irc_forward_opt/irc_forward_opt.inp](legacy/irc_forward_opt/irc_forward_opt.inp) | 频率 + 极小值优化 |
| [legacy/p_opt/output.log](legacy/p_opt/output.log) | [legacy/p_opt/p_opt.inp](legacy/p_opt/p_opt.inp) | 频率 + 极小值优化 |
| [legacy/r_opt/output.log](legacy/r_opt/output.log) | [legacy/r_opt/r_opt.inp](legacy/r_opt/r_opt.inp) | 频率 + 极小值优化 |
| [legacy/ts_lit_seed/output.log](legacy/ts_lit_seed/output.log) | [legacy/ts_lit_seed/ts_lit_seed.inp](legacy/ts_lit_seed/ts_lit_seed.inp) | 频率 + TS优化 |

本题登记 25 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

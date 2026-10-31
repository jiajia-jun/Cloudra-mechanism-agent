# M14 · acrolein s-trans <-> s-cis rotation

正式定义：[M14.json](../../../ideapool/tasks/easy/M14.json) · 档位：easy · 部分原件；声明的 TS22 缺件。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../REPRODUCE.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| M14_E1 | 9.05 | numeric_reference |

## 证据与限定

按历史最终回填表选取输入、原生日志和必要附件；本轮整理不重新裁决科学验收，也不把正常终止当作完整 IRC 证明。

- 历史声明的 TS 作业22原生日志未找到，保留的 RC 与 IRC 不能代替该 TS 日志。

## 复跑所需的外部文件

只在工作副本重定位文件路径；原输入和原日志保留原样。缺失 Hessian 的条目先复跑对应 TS/Freq，禁止拿其他驻点 Hessian 顶替。

| 输入及行号 | 原始读取路径 | 当前文件 / 操作 |
|---|---|---|
| [legacy/irc.inp](legacy/irc.inp):7 | `/public/home/yyywaa/cloudra_workspace/M14/ts.hess` | [legacy/irc.hess](legacy/irc.hess) |

## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [legacy/logs/calc-39.out.log](legacy/logs/calc-39.out.log) | [legacy/irc.inp](legacy/irc.inp) | IRC |
| [legacy/logs/calc-61.out.log](legacy/logs/calc-61.out.log) | [legacy/ep_cis.inp](legacy/ep_cis.inp) | 频率 + 极小值优化 |
| [legacy/logs/calc-62.out.log](legacy/logs/calc-62.out.log) | [legacy/ep_trans.inp](legacy/ep_trans.inp) | 频率 + 极小值优化 |
| [legacy/logs/m14-orca-122762307.out](legacy/logs/m14-orca-122762307.out) | [legacy/min_trans.inp](legacy/min_trans.inp) | 频率 + 极小值优化 |

本题登记 17 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

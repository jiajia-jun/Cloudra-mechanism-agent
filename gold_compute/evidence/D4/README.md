# D4 · cyclopentadiene + acrolein Diels-Alder

正式定义：[D4.json](../../../ideapool/tasks/easy/D4.json) · 档位：easy · 旧题最终原件；未重新科学验收。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../DELIVERY.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| D4_E1 | 11.3 | numeric_reference |

## 证据与限定

按历史最终回填表选取输入、原生日志和必要附件；本轮整理不重新裁决科学验收，也不把正常终止当作完整 IRC 证明。


## 复跑所需的外部文件

只在工作副本重定位文件路径；原输入和原日志保留原样。缺失 Hessian 的条目先复跑对应 TS/Freq，禁止拿其他驻点 Hessian 顶替。

| 输入及行号 | 原始读取路径 | 当前文件 / 操作 |
|---|---|---|
| [legacy/ircA.inp](legacy/ircA.inp):7 | `tsA.hess` | [legacy/tsA.hess](legacy/tsA.hess) |
| [legacy/ircB.inp](legacy/ircB.inp):7 | `tsB.hess` | [legacy/tsB.hess](legacy/tsB.hess) |

## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [legacy/logs/calc-173.out.log](legacy/logs/calc-173.out.log) | [legacy/pA_opt2.inp](legacy/pA_opt2.inp) | 频率 + 极小值优化 |
| [legacy/logs/calc-174.out.log](legacy/logs/calc-174.out.log) | [legacy/pB_opt2.inp](legacy/pB_opt2.inp) | 频率 + 极小值优化 |
| [legacy/logs/calc-233.out.log](legacy/logs/calc-233.out.log) | [legacy/tsA.inp](legacy/tsA.inp) | 频率 + TS优化 |
| [legacy/logs/calc-236.out.log](legacy/logs/calc-236.out.log) | [legacy/ircA.inp](legacy/ircA.inp) | IRC |
| [legacy/logs/calc-241.out.log](legacy/logs/calc-241.out.log) | [legacy/tsB.inp](legacy/tsB.inp) | 频率 + TS优化 |
| [legacy/logs/calc-242.out.log](legacy/logs/calc-242.out.log) | [legacy/rcA.inp](legacy/rcA.inp) | 频率 + 极小值优化 |
| [legacy/logs/calc-246.out.log](legacy/logs/calc-246.out.log) | [legacy/ircB.inp](legacy/ircB.inp) | IRC |
| [legacy/logs/calc-251.out.log](legacy/logs/calc-251.out.log) | [legacy/ircA_F_opt.inp](legacy/ircA_F_opt.inp) | 频率 + 极小值优化 |
| [legacy/logs/calc-252.out.log](legacy/logs/calc-252.out.log) | [legacy/ircA_B_opt.inp](legacy/ircA_B_opt.inp) | 频率 + 极小值优化 |
| [legacy/logs/calc-257.out.log](legacy/logs/calc-257.out.log) | [legacy/ircB_F_opt.inp](legacy/ircB_F_opt.inp) | 频率 + 极小值优化 |
| [legacy/logs/calc-258.out.log](legacy/logs/calc-258.out.log) | [legacy/ircB_B_opt.inp](legacy/ircB_B_opt.inp) | 频率 + 极小值优化 |

本题登记 44 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

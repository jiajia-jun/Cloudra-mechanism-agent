# G3 · propylene + ethylene ene reaction (Alder-ene)

正式定义：[G3.json](../../../ideapool/tasks/easy/G3.json) · 档位：easy · 旧题最终原件；未重新科学验收。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../REPRODUCE.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| G3_E1 | 30.15 | numeric_reference |

## 证据与限定

按历史最终回填表选取输入、原生日志和必要附件；本轮整理不重新裁决科学验收，也不把正常终止当作完整 IRC 证明。

- 历史验收保留项（非本轮复核）：已回填 30.15；源记录 TS 非协同、具双自由基特征，而 step_type 仍写 concerted。这是机制/适用性审查问题，不自行撤回或补算。

## 复跑所需的外部文件

只在工作副本重定位文件路径；原输入和原日志保留原样。缺失 Hessian 的条目先复跑对应 TS/Freq，禁止拿其他驻点 Hessian 顶替。

| 输入及行号 | 原始读取路径 | 当前文件 / 操作 |
|---|---|---|
| [legacy/irc_w35b.inp](legacy/irc_w35b.inp):7 | `ts_w35b.hess` | [legacy/ts_w35b.hess](legacy/ts_w35b.hess) |

## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [legacy/logs/calc-178.out.log](legacy/logs/calc-178.out.log) | [legacy/rc_opt2.inp](legacy/rc_opt2.inp) | 频率 + 极小值优化 |
| [legacy/logs/calc-293.out.log](legacy/logs/calc-293.out.log) | [legacy/ts_w35b.inp](legacy/ts_w35b.inp) | 频率 + TS优化 |
| [legacy/logs/calc-295.out.log](legacy/logs/calc-295.out.log) | [legacy/irc_w35b.inp](legacy/irc_w35b.inp) | IRC |
| [legacy/logs/calc-298.out.log](legacy/logs/calc-298.out.log) | [legacy/epF.inp](legacy/epF.inp) | 频率 + 极小值优化 |
| [legacy/logs/calc-299.out.log](legacy/logs/calc-299.out.log) | [legacy/epB.inp](legacy/epB.inp) | 频率 + 极小值优化 |

本题登记 20 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

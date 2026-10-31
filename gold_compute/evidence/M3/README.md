# M3 · NH3 umbrella inversion

正式定义：[M3.json](../../../ideapool/tasks/easy/M3.json) · 档位：easy · 旧题最终原件；未重新科学验收。

[总索引](../README.md) · [复现说明](../REPRODUCE.md) · [逐文件哈希与旧路径映射](../MANIFEST.json)

原始文件在[Drive交付包](../REPRODUCE.md)，不随Git下载；本页原件链接在按复现说明还原到本地后可用。

## 当前参考

| 步骤 | 当前值 / kcal mol⁻¹ | 类型 |
|---|---:|---|
| M3_E1 | 5.94 | numeric_reference |

## 证据与限定

按历史最终回填表选取输入、原生日志和必要附件；本轮整理不重新裁决科学验收，也不把正常终止当作完整 IRC 证明。


## 原生计算索引

下面按原始输入/输出逐项列出；完整几何、Hessian、来源 JSON 及同字节别名见 MANIFEST。`recovered.inp` 是从相应原生日志 INPUT FILE 回显逐行恢复的输入，不是重新构造的坐标。

| 原生日志 | 输入 | 原生输入中的任务 |
|---|---|---|
| [legacy/logs/calc-49.out.log](legacy/logs/calc-49.out.log) | [legacy/rc_opt.inp](legacy/rc_opt.inp) | 频率 + 极小值优化 |
| [legacy/logs/calc-66.out.log](legacy/logs/calc-66.out.log) | [legacy/ts_opt.inp](legacy/ts_opt.inp) | 频率 + TS优化 |
| [legacy/logs/calc-67.out.log](legacy/logs/calc-67.out.log) | [legacy/ts_irc.inp](legacy/ts_irc.inp) | IRC |
| [legacy/logs/calc-68.out.log](legacy/logs/calc-68.out.log) | [legacy/irc_F_opt.inp](legacy/irc_F_opt.inp) | 频率 + 极小值优化 |
| [legacy/logs/calc-69.out.log](legacy/logs/calc-69.out.log) | [legacy/irc_B_opt.inp](legacy/irc_B_opt.inp) | 频率 + 极小值优化 |

本题登记 21 个证据文件；原始路径与 SHA256 可按 MANIFEST 中 `path` / `sources` 检索。

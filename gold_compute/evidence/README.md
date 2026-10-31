# 正式题库证据索引（2026-10-18）

原始证据保存在 [Google Drive交付包](REPRODUCE.md)，Git只保存索引、哈希清单、校验脚本和复现说明。下载并按[复现步骤](REPRODUCE.md)还原后，文件会落在本目录对应路径；逐题页面中的原件链接届时可用。

面向当前50题，按题整理 **886 个证据文件（137.5 MB）**，其中28份输入从原生ORCA日志回显恢复。31题有选定原件，另19题明确登记“负例无需数值”或“当前版本原件未齐”。本轮不改Gold数值、方法限制或验收标准。

先打开具体题目的 README，沿“TS → IRC → 末帧来源 → 端点优化/频率”审查；能垒另减对应稳定参照。旧题的文件选择依据历史最终回填记录，本轮没有重新作全部化学验收。

- [Google Drive完整交付包与版本记录](REPRODUCE.md)
- [如何回读、复跑和审查](REPRODUCE.md)
- [逐文件大小、SHA256、旧路径和计算链索引](MANIFEST.json)
- [本轮核验结果](AUDIT.md)
- [当前50题状态与评分口径](../queue_20261018/REFERENCE_STATUS.md)

## 保留与清除

保留最终参考采用的输入、原生日志、终态几何、Hessian、真实IRC末帧及来源记录。同字节文件只保留一份，旧路径别名写入MANIFEST。绝不以终态坐标顶替原始输入，也不改写原生日志。

清除旧证据包中的过期题库快照、废弃TS/rotor尝试、临时脚本、状态缓存、重复run和中间副本；Drive交付包和Git当前版本均不保留那套试错包。**HL1 endo有一条失败输出保留在audit_limit/**：它直接证明当前成功反应物端来自独立种子，不能删除后把链条写成闭环。NY3构象扫描是必要辅助证据，不冒称正式TS。

原导入包有1443个文件；其中247个原路径作为选定证据或同字节别名纳入本清单。其余不进入当前包。另补入本机旧题最终原件及IB9正式链。完整旧包留在提交`8fcd99d52214a5776af3323d356b5c454ea013f4`，来源分支提交`9c96b4d368602d72a7290298ef5a2ca0e9c6e91d`；审计需要时按MANIFEST.sources找回。

## 尚未齐备的原件与验收限定

- NR1末步成功ts_0042原件未到货；M14历史声明的TS22日志缺失。
- NU5仅E2有本次选定原件；E1/E3未补齐。
- HA6、NB1、NI1、NI5、NQ1、NQ5、HB1、HD2、HF1、HH1没有对应当前数值版本的选定原件包。不能称50题全部可凭当前归档独立复现。
- HA1、NU6各两条IRC缺原始TS Hessian；TS/Freq输入已恢复，可按原输入重跑生成Hessian，再复跑IRC。
- HI1两条正式syn链已闭环。NR1 E1、NY3 E1/E3和HL1 endo的实际端点来源限制见各题说明；IB9接触体两软虚频由用户人工采信，原工具inconclusive仍保留。
- NB1_E2/NQ5_E2按既定PT规则有意无数值参考；IMP负例也不要求虚构数值。

## 全部50题

| 题目 | 档位 | 选定文件数 | 归档状态 |
|---|---|---:|---|
| [D1](D1/README.md) | easy | 16 | 旧题最终原件；未重新科学验收 |
| [D3](D3/README.md) | easy | 16 | 旧题最终原件；未重新科学验收 |
| [D4](D4/README.md) | easy | 44 | 旧题最终原件；未重新科学验收 |
| [E1](E1/README.md) | easy | 16 | 旧题最终原件；未重新科学验收 |
| [F1](F1/README.md) | easy | 26 | 旧题最终原件；未重新科学验收 |
| [F4](F4/README.md) | easy | 27 | 旧题最终原件；未重新科学验收 |
| [G2](G2/README.md) | easy | 16 | 旧题最终原件；未重新科学验收 |
| [G3](G3/README.md) | easy | 20 | 旧题最终原件；未重新科学验收 |
| [L1](L1/README.md) | easy | 20 | 旧题最终原件；未重新科学验收 |
| [L2](L2/README.md) | easy | 28 | 旧题最终原件；未重新科学验收 |
| [M1](M1/README.md) | easy | 19 | 旧题最终原件；未重新科学验收 |
| [M14](M14/README.md) | easy | 17 | 部分原件；声明的 TS22 缺件 |
| [M15](M15/README.md) | easy | 24 | 旧题最终原件；未重新科学验收 |
| [M16](M16/README.md) | easy | 27 | 旧题最终原件；未重新科学验收 |
| [M17](M17/README.md) | easy | 25 | 旧题最终原件；未重新科学验收 |
| [M3](M3/README.md) | easy | 21 | 旧题最终原件；未重新科学验收 |
| [M8](M8/README.md) | easy | 24 | 旧题最终原件；未重新科学验收 |
| [P2](P2/README.md) | easy | 20 | 旧题最终原件；未重新科学验收 |
| [P3](P3/README.md) | easy | 21 | 旧题最终原件；未重新科学验收 |
| [X1](X1/README.md) | easy | 28 | 旧题最终原件；未重新科学验收 |
| [NB1](NB1/README.md) | normal | 0 | 未归档当前数值原件 |
| [NI1](NI1/README.md) | normal | 0 | 未归档当前数值原件 |
| [NI5](NI5/README.md) | normal | 0 | 未归档当前数值原件 |
| [NQ1](NQ1/README.md) | normal | 0 | 未归档当前数值原件 |
| [NQ5](NQ5/README.md) | normal | 0 | 未归档当前数值原件 |
| [NR1](NR1/README.md) | normal | 72 | E1–E3 原件；E4 成功 run 缺件 |
| [NU3](NU3/README.md) | normal | 22 | 旧题最终原件；未重新科学验收 |
| [NU5](NU5/README.md) | normal | 30 | 仅 E2 原件，E1/E3 缺件 |
| [NU6](NU6/README.md) | normal | 18 | 旧题最终原件；未重新科学验收 |
| [NY3](NY3/README.md) | normal | 73 | 三步原件；端点来源限制 |
| [HA1](HA1/README.md) | hard | 16 | 旧题最终原件；未重新科学验收 |
| [HA6](HA6/README.md) | hard | 0 | 未归档当前数值原件 |
| [HA8](HA8/README.md) | hard | 28 | 旧题最终原件；未重新科学验收 |
| [HB1](HB1/README.md) | hard | 0 | 未归档当前数值原件 |
| [HB10](HB10/README.md) | hard | 46 | 旧题最终原件；未重新科学验收 |
| [HD2](HD2/README.md) | hard | 0 | 未归档当前数值原件 |
| [HF1](HF1/README.md) | hard | 0 | 未归档当前数值原件 |
| [HH1](HH1/README.md) | hard | 0 | 未归档当前数值原件 |
| [HI1](HI1/README.md) | hard | 46 | 两条 syn 完整链 |
| [HL1](HL1/README.md) | hard | 42 | 两通道原件；endo 来源限制 |
| [IA1](IA1/README.md) | impossible | 0 | 负例标签，无数值原件要求 |
| [IA5](IA5/README.md) | impossible | 0 | 负例标签，无数值原件要求 |
| [IA7](IA7/README.md) | impossible | 0 | 负例标签，无数值原件要求 |
| [IA9](IA9/README.md) | impossible | 0 | 负例标签，无数值原件要求 |
| [IB9](IB9/README.md) | impossible | 38 | 人工采信；接触体两软虚频 |
| [IC3](IC3/README.md) | impossible | 0 | 负例标签，无数值原件要求 |
| [ID2](ID2/README.md) | impossible | 0 | 负例标签，无数值原件要求 |
| [IE2](IE2/README.md) | impossible | 0 | 负例标签，无数值原件要求 |
| [IF3](IF3/README.md) | impossible | 0 | 负例标签，无数值原件要求 |
| [IG8](IG8/README.md) | impossible | 0 | 负例标签，无数值原件要求 |

# Hard 数据归档入口 · 2026-10-01

本目录是分类、可读导出与检索层。原始迁移快照、最终快照、逐作业增量及此前服务器归档各自保留，所有链接采用相对路径。原始数据库与文件是恢复依据；本目录的 JSONL/CSV/SQLite 索引是派生资料。

## 按目的查找

| 目录 | 内容 | 从哪里开始 |
|---|---|---|
| 01_results | 已发布 10 道题、归档 HE3/HG2、科学验收说明、映射坐标及题源/registry 快照 | [结果说明](01_results/README.md) |
| 02_calculations | 按题目→作业编号→输入/原始日志/运行目录组织，含失败与拒收证据 | [计算索引](02_calculations/README.md)、[jobs.csv](02_calculations/jobs.csv) |
| 03_context_and_events | 重启前片段、恢复来源、重启后的完整已保存事件和 9 份当前 context | [context 说明](03_context_and_events/README.md) |
| 04_databases | 当前与历史 SQLite 原库链接、schema、表/行数、当前逻辑表 JSONL | [数据库说明](04_databases/README.md) |
| 05_snapshots | 最终、迁移、增量、此前服务器快照入口，互不混淆 | [快照说明](05_snapshots/README.md) |
| 06_environment_and_private_config | 原服务器源码、软件/依赖清单、启动服务、私有配置 | [环境说明](06_environment_and_private_config/README.md) |
| 07_restore | 恢复顺序、大小写文件映射、只读检索示例 | [恢复手册](07_restore/README.md) |
| 08_integrity | 原始文件逐项 SHA 索引、最终核验与停费凭证、整理核验 | [核验说明](08_integrity/README.md) |

## 哪份记录优先

1. 题库已发布状态采用 `3ec62c55c8e3433854246ea50f889668b2659cc4` 的文件快照。
2. 本轮计算终态采用 `final_archive_20261001_1522` 的原始文件与 compute.db。
3. 重启后的 agent/context/events 采用最终 `runtime/recovery_20261001/runtime-v2.db`。
4. 迁移与此前服务器记录仅说明其自身时间段，不覆盖最终状态。

科学限制：HA8/HB10 两道替换已验收；HI1 本轮只验收加成 E2/EM1，E1/E3 保持缺测；HL1 与其它题按既有证据说明。正常结束、DONE、agent succeeded 都不能独立证明化学成功。IRC 原生步数上限、近简并、旧身份错误和工作目录面标签交换均保留。

目录与导出保留私有访问权限。context 可能含工具输出和配置，不应整目录提交 Git 或对外分享。服务器已关机，本次整理全在本地完成。

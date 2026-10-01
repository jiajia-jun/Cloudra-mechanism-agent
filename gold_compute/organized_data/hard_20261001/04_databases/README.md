# SQLite 数据库目录

所有原库通过相对链接保留；读取采用 immutable 只读模式。每库附 schema.sql、tables.json、metadata.json；current 库额外导出逻辑表 JSONL。FTS 内部索引与 sqlite_sequence 仍在完整原库保留，不重复解释为业务记录。

| ID | 时间段 | 原文件 | 用途 |
|---|---|---|---|
| db01 | final | `paratera_final_20261001_0830/final_archive_20261001_1522/runtime/compute.db` | 作业状态、资源请求、实际输入路径、调度错误 |
| db02 | final | `paratera_final_20261001_0830/final_archive_20261001_1522/runtime/conversations/prj_a15fc9525cbf4572/tasks/database.db` | legacy sessions/session_events、DAG、证据绑定、artifacts；不是当前 v2 状态权威 |
| db03 | final | `paratera_final_20261001_0830/final_archive_20261001_1522/runtime/knowledge/chem_kg.db` | 化学知识库实体、关系、标签及 FTS 索引 |
| db04 | final | `paratera_final_20261001_0830/final_archive_20261001_1522/runtime/recovery_20261001/backup/runtime-v2.db` | v2 事件流、完整运行快照和保存的 context；backup 子目录为较早历史 |
| db05 | final | `paratera_final_20261001_0830/final_archive_20261001_1522/runtime/recovery_20261001/runtime-v2.db` | v2 事件流、完整运行快照和保存的 context；backup 子目录为较早历史 |
| db06 | migration | `paratera_final_20261001_0830/migration_snapshot/runtime/compute.db` | 作业状态、资源请求、实际输入路径、调度错误 |
| db07 | migration | `paratera_final_20261001_0830/migration_snapshot/runtime/conversations/prj_a15fc9525cbf4572/tasks/database.db` | legacy sessions/session_events、DAG、证据绑定、artifacts；不是当前 v2 状态权威 |
| db08 | migration | `paratera_final_20261001_0830/migration_snapshot/runtime/knowledge/chem_kg.db` | 化学知识库实体、关系、标签及 FTS 索引 |
| db09 | migration | `paratera_final_20261001_0830/migration_snapshot/runtime/recovery_20261001/backup/runtime-v2.db` | v2 事件流、完整运行快照和保存的 context；backup 子目录为较早历史 |

不要合并覆盖同名库；按 source_path、epoch、SHA 区分。最终固定快照中的 backup/runtime-v2.db 仍是较早记录，不因位于 final 目录就成为最新事件库。

所有 9 个库 integrity_check 均为 ok。逻辑导出不是经过脱敏的共享数据；原表内敏感设置、路径、凭据哈希均仍按私有权限保存。

只读查询示例见 ../07_restore/README.md。

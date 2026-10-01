# 快照时间段与用途

- `final`：生产终态固定快照 → `gold_compute/remote_backups/paratera_final_20261001_0830/final_archive_20261001_1522`。
- `migration`：关机迁移期固定元数据快照 → `gold_compute/remote_backups/paratera_final_20261001_0830/migration_snapshot`。
- `migration_workspace`：迁移工作区及此前预拷贝混合；固定清单覆盖范围见原说明 → `gold_compute/remote_backups/paratera_final_20261001_0830/workspace`。
- `increments`：重启后逐作业终态增量 → `gold_compute/remote_backups/paratera_final_20261001_0830/post_recovery_20261001`。
- `2026-09-23`：此前服务器历史归档；不作本轮终态 → `gold_compute/remote_backups/2026-09-23`。
- `2026-09-23-split`：此前服务器历史归档；不作本轮终态 → `gold_compute/remote_backups/2026-09-23-split`。
- `2026-09-25`：此前服务器历史归档；不作本轮终态 → `gold_compute/remote_backups/2026-09-25`。

迁移 workspace 含 253 项早期预拷贝额外文件：其固定覆盖清单和核验结论看原 MIGRATION_README/BACKUP_VERIFICATION，不把多余文件当作同一固定时间点。各 epoch 不替换彼此；去重信息只用于查找，未删除重复证据。

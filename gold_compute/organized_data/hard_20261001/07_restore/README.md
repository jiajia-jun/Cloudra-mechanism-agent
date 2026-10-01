# 恢复与检索顺序

1. 将 organized_data 与 remote_backups 一并保留在 gold_compute 下，相对链接即可随整个 gold_compute 迁移；单独拷贝索引目录不能替代原始资料。
2. 选择 `final_archive_20261001_1522` 恢复本轮生产终态：workspace → /data/cloudra/workspace，runtime → /data/cloudra/runtime；原迁移与增量另留历史。
3. Mac 大小写冲突：读取最终快照 CASE_SENSITIVE_PATH_MAP.json。在 Linux 先按原路径放小写 em1_ts_final.xyz，再将 em1_TS_final.xyz.__case_preserved 复制为大写原名。两份内容不同，都必须保留。
4. 数据库使用独立 SQLite backup 快照。检查 SHA 和 integrity_check 后部署；同名历史库不能覆盖最新库。-wal/-shm 是运行/只读打开时的辅助文件，未列入固定 manifest 的附件不能取代一致快照。
5. 用 rebuild/ 清单恢复程序与依赖、服务环境和私有配置，落实 8422 的持久 runtime store。先只读验证路径、数据库与 agent/context，再明确决定是否恢复执行；整理数据本身不授权开机或重交 QM。
6. 科学结果取 01_results/published 的已发布 commit；远端源码和旧报告里的过渡结论不覆盖独立验收。查证路径优先最终日志，再历史快照。

## 本地目录查询

在本目录用 Python/sqlite3 的只读连接打开 catalog.sqlite3：

```sql
SELECT id,state,case_id,input_local,log_local,interpretation FROM jobs WHERE case_id='HI1' ORDER BY id;
SELECT source_path,sha256,snapshot_id FROM files WHERE source_path LIKE '%calc-83.out.log';
SELECT id,epoch,source_path FROM databases;
SELECT session_id,current_messages,event_count FROM agents;
SELECT database_id,table_name,row_count FROM database_tables WHERE table_name IN ('events','session_events','compute_jobs');
```

catalog.sqlite3 是派生索引，不能替代原 runtime-v2、compute、DAG、知识数据库。schema.sql 说明原表；JSONL 保留原数据类型及记录，BLOB 如有则带 base64 编码标识。

## 搬迁后全量只读验证

在保留上述相对层级后执行 `python3 07_restore/verify_archive.py`。它只读核对全部原始文件、派生文件、链接、九份原数据库及检索库；返回 verified=true、errors=[] 才表示搬迁后的文件完整。

# 环境恢复与私有配置

- `source/`：远端部署源码固定快照，不等同于已发布科学回填 commit。
- `environment/`：REBUILD_MANIFEST、inventory、下载来源、pip/dpkg/MPI 版本、启动脚本、服务单元等。
- `private/`：config.yaml、API token 与节点配置，仅本地私有引用。
- 老部署、context 和数据库入口见 ../05_snapshots/ 与 ../04_databases/。

ORCA 6.1.1 / 完整 OpenMPI 4.1.8 与各题既定方法见环境清单。新 v2 恢复 API 使用 8422 与持久库 recovery_20261001/runtime-v2.db；旧 8420 的原项目上下文没有完整恢复。源码快照未包含虚拟环境或可执行软件整套二进制，重建时用清单和官方来源恢复，不把清单当作二进制副本。

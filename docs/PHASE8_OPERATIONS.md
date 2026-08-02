# 运维、恢复与发布

> **状态**：备份/恢复、吊销、运行状态查询、签名审计命令已实现并通过本地测试。这不代表已完成生产部署或外部基础设施的灾难恢复演练。

生产环境用 `cloudra backup create FILE.zip` 创建备份。SQLite 通过 SQLite 在线备份 API 捕获，运行中的 WAL 数据库不会以撕裂状态复制。归档里有一份带版本号的清单，列出每个文件的成员名、大小和 SHA-256。遇到符号链接、路径穿越、多余归档成员、校验和变化，或目标位于实时数据目录内的情况，都会拒绝。

每次升级前建议运行：

```text
cloudra backup create /srv/cloudra-backups/pre-upgrade.zip
cloudra backup verify /srv/cloudra-backups/pre-upgrade.zip
```

恢复演练应使用新的空目录，不要覆盖生产数据：

```text
cloudra backup restore /srv/cloudra-backups/pre-upgrade.zip /srv/cloudra-restore-test
CLOUDRA_DATA_DIR=/srv/cloudra-restore-test cloudra sessions
```

确认恢复出的实例正常后，再把服务的数据目录切换过去。在健康检查和 Android 重连测试通过前，保留原目录。

节点路由、Slurm 和 worker lease 的更新会将会话 schema 从 v6 升到 v7。现有数据库会在 Session 读取路径使用新列之前自动迁移。首次启动新 checkout 前先创建并验证一份备份；迁移后不要再让新旧 Cloudra checkout 共用同一个数据目录。

`GET /api/operations/status` 用 Server Token 鉴权，只返回有界的状态计数、数据库检查次数、剩余磁盘字节数和稳定的告警码。它故意不包含提示词、路径、原始错误、令牌和设备能力。`CLOUDRA_MIN_FREE_BYTES` 控制磁盘告警下限，默认 1 GiB。`status=degraded` 时要告警，尤其是 `database_check_failed` 和 `disk_free_low`。

Android 配对设备用 `cloudra devices list` 和 `cloudra devices revoke DEVICE_ID` 管理。吊销会立即让设备 token 哈希失效，并关闭未完成的设备工具调用。REST 等价接口是 `DELETE /api/v1/devices/{device_id}`。吊销后设备必须重新配对，会获得新的身份和 token。

生产 APK 必须通过：

```text
CLOUDRA_ANDROID_CERT_SHA256=<pinned-release-fingerprint> \
  cloudra android audit-apk cloudra-release.apk
```

审计会调用 `apksigner`，要求签名方案被接受，拒绝 Android Debug 证书，并把签名证书与固定的 SHA-256 指纹对比。`--allow-debug` 仅供本地安装测试。

## 数据库与队列迁移决策

当前单服务器部署继续使用 SQLite WAL 和持久化的 `session`、`subagent_requests`、`compute_jobs` 表。工作负载只有一台写主机；只把数据库迁到 PostgreSQL 并不能让本地 worker 进程或 workspace 路径分布式运行。节点注册表和 Android 路由契约已经不依赖数据库，所以这个决定是可逆的，不是 API 约束。

当满足以下任一条件时，再一起迁移到 PostgreSQL 和外部队列：多个服务器进程需要抢任务、写锁延迟超过服务 SLO，或者数据库文件不再能放在 worker 主机上。迁移必须引入带 owner id、lease 过期时间、尝试次数和幂等确认的租约；用 `SELECT ... FOR UPDATE SKIP LOCKED`；保留当前所有稳定的任务状态和命令幂等键；在切换前做双读验证。不要把 SQLite 放在 NFS 上作为中间的多节点方案。

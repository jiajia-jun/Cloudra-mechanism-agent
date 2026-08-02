# 节点路由、Worker 恢复与 Slurm 提交

> **Status：** 已落地，本地契约测试已覆盖。多机物理路由和真实 Slurm 集群行为尚未验证。

Android 端的安装和日常使用请看 [`ANDROID_USER_GUIDE.md`](ANDROID_USER_GUIDE.md)；本文只讲路由和部署契约。

## 路由边界

Android 客户端知道自己在连哪个服务器。远程状态文件里现在存了一份非机密的服务器 profile 列表，以及一个当前启用的 profile。Phase 0-7 留下的 `profile` 状态会在第一次保存时自动迁移。Token 仍然存在 Android Keystore 里，按服务器 origin 索引。

每个 profile 会记录用户选定的 `node_id` 和 `workspace_id`。Android 客户端通过 `GET /api/v1/nodes` 和 `GET /api/v1/workspaces` 拿到合法选项，然后在需要路由的请求里带上 `X-Cloudra-Node-ID` 头，创建 Session 时使用选定的 workspace。事件游标（event cursors）和设备身份都按服务器和路由作用域隔离，这样同一会话或设备标识在另一个节点上无法推进或认证错误的状态。

## 节点注册表

服务器从一个 JSON 注册表里暴露多个逻辑节点和 workspace。把 `CLOUDRA_NODE_REGISTRY_FILE` 设成绝对路径，参考 [`deploy/node-registry.example.json`](../deploy/node-registry.example.json)。

每个配置好的 workspace 必须真实存在并能解析到目录；重复或格式错误的标识符会失败关闭。创建 Session 时使用所选 workspace 的规范路径。只读 workspace 可以在注册表里查看，但不能启动 Agent Session。

如果请求带了未知的 `X-Cloudra-Node-ID`，服务器返回 HTTP 409，而不是默默在默认节点上跑。同一个幂等键在另一个节点或 workspace 上重放会冲突，因为路由信息会写进持久化的命令 payload。后续分布式网关可能会替换这个进程内注册表，但客户端契约保持不变。

## Session 与 Worker 恢复

Session 表会持久保存 `node_id`、`workspace_id` 和规范化工作目录。一个已结束的 Session 被移动端消息重新激活时，会沿用原来的路由。

服务器启动时，旧的未认领 `queued` Session 和心跳超时的活跃 Session 会被标记为 `interrupted`；子 Agent 请求和计算任务也都会进入稳定的失败状态。Worker 线程先消费掉持久化的 `ready` 行，再去等边缘触发通知，这样进程重启前刚提交的任务不会因为内存事件丢失而卡住。

子 Agent 和计算 Worker 用原子 owner id、过期时间和尝试计数来认领任务。父 Worker 活着时会续租执行器；在该租约到期前，其他 Worker 不能续租或认领同一行。过期任务最多可以重认领 3 次。预算耗尽后，任务和等待的 Session 会收到一个明确的终端失败和事件，而不是一直假死成 `running`。这是单机版的持久化契约；后续 PostgreSQL Worker 池必须保留相同字段和终端语义。

## Slurm 提交

节点可以声明 `scheduler.type` 为 `local` 或 `slurm`。Slurm 节点接受 `partition`、`account`、`qos`、`time_limit`、`cpus`、`memory`、`poll_seconds` 等字段，注册表会校验这些值。

`submit_compute_job` 会把输入路径解析到最深的注册 workspace，生成一份可审计的批处理脚本，不使用 shell 插值，然后用 `sbatch --parsable` 提交，并保存调度器 job id、状态、脚本路径和终端错误。提交和监控用参数数组调用 `sbatch`、`sacct`、`scancel`，注册表值不会引入额外的指令或命令。

## 恢复策略

恢复时不会尝试在一个已在远端运行的计算任务周围续跑被中断的 Agent。Session 和对应的计算行会被标记为心跳超时并结束，然后服务器尝试取消已保存的 Slurm job id。取消成功记为 `CANCELLED`；失败记为 `CANCEL_FAILED` 并保留错误信息供运维查看。这里优先选择 bounded 的集群资源使用和可审计语义，而不是不安全的隐式重放。

## 环境变量

单机版服务器保持这样配：

```text
CLOUDRA_NODE_ID=node-local
CLOUDRA_SERVER_NAME=Cloudra Server
```

多节点注册表：

```text
CLOUDRA_NODE_REGISTRY_FILE=/etc/cloudra/nodes.json
```

## 其他与待完成项

备份/恢复、设备撤销、运维计数和告警、APK 签名固定、数据库/队列迁移决策见 [`PHASE8_OPERATIONS.md`](PHASE8_OPERATIONS.md)。

Phase 8 还剩下的：基于网关的真实多机注册表、完整的分布式 Worker 租约。Slurm 适配器需要在真实集群上验证，发布 APK 还需要一份私有的生产签名密钥。这些完成前，不要把多节点路径当生产可用。

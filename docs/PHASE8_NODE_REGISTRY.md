# 节点注册表、工作区路由与 Slurm 提交

> **Status：** 已落地，本地契约测试已覆盖。多机物理路由和真实 Slurm 集群行为尚未验证。

本文说明当前实现（`cloudra/services/nodes.py` + `cloudra/infra/slurm.py` +
`cloudra/scheduler/daemon.py`）的部署契约：JSON 节点注册表、工作区路由、
计算作业的 local/Slurm 两条执行路径与恢复语义。面向需要部署或修改这条链路的开发者。

## 节点注册表

服务器从一个 JSON 注册表暴露多个逻辑节点和 workspace。把 `CLOUDRA_NODE_REGISTRY_FILE`
设成绝对路径，参考 [`deploy/node-registry.example.json`](../deploy/node-registry.example.json)。
未设置时退化为单节点：`CLOUDRA_NODE_ID`（默认 `node-local`）、`CLOUDRA_SERVER_NAME`、
配置的 `workspace_dir` 合成一个 local 节点。

校验规则（加载时失败关闭，不静默降级）：

- 每个配置的 workspace 路径必须真实存在且可解析为目录；标识符须匹配
  `[A-Za-z0-9][A-Za-z0-9_.-]*`，重复或格式错误直接报错。
- 每个节点声明 `scheduler.type`：`local` 或 `slurm`；Slurm 节点接受 `partition`、
  `account`、`qos`、`time_limit`、`cpus`、`memory`、`poll_seconds`，未知字段报错。
- 每个节点可声明 `resources`（`max_concurrent` / `cpus` / `memory_mb`，正整数，
  缺省用本地保守兜底：2 槽位、全核、半内存）——调度守护进程据此做容量记账，
  `submit_compute_job` 据此对 agent 的资源申请（`cpus`/`memory_mb`）做提交时硬校验。
- 能力命名空间（`agent.session` / `artifact.download` / `compute.local` /
  `compute.slurm`）由 registry 校验，且节点必须声明与 scheduler 匹配的
  `compute.<type>` 能力。
- workspace 的 `access` 只能为 `read_write` / `read_only`；只读 workspace 可以在
  注册表里查看，但不能作为计算作业的工作目录。

当前实现里 registry 的消费方是 `submit_compute_job`（工作区路由 + scheduler 选择 +
资源申请校验）与 `cloudra scheduler` 守护进程（容量记账）；
`NodeRegistry.public_nodes()` / `public_workspaces()` 是清单投影，供后续 API 面或
网关复用。`default_node_id` 必须存在于注册表，未知 `node_id` 报错，不默默回落默认节点。

## 工作区路由

`submit_compute_job` 把输入路径解析到注册表里**最深**匹配的 workspace
（`NodeRegistry.route_for_path`：路径等于或在某个注册 workspace 之下）；解析不到时
拒绝提交，提示路径不在已注册 workspace 内。`execution_backend` 为 `auto` 时按该节点
的 scheduler 选择 local/Slurm，也可显式指定。

## 计算作业执行

- 中央库 `data_dir/compute.db` 的 `compute_jobs` 表是作业的持久状态机与唯一事实源
  （已迁出会话级 SQLite）；独立守护进程 `cloudra scheduler`
  （`cloudra/scheduler/daemon.py`，与 API 进程分家）轮询中央库，按节点容量
  （槽位 + CPU/内存记账）以 `priority DESC, id ASC` 认领 `ready` 作业。
  `web` 启动时无活实例会自动 detach 拉起（`CLOUDRA_SCHEDULER=off` 关闭）。
- **local**：拉起 guard 子进程（`python -m cloudra.runtime.monitor`）执行计算。
  guard 持有 `guard-<id>.lock` 排他 flock，calculator 经 `calc_lock_wrapper`
  持有 `calc-<id>.lock`（fd 跨 exec 继承，计算全家存续期间锁有效）——进程存活
  判定一律 flock，不读 PID。calculator 以 nice +10 降权拉起（POSIX），CPU 打满时
  控制面按 CFS 权重优先；Linux 生产部署可进一步给计算 slice 配
  `CPUSchedulingPolicy=idle`。guard 日志落盘 `.cloudra/guard-<id>.log`。
- **slurm**：`run_slurm_compute` 生成批处理脚本（不使用 shell 插值，注册表值不会
  引入额外指令），`sbatch --parsable` 提交并保存 job id；轮询期间经 `sacct` 查询
  状态并续租。
- 失败路径把可读原因落 `compute_jobs.last_error` 与 state json 的 `error` 字段；
  guard 的失败/终态是 DAG 计算证据（CallReview 入箱）的来源，`submit_compute_job`
  调用本身永远不算证据。

## 恢复与取消

- 守护进程对账器（30s 周期 + 启动时）：`running` 本地作业 guard 锁被持有 → 续租防
  重领；guard 锁空闲（guard 已死）→ spawn adopt guard 接管——calc 锁仍被持有则
  阻塞等计算自然跑完再收尾，锁空闲则直接解析日志落终态，无日志判 failed。
  **任何路径不 kill 计算进程**；作业目录建议放本地盘（NFS 上 fcntl 锁语义弱）。
- Slurm 作业以 sacct 为外部权威：服务重启后租约过期被重领，凭 `scheduler_job_id`
  续接管不重复 sbatch；成功拉起即清零 `attempt_count`（重启不消耗重试预算）。
- 取消只有一条显式路径：agent/用户 `cancel_requested` → `scancel`。

## 环境变量

```text
CLOUDRA_NODE_ID=node-local              # 单节点退化模式
CLOUDRA_SERVER_NAME=Cloudra Server      # 展示名
CLOUDRA_NODE_REGISTRY_FILE=/etc/cloudra/nodes.json   # 多节点注册表
```

## 尚未验证 / 待完成

真实 Slurm 集群上的提交、取消与恢复试验、多机物理路由网关、分布式 Worker 租约。
这些完成前，不要把多节点路径当生产可用。

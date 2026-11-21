# 计算节点、工作区路由与远程 / Slurm 提交

本文介绍 Cloudra 如何管理多台计算节点（本地、SSH 远端服务器、Slurm 集群），以及作业是怎么排队、保活、恢复和取消的。相关代码在 `cloudra/services/nodes.py`、`cloudra/infra/slurm.py`、`cloudra/infra/ssh_transport.py`、`cloudra/runtime/remote_compute.py` 和 `cloudra/scheduler/daemon.py`。

> 目前状态：本地契约测试和模拟传输单测都已覆盖；真实的 SSH 远端和真实 Slurm 集群大规模实机验收仍在完善中。

## 配置节点注册表

把环境变量 `CLOUDRA_NODE_REGISTRY_FILE` 指向一个 JSON 文件即可启用多节点（写法参考 [`deploy/node-registry.example.json`](../deploy/node-registry.example.json)）。如果不设这个变量，Cloudra 会自动退化成单本机节点（节点名取 `CLOUDRA_NODE_ID`，默认 `node-local`）。

注册表在加载时严格校验，写错直接报错、绝不静默降级：

- **工作区（`workspaces`）**：路径必须真实存在且是目录，ID 只能含字母数字和 `_.-`；`access` 为 `read_only` 的工作区只能看，不能作为计算目录。
- **调度方式（`scheduler.type`）**：支持 `local`（本机直跑）和 `slurm`（`sbatch` 提集群）。Slurm 节点可配 `partition`、`account`、`qos`、`time_limit`、`cpus`、`memory`、`poll_seconds` 和 `modules`（配了模块会自动在脚本里 `module load`）。
- **连接方式（`connection`）**：默认 `local`；填 `{"type": "ssh", "host": "...", "user": "...", "remote_root": "..."}` 表示远端节点（可选 `port` 和本地 `identity_file`）。连接方式和调度方式正交组合：`ssh + slurm` 是连登录节点提 `sbatch`，`ssh + local` 是连远端裸机直接跑。提交时会把连接信息快照写进作业行，以后改注册表不会把正在跑的作业搞崩。SSH 配置细节见 [`deploy/ssh_remote_node.md`](../deploy/ssh_remote_node.md)。
- **资源额度（`resources`）**：配 `max_concurrent`、`cpus`、`memory_mb`（不配则按本机兜底：10 槽位、全核、物理内存留 8 GiB 余量且不低于一半）。每个节点的额度完全独立——本地额度不会被远程作业吃掉，反之亦然。本机 `local` 节点还会结合操作系统实时剩余内存和负载做上限约束，防止系统被算死；远端节点直接按注册声明算。

## 作业怎么路由到节点

调用 `submit_compute_job` 时，如果不指定 `node_id`，系统按输入文件所在路径匹配注册表里最深的工作区，自动确定归属节点。也可以显式传 `node_id` 指定跑在哪台机器（可先用 `query_compute_queue` 看各节点余量）。

**明确不做自动漂移**：一个作业在提交时归属哪个节点就钉死了，就算别的节点空着也不会偷偷改投。如果该节点从注册表里被删掉，作业会乖乖排队并在界面写清原因，绝不乱换机器。

## 执行、保活与崩溃恢复

所有计算作业统一记在中央数据库 `data_dir/compute.db` 的 `compute_jobs` 表里，由独立进程 `cloudra scheduler` 轮询认领（`cloudra web` 默认自动带起它，也可以用 `CLOUDRA_SCHEDULER=off` 关掉并手动跑 `cloudra scheduler`）。

- **本机作业（`local`）**：每个作业由一个独立的 `guard` 子进程看守，分别持有 `guard-<id>.lock` 和跨进程继承的 `calc-<id>.lock` 文件排他锁。系统只认文件锁判断计算活没活着，不猜 PID；计算进程默认以 `nice +10` 降权运行，保证网页界面不卡。
- **本机 Slurm（`slurm`）**：生成无 shell 注入风险的批处理脚本，用 `sbatch --parsable` 提交并靠 `sacct` 轮询。
- **SSH 远端作业（`ssh_local` / `ssh_slurm`）**：用 `rsync` 把输入目录同步到 `<remote_root>/cloudra-<id>/` 跑完再把结果拉回本地，最后在本地用同样的引擎文本闸门核对结果。`ssh_local` 要求远端有 Python 3.11+，不用装 Cloudra；`ssh_slurm` 直接靠 Slurm 管理。

**为什么服务挂了计算也不会死**：重启时对账器会扫描所有在跑作业。本机作业如果 `guard` 死了但 `calc` 锁还在，会拉起一个接管 guard 静静等它算完收尾；Slurm 作业凭 `scheduler_job_id` 通过 `sacct` 接管，绝不重复提交；SSH 作业凭连接快照找回远端进程或 Slurm 作业续接。

**怎么安全取消**：排队中的作业直接标 `cancelled`；正在跑的作业先写 `cancel_requested` 标志，等对应 guard 给自己拉起的进程组发 `TERM`、确认子进程退出并释放文件锁（或 Slurm `scancel` 确认终态）后，才正式记为 `cancelled` 并释放容量。

## 常用环境变量

```text
CLOUDRA_NODE_ID=node-local
CLOUDRA_SERVER_NAME=Cloudra Server
CLOUDRA_NODE_REGISTRY_FILE=/etc/cloudra/nodes.json
```

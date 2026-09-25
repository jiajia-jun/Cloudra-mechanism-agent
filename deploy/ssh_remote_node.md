# SSH 远端计算节点部署

> 实现：`cloudra/infra/ssh_transport.py`（传输原语）+
> `cloudra/runtime/remote_compute.py`（看守 poller）。注册表 schema 见
> `docs/PHASE8_NODE_REGISTRY.md`。

Cloudra 本体只跑在本地一台机器上；SSH 远端节点让 agent 把计算作业投到
**无 Cloudra 的远端服务器**执行——资源调度（排队、容量记账、认领）全部发生在
本地中央 `compute.db`，远端只是执行器。一台本地机可挂任意多个远端节点，
agent 用 `submit_compute_job(node_id=...)` 选择目标。

两种远端形态（由节点的 `scheduler.type` 决定，与 connection 正交）：

| 注册表组合 | 语义 | 远端依赖 |
|---|---|---|
| `connection: ssh` + `scheduler.type: slurm` | SSH 到登录节点 `sbatch` | sbatch/sacct/scancel、bash、rsync、引擎 |
| `connection: ssh` + `scheduler.type: local` | 远端裸 shell `nohup` 直跑 | bash、rsync、引擎 |

## 前置条件

- 本机到远端 `host` 的**免密 SSH**（`identity_file` 或 ssh-agent/默认密钥），
  非交互（传输层强制 `BatchMode=yes`，需要交互密码的场景直接失败）。
- 两端都有 `rsync`（作业目录 stage-out / 产物 pull-back 的唯一通道）。
- 远端 PATH 上有对应引擎二进制（或用节点 `scheduler.modules`/`environment`
  在脚本里 `module load`/export）。准入时做一次远端探测（`command -v`，
  300s 缓存），缺失即拒收并列出缺什么。
- 远端 `remote_root` 可写（每个作业一个 `cloudra-<id>/` 子目录）。

## 注册一个远端节点

见 `deploy/node-registry.example.json` 的 `hpc-login` / `workstation-b` 示例。
要点：

- `workspaces[].path` 是**本机**目录（staging 语义：注册表要求路径本机存在）。
  agent 把输入写进该目录并按 `execution_backend=auto` 路由到远端节点，或更直接地
  在任意工作目录准备好输入后用 `submit_compute_job(node_id="<节点>")` 显式指定。
- `resources` 是**本地记账额度**（远端节点的 OS 余量不可见，只按注册声明放行）；
  Slurm 节点的真实排队由远端 Slurm 自己承担。
- `scheduler.modules`/`environment`/`partition`/`time_limit`/`poll_seconds`
  照常生效（写进远端 batch/runner 脚本）。

## 执行语义（排障速查）

- 作业在远端的目录是 `<remote_root>/cloudra-<task_id>/`；终态后全部产物
  rsync 拉回本地输入所在目录（`.cloudra/calc-<id>.out.log` 等随之就位，
  `query_compute_job`/日志解析/`resolve_log_path` 与本地作业同口径）。
- 终态判定永远在本地：拉回后用与 guard 同款的引擎文本终止标记复核，
  远端「退出码 0」/「Slurm COMPLETED」但日志无正常终止标记照样判 failed。
- 取消：`cancel-all`（或作业级 cancel）→ 账本 `cancel_requested` → poller
  远端 `scancel`（ssh_slurm）/ TERM runner+calculator（ssh_local），账本随即
  收口 cancelled；远端取消是 best-effort，不成功不阻塞账本收口。
- 本地重启恢复：对账器用账本行的 connection 快照找回句柄（ssh_slurm 按
  job-name 查远端 sacct；ssh_local 探远端 `.cloudra-runner-<id>.pid`），
  找回即重挂 poller，**不重复提交**；ssh_local 确认远端从未起跑才重投
  （stage/submit 幂等）。
- 产物拉回不成功重试 5 轮后落 failed（`last_error` 带原因）；轮询期的
  ssh 抖动按瞬态容忍自动重试。

## 边界（明确不做）

- 远端不装 cloudra、不起 guard（无 flock/adopt 语义；恢复 = 重挂 poller）。
- 不做远端实时容量探测、不做远端 Slurm 队列全景——队列视图是本地账本口径
  （`query_compute_queue` / Ops 面板节点容量卡片，远端节点带 `ssh user@host`
  徽章）。
- 远端作业总是异步（无 `is_async=false` 同步等待路径）。
- 远端直跑节点的「进程存活」靠 pid 探活 + 退出文件，极端场景（runner 被
  SIGKILL 且 pid 被复用）可能延迟到下一轮才判死——以拉回日志的文本闸门兜底。

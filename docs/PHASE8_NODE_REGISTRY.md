# 节点注册表、工作区路由与 Slurm 提交

> **Status：** 已落地，本地契约测试已覆盖。SSH 远端路径（`connection: ssh`）
> 有单元级覆盖（假传输），真实远端/真实 Slurm 集群行为尚未验证。

本文说明当前实现（`cloudra/services/nodes.py` + `cloudra/infra/slurm.py` +
`cloudra/infra/ssh_transport.py` + `cloudra/runtime/remote_compute.py` +
`cloudra/scheduler/daemon.py`）的部署契约：JSON 节点注册表、工作区路由、
计算作业的 local/Slurm/SSH 远端三条执行路径与恢复语义。面向需要部署或修改
这条链路的开发者。

## 节点注册表

服务器从一个 JSON 注册表暴露多个逻辑节点和 workspace。把 `CLOUDRA_NODE_REGISTRY_FILE`
设成绝对路径，参考 [`deploy/node-registry.example.json`](../deploy/node-registry.example.json)。
未设置时退化为单节点：`CLOUDRA_NODE_ID`（默认 `node-local`）、`CLOUDRA_SERVER_NAME`、
配置的 `workspace_dir` 合成一个 local 节点。

校验规则（加载时失败关闭，不静默降级）：

- 每个配置的 workspace 路径必须真实存在且可解析为目录；标识符须匹配
  `[A-Za-z0-9][A-Za-z0-9_.-]*`，重复或格式错误直接报错。
- 每个节点声明 `scheduler.type`：`local` 或 `slurm`；Slurm 节点接受 `partition`、
  `account`、`qos`、`time_limit`、`cpus`、`memory`、`poll_seconds`，以及非空的
  `modules` 列表。配置模块时，批处理脚本会初始化 Environment Modules，并在计算命令
  前执行一次 `module load`；未知字段报错。
- 每个节点可声明 `connection`（缺省 `{"type": "local"}` 即进程内执行）；
  `{"type": "ssh"}` 表示**远端节点**：必填 `host`/`user`/`remote_root`（远端作业
  根目录，绝对路径），可选 `port`（默认 22）与 `identity_file`（本机私钥，必须
  真实存在；省略走 ssh 默认密钥解析）。connection 与 scheduler 正交：
  `ssh + slurm` = SSH 到登录节点 sbatch，`ssh + local` = 远端裸 shell 直跑。
  账本行调度器落 `ssh_slurm`/`ssh_local` 并携带 connection 快照（行自包含，
  改注册表不影响在飞作业）。SSH 远端路径详见
  [`deploy/ssh_remote_node.md`](../deploy/ssh_remote_node.md)。
- 每个节点可声明 `resources`（`max_concurrent` / `cpus` / `memory_mb`，正整数，
  缺省用本地兜底：10 槽位、全核、物理内存扣掉 8 GiB 系统余量且不低于半内存）
  ——`submit_compute_job` 据此对 agent 的资源申请（`cpus`/`memory_mb`）做提交时硬校验。
- **容量按节点分池记账（解耦）**：每个作业在入库时带 `node_id`（准入按工作区路由
  解析出的归属节点），调度认领只在**该节点自己的额度**内放行——本地额度不会被
  云端作业吃掉，反之亦然。
  - 生效容量 = `min(注册声明, OS 实时余量)`，但**只有跑在本机的 `local` 节点**
    受 OS 余量约束（`services/host_capacity.py::effective_node_resources`）；远端/
    集群节点不在这台机器上，OS 读数对它没有意义，原样用注册声明。
  - 作业成本仍按 agent 声明的 `req_cpus`/`req_memory_mb` 记账；OS 侧只回答"这台
    机器现在还剩多少"——剩余内存取 `free + inactive + speculative + purgeable`
    （macOS `vm_stat`／Linux `MemAvailable`），可用核数取 `cpu_count −
    ceil(loadavg 1min)`。这样**账本看不见的占用也被算进去**（agent 绕过
    `submit_compute_job` 直调引擎起的作业、浏览器等无关进程）。
  - 读数只用于放行判定与展示，不参与存活/终态判定；探针读不到时回落声明容量
    （不断停摆，状态翻转记一条 WARNING）。
  - `node_id` 为 NULL 的行（升级前的旧行）视为归属注册表的 `default_node_id`。
  - 作业归属节点**不在注册表里**（节点被摘除、注册表改坏）时：调度器跳过不认领，
    绝不改投到别的机器上跑；`query_compute_queue` 与控制面容量视图会把这条原因
    讲清楚。修复方式是重新注册该节点，或取消这个作业。
- 能力命名空间（`agent.session` / `artifact.download` / `compute.local` /
  `compute.slurm`）由 registry 校验，且节点必须声明与 scheduler 匹配的
  `compute.<type>` 能力。
- workspace 的 `access` 只能为 `read_write` / `read_only`；只读 workspace 可以在
  注册表里查看，但不能作为计算作业的工作目录。

当前实现里 registry 的消费方是 `submit_compute_job`（工作区路由 + scheduler 选择 +
资源申请校验 + 归属节点）、`cloudra scheduler` 守护进程（按节点分池的容量记账）、
容量视图（`query_compute_queue` 工具与 `GET /api/v2/compute/nodes`，口径唯一实现
在 `services/node_capacity.py`）。`NodeRegistry.public_nodes()` /
`public_workspaces()` 是清单投影，供后续 API 面或网关复用。`default_node_id` 必须
存在于注册表，未知 `node_id` 报错，不默默回落默认节点。

## 工作区路由

`submit_compute_job` 把输入路径解析到注册表里**最深**匹配的 workspace
（`NodeRegistry.route_for_path`：路径等于或在某个注册 workspace 之下）；解析不到时
拒绝提交，提示路径不在已注册 workspace 内。`execution_backend` 为 `auto` 时按该节点
的 scheduler 选择 local/Slurm，也可显式指定。此外 `node_id` 参数可显式指定目标节点
（agent 选远端服务器的入口）：给定后跳过工作区路由，`execution_backend` 非 auto 时
必须与节点自身 `scheduler.type` 一致。一台本地 Cloudra 挂多个远端节点时，agent 用
`query_compute_queue` 列出全部节点与余量，按 `node_id` 选择提交目标。

## 计算作业执行

- 中央库 `data_dir/compute.db` 的 `compute_jobs` 表是作业的持久状态机与唯一事实源
  （已迁出会话级 SQLite）；独立守护进程 `cloudra scheduler`
  （`cloudra/scheduler/daemon.py`，与 API 进程分家）轮询中央库，按**每个作业
  归属节点各自的额度**（槽位 + CPU/内存记账）以 `priority DESC, id ASC` 认领
  `ready` 作业。队列是全库统一的，额度是分节点的：某个节点放不下的作业跳过，
  不阻塞别的节点能放下的作业。
  `web` 启动时无活实例会自动 detach 拉起（`CLOUDRA_SCHEDULER=off` 关闭）。
- `compute_jobs.node_id` 由 `ComputeDB.init()` 的幂等 `ALTER` 补列（旧库升级不重建
  表）；NULL 视为默认节点归属。控制面/工具展示该列（`GET /api/v2/compute/nodes`、
  `query_compute_queue`、项目作业队列、Ops 面板）。
- **local**：拉起 guard 子进程（`python -m cloudra.runtime.monitor`）执行计算。
  guard 持有 `guard-<id>.lock` 排他 flock，calculator 经 `calc_lock_wrapper`
  持有 `calc-<id>.lock`（fd 跨 exec 继承，计算全家存续期间锁有效）——进程存活
  判定一律 flock，不读 PID。calculator 以 nice +10 降权拉起（POSIX），CPU 打满时
  控制面按 CFS 权重优先；Linux 生产部署可进一步给计算 slice 配
  `CPUSchedulingPolicy=idle`。guard 日志落盘 `.cloudra/guard-<id>.log`。
- **slurm**：`run_slurm_compute` 生成批处理脚本（不使用 shell 插值，注册表值不会
  引入额外指令），`sbatch --parsable` 提交并保存 job id；轮询期间经 `sacct` 查询
  状态并续租。
- **ssh_slurm / ssh_local**（节点带 `connection: ssh`，`runtime/remote_compute.py`）：
  远端不起 guard，认领进程内 async poller 即看守。`ssh_local` 需要 Python 3.11+，
  随任务发送与本地相同的独立计算 owner，无需安装 Cloudra；`ssh_slurm` 由 Slurm
  根据作业句柄取消和确认退出，不增加 Python 要求。
  rsync 把整棵本地工作目录推送到 `<remote_root>/cloudra-<id>/`（排除 `.cloudra/`、
  `.g16_scratch/`，并单独推内置 calculator.sh），然后远端 sbatch 或 nohup 直跑
  runner 脚本（退出码落 `.cloudra-exit-<id>`）；终态后拉回全部产物到本地输入目录，
  **本地**跑与 guard 同款的引擎文本闸门复核再 CAS 落账本。容量记账、排队、终态
  判定全部发生在本地；远端只是执行器。
- 失败路径把可读原因落 `compute_jobs.last_error` 与 state json 的 `error` 字段；
  guard 的失败/终态是 DAG 计算证据（CallReview 入箱）的来源，`submit_compute_job`
  调用本身永远不算证据。

## 恢复与取消

- 守护进程对账器（30s 周期 + 启动时）：`running` / `cancel_requested` 本地作业 guard 锁被持有 → 续租防
  重领；guard 锁空闲（guard 已死）→ spawn adopt guard 接管——calc 锁仍被持有则
  阻塞等计算自然跑完再收尾，锁空闲则直接解析日志落终态，无日志判 failed。
  异常、Agent 取消、服务停止均不向计算发信号；作业目录建议放本地盘（NFS 上 fcntl 锁语义弱）。
  adopt 没有原始进程句柄，不凭存盘 PID 发信号；取消请求在 calc 锁释放后确认。
- Slurm 作业以 sacct 为外部权威：服务重启后租约过期被重领，凭 `scheduler_job_id`
  续接管不重复 sbatch；成功拉起即清零 `attempt_count`（重启不消耗重试预算）。
- SSH 远端作业（`ssh_local`/`ssh_slurm`）重启恢复：对账器按账本行的 connection
  快照还原端点——ssh_slurm 无句柄时走远端 `sacct --name cloudra-<id>` 找回
  （只认非终态行，找不回不盲投）；ssh_local 无句柄时探远端 runner pid 文件
  （`.cloudra-runner-<id>.pid` 是 runner 的第一条写操作，查不到即确认未起跑，
  安全重挂 poller 重新 stage+submit）；有柄则续租重挂 poller，不重复提交。
- 用户取消计算：排队作业直接 `cancelled`，所有运行中作业先 `cancel_requested`，
  未确认停止时继续占用容量。本地原始 guard 只向自己创建的独占进程组发送一次
  TERM，回收子进程并取得已释放的 calc 锁后才写 `cancelled`、清理 Gaussian scratch。
  忽略 TERM 的计算保持取消中；已运行的旧 guard 不会自动加载新代码。
- 本机 Slurm 显式请求走 `scancel`，继续查询 `sacct`，确认终态后才落 `cancelled`；
  请求失败、状态未知或句柄无法恢复均保留取消中。
- SSH 远端取消仍由 `remote_compute.py` 的 poller 执行；远端提交、取消与恢复的实机验收见下节。

## 环境变量

```text
CLOUDRA_NODE_ID=node-local              # 单节点退化模式
CLOUDRA_SERVER_NAME=Cloudra Server      # 展示名
CLOUDRA_NODE_REGISTRY_FILE=/etc/cloudra/nodes.json   # 多节点注册表
```

## 尚未验证 / 待完成

真实 Slurm 集群与真实 SSH 远端上的提交、取消与恢复试验、分布式 Worker 租约
（把裸 VM/容器当 worker 挂进同一条队列——SSH 路径已覆盖其中「裸服务器直跑」
场景；更通用的网络化租约与远端判活仍未做）。这些完成前，不要把多节点路径当
生产可用。

**已明确不做**：作业不会因为"别的节点有空闲"而被改投——归属节点是提交时按工作区
路由钉死的，节点摘除只会让作业排队（视图里给出原因），绝不会换机器跑。

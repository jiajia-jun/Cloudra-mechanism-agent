# HPC 集群与 Slurm 登录节点部署实战指南

> **适用场景：** 将 Cloudra 部署在高校、科研院所或国家超算中心（如中科曙光、联想网格、天河等 Slurm 集群），并在本地客户端（如 Mac）通过浏览器远程访问。

---

## 1. 架构设计与合规性

### 1.1 为什么把 Cloudra 部署在登录节点？
- **角色定位**：Cloudra 在超算中扮演 **Workflow Manager（工作流编排器）** 的角色，与 Snakemake、Nextflow、AiiDA 定位一致。
- **资源合规**：
  - Cloudra 自身仅负责 LLM 通信、任务图（DAG）编排、输入文件生成以及定时轮询 `sacct` 探活，CPU 与内存开销极低（秒级占用 < 1%）。
  - 所有量子化学与分子力场计算（ORCA、Gaussian、xTB、CP2K 等）均由 `cloudra scheduler` 通过 `sbatch` 投递至 **Slurm 计算节点（Compute Nodes）** 运行，完全不占用登录节点的核心算力，符合绝大多数集群的管理规范。

### 1.2 网络通信拓扑
超算登录节点通常处于内部私有网络，外部不可直接访问非标准端口。推荐使用 **SSH 本地端口转发隧道** 进行连接：

```text
[本地 Mac / PC]                                           [远程 HPC 集群]
  Chrome / Safari 浏览器                                    登录节点 (Login Node)
        │                                                          │
        │ 访问 http://127.0.0.1:8420/#token=...                    │
        ▼                                                          ▼
  本地端口 8420  <====== SSH 隧道 (加密转发) ======>  Cloudra Web 服务 (127.0.0.1:8420)
                                                                   │
                                                                   │ 自动驱动
                                                                   ▼
                                                          cloudra scheduler 调度守护
                                                                   │
                                                                   │ sbatch / sacct
                                                                   ▼
                                                          Slurm 计算集群 (Compute Nodes)
```

---

## 2. 真实超算环境关键踩坑与解法

### 坑 1：多登录节点随机轮询（Round-Robin 负载均衡）
- **现象**：
  外部 SSH 域名（如 `cancon.hpccube.com:65023`）背后通常挂着一个登录节点池（`login01`, `login02` ... `login09`）。每次新建 SSH 会话，网关会随机分流到不同的机器上。在 `login03` 启动了后台服务，下次连接分流到了 `login09`，会导致本地端口转发报 `Connection refused`。
- **解法**：
  在客户端（Mac）的 `~/.ssh/config` 中利用 `ProxyJump` 语法将连接**强行锁定到特定的物理登录节点**（例如 `login03`）：
  ```ssh-config
  # 负载均衡入口（外网网关）
  Host gold-lb
      HostName cancon.hpccube.com
      Port 65023
      User yyywaa
      IdentityFile ~/.ssh/id_gold
      StrictHostKeyChecking no

  # 锁定内网固定节点（服务常驻点）
  Host gold
      HostName login03
      User yyywaa
      ProxyJump gold-lb
      IdentityFile ~/.ssh/id_gold
      ServerAliveInterval 60
      StrictHostKeyChecking no
  ```
  配置后，终端执行 `ssh gold` 永远直达 `login03`，端口与进程不再漂移。

---

### 坑 2：登录节点断外网（无法联网 pip / git）
- **现象**：
  大部分安全性严格的超算禁止登录节点直接出站访问公网（无法连接 PyPI、GitHub、npm 源），执行 `pip install` 或 `curl` 会直接超时。
- **解法：本地跨平台预打包（Wheel Bundle）+ 离线安装**
  1. **本地交叉下载 Linux x86_64 依赖**：
     在本地电脑上，利用 `pip download` 强制指定目标超算的架构与 Python 版本：
     ```bash
     pip download \
       -r requirements.txt \
       --dest /tmp/cloudra_wheels \
       --platform manylinux2014_x86_64 \
       --platform manylinux_2_17_x86_64 \
       --python-version 3.12 \
       --implementation cp \
       --abi cp312 \
       --only-binary=:all:
     ```
  2. **打包同步**：
     通过 `rsync` 将源码与 Wheel 文件夹同步至超算。**注意排除本地的大型虚拟环境（如 `.venv*`）**，避免传输数万个小文件导致网络卡顿：
     ```bash
     rsync -avz --exclude=".venv*" --exclude=".git" --exclude="node_modules" \
       ./ gold:~/cloudra/
     rsync -avz /tmp/cloudra_wheels/ gold:~/cloudra_wheels/
     ```
  3. **超算离线安装**：
     使用超算公共模块中的 Python 3.12（如 `/public/software/apps/miniconda3/py312_24.9.2/bin/python`）创建专属虚拟环境并离线秒级安装：
     ```bash
     python -m venv ~/.venvs/cloudra
     ~/.venvs/cloudra/bin/pip install --no-index --find-links=$HOME/cloudra_wheels $HOME/cloudra_wheels/*.whl
     ~/.venvs/cloudra/bin/pip install --no-index --find-links=$HOME/cloudra_wheels -e $HOME/cloudra --no-deps
     ```

---

### 坑 3：超算端避免引入 Node.js / npm 工具链
- **原则**：
  超算登录节点的核心职责是科学计算与作业提交，环境通常偏老旧（如 CentOS 7），**完全没有必要在超算上折腾 Node.js 与前端编译工具链**。
- **解法**：
  - **静态资源本地编译**：在本地开发机执行 `npm run build` 生成 `frontend/dist`，随源码直接同步到超算。
  - **启动带 `--skip-build`**：服务端 FastAPI / Uvicorn 仅作为静态文件托管服务器，使用 `--skip-build` 参数直接托管已有的 `dist/`，超算环境零 Node.js 依赖。

---

### 坑 4：后台常驻与 SSH 连接脱钩
- **现象**：
  在 SSH 会话中执行普通的 `nohup ... &`，断开 SSH 时往往因为标准输入（stdin）没有切断，导致 SSH 客户端卡死或返回错误码 `255`，进而带崩后台服务。
- **解法**：
  后台拉起必须重定向三向文件描述符（标准输入来自 `/dev/null`，标准输出和错误重定向到文件）：
  ```bash
  nohup "$HOME/cloudra/run_server.sh" </dev/null >/public/home/yyywaa/cloudra/server.log 2>&1 &
  ```

---

## 3. Slurm 节点配置清单（`nodes.json`）

在超算 `~/cloudra/config/nodes.json` 中配置 Slurm 分区与资源配额：

```json
{
  "default_node_id": "hpc-slurm",
  "nodes": [
    {
      "node_id": "hpc-slurm",
      "display_name": "Cancon Slurm Cluster",
      "state": "online",
      "capabilities": ["agent.session", "artifact.download", "compute.slurm"],
      "resources": {
        "max_concurrent": 10,
        "cpus": 64,
        "memory_mb": 262144
      },
      "scheduler": {
        "type": "slurm",
        "partition": "kshctest02",
        "account": "yyywaa",
        "qos": "user_yyywaa",
        "time_limit": "1-00:00:00",
        "cpus": 16,
        "memory": "64G",
        "poll_seconds": 15
      },
      "workspaces": [
        {
          "workspace_id": "default",
          "display_name": "Cloudra Workspace",
          "path": "/public/home/yyywaa/cloudra_workspace",
          "access": "read_write"
        }
      ]
    }
  ]
}
```

> **注意**：`path` 必须位于所有 Slurm 计算节点均可读写的**共享并行文件系统**（如 `/public/home/...`、`/scratch/...` 或 Lustre 挂载点），不能使用登录节点独享的本地 `/tmp`。

---

## 4. 推荐生产启动脚本（`run_server.sh`）

在超算端保存为 `~/cloudra/run_server.sh`，赋予可执行权限（`chmod +x`）：

```bash
#!/bin/bash
set -euo pipefail

# 1. 环境变量与路径补齐
export PATH="$HOME/.local/bin:/opt/gridview/slurm/bin:$HOME/.venvs/cloudra/bin:$PATH"
export PYTHONPATH="$HOME/cloudra:${PYTHONPATH:-}"
export CLOUDRA_NODE_REGISTRY_FILE="$HOME/cloudra/config/nodes.json"
export CLOUDRA_FRONTEND_SERVE_DIR="$HOME/cloudra/frontend/dist"
export CLOUDRA_API_BIND_HOST="127.0.0.1"
export CLOUDRA_NO_BROWSER="1"

# 2. 超算科学计算模块（根据集群实际情况加载）
if type module >/dev/null 2>&1; then
    module load apps/orca/5.0.2/hpcx-2.7.4-gcc-7.3.1 2>/dev/null || true
fi

cd "$HOME/cloudra"

# 3. 启动 ASGI Web 服务（生命周期管理器会自动拉起并维护 cloudra.scheduler 守护）
exec "$HOME/.venvs/cloudra/bin/python" -m uvicorn cloudra.services.api_v2:create_default_v2_app \
    --factory \
    --host 127.0.0.1 \
    --port 8420 \
    --timeout-graceful-shutdown 20
```

---

## 5. 运维操作手册

| 操作 | 对应命令 | 说明 |
| :--- | :--- | :--- |
| **一键登录超算** | `ssh gold` | 本地终端直接进入目标登录节点 |
| **查看服务日志** | `tail -f ~/cloudra/server.log` | 查看实时推理与 API 访问日志 |
| **查看调度守护** | `ps aux \| grep cloudra.scheduler` | 验证 Slurm 队列调度器是否存活 |
| **查看 Slurm 任务** | `squeue -u $USER` 或 `sacct` | 监控计算节点上的 ORCA/Gaussian 作业 |
| **本地建立隧道** | `ssh -N -L 8420:127.0.0.1:8420 gold` | 在本地 Mac 打开网页访问端口 |
| **重启服务** | `pkill -f 'uvicorn' && ~/cloudra/run_server.sh &` | 重启 Web 进程（scheduler 会自动自愈） |

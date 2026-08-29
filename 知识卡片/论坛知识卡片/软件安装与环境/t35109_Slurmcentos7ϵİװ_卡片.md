---
key: t35109
title: Slurm��centos7�����ϵİ�װ����
url: http://bbs.keinsci.com/thread-35109-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 11
---

# Slurm��centos7�����ϵİ�װ���� — 知识卡片

## 1. SLURM 环境依赖安装命令

SLURM 在 CentOS 7 系统下安装前需执行特定命令安装必要的开发库与工具。所需依赖包包括 hwloc-devel、libevent-devel、munge、munge-libs、munge-devel 和 s-nail。安装 munge 后需执行 `/usr/sbin/create-munge-key` 生成密钥，并使用 `systemctl` 命令设置 munge 服务开机自启并立即启动。
- 命令: `yum -y install hwloc-devel libevent-devel`
- 命令: `yum -y install munge munge-libs munge-devel`
- 命令: `yum -y install install s-nail`
- 命令: `/usr/sbin/create-munge-key`
- 命令: `systemctl enable munge --now`

---

## 2. PMix 编译安装步骤

PMix 需下载源码包并在解压后通过 configure 配置环境，接着使用 make 命令进行多线程编译与安装。示例中使用的是版本 pmix-4.2.3rc2，编译时利用 `$(nproc)` 自动调用所有可用 CPU 核心加速构建过程，最终安装目录默认为系统预设路径。
- 版本: `pmix-4.2.3rc2`
- 命令: `tar -xvf pmix-4.2.3rc2.tar.gz && cd pmix-4.2.3rc2`
- 命令: `./configure && make install -j $(nproc) && cd /opt`

---

## 3. SLURM 编译安装步骤

SLURM 需下载源码包并在解压后执行 configure 与 make 进行编译安装，操作流程与 PMix 类似。示例中使用的版本为 slurm-22.05.8，编译完成后工作目录切换至 /opt，后续配置文件将位于 /usr/local/etc/ 目录下。
- 版本: `slurm-22.05.8`
- 命令: `tar -xvf slurm-22.05.8.tar.bz2 && cd slurm-22.05.8`
- 命令: `./configure && make install -j $(nproc) && cd /opt`

---

## 4. 系统硬件信息收集命令

配置 SLURM 前需收集节点的硬件信息以填入配置文件，包括 CPU、内存及 GPU 状态。使用 `find` 命令定位 slurm.conf 和 gres.conf 的位置，使用 `hostname` 获取主机名，利用 `lscpu` 查看 CPU 详情，`free -m` 查看内存，`nvidia-smi` 查看 GPU 信息。
- 命令: `find / -name slurm.conf && find / -name gres.conf && hostname && lscpu && free -m && nvidia-smi`

---

## 5. SLURM 配置文件生成与核心参数

SLURM 提供在线配置生成器网页，用户需填入集群名称、控制节点主机名、节点名及硬件资源信息。关键参数配置包括：ClusterName 和 SlurmctldHost 设为主机名，CPU 核心数与插槽数依据 `lscpu` 结果，RealMemory 依据 `free -m` 结果，SlurmUser 设为 root，Default MPI Type 可选 pmix，Process Tracking 选 LinuxProc，Resource Selection 选 Cons_res/cons_tres，SelectTypeParameters 选 CR_Memory，Job Accounting Gather 选 Linux。
- 网页: `/opt/slurm-22.05.8/doc/html/configurator.easy.html`
- 关键参数: `SelectType=select/cons_tres`
- 关键参数: `JobAcctGatherType=jobacct_gather/linux`
- 关键参数: `ProctrackType=proctrack/linuxproc`

---

## 6. slurm.conf 配置文件内容示例

生成器的配置结果需写入 `/usr/local/etc/slurm.conf` 文件中，文件包含集群定义、日志路径、节点资源与分区设置。示例中定义了集群名为 VM-0-5-centos，开启了任务亲和插件，指定了 slurmd 与 slurmctld 的 PID 及日志文件路径，并设置了名为 debug 的分区包含所有节点。
- 文件路径: `/usr/local/etc/slurm.conf`
- 配置示例:
  ```
  ClusterName=VM-0-5-centos
  SlurmctldHost=VM-0-5-centos
  SlurmUser=root
  SelectType=select/cons_tres
  PartitionName=debug Nodes=ALL Default=YES MaxTime=INFINITE State=UP
  ```

---

## 7. gres.conf GPU 资源配置

GPU 资源需在 `/usr/local/etc/gres.conf` 文件中显式配置，将节点名与具体的 GPU 设备文件关联。示例中节点 VM-0-5-centos 配置了两块 GPU，分别对应 `/dev/nvidia0` 和 `/dev/nvidia1`，配置完成后 SLURM 才能识别和调度 GPU 资源。
- 文件路径: `/usr/local/etc/gres.conf`
- 配置内容:
  ```
  NodeName=VM-0-5-centos Name=gpu File=/dev/nvidia0
  NodeName=VM-0-5-centos Name=gpu File=/dev/nvidia1
  ```

---

## 8. SLURM 系统服务启动命令

SLURM 编译源码目录中包含 systemd 服务单元文件，需将其复制至系统服务目录并设置权限。使用 `systemctl enable --now` 命令可同时设置 slurmctld 和 slurmd 服务开机自启并立即启动运行。
- 命令: `cd ./slurm-22.05.8//etc/ && chmod 755 *.service && cp *.service /etc/systemd/system`
- 命令: `systemctl enable slurmctld --now`
- 命令: `systemctl enable slurmd --now`

---

## 9. SLURM 基本功能测试命令

SLURM 服务启动后，使用 `sinfo` 查看集群节点与分区状态，使用 `srun -n 2 hostname` 提交一个简单的双进程作业测试系统是否正常调度。此外，`scontrol show node` 命令可用于显示节点的详细状态信息，以确认资源是否被正确识别。
- 测试命令: `sinfo && srun -n 2 hostname`
- 状态查询: `scontrol show node`

---

## 10. SLURM 作业脚本 (run.sh) 参数设置

提交给 SLURM 的作业脚本需包含特定的 SBATCH 参数以申请资源，如作业名、时间限制、输出文件、节点数、CPU 数及 GPU 数。示例脚本申请 1 个节点、8 个 CPU、2 块 GPU，并指定了每个 GPU 的内存限制，同时设置环境变量以支持 Intel MPI 和 CUDA-aware MPI。
- 脚本参数: `#SBATCH --gres=gpu:2`
- 脚本参数: `#SBATCH --cpus-per-task=8`
- 环境变量: `export I_MPI_ROOT=/opt/intel/oneapi/mpi/2021.1.1`
- 环境变量: `export MPICH_GPU_SUPPORT_ENABLED=1`

---

## 11. JDFTx GPU 作业运行命令

在作业脚本中，使用 `srun` 命令启动 JDFTx 的 GPU 版本程序进行计算。示例中调用 `jdftx_gpu`，输入文件为 `Ion_opt.in`，标准输出重定向至 `Ion_opt.out`，程序初始化日志显示识别到了 Tesla P4 GPU 设备。
- 运行命令: `srun jdftx_gpu -i Ion_opt.in > Ion_opt.out`
- 日志示例: `gpuInit: Found compatible cuda device 0 'Tesla P4'`

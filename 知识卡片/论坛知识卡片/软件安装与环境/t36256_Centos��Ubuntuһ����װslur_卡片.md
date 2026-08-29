---
key: t36256
title: Centos��Ubuntuһ����װslurm
url: http://bbs.keinsci.com/thread-36256-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 9
---

# Centos��Ubuntuһ����װslurm — 知识卡片

## 1. SLURM 简化安装方案

为简化配置流程，省略了大部分手动步骤，采用脚本方式进行 SLURM 的快速安装。
- 安装前需下载 SLURM 源码包 slurm-23.02.0.tar.bz2 以及对应的安装脚本 SLURM_installation_centOS.sh。
- 通过自动化脚本处理编译和安装过程，减少人工干预。

---

## 2. SLURM 安装前的版本变量设置

执行安装脚本前，需在终端中设置版本号变量。
- 命令为 `export VER=23.02.0`。
- 该变量用于在后续安装过程中指定 SLURM 的版本号。

---

## 3. SLURM 安装脚本的执行

下载并设置好环境后，在脚本所在目录下运行安装命令。
- 执行命令为 `bash SLURM_installation_centOS.sh`。
- 脚本会自动处理后续的编译和安装步骤。

---

## 4. slurm.conf 配置文件中的 SelectType 设置

安装完成后需修改配置文件，调整节点选择类型。
- 需将 `SelectType` 的值设置为 `select/linear`。
- 此配置用于在节点上选择线性分配的资源管理作业。

---

## 5. slurm.conf 配置文件中的 CPU 选择参数注释

在配置文件中，需将 CPU 相关的选择参数进行注释。
- 操作为将 `SelectTypeParameters=CR_CPU` 前面加上 `#` 符号。
- 注释掉该行表示不采用 CPU 内存绑定（CR_CPU）模式。

---

## 6. slurm.conf 配置文件中的节点定义配置

配置文件中需定义计算节点的名称、硬件资源及状态。
- 配置行示例：`NodeName=localhost.localdomain CPUs=72 RealMemory=61440 Sockets=2 CoresPerSocket=18 ThreadsPerCore=2 State=idle`。
- `NodeName` 为节点名称，`CPUs` 为线程数，`RealMemory` 为内存大小（MB），`Sockets`、`CoresPerSocket`、`ThreadsPerCore` 描述 CPU 物理结构。
- 具体参数值可通过 `lscpu` 命令查看系统 CPU 配置后填写。

---

## 7. slurm.conf 配置文件中的分区设置

配置文件中需设置分区名称、所属节点、默认状态及时间限制。
- 配置行示例：`PartitionName=test Nodes=localhost.localdomain Default=YES MaxTime=INFINITE State=UP`。
- `PartitionName` 定义分区名称，`Nodes` 指定归属于该分区的节点。
- `Default=YES` 设为默认分区，`MaxTime=INFINITE` 表示作业运行时间无限制，`State=UP` 表示分区处于启用状态。

---

## 8. Ubuntu 系统下的 SLURM 自动安装脚本来源

除了 CentOS 的安装脚本，Ubuntu 系统也有对应的自动构建安装资源。
- 资源来源为 NI SP 官网提供的 Automatic SLURM Build & Installation Script。
- 支持平台包括 Rh/Centos 7 和 8（原帖虽提及 Ubuntu 也可用，但链接标题指向 Rh/Centos）。

---

## 9. 安装文件的格式转换注意事项

下载的脚资料件可能存在格式问题，在 Linux 环境下使用前需检查。
- 如果文件是在 Windows 环境下下载或编辑过的，文件格式可能需要转换。
- 建议使用 `dos2unix` 工具对文件进行格式转换，以避免执行错误。

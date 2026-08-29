---
key: t52619
title: RockyLinux10.0����slurm��װ�ű�
url: http://bbs.keinsci.com/thread-52619-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2025
cards: 7
---

# RockyLinux10.0����slurm��װ�ű� — 知识卡片

## 1. SLURM 安装脚本来源与说明

安装 SLURM 可参考 GitHub 上的 Linux 安装脚本。配置参数需参考 SLURM 官方文档及配置文件生成器，脚本内容不涉及 slurmdbd 服务，且经修改后在单节点测试成功。
- 脚本来源：https://github.com/NISP-GmbH/SLURM
- 官方文档：https://slurm.schedmd.com/quickstart_admin.html

---

## 2. slurm.conf 与 cgroup.conf 文件配置

slurm.conf 和 cgroup.conf 的配置需参考官方文档及生成器，并根据实际环境进行修改。配置文件的大小写敏感性和版本兼容性需严格遵守，不同 SLURM 版本要求的配置格式可能不同。
- 配置生成器：https://slurm.schedmd.com/configurator.easy.html
- cgroup 配置参考：https://slurm.schedmd.com/cgroup.conf.html

---

## 3. 集群名称与控制节点参数设置

脚本中的 ClusterName 和 SlurmctldHost 需修改为实际环境的集群名称和控制节点主机名。若管理节点与计算节点为同一台机器，SlurmctldHost 可与管理节点主机名保持一致。
- 参数示例：
  - ClusterName=fate
  - SlurmctldHost=Avalon

---

## 4. 计算节点资源配置参数

NodeName 需修改为计算节点的主机名，并配合设置 CPU 数量、内存大小及物理核心布局。参数修改必须符合 CPU、插槽和线程的实际硬件逻辑，其中 CPUs 数值等于 Sockets、CoresPerSocket 与 ThreadsPerCore 的乘积。
- 参数示例：
  - NodeName=Avalon
  - CPUs=192
  - RealMemory=500000
  - Sockets=2
  - CoresPerSocket=48
  - ThreadsPerCore=2
  - State=UNKNOWN

---

## 5. 分区配置与资源限制

PartitionName 需根据使用偏好设定，Nodes 可指定为 ALL。MaxTime 可设置为 INFINITE 以移除作业时间限制，State 通常设置为 UP 以启用分区。
- 参数示例：
  - PartitionName=saber
  - Nodes=ALL
  - Default=YES
  - MaxTime=INFINITE
  - State=UP

---

## 6. Rocky Linux 10 与 SLURM 25.05.0 版本安装

提供的安装脚本已测试适用于 Rocky Linux 10 系统及 SLURM 25.05.0 版本。脚本执行后会自动处理版本变量 VER，并包含构建和安装 SLURM 的完整流程。
- 执行命令：
  - sudo bash rockylinux.sh

---

## 7. SLURM 版本更新与重装思路

若需安装非脚本默认版本，可手动修改脚本中的 VER 变量为目标版本号。重装时建议删除之前 root 目录下的 rpm_build 文件夹，并通过重新执行脚本的构建部分来完成安装。
- 关键步骤：修改 VER 变量，删除 rpm_build，重新运行脚本

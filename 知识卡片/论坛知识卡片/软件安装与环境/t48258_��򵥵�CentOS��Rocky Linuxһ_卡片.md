---
key: t48258
title: ��򵥵�CentOS��Rocky Linuxһ����װslurm����ϵͳ����
url: http://bbs.keinsci.com/thread-48258-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 18
---

# ��򵥵�CentOS��Rocky Linuxһ����װslurm����ϵͳ���� — 知识卡片

## 1. 适用系统与安装账号

本教程适用于Rocky Linux 8.1、CentOS 7.7及CentOS 7.9版本的Linux系统。此类系统的Slurm安装操作需使用root账户进行。

---

## 2. 安装文件与脚本准备

安装所需的文件包括Slurm源码包`slurm-23.02.8.tar.bz2`和安装脚本`SLURM_installation_rocky.sh`（或`SLURM_installation.sh`）。参考配置文件`slurm_sucsess.conf`提供了成功配置的示例，用户需根据实际环境修改参数。

---

## 3. 设置版本与执行安装

在终端中设置环境变量`VER`指定Slurm版本号（如`export VER=23.02.8`）。在脚本目录下使用bash命令执行安装脚本（如`bash SLURM_installation.sh`）。

---

## 4. 备份与重建slurm.conf

安装完成后需进入`/etc/slurm/`目录操作配置文件。建议先使用`cp slurm.conf slurm.conf.bak`备份原文件，然后删除`/etc/slurm/slurm.conf`，再使用`vi /etc/slurm/slurm.conf`新建配置文件。

---

## 5. slurm.conf核心参数配置

配置文件中需将`ControlMachine`和`NodeName`修改为`slurmd -C`命令输出的节点名称。`CPUs`参数应根据实际物理核心数或线程数填写，且该步骤建议不要在Windows环境下进行配置。

---

## 6. slurm.conf参考模板

以下模板内容可直接写入`slurm.conf`文件，需根据实际情况替换节点名和CPU数：
```
ControlMachine=节点名称
SlurmdUser=root
SelectType=select/cons_res
SelectTypeParameters=CR_CPU
NodeName=节点名称 CPUs= State=UNKNOWN
PartitionName=debug Nodes=节点名称 Default=YES MaxTime=INFINITE State=UP
```

---

## 7. 创建必要运行目录

需在`/var/spool/`下创建`slurm-llnl`目录，并在`/var/run/`下创建`slurm-llnl`目录。创建命令示例：`sudo mkdir slurm-llnl`。

---

## 8. 关闭防火墙与SELinux

安装过程要求关闭防火墙和SELinux。操作命令包括备份SELinux配置、禁用SELinux以及停止并禁用firewalld服务：
```bash
cp /etc/selinux/config /etc/selinux/config.bak
echo SELINUX=disabled >/etc/selinux/config
systemctl stop firewalld
systemctl disable firewalld
```

---

## 9. 服务启动脚本

在用户目录下创建`slurm.sh`脚本并写入以下内容以启动相关服务：
```bash
#!/bin/bash
/usr/sbin/create-munge-key
service munge restart
service slurmctld restart
service slurmd restart
```

---

## 10. 执行服务启动与权限确认

使用`sudo sh slurm.sh`执行启动脚本，执行过程中通常需输入一次sudo密码并确认yes。若服务未启动成功，需检查权限配置。

---

## 11. 配置Hosts文件

需将主机名映射到本地回环地址，命令示例如下：
```bash
echo 127.0.0.1 'cell' >>/etc/hosts
```
`cell`应替换为实际的hostname，且需确保IP地址与`/etc/hosts`文件首行的IP地址一致。

---

## 12. 恢复节点状态

若节点出现down或offline状态，可使用`scontrol`命令尝试恢复。命令示例：`scontrol update NodeName=cell State=RESUME`，其中`cell`需替换为实际节点名。

---

## 13. 验证安装与服务状态

重启系统后，使用`slurmd -V`查看版本信息，`slurmd -C`查看节点配置信息，`sinfo`查看分区信息。通过`systemctl status`检查`slurmdbd`、`slurmctld`和`slurmd`服务状态，正常应显示`active (running)`。

---

## 14. PBS命令兼容包安装

通过安装`slurm-wlm-torque`包，可以使Slurm系统兼容PBS命令。安装命令为：`sudo apt install slurm-wlm-torque`。

---

## 15. VASP作业提交脚本

VASP作业脚本（`job.sh`）示例如下，需注意分区名称需与`slurm.conf`一致：
```bash
#!/bin/bash
#SBATCH -J test
#SBATCH -p debug
#SBATCH -N 1
#SBATCH --ntasks-per-node=8
#SBATCH -o %j.out
#SBATCH -e %j.err
ulimit -s unlimited
mpirun -np 8 vasp_std
```

---

## 16. Siesta作业提交脚本

Siesta作业脚本示例中指定了可执行文件路径和输入文件：
```bash
#!/bin/bash
#SBATCH --job-name=
#SBATCH --output=
#SBATCH -N 1
#SBATCH --ntasks-per-node=4
#SBATCH --time=00:30:00
#SBATCH -p debug
EXEC=/path/to/siesta
mpirun $EXEC input.fdf | tee result
```

---

## 17. Slurm作业管理命令

Slurm系统使用`sbatch job.sh`提交作业，`squeue`查看作业信息，`scancel jobid`取消作业。

---

## 18. PBS兼容命令

在安装兼容包后，可使用`qsub job.sh`提交作业，`qstat`查看作业状态，`qdel jobid`删除作业。

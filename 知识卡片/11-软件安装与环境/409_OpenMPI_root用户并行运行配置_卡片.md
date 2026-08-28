---
id: 409
title: root用户在用openmpi并行计算时避免加--allow-run-as-root的方法
url: http://sobereva.com/409
domain: 软件安装与环境
topic: OpenMPI_root用户并行运行配置
cards: 5
---

# OpenMPI_root用户并行运行配置 — 知识卡片

## 1. OpenMPI 2.0及以上版本的root用户运行限制

OpenMPI从2.0版本开始禁止root用户通过mpirun并行运行程序，系统会提示mpirun has detected an attempt to run as root并拒绝计算。若必须运行，必须在mpirun命令中带上--allow-run-as-root参数。这一设计是为了防止因定义TMPDIR等错误或bug导致操作系统文件系统受到灾难性损坏。

---

## 2. 通过环境变量解决特定程序的root运行限制

对于某些程序（如DIRAC），可以通过在环境变量中设定mpirun命令参数来避免每次手动添加--allow-run-as-root。例如可以设置export DIRAC_MPI_COMMAND="mpirun -np 36 --allow-run-as-root"。对于ORCA等程序，单纯通过.bashrc添加alias mpirun='mpirun --allow-run-as-root'或alias orca='orca --allow-run-as-root'往往无效。

---

## 3. OpenMPI修改源码绕过root检测的具体文件

为了彻底去除OpenMPI对root用户的运行限制，可以通过修改源码实现。在编译openmpi之前，需分别修改openmpi目录下的orte/tools/orte-dvm/orte-dvm.c、orte/tools/orte-submit/orte-submit.c以及orte/tools/orterun/orterun.c这三个文件。

---

## 4. OpenMPI修改源码绕过root检测的操作步骤

在指定的源码文件中搜索if (0 == geteuid，将该段落一直删除到对应的if结束符号}为止。完成修改后重新编译OpenMPI，程序就不会因为检测到root用户且缺少--allow-run-as-root参数而报错退出。对于OpenMPI 3.x版本，orte/tools/orte-submit/orte-submit.c文件应修改为orte/orted/orted_submit.c。

---

## 5. OpenMPI 4.0及以上版本允许root运行的环境变量

从OpenMPI 4.0版本开始，无需修改源代码即可允许root用户使用mpirun。只需定义两个环境变量：export OMPI_ALLOW_RUN_AS_ROOT=1 和 export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1。

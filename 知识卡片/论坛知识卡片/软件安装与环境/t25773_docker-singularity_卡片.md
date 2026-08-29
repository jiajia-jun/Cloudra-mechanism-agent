---
key: t25773
title: docker-singularity������װ��������ֲ��cp2k
url: http://bbs.keinsci.com/thread-25773-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 18
---

# docker-singularity������װ��������ֲ��cp2k — 知识卡片

## 1. CP2K编译与Docker安装概述

CP2K安装过程耗时且容易出错，相比VASP和QE具有更高的功能丰富度和计算速度。使用官方Dockerfile进行安装可以确保获得与官方完全一致的环境，生成的镜像可直接复制到不同指令集的系统上使用，从而保证了速度和稳定性。相比源码编译，采用基于Docker的方式虽然需要等待镜像构建，但成功率可达100%且能避免繁琐的依赖配置。

---

## 2. Docker安装命令

在Linux系统（以CentOS 7.6为例）下，安装Docker可执行以下命令。首先使用阿里云镜像安装Docker，然后设置开机自启并启动服务。
- curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
- systemctl enable docker
- systemctl start docker
- systemctl restart docker

---

## 3. Singularity安装命令

在Linux系统下，安装Singularity需要先安装epel-release源，随后直接安装singularity软件包。
- yum install -y epel-release
- yum install -y singularity

---

## 4. 构建CP2K Toolchain Docker镜像

下载并解压CP2K源码（如cp2k-8.2.tar.bz2）后，进入toolchain目录，使用docker build命令构建名为cp2k/toolchain的镜像。注意命令末尾的点(.)表示使用当前目录的Dockerfile。
- tar jxf cp2k-8.2.tar.bz2
- cd cp2k-8.2/tools/toolchain
- docker build -t cp2k/toolchain .

---

## 5. CP2K编译的后续步骤提示

Docker镜像构建完成后，屏幕会输出后续操作指引。需将toolchain生成的arch文件复制到cp2k/arch目录，并source setup脚本，最后执行make命令编译指定版本。
- cp /opt/cp2k-toolchain/install/arch/* to the cp2k/arch/ directory
- source /opt/cp2k-toolchain/install/setup
- cd cp2k/
- make -j 48 ARCH=local VERSION="ssmp sdbg psmp pdbg"

---

## 6. 查看Docker镜像信息

使用`docker image ls`命令可以查看已构建的镜像列表。构建成功的cp2k/toolchain镜像大小约为5.19GB，基础镜像为Ubuntu 20.04。
- $ docker image ls

---

## 7. Docker镜像保存为Tar文件

为了迁移或转换格式，需要将Docker镜像保存为tar文件。使用`docker save`命令，并指定镜像ID（需通过docker image ls查询）和输出文件名。
- docker save 68e78acf2465 -o cp2k82.tar

---

## 8. Docker镜像转换为Singularity镜像

使用Singularity将docker镜像转换为sif文件时，建议使用--tmpdir参数指定临时文件目录（如/home），以避免因系统默认/tmp目录空间不足导致的报错。
- singularity build --tmpdir /home cp2k82.sif docker-archive://cp2k82.tar

---

## 9. 转换为Singularity Sandbox目录

为了修改容器内的内容，需将sif文件转换为可读写的sandbox目录。转换过程同样建议指定临时文件目录。
- singularity build --sandbox --tmpdir /home cp2k82/ cp2k82.sif

---

## 10. 进入Sandbox容器环境

使用`singularity shell -w`命令以可写模式进入容器环境。进入后，命令行提示符将从[root@master /opt]#变为Singularity>，表示已处于容器内部的虚拟系统中。
- singularity shell -w cp2k82

---

## 11. 在Sandbox内编译CP2K

进入容器后，需先更新apt源并安装vim等工具。随后将CP2K源码包复制进容器，解压并利用之前toolchain生成的环境进行编译。
- apt-get update
- apt-get install -y vim
- cd /opt
- tar jxf cp2k-8.2.tar.bz2
- cp /opt/cp2k-toolchain/install/arch/* /opt/cp2k-8.2/arch/
- source /opt/cp2k-toolchain/install/setup
- cd /opt/cp2k-8.2
- make -j 24 ARCH=local VERSION="psmp"

---

## 12. CP2K测试命令

编译完成后，执行make test命令进行测试。若测试通过，应显示所有测试用例均为CORRECT，无FAILED或WRONG项。
- make -j 24 ARCH=local VERSION="psmp" test

---

## 13. 配置容器环境变量

为了在容器启动时自动加载CP2K环境，需修改容器内的环境配置文件。在/.singularity.d/env/91-environment.sh文件中添加toolchain的setup脚本、可执行文件路径及数据目录路径。
- vi /.singularity.d/env/91-environment.sh
- source /opt/cp2k-toolchain/install/setup
- export PATH=$PATH:/opt/cp2k-8.2/exe/local
- export CP2K_DATA_DIR=/opt/cp2k-8.2/data

---

## 14. 封装Sandbox为SIF文件

修改完Sandbox目录后，可将其重新打包为SIF文件，以便分发到其他计算节点使用。打包时同样建议指定临时目录。
- singularity build --tmpdir /home cp2k82-1.sif cp2k82/

---

## 15. 编写CP2K运行脚本

在宿主机上编写Shell脚本调用Singularity容器中的CP2K。脚本需加载MPI环境，设置CPU核心数，并使用mpirun启动容器内的cp2k.popt执行计算。
- #!/bin/sh
- export EXE="singularity exec /opt/cp2k82"
- source /opt/intel2018/parallel_studio_xe_2018/psxevars.sh
- export cpu_cores=24
- ulimit -s unlimited
- mpirun -np ${cpu_cores} ${EXE} cp2k.popt cp2k.inp 1>cp2k.out 2>cp2k.err

---

## 16. CP2K-8.2版本已知Bug与修复

CP2K-8.2版本存在一个bug，需在输入文件的&GLOBAL部分添加PREFERRED_DIAG_LIBRARY SL选项以解决对比集群时的错误。
&GLOBAL
...
PREFERRED_DIAG_LIBRARY SL
&END GLOBAL

---

## 17. 编译优化与CPU指令集警告

如果在本地编译toolchain和CP2K时未匹配宿主机的CPU指令集（如AVX2或AVX512），运行时cp2k.out可能会显示"this binary cannot exploit all extensions of this CPU model"的警告。这意味着高频迭代计算的速度未达到最优，相比针对特定指令集优化的版本，性能可能损失12%-19%。

---

## 18. 计算性能对比

在特定体系下（较大体系使用OT算法），使用资料方法构建的CP2K比自带的Intel-CP2K版本速度快8%-9.5%。对于小体系，计算速度差异可能更为明显（每步迭代时间分别为4.7s vs 2.1s等）。

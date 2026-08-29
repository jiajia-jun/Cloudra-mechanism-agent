---
key: b688
title: Multiwfn在Linux下安装的中文说明
url: http://sobereva.com/688
domain: 软件安装与环境
source: blog
year: 2023
cards: 12
---

# Multiwfn在Linux下安装的中文说明 — 知识卡片

## 1. Multiwfn Linux版本分类

Multiwfn的Linux版分为普通版和noGUI版，普通版文件名包含Multiwfn_[版本号]_bin_Linux.zip，需要motif图形库提供的libXm.so.4文件支持，安装该库通常需要root权限。noGUI版文件名包含noGUI字样，启动时不需要motif库，适合无法获取root权限的普通用户在服务器上安装，但无法使用任何图形相关功能，如显示图形界面、绘制曲线图/等值面图及可视化拓扑分析结果。

---

## 2. Redhat系Linux安装motif库

在Redhat、CentOS、Rocky Linux、Fedora等Redhat系操作系统上，若可访问互联网，输入yum install motif命令即可安装motif库，执行此命令需要root权限。如果是Rocky Linux或相似系统且版本大于等于10，需先执行dnf install epel-release安装扩展程序源。若无法访问互联网，可下载x86_64架构的motif库rpm包（如motif-2.3.4-1.x86_64_0.rpm），使用rpm -i motif-2.3.4-1.x86_64_0.rpm命令手动安装，但可能遇到依赖库缺失的问题。

---

## 3. Debian系Linux安装motif库

在Ubuntu等Debian系Linux上，连接互联网的情况下，使用sudo apt-get install libxm4 libgl1命令可安装motif及相关libgl1库。

---

## 4. 检查SysV共享内存段

运行cat /proc/sys/kernel/shmmax命令可检查SysV共享内存段的值（单位为字节），该值过小（如32MB）会导致Multiwfn在处理高耗内存分析或载入大波函数文件时崩溃。若需增大该值，需在/etc/sysctl.conf文件中添加kernel.shmmax = 2000000000并重启系统，将上限提升至约2GB，修改资料件需要root权限。

---

## 5. 解压Multiwfn程序包

从官网下载包含bin和Linux字样的压缩包后，使用unzip [文件名]命令将其解压到当前目录，假设解压后的目录为/home/sob/Multiwfn_[版本号]_bin_Linux/，该目录下应包含程序文件。

---

## 6. 配置~/.bashrc文件

在用户主目录下的.bashrc文件末尾添加ulimit -s unlimited、export OMP_STACKSIZE=200M、export Multiwfnpath=/home/sob/Multiwfn_[版本号]_bin_Linux以及export PATH=$PATH:/home/sob/Multiwfn_[版本号]_bin_Linux。ulimit -s unlimited用于解除操作系统对堆栈内存使用的限制，防止Segmentation fault报错；export OMP_STACKSIZE=200M设定每个OpenMP线程的堆栈内存上限为200MB，并行核数乘以该值必须显著小于物理内存可用量。

---

## 7. 设置环境变量的目的

定义Multiwfnpath环境变量是为了让Multiwfn在非程序目录下启动时能找到settings.ini配置文件；将Multiwfn所在目录加入PATH环境变量，使得在任意目录下均可直接输入程序名启动Multiwfn，无需输入完整路径。

---

## 8. 增加可执行权限

对于普通版，在终端运行chmod +x /home/sob/Multiwfn_[版本号]_bin_Linux/Multiwfn增加可执行权限；对于noGUI版，运行chmod +x /home/sob/Multiwfn_[版本号]_bin_Linux/Multiwfn_noGUI。

---

## 9. 配置settings.ini中的线程数

编辑Multiwfn目录下的settings.ini文件，搜索nthreads并将其数值修改为计算时使用的并行核数，通常设置为CPU的物理核心数。

---

## 10. 配置settings.ini中的外部程序路径

settings.ini中的formchkpath若设为Gaussian目录下formchk程序的路径，Multiwfn可直接载入Gaussian的chk文件并自动转换；orca_2mklpath若设为ORCA目录下orca_2mkl的路径，可直接载入ORCA的gbw文件并自动转换；gaupath和orcapath若分别设为Gaussian和ORCA可执行文件的路径，可使Multiwfn的相关功能自动调用外部程序进行计算。

---

## 11. 测试Multiwfn安装

退出终端并重新进入后，直接输入Multiwfn（普通版）或Multiwfn_noGUI（noGUI版）应能启动程序。载入程序包自带的examples/CH3CONH2.fch文件，依次输入9和8，若屏幕输出拉普拉斯键级，则表明安装测试成功。

---

## 12. 纯文本界面连接服务器的显示设置

若通过纯文本界面连接远程Linux服务器运行Multiwfn普通版，发现启动时短暂卡住，可在~/.bashrc文件末尾加入export DISPLAY=":0"予以解决。

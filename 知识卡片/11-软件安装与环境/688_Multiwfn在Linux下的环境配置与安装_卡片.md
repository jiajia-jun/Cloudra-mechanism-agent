---
id: 688
title: Multiwfn在Linux下安装的中文说明
url: http://sobereva.com/688
domain: 软件安装与环境
topic: Multiwfn在Linux下的环境配置与安装
cards: 14
---
## 1. Multiwfn普通版与noGUI版的区别

Multiwfn的Linux版分为普通版和noGUI版，普通版具备完整功能但运行依赖motif图形库提供的libXm.so.4文件，安装该库需要root权限。noGUI版不需要motif库因此适合无root权限的普通用户，但缺点是无法使用任何图形相关功能。高性能Linux服务器上运行高耗时任务通常不直接涉及图像显示，因此noGUI版足以应对。

---

## 2. Redhat系系统安装motif库

对于Redhat系操作系统，若能访问Internet，在终端输入`yum install motif`命令即可安装motif库，这需要root权限。Rocky Linux或相似系统 >=10版的用户需先执行`dnf install epel-release`安装扩展程序源。若无法访问Internet，可从官网下载rpm包后用`rpm -i motif-2.3.4-1.x86_64_0.rpm`命令手动安装。

---

## 3. 检查系统是否已安装motif库

运行`rpm -qa|grep motif`命令可以检查当前系统是否已经安装了motif库，如果找到了结果则无需重复安装。

---

## 4. Debian系系统安装motif库

Debian系Linux如Ubuntu的用户，在连接Internet的情况下可以用`sudo apt-get install libxm4 libgl1`命令安装motif和相关的libgl1库。

---

## 5. 检查SysV共享内存段配置

Rocky Linux、CentOS用户无需此步骤，其他系统需运行`cat /proc/sys/kernel/shmmax`检查SysV共享内存段的值（字节）。若默认值过小（如32MB）会导致Multiwfn崩溃，可在/etc/sysctl.conf里加入`kernel.shmmax = 2000000000`然后重启系统以将上限提升到约2GB，修改该资料件需要root权限。
---

## 6. 解压Multiwfn程序包

从官网下载带有bin和Linux字样的压缩包，使用`unzip [文件名]`命令将其解压到当前目录，假设解压后的目录为`/home/sob/Multiwfn_[版本号]_bin_Linux/`。

---

## 7. 配置.bashrc文件设置环境变量

在用户主目录下的.bashrc文件末尾添加以下内容：
`ulimit -s unlimited`
`export OMP_STACKSIZE=200M`
`export Multiwfnpath=/home/sob/Multiwfn_[版本号]_bin_Linux`
`export PATH=$PATH:/home/sob/Multiwfn_[版本号]_bin_Linux`

---

## 8. 设置ulimit和OMP_STACKSIZE的意义

`ulimit -s unlimited`用于去除操作系统对堆栈内存使用的限制，防止处理大波函数时出现Segmentation fault。`export OMP_STACKSIZE=200M`将每个线程的堆栈内存上限设为200MB，若设得太小会导致并行计算崩溃，且并行核数乘以该值必须显著小于物理内存可用量。

---

## 9. 设置Multiwfnpath和PATH的意义

Multiwfn启动时先在当前目录寻找settings.ini，若找不到则在Multiwfnpath环境变量指定的目录寻找。将Multiwfn目录加入PATH环境变量是为了在任意目录下直接输入程序名即可启动，无需输入完整路径。

---

## 10. 增加Multiwfn可执行权限

对于普通版，在终端运行`chmod +x /home/sob/Multiwfn_[版本号]_bin_Linux/Multiwfn`赋予可执行权限。如果是noGUI版，则将命令中的Multiwfn替换为Multiwfn_noGUI。

---

## 11. 配置settings.ini中的并行核数

编辑Multiwfn目录下的settings.ini，搜索nthreads，将其数值改为计算时要用的并行核数，通常设为CPU的物理核心数。

---

## 12. 配置settings.ini中的外部程序路径

settings.ini中的formchkpath设为Gaussian的formchk程序路径可支持直接载入chk文件。orca_2mklpath设为ORCA的orca_2mkl路径可支持直接载入gbw文件。gaupath和orcapath分别设为Gaussian和ORCA的可执行文件路径，可使Multiwfn自动调用这些程序进行计算。

---

## 13. 运行Multiwfn测试

退出终端并重新进入后，直接输入Multiwfn或Multiwfn_noGUI启动程序。载入examples目录下的CH3CONH2.fch文件，依次输入9和8，屏幕应输出拉普拉斯键级。

---

## 14. 远程文本界面卡顿的解决方案

通过纯文本界面连接远程Linux服务器运行普通版Multiwfn时，若启动短暂卡住，可在~/.bashrc文件末尾加入`export DISPLAY=":0"`来避免。

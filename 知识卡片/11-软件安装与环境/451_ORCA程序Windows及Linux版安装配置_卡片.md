---
id: 451
title: 量子化学程序ORCA的安装方法
url: http://sobereva.com/451
domain: 软件安装与环境
topic: ORCA程序Windows及Linux版安装配置
cards: 1
---

# ORCA程序Windows及Linux版安装配置 — 知识卡片

## 1. ORCA程序简介与官网获取

ORCA是一款对学术用户免费但不开源的量子化学程序，官方网址为https://orcaforum.kofo.mpg.de，用户需注册并登录后在页面点击Download按钮下载可执行程序和手册。目前本文对应的版本为ORCA 6。
- ORCA官网与论坛在一起，若官网打不开或验证码无法显示需通过特殊方式上网。

## ORCA简单测试输入文件
为了测试ORCA安装后是否能正常运行，可将以下内容复制到如test.inp文件中作为输入文件，该任务要求4核并行：
! BLYP def2-SVP pal4
 * xyz 0 1
  C 0.00000000 0.00000000 -0.56221066
  H 0.00000000 -0.92444767 -1.10110537
  H -0.00000000 0.92444767 -1.10110537
  O 0.00000000 0.00000000 0.69618930
 *

## ORCA Windows版系统要求与MSMPI依赖
ORCA的Windows版仅有64位版本，32位Windows系统无法使用，需安装64位系统或通过虚拟机运行Linux版。ORCA在Windows下依赖Microsoft MPI (MSMPI)库进行并行运算，ORCA 6可搭配MSMPI 10.0运行。
- 用户需下载并安装MSMPI 10.0。

## ORCA Windows版安装步骤
下载“ORCA [版本号], Windows, 64bit, Installer”页面里的压缩包并解压，运行Orca[版本号].Win64.exe启动安装程序，选择Complete方式进行安装。对于ORCA 6.0.0，安装完成后会占用13GB以上硬盘空间。
- 安装需选择Complete模式。

## ORCA Windows版并行运行测试方法
将测试文件放入某目录，进入Windows cmd界面，输入`D:\study\ORCA_6.0.0\orca H2CO.inp > H2CO.out`（路径需根据实际情况修改）来执行输入文件并将输出重定向。若输出信息正常且最后显示****ORCA TERMINATED NORMALLY****，说明安装成功；若输出信息混乱交错，说明并行进程未协同工作。
- Windows下并行计算输入必须使用ORCA的绝对路径。

## ORCA Windows版autoCI模块安装
若需使用FIC-MRCI、CCSDT等只有autoCI模块支持的后HF和多参考计算功能，需在基础安装之上，下载官方论坛“ORCA [版本号], Windows, 64bit, autoci / parallel part”页面的压缩包。将压缩包解压到ORCA安装目录下，安装autoCI模块后ORCA 6目录将达到30GB以上。
- autoCI模块的可执行文件名带有autoci_字样。

## 使用cmder便捷运行ORCA Windows版
下载cmder Full版并解压，在命令行输入`Cmder.exe /REGISTER ALL`注册右键菜单。在Settings中将General页面设为{bash::bash as Admin}，并在config\user_profile.sh中添加别名如`alias oo='D:/study/orca600/orca'`。之后可在任意目录右键进入cmder，使用`oo Roselia.inp |tee RAS.out`运行ORCA。
- cmder提供了类似Linux Bash的环境，包含awk、vi等工具。

## ORCA Linux版OpenMPI编译与安装
ORCA在Linux下通过OpenMPI实现并行，需先编译OpenMPI库（如4.1.6版本）。解压源码包后，进入目录执行`./configure --prefix=/sob/openmpi416 --disable-builtin-atomics`和`make all install -j`将其安装到指定目录。
- 编译前必须安装gcc和gcc-gfortran编译器，否则ORCA无法正常并行。

## Linux下OpenMPI环境变量配置
对于Bash shell系统（如CentOS、Rocky Linux），需在用户目录下的.bashrc文件末尾添加环境变量：
export PATH=$PATH:/sob/openmpi416/bin
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/openmpi416/lib
保存后重新打开终端，运行`mpiexec -V`若显示版本号则说明安装成功。

## ORCA Linux版安装与路径配置
下载对应CPU指令集（如avx2）的ORCA Linux包并使用tar命令解压。在.bashrc文件中添加ORCA目录路径：
export PATH=$PATH:/sob/orca600
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/orca600
重启终端生效后，可使用绝对路径`/sob/orca600/orca test.inp > test.out`运行程序。

## Linux下ORCA命令别名设置
为避免每次运行都输入绝对路径，可在.bashrc文件中添加`alias orca='/sob/orca600/orca'`，之后即可直接使用`orca test.inp > test.out`命令运行程序。
- 别名需在重新登录终端后生效。

## Linux下与系统自带orca冲突的解决
部分Linux系统（如CentOS）自带名为orca的屏幕阅读器程序，会与量子化学程序ORCA冲突。应使用`rpm -e orca`命令卸载系统自带的orca程序。
- 卸载后可直接使用ORCA命令。

## Linux下root用户运行OpenMPI的配置
若在root用户下使用ORCA，OpenMPI要求每次执行命令必须带有-allow-run-as-root选项。可在.bashrc中加入以下两行环境变量来避免手动添加该选项：
export OMPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1

## Linux下多MPI库版本冲突的处理
若系统中存在其他MPI库或OpenMPI版本，且`which mpiexec`指向的路径优先级高于新装的OpenMPI，ORCA可能无法正常并行。解决方法包括：重命名或注释掉旧MPI库的配置，或将新装OpenMPI的路径（如/sob/openmpi416/bin:$PATH）置于环境变量的最前面以提升优先级。
- 确保OpenMPI路径在PATH和LD_LIBRARY_PATH中优先于旧版本。

## ORCA输出文件转换为Molden格式
使用ORCA自带的orca_2mkl工具可以将计算产生的.gbw文件转化为Multiwfn可识别的.molden.input文件，命令为`orca_2mkl xxx -molden`。若在Multiwfn的settings.ini中设置orca_2mklpath参数，Multiwfn可直接载入.gbw文件。
- orca_2mkl功能类似于Gaussian的formchk。

## Windows下ORCA输出文件的编码问题
在Windows下运行ORCA时，不应使用PowerShell进行输出重定向，因为其产生的文件默认为Unicode编码，Multiwfn和OfakeG等程序无法读取。应使用cmd或cmder来生成正确编码的输出文件。
- PowerShell 7已改变此行为。

## Multiwfn结合ORCA进行波函数分析与绘图
波函数分析程序Multiwfn可载入ORCA的输出文件或转换后的molden文件进行波函数分析和轨道图形查看。Multiwfn还可基于ORCA输出文件绘制红外、拉曼、UV-Vis、ECD、VCD和ROA等光谱图。
- 相关教程见《详谈Multiwfn产生ORCA量子化学程序的输入文件的功能》及《使用Multiwfn绘制红外、拉曼、UV-Vis、ECD、VCD和ROA光谱图》。

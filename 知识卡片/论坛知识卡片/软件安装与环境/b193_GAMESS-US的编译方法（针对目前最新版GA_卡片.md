---
key: b193
title: GAMESS-US的编译方法（针对目前最新版GAMESS-US的情况重写了此文）
url: http://sobereva.com/193
domain: 软件安装与环境
source: blog
year: 2024
cards: 19
---

# GAMESS-US的编译方法（针对目前最新版GAMESS-US的情况重写了此文） — 知识卡片

## 1. GAMESS-US编译环境与版本要求

资料以GAMESS-US 2024-R2 Patch 1版本为例介绍编译方法。编译环境为RockyLinux 9.0操作系统，使用Intel oneAPI HPC 2024.0提供的Intel Fortran编译器和Intel oneAPI base提供的MKL数学库。程序建议安装在/sob/gamess目录下。

---

## 2. Intel MKL数学库的重要性

编译GAMESS-US时必须使用Intel MKL数学库。若仅使用程序自带的子程序，根据编译脚本中的说法，MP2计算速度会慢两倍，CCSD(T)计算速度会慢5倍。即便使用AMD CPU，也可以使用Intel的Fortran编译器和MKL数学库。

---

## 3. GAMESS-US程序下载与解压

在官网注册后选择"64 bit x86_64 under Linux using Intel OneAPI compilers"类型进行下载。将下载的压缩包放入/sob目录下，使用命令`tar -xf [压缩包名]`进行解压，得到/sob/gamess目录。

---

## 4. GAMESS-US 2024版配置文件生成参数

在/sob/gamess目录下运行`./config`命令，依次输入：linux64（操作系统类型）、oneapi-ifort（编译器）、mkl（数学库类型）、/opt/intel/oneapi/mkl/latest（MKL路径）、sockets（DDI类型）。后续编译选项全部选择no以跳过附加组件编译。

---

## 5. GAMESS-US 2024版MKL路径设置注意事项

在配置过程中设置MKL路径时，应输入`/opt/intel/oneapi/mkl/latest`。若输入`/opt/intel/oneapi/mkl/2024.0`等具体版本号，脚本可能无法识别，属于脚本的bug。

---

## 6. GAMESS-US 2024版编译命令

生成配置文件install.info后，在当前目录运行`make -j 64`（使用64核并行编译）进行编译。编译完成后会在/sob/gamess目录下生成可执行文件gamess.00.x。

---

## 7. GAMESS-US 2024版运行脚本rungms配置

修改/sob/gamess/rungms文件，在`set TARGET=sockets`下方将路径修改为实际安装路径：`set SCR=/sob/gamess/scr`、`set USERSCR=/sob/gamess/scr`、`set GMSPATH=/sob/gamess`。同时将NCPUS后的数值修改为默认CPU核心数。

---

## 8. 自动清空GAMESS-US临时目录

在/sob/gamess/rungms文件开头的`#!/bin/csh`下方加入`rm -f /sob/gamess/scr/*`。此操作使得每次调用rungms时自动清空临时目录，避免临时文件堆积。

---

## 9. GAMESS-US环境变量设置与运行

在用户主目录下的.bashrc文件中加入`export PATH=$PATH:/sob/gamess`，使得任意目录下均可使用rungms命令。重新进入终端后，可使用`rungms test.inp |tee test.out`运行计算。

---

## 10. GAMESS-US并行运行命令格式

使用`rungms test.inp 00 64`可以指定使用64个核心并行运行，其中00为可执行文件的版本号。若不指定核心数，则使用rungms文件中NCPUS变量设置的默认值。

---

## 11. GAMESS-US全面测试脚本配置

修改/sob/gamess/runall文件，将第一处`si.msg.chem.iastate.edu`改为本机名。将`./rungms exam$NUM $VERNO 1`中的1改为测试时使用的并行核数。

---

## 12. GAMESS-US全面测试执行与验证

进入/sob/gamess目录运行`./runall 00`进行测试，直接按回车键开始。测试会产生40多个log文件，将这些文件拷贝到/sob/gamess/tests/standard目录下，运行`./checktst`脚本与标准结果对照。

---

## 13. GAMESS-US测试结果判断标准

运行checktst脚本后，只要大部分任务通过测试即可。少部分任务未通过通常是由于测试文件与当前版本GAMESS-US特征不兼容，或者某些任务只能串行运行所致。测试前应确保/sob/gamess/scr目录已清空。

---

## 14. GAMESS-US旧版本编译环境示例

旧版本（如2013-May、2014-Dec、2016-Aug）编译环境示例包括：RHEL6-U1 64bit系统，ifort 12.1.0编译器及MKL数学库（安装在默认路径），程序安装在/sob/gamess。2016-Aug版配置时需输入proceed而非skip。

---

## 15. GAMESS-US旧版本配置文件生成参数

运行./config后依次输入：linux64、ifort、12（MKL版本号）、mkl、/opt/intel/mkl、skip、sockets。后续选项选择no，尤其是不编译用于GPU加速的LIBCCHEM。

---

## 16. GAMESS-US旧版本DDI编译步骤

进入ddi目录，运行`./compddi`编译DDI。如果CPU核心数超过32个，需在执行compddi前修改脚本中第一次出现的`set MAXCPUS=`后的数值为当前CPU核心数。将生成的ddikick.x移动到上一级目录/sob/gamess。

---

## 17. GAMESS-US旧版本主程序编译

在/sob/gamess目录下运行`./compall`进行编译，耗时约十几分钟。编译完成后objects目录下会生成近300个文件，且/sob/gamess下产生gamess.00.x可执行文件。若未产生，需手动执行`./lked gamess 00`。

---

## 18. GAMESS-US旧版本主机名配置

为了支持单机多核计算，在rungms文件的`switch (`hostname`)`行下面需插入配置内容。其中xxx需替换为本机名（即运行hostname命令显示的内容），并设置NNODES=1及HOSTLIST。

---

## 19. GAMESS-US旧版本源文件单独编译

若修改了某个源程序文件（如int2a.src）并希望其生效，无需重新编译整个程序。可运行`./comp int2a`编译该文件，然后运行`./lked gamess 00`进行连接。

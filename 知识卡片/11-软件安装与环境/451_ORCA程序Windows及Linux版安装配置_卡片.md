---
id: 451
title: 量子化学程序ORCA的安装方法
url: http://sobereva.com/451
domain: 软件安装与环境
topic: ORCA程序Windows及Linux版安装配置
cards: 19
---
## 1. ORCA程序版本与适用平台

ORCA是一款对学术用户免费但不开源的量子化学程序，目前对应ORCA 6版本。ORCA Windows版仅有64bit版本，且虽然存在Mac版但因极其小众而不提供安装方法。ORCA官网与论坛地址为https://orcaforum.kofo.mpg.de，注册登录后点击页面上方Download按钮即可下载可执行程序和手册。

## 2. ORCA测试输入文件示例

为测试安装后ORCA是否能正常运行，可将以下内容复制为test.inp作为输入文件，此任务要求4核并行：
! BLYP def2-SVP pal4
 * xyz 0 1
  C 0.00000000 0.00000000 -0.56221066
  H 0.00000000 -0.92444767 -1.10110537
  H -0.00000000 0.92444767 -1.10110537
  O 0.00000000 0.00000000 0.69618930
 *

---

## 3. ORCA Windows版安装要求

ORCA Windows版需要64bit系统，32bit Windows无法直接运行ORCA Windows版。ORCA基于MPI方式并行，Windows下依赖Microsoft MPI (MSMPI)库运行，ORCA 6需搭配MSMPI 10.0，用户需自行下载并安装MSMPI 10.0。

---

## 4. ORCA Windows版安装步骤

进入ORCA论坛下载“ORCA [版本号], Windows, 64bit, Installer”压缩包，解压后运行Orca[版本号].Win64.exe安装程序。安装时选择Complete方式，对于ORCA 6.0.0安装完成后将占用13多GB硬盘空间。

---

## 5. ORCA Windows版运行测试与验证

将测试文件拷贝到某处，进入Windows cmd界面，输入绝对路径命令执行测试，例如D:\study\ORCA_6.0.0\orca H2CO.inp > H2CO.out。输入文件要求并行计算时必须使用绝对路径，若输出信息正常且最后显示****ORCA TERMINATED NORMALLY****则说明安装成功；若输出信息混乱交错则说明并行未正常协同工作。

---

## 6. ORCA Windows版autoCI模块安装

ORCA中部分后HF和多参考计算功能（如FIC-MRCI、CCSDT等）需安装autoCI模块。在完成基础安装后，需进入官方论坛下载页面中的“ORCA [版本号], Windows, 64bit, autoci / parallel part”页面，下载并解压压缩包到ORCA安装目录下。安装autoCI模块后，ORCA 6目录大小将达到30多GB。

---

## 7. Windows下使用cmder便捷运行ORCA

下载Full版cmder并解压，在命令行输入Cmder.exe /REGISTER ALL实现右键菜单进入cmder。在Settings里选择{bash::bash as Admin}，并在config\user_profile.sh中添加别名如alias oo='D:/study/orca600/orca'。配置后可使用oo Roselia.inp |tee RAS.out形式调用ORCA，同时显示并保存输出信息。

---

## 8. ORCA Linux版依赖OpenMPI安装

ORCA在Linux下通过OpenMPI实现并行，需根据ORCA文件包名中注明的版本（如openmpi416代表4.1.6）下载并编译OpenMPI源码。安装前需确保系统有gcc和gcc-gfortran编译器（如CentOS下用yum install gcc-gfortran安装），否则OpenMPI虽能编译但会导致ORCA无法正常并行。

---

## 9. OpenMPI编译配置命令

解压OpenMPI源码包后，进入目录执行以下命令将其安装到/sob/openmpi416目录：
 ./configure --prefix=/sob/openmpi416 --disable-builtin-atomics
 make all install -j
 注：使用-j是为了并行编译降低耗时，若编译报错需去掉-j重试。

---

## 10. Linux环境变量配置与OpenMPI验证

对于Bash shell用户，在~/.bashrc文件末尾添加以下两行并保存：
 export PATH=$PATH:/sob/openmpi416/bin
 export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/openmpi416/lib
 重新打开终端后运行mpiexec -V，若正常显示版本号则说明OpenMPI安装成功。

---

## 11. ORCA Linux版安装解压与CPU指令集要求

使用tar -xf命令解压下载的ORCA包，例如orca_6_0_0_linux_x86-64_avx2_shared_openmpi416.tar。文件名中的avx2代表CPU必须支持AVX2指令集，老款CPU需下载不带avx2字样的包，主流CPU通常支持AVX2。

---

## 12. ORCA Linux版环境变量配置

假设ORCA解压目录为/sob/orca600/，需在.bashrc文件中添加以下内容：
 export PATH=$PATH:/sob/orca600
 export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/orca600
 重新进入终端后即可运行ORCA，并行运行时必须写明绝对路径如/sob/orca600/orca test.inp > test.out。

---

## 13. Linux下设置ORCA命令别名

为避免每次输入绝对路径，可在.bashrc文件中添加alias orca='/sob/orca600/orca'。保存后重新进入终端，即可直接使用orca命令代替绝对路径来运行程序。

---

## 14. Linux系统自带orca程序冲突处理

部分Linux系统（如CentOS）自带名为orca的屏幕阅读器程序，直接输入orca会启动该程序而非量子化学软件ORCA。应当使用rpm -e orca命令将系统自带的orca程序卸载掉。

---

## 15. root用户运行OpenMPI的配置

若在root用户下使用ORCA，OpenMPI要求每次执行命令必须带-allow-run-as-root选项。可在.bashrc中加入以下两行来避免每次手动添加：
 export OMPI_ALLOW_RUN_AS_ROOT=1
 export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1

---

## 16. 多MPI库环境下的路径优先级处理

若系统中存在其它MPI库，且which mpiexec指向非新装OpenMPI的目录，需调整环境变量优先级。如果其它MPI装在自定义目录，可修改其目录名或注释掉.bashrc中的相关配置；如果装在/usr/local等默认路径，需将.bashrc中的路径顺序改为/sob/openmpi416/bin:$PATH和/sob/openmpi416/lib:$LD_LIBRARY_PATH，确保新装库被优先使用。

---

## 17. ORCA输出文件转换为Multiwfn输入格式

使用ORCA自带的orca_2mkl工具，运行orca_2mkl xxx -molden命令，可将ORCA计算产生的xxx.gbw文件转化为xxx.molden.input文件。该文件可直接作为波函数分析程序Multiwfn的输入文件用于波函数分析和观看轨道图形。

---

## 18. Multiwfn直接读取gbw文件的配置

将Multiwfn目录下settings.ini里的orca_2mklpath参数设为当前机器中orca_2mkl可执行文件的实际路径，Multiwfn就可以直接载入ORCA产生的gbw文件，无需手动转换。

---

## 19. Windows下ORCA输出文件的编码问题

在Windows下运行ORCA进行计算以便后续用Multiwfn绘制光谱时，不要使用PowerShell。因为PowerShell通过重定向产生的输出文件默认是Unicode编码，Multiwfn和OfakeG等工具无法读取；应使用cmd或cmder以避免编码问题。

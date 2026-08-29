---
id: 193
title: GAMESS-US的编译方法
domain: 其他量化软件
topic: GAMESS-US_编译安装与运行环境配置
cards: 23
---

## 1. GAMESS-US 2024-R2 Patch 1编译环境配置
介绍的GAMESS-US程序编译方法版本为2024-R2 Patch 1。编译环境为RockyLinux 9.0系统、双路AMD EPYC 7R32 CPU、root用户，安装目录为/sob/gamess。编译器使用Intel oneAPI HPC 2024.0提供的Intel Fortran和Intel oneAPI base提供的MKL数学库，安装顺序为先装base再装HPC。

---

## 2. Intel MKL数学库对计算速度的影响
必须使用Intel MKL数学库，根据编译脚本里的说法，如果只用程序自带的子程序，MP2计算会慢两倍，CCSD(T)计算会慢5倍。即便使用AMD的CPU，也可以正常使用Intel的Fortran编译器和MKL数学库。

---

## 3. GAMESS-US程序下载与解压
进入GAMESS-US官网注册页输入E-mail地址选择下载类型，选择64 bit x86_64 under Linux using Intel OneAPI compilers。将下载的压缩包放入/sob目录，使用tar -xf [压缩包名]命令解压，得到/sob/gamess目录。

---

## 4. GAMESS-US 2024-R2配置文件生成步骤
进入/sob/gamess目录运行./config命令，依次输入配置内容。输入linux64，后续路径均直接回车使用默认值，编译器选oneapi-ifort。数学库设置选mkl，位置输入/opt/intel/oneapi/mkl/latest。GAMESS DDI设置选sockets，后续所有编译选项均输入no。

---

## 5. GAMESS-US 2024-R2数学库路径输入技巧
在配置过程中输入MKL数学库位置时，应输入/opt/intel/oneapi/mkl/latest。如果输入opt/intel/oneapi/mkl/2024.0，脚本可能无法识别，这是脚本的一个bug。

---

## 6. GAMESS-US 2024-R2编译选项建议
在编译设置阶段，对于libxc界面、MDI界面、MSU CCT3等附加代码、GPU加速LIBCCHEM 2.0、VeraChem's VM2库、TINKER插件、VB2000插件、XMVB插件、NEO插件、NBO插件、RISM-SCF-cSED插件，全部输入no不进行编译。这可以节省编译时间并避免联网下载等依赖问题。

---

## 7. GAMESS-US 2024-R2执行编译命令
配置完成后在当前目录生成install.info文件。运行make -j 64命令使用64核并行编译，编译完成后会在/sob/gamess目录下生成可执行文件gamess.00.x，其中00是版本号。

---

## 8. GAMESS-US 2024-R2运行脚本rungms修改
对/sob/gamess/rungms文件进行修改，将set TARGET=sockets下面的三行改为set SCR=/sob/gamess/scr、set USERSCR=/sob/gamess/scr、set GMSPATH=/sob/gamess。将if (null$NCPUS == null) set NCPUS=1中的数值改为默认使用的CPU核心数。

---

## 9. GAMESS-US运行时自动清理临时目录
建议在/sob/gamess/rungms文件开头的#!/bin/csh部分下方添加rm -f /sob/gamess/scr/*。这样每次调用rungms时会自动清空临时目录，防止临时文件逐渐积累。

---

## 10. GAMESS-US环境变量PATH配置
在用户主目录下的.bashrc文件中加入export PATH=$PATH:/sob/gamess。重新进入终端后，即可在任何目录下使用rungms命令运行GAMESS-US。

---

## 11. GAMESS-US 2024-R2基本运行命令
使用rungms test.inp |tee test.out命令调用GAMESS-US对当前目录下的test.inp进行计算。输出信息既显示在屏幕上也输出到test.out文件，默认使用rungms中NCPUS设置的并行核数。

---

## 12. GAMESS-US 2024-R2指定核心数运行
如果想指定使用例如64个核心并行运行，命令格式为rungms test.inp 00 64。其中00是可执行文件的版本号，64是使用的核心数。

---

## 13. GAMESS-US 2024-R2全面测试脚本修改
将/sob/gamess/runall文件里第一处si.msg.chem.iastate.edu改为本机名。把./rungms exam$NUM $VERNO 1里面的1改为测试时使用的并行核数。进入/sob/gamess/目录运行./runall 00开始测试，共40多个测试任务将依次执行。

---

## 14. GAMESS-US 2024-R2测试结果验证
将测试产生的log文件拷贝到/sob/gamess/tests/standard目录下，进入此目录运行./checktst脚本。该脚本会将计算结果与标准结果进行对照，只要大部分任务通过测试即可。未通过的任务大概率是测试文件与当前版本不兼容或只能串行运行所致。

---

## 15. GAMESS-US老版本编译注意事项
不同版本的GAMESS-US编译方法有所不同，老版本部分介绍2013-May和2014-Dec版。2016-Aug版编译方法与此处一致，但输入skip那一步需改为输入proceed。2011-Aug-11版和2009 R3版需参考相应的单独文章。

---

## 16. GAMESS-US老版本编译环境
老版本编译环境为RHEL6-U1 64bit系统（Vmware7.1.2虚拟机）、root用户、Toshiba X500 (i7-2630QM)处理器。程序安装在/sob/gamess下。编译器使用ifort 12.1.0和MKL数学库，均安装在默认路径。

---

## 17. GAMESS-US老版本config配置步骤
将压缩包解压至/sob/gamess，执行./config，依次输入linux64、路径默认、版本号00。编译器选ifort，MKL版本号输入12，忽略ifort 12.0有bug的提示。数学库选mkl，位置输入/opt/intel/mkl，输入skip，DDI选sockets，LIBCCHEM选no。

---

## 18. GAMESS-US老版本ddi编译与核心数限制
进入ddi目录运行./compddi，将得到的ddikick.x移动到/sob/gamess目录。如果CPU核心数超过32个，需要将compddi文件里第一次出现的set MAXCPUS=后面的值改为当前的CPU核心数，然后再执行compddi。

---

## 19. GAMESS-US老版本主程序编译
返回上级目录运行./compall进行编译。十几分钟后objects目录下生成近300个文件，/sob/gamess下产生gamess.00.x可执行文件。如果未产生可执行文件，需手动执行./lked gamess 00。

---

## 20. GAMESS-US老版本单机多核运行配置
为了能单机多核计算，在rungms文件的switch (`hostname`)这行下面插入特定内容。其中xxx是本机名（即hostname命令显示的内容），内容为：case xxx:、set NNODES=1、set HOSTLIST=(`hostname`:cpus=$NCPUS)、breaksw。

---

## 21. GAMESS-US老版本测试与验证
修改runall文件将si.msg.chem.iastate.edu改为本机名，将./rungms exam$NUM $VERNO 1中的1改为并行核数。运行./runall 00进行测试，将产生的log文件拷贝到/sob/gamess/tests/standard目录下。运行./checktst脚本，所有47个测试任务应检验通过。

---

## 22. GAMESS-US源程序单独重编译方法
如果修改了某个源程序文件并想使其生效而不重新编译整个程序，例如修改了int2a.src。可以运行./comp int2a，然后运行./lked gamess 00。

---

## 23. CentOS 8与OneAPI 2021编译特殊设置
使用CentOS 8结合Intel OneAPI 2021版编译GAMESS-US 2020(R2)版时，执行./config需根据提示随机应变。在让你输入mkl版本号时应当输入12，不要输入当前实际版本号，否则在执行./lked gamess 00时无法连接MKL。此外，不需要在switch (`hostname`)后面插入额外内容。

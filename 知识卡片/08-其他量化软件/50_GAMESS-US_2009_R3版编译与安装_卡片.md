---
id: 50
title: GAMESS-US 2009 R3版编译方法
url: http://sobereva.com/50
domain: 其他量化软件
topic: GAMESS-US_2009_R3版编译与安装
cards: 17
---
## 1. GAMESS-US 2009 R3版环境配置与软件准备

操作系统为Fedora7-64bit，已装gcc 4.1.2和csh，CPU为Intel Core2 Q6600，2G内存。对于Intel CPU，使用ifort编译器结合MKL数学库可使代码执行速度大大提升，故采用ifort+MKL方案。C语言代码部分使用gcc即可。文中Intel Fortran Compiler版本为10.1.015，安装在/opt/intel/fce/10.1.015；Intel MKL版本为10.0.4.023，安装在/opt/intel/mkl/10.0.4.023。
- 修改/root/.bashrc添加环境变量：
source /opt/intel/fce/10.1.015/bin/ifortvars.sh
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/intel/mkl/10.0.4.023/lib/em64t

---

## 2. Intel编译器缺少依赖的安装方法

在安装Intel Fortran Compiler时如果系统提示缺少libstdc++.so.5，需将libstdc++-5.0.7-86.x86_64.rpm文件在图形界面下双击安装进系统。

---

## 3. GAMESS-US源码下载与解压

在Iowa State大学网站提交下载申请，收到包含用户名和密码的确认信后，下载64 bit IA64/x86_64 under Linux with Intel compilers版本的GAMESS源码。将下载的gamess-current.tar.gz解压至/sob/gamess目录，最终可执行文件也将编译至此，建议阅读misc文件夹下的readme.unix文件。

---

## 4. GAMESS-US编译脚本路径修改

修改gamess目录下compall、comp、lked文件开头的TARGET=为linux-ia64，chdir=为/sob/gamess。修改runall文件中chdir=为/sob/gamess（runall无TARGET字段）。修改rungms文件：SCR=改为/sob/gamess/scr，setenv ERICFMT和setenv MCPPATH后的~mike改为/sob，if ($os == Linux)行的GMSPATH=改为/sob/gamess，~$USER全替换为/sob/gamess。
- 注意：gamess中的linux-ia64不仅指Itanium的IA64架构，也包括EM64T架构，此模式默认且只能使用ifort编译器和MKL数学库。

---

## 5. GAMESS-US激活程序actvte的编译

将/sob/gamess/tools/actvte.code复制为actvte.f，并把actvte.f中所有*UNX用四个空格替换。运行命令`ifort -o actvte.x -Vaxlib actvte.f`进行编译。该程序用于在编译过程中自动将源代码（.SRC文件）替换为适应当前环境的.FOR文件（称为“激活”），生成的.o文件被编译后会被自动删掉。

---

## 6. GAMESS-US主程序源码编译

在/sob/gamess目录下运行`./compall`，它会自动调用comp脚本编译各个源文件成为.o文件并放到object目录中。编译过程大约持续半个小时，最终会得到230多个.o文件。

---

## 7. DDI库编译配置

无论是否并行计算都必须编译DDI库，否则lked步骤无法通过。在/etc/hosts中填入主机IP和主机名（如192.168.153.3 f71）。进入/sob/gamess/ddi目录，修改compddi文件开头的set TARGET =为linux-ia64。将set MAXCPUS（每个节点内SMP并行的核心数）和set MAXNODES（最多节点数）设为实际情况或更大，此处均设为2。
- 在/sob/gamess/ddi/src/std_system.c里面的`struct hostent *hp;`后面加入一行`name="f71";`（f71为主机名），这是为了修复GAMESS将主机名误认为localhost导致TCP error的bug。

---



---

## 8. DDI库的编译与安装

在/sob/gamess/ddi目录下运行`./compddi >& compddi.log`进行编译，过程很快。编译完成后，将得到的ddikick.x文件移动到上一级目录/sob/gamess下。

---

## 9. GAMESS-US可执行文件链接

在/sob/gamess目录下运行`./lked gamess 03 >& lked.log`，将.o文件、DDI库文件和数学库连接成可执行文件gamess.03.x。参数03是版本标识，若不写则默认生成gamess.00.x。

---

## 10. 测试前脚本版本号与临时目录设置

将runall文件里面的set VERNO=默认值00改为03以匹配生成的可执行文件。建立/sob/gamess/scr文件夹作为GAMESS运行的临时文件夹。

---

## 11. GAMESS-US编译测试与结果检验

在/sob/gamess目录下运行`./runall`自动运行44个测试文件，生成exam??.log文件。修改tools/checktst目录下checktst文件的set GMSPATH=为/sob/gamess，运行该资料件并输入/sob/gamess路径，程序会将log结果与标准结果对比，检查任务结束状态及计算误差是否超阈值。对于failed的任务需检查log文件，排查故障后删掉scr目录下文件并重新测试。

---

## 12. Linux共享内存段大小限制调整

如果exam36和43通不过且log提示Check system limits on the size of SysV shared memory segments，说明Linux默认的单个共享内存段最大值太小（默认32MB，任务需约48MB）。修改/etc/sysctl.conf，加入一行`kernel.shmmax = 1610612736`将上限提高至1.5G，重启或运行`/sbin/sysctl -w kernel.shmmax=1610612736`立刻生效。
- 查看当前设置命令：`/sbin/sysctl -a|grep shmmax`

---

## 13. SMP并行运行配置

若想用SMP方式并行双核运行，需在rungms文件的`if ($NCPUS > 2) set NCPUS=2`那一行上面插入一行`case f71:`（f71为主机名）。四核机器则在`if ($NCPUS > 4) set NCPUS=4`前插入。运行命令如`./rungms exam01.inp 03 2 &> a.txt`表示用单节点双核调用gamess.03.x执行任务；若只输入`./rungms exam01.inp`则表示用单核心调用gamess.00.x执行任务。

---

## 14. 图形应用程序编译

进入graphics目录，修改complink文件：chdir改为/sob/gamess/graphics，set TARGET=改为linux-pc，`if ($TARGET == linux-pc)`下的`set FORT=`改为`'ifort -O2'`。之后运行`./complink`进行编译。

---

## 15. 源代码修改后的增量编译方法

编译成功后若修改了src目录下某个源代码（如int2a.src），只需在/sob/gamess目录下运行`./comp int2a`，删掉原GAMESS可执行文件，重新运行lked即可，不必使用compall重新编译所有文件。

---

## 16. 32位系统+gfortran编译配置

在32bit系统+任意CPU+gfortran下，数学库自动使用GAMESS自带的blas库（速度较慢）。将前文提到的linux-ia64改为linux32。激活命令改为`gfortran -o actvte.x actvte.f`。修改lked第302行（if ($TARGET == linux32) then）下的set FORTRAN=为gfortran。修改comp第1138行的set FORTRAN=为gfortran。修改ddi/compddi第540行（if ($TARGET == linux32) then）下的set FORTRAN=为gfortran。修改graphics/complink中`if ($TARGET == linux-pc) set FORT=`为`'gfortran -O2'`。

---

## 17. 64位系统+gfortran编译配置

在64bit系统+任意CPU+gfortran下，将32位配置中的linux32改为linux64。lked、comp和compddi对linux64模式默认使用gfortran，不必手动修改。需删除lked中`# Using blas.o will give a successful link, to slow matrix multiply routines.`下面的`exit 4`，以便在没有安装MKL、Atlas或ACML库时使用自带的blas库代替。

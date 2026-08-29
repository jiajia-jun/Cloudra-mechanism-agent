---
id: 105
title: GAMESS-US 2011-Aug-11版编译方法
domain: 其他量化软件
topic: GAMESS-US_2011版编译与配置
cards: 10
---

## 1. GAMESS-US 2011-Aug-11版编译文档过时提示
GAMESS-US 2011-Aug-11版编译方法文章已经完全过时。新版的编译方法可参考《GAMESS-US的编译方法》一文。

---

## 2. 编译环境与版本信息
本次编译使用的GAMESS-US版本为2011-Aug-11。编译器和数学库为ifort 12.1.0+MKL，均安装在默认路径。系统环境为RHEL6-U1 64bit（Vmware7.1.2虚拟机），使用root用户，程序将安装在/sob/gamess下。

---

## 3. 生成配置文件的具体操作
将压缩包解压至/sob/gamess，并进入此目录。执行./config，依次输入[enter]、linux64、[enter]、ifort、12、[enter]、[enter]、mkl、/opt/intel/mkl、skip、[enter]、[enter]、sockets。此时配置文件install.info在当前目录下生成。

---

## 4. 编译ddi模块步骤
进入ddi目录，执行./compddi命令进行编译。将得到的ddikick.x文件移动到上一级目录，即/sob/gamess下。

---

## 5. 编译代码并连接可执行文件
返回上一级目录，执行./compall进行编译，经过近20分钟编译后，objects目录下生成了255个.o文件。执行./lked gamess 00命令连接为可执行文件。

---

## 6. 配置rungms文件的路径变量
对rungms文件作如下修改：将setenv AUXDATA ~mike/gamess/auxdata改为setenv AUXDATA /sob/gamess/auxdata；将~$USER全都替换为/sob/gamess；将所有/home/mike替换为/sob；将if ($os == Linux) set GMSPATH=/cu/mike/gamess改为if ($os == Linux) set GMSPATH=/sob/gamess；将set SCR=/scr/$USER改为set SCR=/sob/gamess/scr。

---

## 7. 配置单机多核计算设置
如果想要单机多核计算，在rungms文件约556行处的switch (`hostname`)这行下面插入指定内容。其中xxx是本机名，即运行hostname命令所显示的内容。插入内容
case xxx
set NNODES=1
set HOSTLIST=(`hostname`:cpus=$NCPUS)
breaksw

---

## 8. 运行测试与修改runall文件
建立/sob/gamess/scr文件夹。把runall文件的chdir /u1/mike/gamess改为chdir /sob/gamess。执行./runall进行测试，经过10分钟左右，全部44个任务测试完成。

---

## 9. 检查测试结果
修改tools/checktst目录下checktst文件的set GMSPATH=后面为/sob/gamess。运行该资料件，出现提示时输入/sob/gamess。机子上44个测试全部通过。

---

## 10. 单机多核测试验证
同时也测试一下单机多核方式能否正常运行，运行命令./rungms exam01.inp 00 4，其中4代表用4核。这里直接测试通过。

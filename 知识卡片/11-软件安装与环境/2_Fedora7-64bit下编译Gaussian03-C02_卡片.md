---
id: 2
title: Fedora7-64bit下编译Gaussian03-C02
url: http://sobereva.com/2
domain: 软件安装与环境
topic: Fedora7-64bit下编译Gaussian03-C02
cards: 22
---

# Fedora7-64bit下编译Gaussian03-C02 — 知识卡片

## 1. 编译环境与预期成功率

编译平台为root账户、Fedora7-64bit操作系统、Intel Q6600处理器，目标为编译32位版本Gaussian 03-C02。如果软硬件严格符合要求且未乱改设置，用户对Linux、Gaussian和编译器有一定了解，一遍编译成功的概率保证为95%。

---

## 2. PGI编译器下载与安装

到http://www.pgroup.com下载pgf77 workstation，文件大小约290MB，使用版本为8.01版。解压后运行install安装到默认路径，安装过程中不需要安装ACML和mpich1。

---

## 3. PGI编译器License申请与配置

注册新账户后登录，选择Create trial keys，输入/opt/pgi/license.info里FLEXnet hostid后面的内容获取license.dat，并将其拷进/opt/pgi。该license.dat使编译器在两周内有效，每台机子的id不同，更换机子需重新申请。

---

## 4. 建立编译器软链接

执行命令ln -s /opt/pgi/linux86/8.0-1/bin/pgf77 /usr/bin/pgf77，将32位版本的pgf77编译器链接到/usr/bin，用于编译32位版本的Gaussian。

---

## 5. 修改脚本中的set-mflags路径

修改/sob/g03/bsd/updatelink1的第42行、/sob/g03/bsd/setup-make的第28和68行、/sob/g03/bsd/g03.login的第74和75行、/sob/g03/bsd/bldg03的第198、205、208、211行，将set-mflags改为/sob/g03/bsd/set-mflags。

---

## 6. 修改g03.login与bldg03文件

修改/sob/g03/bsd/g03.login的第87行，将gau_machine改为./gau_machine。修改/sob/g03/bsd/bldg03的第120行，将其内容改为set x = i386。

---

## 7. i386.make编译参数修改

修改/sob/g03/bsd/i386.make文件，在第580行编译cmpdst.o的-c参数前加上-m32，在第599行编译mdutil.o的-c参数前加上-m32。

---

## 8. mdutil.c源码修改

修改/sob/g03/mdutil.c文件，将第1267行的pthread_kill_other_threads_np()那行代码删掉。

---

## 9. set-mflags缓存与架构设置

修改/sob/g03/set-mflags文件，将第23行改为set csize=4096（该数值对应cat /proc/cpuinfo显示的cache size）。将第30行的amd64改为aamd64，使脚本无法识别64位平台，从而默认使用32位版本编译参数。

---

## 10. 拷贝头文件与环境初始化

将/sob/g03目录内所有.inc文件拷贝至/usr/include。进入csh shell，设置环境变量g03root为/sob，赋予当前目录及bsd子目录下文件777权限，并执行source bsd/g03.login。

---

## 11. 执行编译命令

执行命令/sob/g03>bsd/bldg03 >& all.txt开始编译。如果编译失败，可以在all.txt文件中搜索error关键字查找具体原因。

---

## 12. 配置运行环境变量

将以下内容按顺序加入/root/.bashrc：export g03root=/sob；source /sob/g03/bsd/g03.profile；export GAUSS_SCRDIR=/sob/g03/scratch。然后在/sob/g03下创建scratch目录并切换到bash即可使用。

---

## 13. 编译性能验证结果

经简单测试，编译出来的Gaussian 03-C02与网上已编译好的G03-C02(IA32)运算结果一致，且运算速度比官方版本快10%。

---

## 14. 编译机制与工具

编译过程通过bldg03调用g03.make和updatelink1完成。首先编译gau-fsplit等工具，gau-fsplit将Fortran源代码拆分为单个子程序源文件，分别编译为.o文件再连接。

---

## 15. util.so编译流程

系统先在temputil临时目录下编译util.a所需的.o文件，连接成util.a后再连接成util.so，之后删除临时目录。随后依次编译lxxx.exe，暂存在temp-lxxx目录组合后删除。

---

## 16. g03.make的自动生成

编译开始时会删掉bsd/g03.make，根据系统架构自动制作g03.make软连接连接到对应的.make文件（如i386.make），以此控制文件编译过程。

---

## 17. 保留临时文件的方法

若要保留util.so的临时文件夹temputil，需把bldg03第342行的rm -f -r temputil注释掉。若要保留每个子程序的临时文件夹，需把g03.make里所有rm -f替换为#rm -f。

---

## 18. 单独或批量编译可执行文件

若想编译某个子程序，例如l502.exe，运行make -f bsd/i386.make l502.exe。若要编译所有.exe文件但不编译util.a，运行make -f bsd/i386.make exe。

---

## 19. gau-machine脚本功能

gau-machine的返回值代表当前CPU架构，如i386或amd64。在64位环境下即便是Intel CPU也会显示amd64。gau-machine由bsd/machine.c编译得到，每次运行bldg03时都会先编译一次。

---

## 20. set-mflags脚本功能

bsd/set-mflags用于设定编译时的参数脚本。它会调用gau-machine确定编译参数，决定使用的参数和.a库，参数保存在$mflags中并传递给其它脚本。

---

## 21. 64位平台编译32位的替代方案

在64位平台下编译32位版本的另一种办法是修改/sob/g03/bsd/gau-machine.c的第131行，将amd64改为i386。此方法不需要修改bldg03第120行和set-mflags第30行。

---

## 22. 替代编译方案的性能与适用性

修改gau-machine.c的替代方案编译出来的Gaussian比前述方法慢1/5以上，且比官方编译版本更慢，但更为保险。如果前述方法编译出来的程序运行有问题，建议使用此方法。

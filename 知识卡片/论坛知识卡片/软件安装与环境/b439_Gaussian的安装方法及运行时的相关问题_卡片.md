---
key: b439
title: Gaussian的安装方法及运行时的相关问题
url: http://sobereva.com/439
domain: 软件安装与环境
source: blog
year: 2018
cards: 34
---

# Gaussian的安装方法及运行时的相关问题 — 知识卡片

## 1. Gaussian的流行度及安装文档现状

Gaussian是目前最流行、用户最多的量化程序，网上关于安装Gaussian的中文资料存在很多错误，容易导致初学者走弯路。资料所述的安装方法被宣称为最正确的步骤，若与网上其它资料不同，则网上资料可能包含多余步骤或错误。

---

## 2. Linux下的Shell环境与切换

Linux下有多种Shell（如bash、csh、ksh），不同Shell下的命令（如设置环境变量）有所不同。Bash是最常见的默认Shell，若当前Shell不是bash，可在终端输入bash命令进行切换。

---

## 3. Linux下的用户主目录与权限管理

Linux用户登录后默认位于用户主目录（普通用户为/home/[用户名]/，root用户为/root/）。文件权限可通过chmod命令修改，例如chmod 750 -R *可将当前目录下所有文件及子目录的权限设置为750（即用户可读写执行，同组用户可读执行，其它用户无权限）。

---

## 4. Linux下.bashrc文件的作用

.bashrc文件位于用户主目录下，是隐藏文件，记录了每次登录bash shell终端时自动执行的命令。若需命令每次登录都生效，应将其添加至资料件末尾。

---

## 5. Linux下Gaussian的安装步骤

将Gaussian压缩包解压至主目录（如/home/sob/），建立临时文件目录（如/home/sob/g09/scratch）。在.bashrc文件中添加g09root、GAUSS_SCRDIR环境变量并source Gaussian自带的profile文件，重新登录终端即可。

---

## 6. Gaussian环境变量配置详解

安装时需设置g09root指向Gaussian目录，GAUSS_SCRDIR指向临时文件目录，并通过source命令执行g09.profile脚本以配置运行环境。对于Gaussian 16，只需将上述步骤中的g09替换为g16。

---

## 7. Gaussian默认计算资源配置文件Default.Route

Gaussian目录下的Default.Route文件用于设定默认的计算资源，-M-设置默认最大内存量，-P-设置默认CPU核数。资料件中的设置优先级低于输入文件中的%mem和%nproc设置。

---

## 8. Gaussian默认内存与核心配置的注意事项

若未在Default.Route或输入文件中设置内存和核数，G09默认最多使用256MB内存，G16默认最多使用800MB内存。G16 C.01版本存在bug，Default.Route里的-M-设置不生效，必须使用%mem定义内存。

---

## 9. Gaussian目录权限设置

安装完成后，需在Gaussian目录下运行chmod 750 -R *命令，对当前目录及所有子目录下的文件设置权限，否则运行时可能报错。

---

## 10. Linux下临时文件夹管理建议

Gaussian任务中断后会在GAUSS_SCRDIR指定的临时文件夹残留文件，长期积累可能占满硬盘。建议定期清空临时文件夹，但需避免在任务运行时清理当前任务对应的临时文件。

---

## 11. Linux下Gaussian的运行命令格式

Gaussian在Linux下常见运行命令包括：g09 < test.gjf > test.out（输出到文件并可在后台运行）、g09 < test.gjf |tee test.out（同时输出到文件和屏幕）、g09 test.gjf（默认输出为test.log）。

---

## 12. Linux下Gaussian任务的持续运行

使用SSH远程登录时，为防止断开连接导致任务中断，应使用nohup g09 < test.gjf > test.out &提交任务，并使用exit命令优雅断开连接。

---

## 13. G16命令行参数指定资源

从Gaussian 16开始，可在运行命令中直接指定CPU核数和内存，如g16 -p=16 -m="40GB" < love.gjf > love.out，这等同于在输入文件中定义%nprocs=16和%mem=40GB。

---

## 14. 错误提示：files in the gaussian directory are world accessible

此报错提示说明未执行chmod 750 -R *命令，Gaussian因检测到可执行文件对所有用户可访问而拒绝运行。

---

## 15. 错误提示：Error: illegal instruction

此报错说明CPU与Gaussian不兼容，通常是因为CPU太老不支持编译时使用的指令集（如AVX2）。解决方法是购买非AVX2版Gaussian或更换较新的CPU。

---

## 16. AMD CPU运行Gaussian报错的解决

较新的AMD CPU（如ZEN2架构）虽支持指令集，但因编译器兼容性可能报错。可尝试在运行前设置环境变量export PGI_FASTMATH_CPU=sandybridge。

---

## 17. Gaussian并行计算核心数选择建议

若机器仅运行一个Gaussian任务，建议使用所有物理核心进行并行。注意区分物理核心与逻辑核心，对于开启超线程的CPU，建议使用物理核心数（如双路2696v3共36核）。

---

## 18. Gaussian并行效率与多任务策略

计算速度与核数并非线性正比，Gaussian 16在约50核时接近速度极限。对于多核机器，同时运行多个任务（如双路服务器跑两个48核任务）通常比跑一个高核数任务更能充分利用CPU性能。

---

## 19. Gaussian并行核数超过64的配置

对于Gaussian 16 B.01及之前版本，并行核数超过64可能会报错。解决方法是在~/.bashrc中添加export OMP_THREAD_LIMIT=256，以提升并行核数上限。

---

## 20. Gaussian内存分配原则

Gaussian在有足够内存时会自动选择较快算法，一般建议将约90%的空余物理内存分配给Gaussian。若分配超过物理内存，会导致报错或严重拖慢计算速度（使用虚拟内存）。

---

## 21. Gaussian多任务运行的资源分配限制

运行多个Gaussian任务时，所有任务调用的核数总和不应超过机器物理核心数，且分配内存总和不应超过空余物理内存。耗内存且读写量大的任务不建议多任务并行。

---

## 22. Gaussian 09与16的并存切换

G09和G16因运行环境配置共通，无法同时直接使用。可通过在.bashrc中注释掉其中一套环境的配置行，并source另一套环境的profile文件来实现切换。

---

## 23. 错误提示：formchk命令未找到

提示找不到formchk命令通常是因为未按照正确方法配置Gaussian环境（如未source profile文件）。

---

## 24. 错误提示：PGFIO/stdio: No such file or directory

此报错表明GAUSS_SCRDIR环境变量指向的路径不存在，或者用户在该路径下没有读写权限，导致无法创建临时文件。

---

## 25. 错误提示：galloc: could not allocate memory

此报错说明设置的内存使用上限超过了实际可分配的物理内存量。Gaussian会在计算开始时请求设定内存，若无法分配则报错。

---

## 26. Gaussian任务非正常中断的可能原因

任务无报错但莫名停止可能由巧合、版本Bug、软件环境兼容性、被恶意终止、被作业调度系统终止、内存不足或硬件不稳定引起。

---

## 27. Windows下Gaussian的安装注意事项

Windows版Gaussian安装需注意路径不能包含中文。安装后需在目录下建立scratch文件夹及Default.Rou文件（内容与Linux版Default.Route相同）以配置默认资源。

---

## 28. Windows版Gaussian的资源限制

Windows版Gaussian常见为32bit版，并行核数限制为4，内存限制约1500MB（建议设为1400MB）。若需突破核数和内存限制，应使用64bit版。

---

## 29. Windows下Gaussian与GaussView的安装顺序

安装GaussView前必须先安装Gaussian，且GaussView应安装在与Gaussian相同的目录下，否则GaussView无法识别Gaussian可执行文件，导致功能受限。

---

## 30. Gaussian与GaussView的版本兼容性

Gaussian 09建议搭配GaussView 5.0.9，Gaussian 16建议搭配GaussView 6。版本不匹配可能导致帧号顺序错乱、无法载入输出文件等问题。

---

## 31. Windows版Gaussian图形界面配置

在Gaussian图形界面的File - Preference中可修改Scratch Path（临时文件路径）和ASCII Editor（文本编辑器路径）等配置。

---

## 32. Windows版Gaussian运行故障排除

Windows下运行卡顿或报错常由360等安全软件干扰引起。部分CPU（如XEON v3）运行win32版Gaussian可能因兼容性问题失败。

---

## 33. Windows下Gaussian命令行调用配置

在Windows环境变量Path中添加Gaussian目录（如D:\study\G16W），并新建环境变量GAUSS_EXEDIR指向该目录。之后可通过命令行使用g16 test.gjf运行计算。

---

## 34. Gaussian安装环境变量设置的误区

网上部分文章要求手动设置PATH、LD_LIBRARY_PATH、GAUSS_EXEDIR等环境变量是多余的，这些变量在source g09.profile脚本时会自动设置。正确安装步骤仅需source该脚资料件即可。

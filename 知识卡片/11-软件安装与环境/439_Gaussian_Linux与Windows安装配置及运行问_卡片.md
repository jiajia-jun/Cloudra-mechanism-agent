---
id: 439
title: Gaussian的安装方法及运行时的相关问题
domain: 软件安装与环境
topic: Gaussian_Linux与Windows安装配置及运行问
cards: 29
---

## 1. Linux下bash与csh shell的区别
Linux下有bash、csh、ksh等多种shell，相当于不同的文本终端界面。在bash里设置环境变量用export命令，而在csh里用set命令。如果不确定当前使用的shell，可在终端输入echo $SHELL查看；若非bash，可输入bash切换。

---

## 2. Linux用户主目录路径
Linux下每个用户都有主目录，普通用户的主目录为/home/[用户名]/，root用户的主目录为/root/。登录系统后当前目录即为主目录，可敲pwd命令显示当前目录。

---

## 3. Linux文件权限修改命令chmod
Linux文件权限包括可执行、可读取和可修改，可用chmod命令修改。例如，chmod +x./niconiconi给当前目录下文件添加可执行权限；chmod 750 /sob/yoshiko.exe将文件权限设为750，其中7、5、0分别对应当前用户、同组用户和其他用户的权限（7为全权限，5为读执行，0为无权限）。

---

## 4. Linux .bashrc文件的作用
用户主目录下的.bashrc文件是隐藏文件，记录每次登录bash shell终端时自动执行的命令。若希望命令每次登录生效，应将其写入该资料件末尾。隐藏文件需用ls -a命令或在文件浏览器中按Ctrl+H查看。

---

## 5. Gaussian在Linux下的环境变量配置
在.bashrc文件中需添加以下语句并保存：export g09root=/home/sob；export GAUSS_SCRDIR=/home/sob/g09/scratch；source /home/sob/g09/bsd/g09.profile。其中g09root指定Gaussian目录位置，GAUSS_SCRDIR指定临时文件夹，source命令执行配置脚本。保存后需重新进入终端生效。

---

## 6. Gaussian Linux安装后的权限设置
安装完成后，需切换到Gaussian目录（如/home/sob/g09/）运行chmod 750 -R *命令。该命令对当前目录下所有文件和子目录设置权限，若未执行此步，运行时会报错提示文件全局可访问。

---

## 7. Gaussian Default.Route文件设置
Gaussian目录下的Default.Route文件用于设定默认计算资源。写入-M- 60GB设置默认最大内存为60GB，写入-P- 36设置默认使用36个CPU核。该资料件设置优先级低于输入文件里的%mem和%nproc设置；若未设置则G09默认用256MB内存、单核，G16默认用800MB内存。

---

## 8. Linux下Gaussian临时文件清理
Gaussian任务中断时会在GAUSS_SCRDIR指定的临时文件夹残留临时文件。建议定期清空该文件夹以避免占满硬盘，但不要在有任务运行时清理，且避免清理当前任务对应的pid号文件。

---

## 9. Linux下Gaussian的运行命令
Gaussian在Linux下常见运行方式包括：g09 < test.gjf > test.out（输出到文件）；g09 < test.gjf |tee test.out（同时输出到屏幕和文件）；g09 test.gjf（默认输出为test.log）。使用第一种或第三种方式时，可用tail -f test.out同步显示输出信息。

---

## 10. SSH远程提交Gaussian后台任务
使用SSH远程登录服务器提交Gaussian任务时，为防止断开连接后任务中断，应输入nohup g09 < test.gjf > test.out &。退出时需用exit命令优雅断开，不要直接关闭终端。

---

## 11. Gaussian 16命令行参数指定资源
从G16开始，可在运行命令里直接指定核数和内存，如g16 -p=16 -m="40GB" < love.gjf > love.out，等同于定义%nprocs=16和%mem=40GB。也可用-c="0-47"指定只在第0~47号CPU核心上计算。命令行参数优先级高于Default.Route。

---

## 12. 报错：files in the gaussian directory are world accessible
此报错说明未执行chmod 750 -R *命令。Gaussian要求其可执行文件不能对所有用户开放访问权限，否则拒绝运行。

---

## 13. 报错：Error: illegal instruction / illegal opcode
此报错说明CPU太老，不支持Gaussian编译时使用的指令集（如AVX2）。解决方法是购买非AVX2版Gaussian或更换新CPU。对于较新的AMD CPU，可尝试在运行前定义环境变量export PGI_FASTMATH_CPU=sandybridge。

---

## 14. Gaussian运行时CPU核心数分配建议
若机器只跑一个Gaussian任务，一般建议使用全部物理核心数并行。对于采用超线程(HT)技术的CPU，逻辑核心数是物理核心数两倍，应基于物理核心数设置（如双路2696v3有36物理核心，应设为36）。特别小的任务在核数过多时可能反而变慢。G16并行核数在50左右接近速度极限。

---

## 15. 多任务并行运行Gaussian的策略
当CPU核数很多时，同时跑多个任务比跑单任务更能充分利用性能。如96核服务器跑两个48核任务，并建议用%cpu绑定不同CPU以减少争抢。所有任务调用的核数总和不应超过物理核心数，内存总和不应超过空余物理内存。耗内存和读写大的任务不宜多任务同跑。

---

## 16. Gaussian 16 B.01及之前版本的核数限制
对于Gaussian 16 B.01及之前的版本，当并行核数超过64时可能报错。解决办法是在~/.bashrc中添加export OMP_THREAD_LIMIT=256，将并行核数上限提升至256。

---

## 17. Gaussian运行时内存分配建议
一般建议将空余物理内存的90%左右分配给Gaussian。分配内存是上限，实际占用未必占满。内存分配超过空余物理内存会导致报错或使用虚拟内存严重拖慢速度。多任务运行时，各任务内存总和不应超过空余物理内存。

---

## 18. Gaussian内存分配的最低原则
使用N核并行时，理应分配不少于N GB的内存。对于耗内存多的任务（如大体系DFT振动分析、CCSD(T)），建议在物理内存总量大于CPU核心数乘以4GB的机器上运行，并尽可能多分配内存。

---

## 19. Linux下Gaussian 09和16并存设置
将g09和g16放在同一目录下，通过修改.bashrc文件中的#注释行切换。启用g09时注释掉g16的export和source行，启用g16时反之。由于环境配置共通，无法同时让g09和g16命令都生效。

---

## 20. 报错：formchk命令找不到
此报错说明未严格按照相关方法配置Gaussian（如未正确source profile文件或被网上一键脚本误导）。

---

## 21. 报错：PGFIO/stdio: No such file or directory
此报错说明GAUSS_SCRDIR环境变量指向的路径不存在，或者虽然存在但没有可读写权限。需检查路径设置及权限。

---

## 22. 报错：galloc: could not allocate memory
此报错说明Gaussian内存使用量上限设置过大，超过了实际可分配的内存量。Gaussian会在计算一开始请求设定的内存，若无法满足则报错。

---

## 23. Gaussian任务莫名停止的排查
任务无报错但停止可能原因有：巧合或版本bug、软件环境兼容性问题、被恶意kill或作业调度系统杀死、内存分配不足或运行中被抢占、硬件不稳定。可尝试重算、换版本、增大内存或更换机子。

---

## 24. Windows版Gaussian的安装与路径
Windows版Gaussian安装时输入序列号即可，注意绝对不能安装在带有中文的路径下。安装后应手动建立如D:\study\G09W\scratch\Default.Rou文件，内容与Linux版Default.Route相同。

---

## 25. Windows版Gaussian的资源限制
绝大多数Windows版Gaussian为32bit，并行核数最多4，内存最多分配1500MB左右（建议设为1400MB）。若想突破限制，需使用64bit版。Linux版Gaussian则一律为64bit。

---

## 26. GaussView与Gaussian的安装兼容性
必须先安装Gaussian再安装GaussView，且GaussView必须安装在与Gaussian相同的目录下，否则无法识别可执行文件，导致无法载入chk文件、绘制分子轨道等。建议Gaussian 09搭配GaussView 5.0.9，Gaussian 16搭配GaussView 6以避免兼容性问题。

---

## 27. Windows版Gaussian临时目录与编辑器设置
在Gaussian图形界面的File - Preference中，Scratch Path可修改临时文件夹路径（默认为安装目录下scratch）。ASCII Editor可设置打开输出文件的文本编辑器，建议设为Ultraedit或notepad++等强力编辑器。

---

## 28. Windows版Gaussian运行故障排除
Windows版Gaussian若输入文件正确却卡住或报错，往往是360等安全软件干扰，建议卸载。部分XEON v3等系列CPU运行win32版Gaussian09/16可能因兼容性失败，目前无解法。

---

## 29. Windows下Gaussian命令行调用配置
在“高级系统设置”的“环境变量”中，编辑Path变量加入Gaussian目录（如D:\study\G16W），并新建变量GAUSS_EXEDIR设为该目录。配置后可用g16 test.gjf命令运行。注意此时临时文件在当前目录，且需将Default.Rou拷至当前目录或在gjf中直接写%nproc和%mem。

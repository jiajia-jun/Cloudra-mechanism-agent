---
id: 439
title: Gaussian的安装方法及运行时的相关问题
url: http://sobereva.com/439
domain: 软件安装与环境
topic: Gaussian_Linux与Windows安装配置及运行问
cards: 1
---

# Gaussian_Linux与Windows安装配置及运行问 — 知识卡片

## 1. Linux下Gaussian安装所需环境变量配置

在Linux下安装Gaussian时，需在用户主目录下的.bashrc文件中添加特定语句。这些语句包括export g09root=/home/sob指定根目录、export GAUSS_SCRDIR=/home/sob/g09/scratch指定临时文件夹路径，以及source /home/sob/g09/bsd/g09.profile执行自带脚本。完成编辑后需重新进入终端使配置生效，对于Gaussian 16只需将上述路径中的g09改为g16。

## Linux下Gaussian安装文件权限设置
Gaussian安装完成后必须设置正确的文件权限才能运行，需切换到Gaussian目录执行chmod 750 -R *命令。该命令对当前目录及所有子目录下的文件设置权限，750分别代表当前用户拥有完整权限、同组用户拥有读取和执行权限、其它组用户无任何权限。如果未执行此步，运行时会报错提示files in the gaussian directory are world accessible。

## Linux下Gaussian默认计算资源配置文件
Default.Route文件用于设定Gaussian默认使用的计算资源，若不存在则需新建。文件内容使用-M-参数设置默认最大内存量（支持MB、GB、MW、GW单位），使用-P-参数设置默认CPU并行核数。该文件中的设置优先级低于输入文件里的%mem和%nproc设置，若两者均未设置，G09默认使用256MB内存和单核，G16默认使用800MB内存和单核。

## Linux下Gaussian运行命令格式
Gaussian在Linux下有三种常见运行命令格式：g09 < test.gjf > test.out将信息输出到文件，g09 < test.gjf |tee test.out同时输出到文件和屏幕，g09 test.gjf默认生成test.log输出文件。使用第一种方式时可通过tail -f test.out实时查看屏幕输出。对于Gaussian 16，命令需改为g16。

## SSH远程提交后台任务的方法
通过SSH远程登录服务器提交Gaussian任务时，为防止断开连接导致任务中断，应使用nohup命令提交并在末尾加&。完整的命令格式为nohup g09 < test.gjf > test.out &，退出连接时必须使用exit命令优雅断开。这样任务会在服务器上持续运行直到完成，不受终端断开影响。

## G16命令行直接指定计算资源参数
从Gaussian 16开始，可以在运行命令中直接指定CPU核数和内存，优先级高于Default.Route文件。使用-p=参数指定核数（如-p=16），使用-m=参数指定内存（如-m="40GB"），使用-c=参数指定CPU核心范围（如-c="0-47"）。命令示例如g16 -p=16 -m="40GB" < love.gjf > love.out，效果等同于在输入文件中定义%nprocs=16和%mem=40GB。

## Gaussian报错提示world accessible的解决方法
运行Gaussian时若提示“files in the gaussian directory are world accessible. this must be fixed”，说明未设置正确的文件权限。这是因为Gaussian检测到其可执行文件对所有用户都可访问，解决方法是进入Gaussian目录执行chmod 750 -R *命令。

## Gaussian报错illegal instruction的原因
运行Gaussian时提示“Error: illegal instruction , illegal opcode”说明CPU与程序不兼容。原因通常是CPU太老不支持编译时使用的指令集（如AVX2），或者是较新的AMD CPU与编译器兼容性问题。解决方法是购买非AVX2版程序、更换机器，或对AMD CPU尝试设置环境变量export PGI_FASTMATH_CPU=sandybridge。

## Gaussian并行计算核数选择建议
若机器只运行一个Gaussian任务，建议使用所有物理核心进行并行以获得最快速度。注意区分物理核心与逻辑核心，对于开启超线程的CPU，应使用物理核心数（如双路2696v3为36核）。特别小的任务可能核数过多反而变慢，G16并行核数在50左右接近极限，核数很多时分跑多个任务效率更高。

## G16 B.01及之前版本突破64核限制
对于Gaussian 16 B.01及之前的版本，当设定的并行核数超过64时程序可能报错。解决方法是在~/.bashrc文件中添加export OMP_THREAD_LIMIT=256，将并行核数上限提升至256，从而允许使用超过64核进行并行计算。

## Gaussian内存分配建议
Gaussian任务应尽可能分配较多的空余物理内存，建议将约90%的物理内存分配给程序，因为足够的内存能让程序自动选择更快的算法或减小计算量。如果内存分配超过空余物理内存，会导致报错或严重拖慢速度。对于多任务并行，所有任务分配的内存总和不应超过空余物理内存量。

## Linux下Gaussian 09和16并存切换
Linux下无法同时激活g09和g16命令，需通过修改.bashrc文件切换使用。将其中一套命令用#注释掉，另一套保留，保存并重新进入终端即可生效。例如注释掉g16相关行，取消注释g09相关行，则当前只能使用g09，反之亦然。

## Gaussian报错PGFIO/stdio: No such file or directory
运行开始时提示“PGFIO/stdio: No such file or directory”且包含路径信息，说明GAUSS_SCRDIR环境变量指向的路径不存在。如果路径存在但用户没有读写权限，也会因无法创建临时文件而导致运行失败。

## Gaussian报错galloc: could not allocate memory
运行开始报错“galloc: could not allocate memory”说明设置的内存使用上限超过了实际可分配的内存量。Gaussian会在计算开始时向系统请求设定的内存量，如果系统无法满足该请求就会直接报错。

## Windows下Gaussian安装及Default.Rou配置
Windows版Gaussian安装时不能使用中文路径，安装后需在目录下手动建立scratch\Default.Rou文件。该文件内容与Linux下的Default.Route相同，用于配置默认计算资源。32位版Gaussian限制较多，建议大型计算使用64位版。

## Windows下Gaussian版本与GaussView搭配
Gaussian和GaussView版本存在兼容性问题，建议Gaussian 09搭配GaussView 5.0.9，Gaussian 16搭配GaussView 6。错误的搭配会导致问题，如GaussView 6.0.16打开G09的IRC帧号错乱，GaussView 5.0.9无法载入G16的振动分析文件。

## Windows下Gaussian命令行调用环境变量设置
要在Windows命令行中使用Gaussian，需在系统环境变量中设置。编辑Path变量加入Gaussian目录（如D:\study\G16W），并新建用户变量GAUSS_EXEDIR值设为Gaussian目录。设置后可使用g16 test.gjf命令运行，注意此时Default.Rou设置不生效，需在gjf中直接指定%nproc和%mem。

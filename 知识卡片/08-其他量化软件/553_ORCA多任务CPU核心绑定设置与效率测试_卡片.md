---
id: 553
title: 通过设置CPU内核绑定降低ORCA同时做多任务的耗时
url: http://sobereva.com/553
domain: 其他量化软件
topic: ORCA多任务CPU核心绑定设置与效率测试
cards: 13
---

# ORCA多任务CPU核心绑定设置与效率测试 — 知识卡片

## 1. ORCA多任务运行与CPU绑定的意义

并行程序效率随核数增加而降低，在多核机器上同时运行多个任务且每个任务使用较少核心，总耗时通常低于逐个任务调用所有核心。同时运行多个任务涉及资源争抢问题，通过线程或进程与CPU内核绑定可避免操作系统自动调度引起的切换，从而降低资源争抢并提升运行效率。ORCA自身不直接提供内核绑定设置，但可通过指定OpenMPI运行选项实现。

---

## 2. ORCA实现CPU内核绑定的前提

ORCA在Linux下结合OpenMPI并行，只有编译OpenMPI时提供了libnuma静态库，ORCA运行时才能借助OpenMPI设置实现内核绑定。对于CentOS 7.x系统，可通过yum install numactl-devel命令安装libnuma静态库，随后按照常规方法编译OpenMPI即可。

---

## 3. 在ORCA命令中启用内核绑定

ORCA运行命令中可以加入传递给OpenMPI的mpirun选项，例如执行`orca test.inp "--bind-to core"`会将`--bind-to core`传递给mpirun。该选项使得ORCA在利用mpirun运行并行模块时进行内核绑定，具体支持的参数可参考OpenMPI 3.1.x版mpirun的官方文档。

---

## 4. mpirun绑定选项--bind-to core的作用

mpirun选项`--bind-to core --map-by core`按照循环各个核的顺序绑定，例如进程0绑定第一个CPU的第一个核心，进程1绑定第一个CPU的第二个核心，以此类推。此设置确保每个进程只被指定到一个核心上运行。

---

## 5. mpirun绑定选项--bind-to socket的作用

mpirun选项`--bind-to socket --map-by socket`按照循环各个CPU（socket）的顺序绑定，例如进程0绑定第一个CPU的所有核心，进程1绑定第二个CPU的所有核心。此设置确保一个进程独占一个物理CPU上的所有核心。

---

## 6. 验证mpirun内核绑定设置

在mpirun命令中加入`--report-bindings`选项，可以在开始并行执行时显示当前的绑定情况。该选项用于确认实际的绑定方式是否符合用户设定的要求。

---

## 7. 使用rankfile文件精细控制内核绑定

若需精细控制绑定规则，可创建rankfile文件并通过mpiexec的`-rf`参数调用，例如`mpiexec -np 3 -rf /sob/miku.txt --report-bindings ./violet.x`。rankfile文件内容格式如`rank 0=Saber110 slot=1:0,1`，表示第0个进程与Saber110节点的第1号CPU的0、1两个核心绑定，进程、CPU和核心编号均从0开始。

---

## 8. 双路36核机器的逻辑核心编号顺序

双路共36核72线程机器的逻辑核心序号顺序为：第一个CPU的18个物理核心依次为0~17，第二个CPU的18个物理核心依次为18~35，第一个CPU的18个虚拟核心依次为36~53，第二个CPU的18个虚拟核心依次为54~71。实际计算中，0和36号逻辑核心对应同一物理核心，若两个MPI进程同时占用这两个逻辑核心，速度会降至约一半。

---

## 9. 使用rankfile实现两个ORCA任务独占不同CPU

在双路36核机器上运行两个各18核的ORCA任务，为避免资源争抢，可分别创建CPU1.txt和CPU2.txt两个rankfile文件。CPU1.txt包含`rank 0=2696v3 slot=0:0`到`rank 17=2696v3 slot=0:17`，CPU2.txt包含`rank 0=2696v3 slot=1:0`到`rank 17=2696v3 slot=1:17`。执行命令`orca MD1.inp "-rf /sob/CPU1.txt" > MD1.out`和`orca MD2.inp "-rf /sob/CPU2.txt" > MD2.out`，可使MD1和MD2分别仅在第一个和第二个CPU上运行，其中2696v3为主机名。

---

## 10. 使用rankfile实现四个ORCA任务分片运行

若需运行四个各9核的ORCA任务，可创建四个rankfile将两个CPU的核心各自分为两半。CPU1a.txt绑定slot=0:0-8，CPU1b.txt绑定slot=0:9-17，CPU2a.txt绑定slot=1:0-8，CPU2b.txt绑定slot=1:9-17。运行时分别指定这四个rankfile，可使四个任务分别占用第一个CPU的前9个、后9个核心以及第二个CPU的前9个、后9个核心，从而最大程度减小任务间的干扰。

---

## 11. 内核绑定对ORCA多任务耗时的实测影响

在B3LYP-D3(BJ)/def2-QZVP/RIJCOSX级别下对碱基对体系（29原子）的测试表明，跑两个18核任务时绑定与否对耗时影响可忽略。跑两个9核任务时，分别绑定在两个CPU上比绑定在同一CPU的不同核心上耗时更低。跑四个9核任务时，直接运行比绑定不同核心（0-8, 9-17, 18-26, 27-35）的耗时高出1/3以上。

---

## 12. 内核绑定对ORCA AIMD模拟的加速效果

对于ORCA的AIMD模拟，即使只同时跑两条轨迹（各9核），分别绑在两个CPU上运行的速度也显著快于不设置绑定直接提交两个任务。不绑定时提交第二个任务会导致第一个任务的每步耗时显著增加，而绑定不同核心时第一个任务的每步耗时几乎不受影响。

---

## 13. Gaussian多任务运行与CPU绑定的关系

Gaussian从16版开始支持%cpu设置可直接控制任务运行的CPU核心，但实测表明（M06-2X/def2-TZVP单点计算），将不同任务绑定在不同CPU核心上对耗时基本无影响。如果两个9线程任务分别绑定在同一个CPU的前9个和后9个核心运行，速度会明显不如照常提交，这与ORCA的测试情况一致。

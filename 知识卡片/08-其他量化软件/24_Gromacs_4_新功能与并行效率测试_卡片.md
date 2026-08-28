---
id: 24
title: Gromacs 4杂谈
url: http://sobereva.com/24
domain: 其他量化软件
topic: Gromacs_4_新功能与并行效率测试
cards: 13
---

# Gromacs_4_新功能与并行效率测试 — 知识卡片

## 1. 二维周期边界条件新支持

Gromacs 4支持仅xy方向的周期边界条件，以前版本只能靠在z方向增加很厚真空层来实现。该功能可以与WALL组合使用，因为WALL也只能用于二维周期边界条件。nwall设2就是在box的z值位置上加两个wall，此时可以用控压和ewald相关静电加和方法；设1就是z=0上一个wall。

---

## 2. 周期性分子支持

Gromacs 4新增了对周期性分子的支持。

---

## 3. Pull代码设置变更

Pull代码作了完全改写，以前的ppa文件不能用了，相关设置需在mdp文件里进行。

---

## 4. grompp与并行负载均衡

Gromacs 4的grompp去除了-np设置，不用事先指定tpr在各个节点上的负载分配。mdrun时默认使用域分解方法均衡负载，并行或串行都可以用一个tpr。grompp也去掉了shuffle和sort选项，对于默认的域分解方法已经没用了。在某些情况下不能用域分解，比如pbc=xy，此时还得用-pd (particle decomposition)。

---

## 5. Checkpoint机制与断点续算

Gromacs 4新增checkpoint设计，默认每隔15分钟更新一个.cpt文件。mdrun时用-cpt调整写入频率，-1表示不写。新.cpt生成后会将老的.cpt改名为_prev.cpt，再之前的就删掉。.cpt包含速度、坐标、能量，文件不大，只需有.cpt即可用`mdrun -v -deffnm a-sol-md4 -cpi sdf`完整继续断掉的工作。相比以前需用trjconv处理trr生成新tpr且受制于trr保存频率，此方法更方便。

---

## 6. 详细输出频率变更

Gromacs 4中mdrun的-v选项开启后默认每100步输出一次剩余时间和当前步数，以往是10步输出一次。

---

## 7. 高受力原子打印

mdrun新增了-pforce选项，可以设定受力大于多少的原子被打印出来。

---

## 8. Fortran编译错误的解决

目前的版本开了-enable-fortran选项会编译不过去，解决方法是把src/gmxlib/libxdrf.c的第1156行`#define XDR_INT_SIZE 4`挪到第68行，即在`#ifdef GMX_FORTRAN`之前。

---

## 9. 负载均衡参数-dlb

mdrun时开-dlb yes可以降低imb（不均衡负载），测试中imb由4%降到1%以下，性能提高约3%。默认是auto，似乎是没开，和-dlb no差不多。dlb只能用于-dd（默认的域分解），对不均匀体系效果更好。

---

## 10. Gromacs 3并行优化建议

很多人感觉Gromacs 4并行效率大增，实际上是因为不知道以前Gromacs应该开-shuffle -sort。用Gromacs 3.3.x最好用-enable-fortran，并行计算一定要在grompp时设-shuffle -sort，并开-dlb yes。

---

## 11. Gromacs 4编译优化倡议

根据测试数据，用Gromacs 4要用-enable-fortran选项。不开-enable-fortran时，Gromacs 4并行效能不如Gromacs 3.3.3开了shuffle；用了-enable-fortran后，Gromacs 4性能激变，达到Gromacs 3.3.3默认方式并行的3/2，串行版本也获益匪浅。

---

## 12. 并行性能测试数据 (4核)

在Q6600 oc 3.2平台测试体系gmxbench d.dppc (12万原子, 5000步, PME)，性能数据如下：PME gmx4 pc (no fortran) -np 4: Time 802s, 1.077 ns/day; PME gmx4 pf (fortran) -np 4: Time 611s, 1.414 ns/day; PME gmx3.3.3 pc -np 4 -shuffle -sort: Time 724s, 1.193 ns/day。gmx4 pf表现最优。

---

## 13. 串行性能测试数据

在Q6600 oc 3.2平台测试体系gmxbench d.dppc (12万原子, 5000步, PME)，串行性能数据如下：PME gmx4 c (no fortran): Time 2824s, 0.306 ns/day; PME gmx4 f (fortran): Time 1975s, 0.437 ns/day; PME gmx3.3.3 c: Time 2143.480s, 0.403 ns/day; PME gmx3.3.3 f: Time 2109.680s, 0.410 ns/day。gmx4开启fortran后速度超过3.3.3版本。

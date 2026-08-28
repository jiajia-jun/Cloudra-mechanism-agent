---
id: 40
title: Gromacs的pull code介绍(3.3.x+4.0.x)
url: http://sobereva.com/40
domain: 分子动力学与力场
topic: GROMACS_Pull_Code_参数设置与使用
cards: 32
---

# GROMACS_Pull_Code_参数设置与使用 — 知识卡片

## 1. Gromacs 3.3.x Pull Code的三种类型

Pull Code包含AFM pulling、Umbrella sampling和constraint三种类型。AFM是给原子一个外力，实际上是一个弹簧点在恒速远离，弹簧点拉动一组原子，其力取决于弹簧点与这组原子质心的距离和自己定义的力常数。Constraint是保持两组原子质心间距离不变(用SHAKE算法实现)，监视它们之间的限制力。Umbrella是给一组原子的质心加一个谐振势。

---

## 2. Gromacs 3.3.x Pull Code的输入输出文件

输入文件包含-pi pull.ppa（包含pull的控制代码）和-pn index.ndx（指定哪些原子组成哪些组）。输出文件包含-po pullout.ppa（形式化的输入文件的拷贝，类似mdout.mdp）和-pdo pull.pdo（记录pull的过程中的力、位置等的变化信息）。

---

## 3. Gromacs 3.3.x 定义组的方法

组定义方法包括com（每一步计算一次设定的组内原子的质心）、com_t0（每一步计算一次质心，但对原子穿越盒子导致质心位置突然变动进行校正）、dynamic（只有组内的在某个柱形空间范围内的才被当回事）以及dynamic_t0（同com_t0与com的关系，做校正而已）。

---

## 4. Gromacs 3.3.x Pull Code一般参数设置

verbose默认为no，设yes会往.pdo多写一些东西并通过stderr多输出；Skip steps默认为1，控制.pdo输出频率；runtype可设afm、contraint、umbrella；ngroups设定总组数（不含参考组），最大20；reference_group设定参考组，若不定义则外力从绝对坐标而来；若用参考组，pull组相对于参考组，体系质心不因pull而平移；若不定义且comm_mode=none，体系质心会移动。

---

## 5. Gromacs 3.3.x reference_group与体系质心控制

如果用了参考组，则pull组都是相对于参考组的坐标的，而体系质心不会因为pull了某个东西而平移，字面上看是参考组不动，实际上与pull组相反方向走。如果不定义参考组，pull组在绝对坐标中pull，如果此时设了comm_mode = none，就会导致体系质心也发生移动，若开了消平动，质心基本还是原处。

---

## 6. Gromacs 3.3.x weights与reftype参数

weights_1/weights_2设定pull组的权重，reference_weights设定参考组的权重，权重对决定质心位置和相关原子受力有影响。reftype定义参考组的类型，可以是com、com_t0、dynamic、dynamic_t0。

---

## 7. Gromacs 3.3.x reflag与pulldim参数

reflag设为1表示参考组的位置由许多步取平均得到。pulldim设定往哪个方向pull，例如N N Y代表Z方向，默认都是Y；设了几个Y，在.pdo里面就会有几个维度的数据；不管afm_dir1怎么设的，这里是N的方向就被忽略。

---

## 8. Gromacs 3.3.x Dynamic参考组选项参数

r=0设定使用dynamic/dynamic_t0类型参考组时的柱形半径。rc=0设定在r至rc的范围内的粒子权重为1至0，建议r=1，rc=1.5。update=1设定多少步更新一次dynamic参考组。

---

## 9. Gromacs 3.3.x Constraint模式参数

constraint_direction设定限制的方向，默认为0.0 0.0 0.0（没有方向，限制两个组之间距离）。constraint_distance1/2设定最初的限制距离，默认是0（根据初始坐标决定）。constraint_rate1/2设定距离限制的变化速率，单位nm/ps，默认为0。constraint_tolerance设定距离限制的容忍限（即SHAKE的tolerance），默认1e-6。

---

## 10. Gromacs 3.3.x AFM模式参数详解

afm_rate1/2设定每个组弹簧移动的速率(nm/ps)。afm_k1/2设定每个组的弹簧力常数(KJmol^-1*nm^-2)。afm_dir1/2设定弹簧点移动的向量（相对于当前位置），若设参考组则弹簧点随之动保持相对位置不变。afm_init1/2描述弹簧最初位置相对于参考组的向量，若想让开始时力为0，必须设为pull组相对于参考组的值。

---

## 11. Gromacs 3.3.x AFM模式示例说明

不设参考组，afm_k1 = 1 -1.0 0，pulldim = N Y N，afm_rate1 = 0.5，不设afm_init1，则pull组会一直朝自己的y负方向走，不主动向x方向走即便afm_dir1设了这个方向，此时弹簧点绝对坐标应为0 -0.1 0，0 -0.2 0等变化，但因x和z方向是N所以不会。但如果pulldim都设Y，则pull不仅y随弹簧点的y增大而增大，由于弹簧点的x和z一直都是0，x和z也逐渐趋近于0，pull组会追着从绝对坐标0点开始走的弹簧点。

---

## 12. Gromacs 3.3.x Umbrella模式参数

Umbrella给pull组施加谐振势来维持pull组相对于参考组的位置，如果参考组移动了，pull组也会随之移动；如果没有定义参考组，pull组就处于绝对坐标中，参考组被设为[0 0 0]。k1/k2指定每个pull组的力常数(kJ*mol^-1*nm^-2)。pos1/pos2指定pull组被限制到的位置，此值是相对于参考组的。

---

## 13. Gromacs 3.3.x Umbrella模式位置计算示例

不设参考组，pos1设0.0 5.0 0.0，当.pdo中的距离很小后，检查pull组的y值，应当很接近于5.0，相当于把pull组往某个坐标点拉。设参考组，pos1设0.0 5.0 0.0，当.pdo中的距离很小后，检查pull组的y值和参考组的y值，其差应当很接近于5.0；动的时候参考组和pull组一起在对称地动，并非只动pull组。

---

## 14. Gromacs 3.3.x Umbrella与AFM的本质区别

总的来说，umbrella和afm实际上是一样的，区别只是umbrella的弹簧点是不相对移动的（相当于afm_rate1=0，没有afm_dir1选项），afm的弹簧点是相对移动的。pull组始终是向着弹簧点坐标受力，pulldim控制这个力的哪些分量被表达出来。

---

## 15. Gromacs 3.3.x 弹簧点位置计算逻辑

弹簧点的t=0位置(原始位置)都是这两项的矢量和：参考组(reference_group)+相对参考组的初始位置(afm_init1或pos1)。弹簧点是从原始位置开始根据afm_dir移动。如果参考组不是固定的坐标而是一个组，则这个组的位置变化会加到弹簧点上。

---

## 16. Gromacs 3.3.x Pull Code输出结果解读

时间单位都是ps，位置都是nm。对于Constraint，如10.5 -81.2，分别代表时间和限制力，负数说明pull组与参考组相互吸引。对于AFM，如10.5 3.5 3.63 3.6，分别代表时间，参考组的位置，pull组的位置，弹簧的位置（只有pulldim设为Y的维度的结果才会被输出）。对于Umbrella，如10.5 0.002，分别代表时间和pull组相对于其限定的位置。

---

## 17. Gromacs 模拟崩溃排查建议

如果跑起来没多久就出现一堆东西，提示write pdb之类，说明体系崩了，就把力常数设小点。并且检查是否拉伸过程合理，比如拉伸过程中是否出现过度碰撞、挤压。

---

## 18. Gromacs 4.0 Pull Code的主要变化

Gromacs 4中pull代码重写，参数定义从pull文件改为.mdp中定义。拉伸方式把afm和umbrella合并为umbrella（因为本质一样），新增加了常力拉伸(constant_force)，即外加力大小一直不变。pull_vec1和pull_init1的格式是坐标向量如1.0 2.0 3.0。参数对应关系为：runtype->pull，pulldim->pull_dim，reference_group->pull_group0，group_x->pull_groupx，pos1/afm_init1->pull_init1，afm_dir1->pull_vec1，afm_rate1->pull_rate1，ngroups->pull_ngroups，k1/afm_k1->pull_k1。

---

## 19. Gromacs 4.0 pull_geometry=position模式（Umbrella）

position模式等价于3.3.3的afm，即弹簧点位置是参考组位置+pull_init+time*pull_rate*pull_vec，朝着弹簧点拉。如果将pull_rate1设为0，则相当于弹簧点位置不变，就等价于3.3.3版本中的umbrella。

---

## 20. Gromacs 4.0 pull_geometry=distance模式（Umbrella）

distance模式始终顺着连接参考组与pull组向量的方向拉，弹簧点只会在参考组与pull组连线方向上移动。pull_init1只能设一个数（弹簧点t=0时与参考组的距离）。pull_rate1是弹簧点在连线方向上的移动速度（正负控制远离或靠近）。pull_vec1对弹簧点运动方向无任何影响。

---

## 21. Gromacs 4.0 pull_geometry=direction模式（Umbrella）

direction模式定义一个过pull组在t=0时坐标的向量（pull_vec1方向）。pull_init只能设一个数。设参考组在这个向量上投影点是P，则弹簧点的位置是P+pull_init*uni(pull_vec)+time*pull_rate1*pull_vec1，其中uni()代表求单位向量。

---

## 22. Gromacs 4.0 Pull Code参考组移动的影响

上述模式都是假设参考组是绝对坐标或者固定住参考组，如果参考组在拉伸过程中位置变化，弹簧点位置也相应变化。

---

## 23. Gromacs 4.0 pull=constraint与geometry结合

使用pull=constraint结合三种模式的情况和umbrella一样，区别只是将pull组位置用约束算法固定在弹簧点位置上，而不是被弹簧点拉着走。比较常用的是distance模式，这个模式可使参考组与pull组之间的距离固定保持不变(即pull_init1)或者刻意让其逐渐改变(即pull_init1+time*pull_rate1)，而它们之间的相对角度方位可随意变化。

---

## 24. Gromacs 4.0 constant_force模式注意事项

注意，拉力大小始终不变，为pull_k1。无论哪种模式皆没有弹簧点的概念，故pull_rate1、pull_init1对结果皆无影响。

---

## 25. Gromacs 4.0 constant_force+position模式

position模式下pull组由t=0时的位置向-1,-1,-1方向拉（不是指朝着(-1,-1,-1)坐标）。pull_group0、pull_vec1的设定不对结果产生影响。这种模式不适合constant_force。

---

## 26. Gromacs 4.0 constant_force+distance模式

distance模式下如果参考组设的是一个组，则无论何时，pull组始终朝着参考组方向拉，若拉伸过程中经过了参考组，则拉力方向反过来。如果参考组是绝对坐标(0,0,0)，则拉力方向始终是t=0时pull组朝着参考组的方向，即便pull组可能已经经过了参考组。pull_vec1的设定不对结果产生影响。

---

## 27. Gromacs 4.0 constant_force+direction模式

direction模式将pull组（将其假想为坐标原点）向pull_vec1的反方向拉。pull_group0的设定不对结果产生影响。

---

## 28. Gromacs 4.0 Pull Code的对称运动与pull_dim控制

上述六种组合中，假定参考组位置固定，若不进行位置固定，则group0与group1是对称运动的，质心位置不变（包括constant_force+direction这样不直接涉及到group0的模式也是如此），两个组相当于等价。pull_dim控制哪个方向上的力真正生效，最终在pull组上真正生效的力是pull_dim允许方向上的分量。但如果是constant_force，则在pull_dim方向上的总受力仍是pull_k1。

---

## 29. Gromacs 4.0 三种geometry模式总结

position本意是相对于参考组位置设定一个点，以其为依据进行拉伸操作。用distance时，拉伸的方向是根据pull组与参考组连线的瞬时方向。direction是直接定义pull组的拉伸方向。常用的组合模式是umbrella+position可固定势阱位置；constraint+distance可约束pull组与参考组的距离；constant_force+direction方便地直接将pull组往某个方向拉。

---

## 30. Gromacs 4.0 pull_start参数含义

另外，pull_start如果设为yes，则最终的pull_init相当于你设的pull_init加上被pull组与参考组之间质心的距离矢量。

---

## 31. Gromacs 4.0 mdrun输出文件选项

mdrun时利用-pf可以指定输出的包含pull组的时间和对应时刻受力的xvg文件名（输出的是外加的pull力，而非这个组的净受力；若为position模式会输出受力xyz分量，distance和direction只输出总受力）。-px可以指定输出的包含pull组的坐标和对应时刻受力的xvg文件名，第一列是时间，第2、3、4列是pull_group0的xyz绝对坐标，5、6、7列是pull_group1相对于pull_group0的xyz坐标。它们的输出频率使用pull_nstfout和pull_nstxout选项控制。

---

## 32. Gromacs 4.0 同时Pull多个组

设定方法同pull一个组，写pull_ngroups=N，增加定义pull_group2、pull_init2、pull_k2、pull_rate2；pull_group3、pull_init3...... 受力-时间和坐标-时间的.xvg文件内也会输出这些组。

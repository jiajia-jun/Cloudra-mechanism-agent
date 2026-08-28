---
id: 10
title: 解析gromacs的restraint、constraint和freeze
url: http://sobereva.com/10
domain: 分子动力学与力场
topic: GROMACS中限制、约束与冻结机制解析
cards: 23
---

# GROMACS中限制、约束与冻结机制解析 — 知识卡片

## 1. GROMACS坐标固定方式分类

GROMACS中人为固定坐标有三大类方式：restraint、constraint和freeze，这三种方式各自具有不同的特点和应用场景。

---

## 2. 限制的基本原理

限制的特点是可以让被限制的东西在一定范围内运动，而非彻底固定住，实际上就是施加一个谐振势来限制其移动。

---

## 3. 位置限制

位置限制是常说的正式MD前首先要进行的限制性动力学，在posre.itp里面的[ position_restraints ]中定义，默认相对于最初位置进行限制。

---

## 4. 两对原子间的角度限制

角度限制中一类是两对儿原子间角度的限制，用[ angle_restraints ]来指定，示例格式为[ angle_restraints ]; i j k l type theta0 fc multiplicity / 651 1211 1683 1211 1 67.0 1500 1。此示例限制651-1211与1683-1211原子对儿之间的夹角在67度附近，力常数为1500，其中type无用。

---

## 5. 原子与z轴的角度限制

角度限制另一类包括一对儿原子与z轴夹角角度的限制，用[ angle_restraints_z ]来指定，示例格式为[ angle_restraints_z ]; #1 #2 type theta0 fc multiplicity / 22 45 1 90 500 2。此示例限制22与45号原子的连线与z轴垂直，力常数是500，多重性是2，使得90度夹角时候限制势能最低，0和180度时最高，其中type无用。

---

## 6. 二面角限制定义

二面角限制使用[ dihedral_restraints ]段落来定义，实际上improper项就是用二面角限制方式限制的，示例格式为[ dihedral_restraints ]; i j k l type label phi dphi kfac power / 5 7 9 15 1 1 180 0 1 2。此示例中被限制的是5,7,9,15原子组成的二面角，type总是1，label没用，phi是参考角，dphi是超过参考角多少度开始使用限制势，power没用，kfac乘上mdp中的dihre_fc将作为限制势力常数。

---

## 7. 二面角限制的mdp设置

使用二面角限制时需要在mdp中加入相关参数，示例设置为dihre = simple / dihre_fc = 100 / dihre_tau = 0.0 / nstdihreout = 50。

---

## 8. 距离限制定义

距离限制在[ distance_restraints ]里面定义，示例格式为[ distance_restraints ]; i j type index type low up1 up2 fac / 10 16 1 0 1 0.0 0.3 0.4 1.0。type总是1，index是计算的顺序，如果几个项index都一样就同时计算，low,up1,up2分别指图上的r0,r1,r2，原子间距离在low至up1区间内是不受限制的，fac是指这个因子乘上mdp中disre_fc作为限制势力常数。

---

## 9. 距离限制的谐振子定义方式

也可以定义两个原子在[ bonds ]里用bond type 6，就是个和普通键一样的谐振子势，但是这两个原子间被认为没有键连。

---

## 10. 限制定义的位置要求

应当注意以上限制方式中[]段落应当紧接着写在被限制分子的.itp后面（或者说对应的[ moleculetype ]后面），这样程序才知道其中的原子编号指的是哪种分子中的原子。

---

## 11. 约束的特点与类型

约束用shake或lincs方法固定住原子之间的相对位置，固定的几何关系是绝对不变的，分为两种类型：type 1和type 2的效果其实一样，但是type 1被认为将这两个原子键连了，而type 2没有键连。

---

## 12. 约束类型对相互作用计算的影响

一般被键连的原子间都不计算相互作用，在[ moleculetype ]里定义nrexcl来控制相隔几个键内的原子间不计算相互作用，即type 1时一般就不计算这两个原子间的非键作用了，而type 2时仍然计算。

---

## 13. 约束算法设置

用哪种约束算法用.mdp里的constraint_algorithm设定，默认lincs；.mdp里的constraints = all-bonds也是应用这种约束方法，即约束住所有[ bonds ]项，原本[ bonds ]的设定就被覆盖了，即不体现成键效果，只体现约束效果。

---

## 14. 自定义约束项定义

自定义约束项可以在拓扑文件中这么写: [ constraints ] / 1 8 2 0.153 //原子1 原子2 type 约束的距离(0.153nm)。之后1 8原子距离会固定保持在0.153nm，即便1 8原子在[ bonds ]中定义是成键的也是如此。

---

## 15. 自定义约束与none参数的关系

注意，.mdp里如果写constraint=none，只是说批量约束hbonds、all-bonds等没有了，在拓扑文件中自定义的constraint约束项仍然生效。

---

## 16. 水分子的刚性约束

在默认情况下，gromacs的水的结构是被settle算法约束住的，也就是所说的rigid water，settle就是专用于水的约束算法，在spce.itp里面[settles]即是定义，不计算分子内氢、氧彼此之间的相互作用。

---

## 17. 柔性水的定义与影响

如果.mdp里面设define=-DFLEXIBLE，也就是激活了#ifdef FLEXIBLE后面那段，则不用settle算法约束结构，而是照常按照谐振势的键长键角项控制水的结构。-DFLEXIBLE开不开对溶质没什么影响，对计算速度也没什么影响。

---

## 18. 不建议使用柔性水的情况

除了能量最小化外，都不要用-DFLEXIBLE，因为拟合水、力场参数的时候都一般是认为水是刚性情况下进行的，即约束住键长键角，开了FLEXIBLE实际上参数还得再作调整。

---

## 19. GROMACS 4中能量最小化的处理

在gmx4中，在能量最小化时自动是限制方法，就没必要设-DFLEXIBLE了，从此可忘掉它；.mdp中constraints以及constraint_algorithm设定皆与水的约束无关，除非define=-DFLEXIBLE，否则水都是用settle算法约束住。

---

## 20. 冻住的功能与耗时

冻住(freeze)是彻底冻在最初坐标，一点也不动，但仍然计算与其它原子间的相互作用，所以并不会省时间，除非是写进[ exclusions ]。

---

## 21. 冻住的参数设置

使用冻住时在.mdp里面定义，例如：freezegrps = protein 设蛋白冻住 / freezedim = Y Y Y 设冻住的方向，分别对应X Y Z轴。

---

## 22. 冻住与其他参数的兼容性

同时使用freezegrps, constraints, pressure coupling可能会有问题，不要组合使用。

---

## 23. 绝对坐标与相对坐标限制的区别

注意绝对坐标与相对坐标的限制方式的不同，比如想保持一个结构的刚性，用位置限制或freeze是原地不动，而通过约束方法对分子内的结构进行约束，结构仍然可以有整体平动和转动，应根据实际情况选择。

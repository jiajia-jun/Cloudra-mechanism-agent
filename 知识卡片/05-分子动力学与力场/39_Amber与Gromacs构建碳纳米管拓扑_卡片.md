---
id: 39
title: Amber与Gromacs读入碳纳米管的方法
url: http://sobereva.com/39
domain: 分子动力学与力场
topic: Amber与Gromacs构建碳纳米管拓扑
cards: 7
---

# Amber与Gromacs构建碳纳米管拓扑 — 知识卡片

## 1. Amber读入碳纳米管的结构预处理与原子命名

碳纳米管结构较大且原子名相同，需使用文本编辑器（如Ultraedit）开启列模式，选定原子名C后的两列，插入数字将原子名修改为C1至C240并保存为tubename.pdb。leap要求相同残基中每个原子都有独立的名字，此步骤是满足leap读入要求的必要操作。

---

## 2. Amber中碳纳米管成键与原子类型设定

在xleap中加载gaff力场和tubename.pdb后，使用bondbydistance命令（默认2埃内成键）建立碳碳键，并通过脚本运行`set a.1.$i type c2`将240个C原子全部设为c2原子类型。该操作假定C原子使用gaff力场的c2原子类型对应的力场参数。

---

## 3. Amber中批量设定原子类型的脚本操作

由于leap不支持shell脚本循环，需在shell下运行for循环脚本生成包含`set a.1.$i type c2`的leapdo文件，随后在leap中运行source leapdo批量设置原子类型。脚本命令为`for ((i=1;i<=240;i=i+1)); do echo "set a.1.$i type c2" >> leapdo; done`。

---

## 4. Gromacs中x2top工具的n2t文件编写规则

编写n2t文件（如ffgmx2.n2t）以定义原子类型，格式如`C CX 0.0 12.011 3 C 0.14 C 0.14 C 0.14`，表示将与周围3个C原子距离在0.14nm左右的C原子识别为CX类型。文件需包含与1个、2个、3个C原子成键的C原子的定义，所有原子在此例中都被设为CX类型。

---

## 5. Gromacs中使用x2top生成碳纳米管拓扑文件

运行命令`x2top -f tube.pdb -o tube.top -ff gmx2`生成包含全部键结项的tube.top文件，参数-ff指定使用ffgmx2力场。若程序卡住不动，可尝试加-noparam解决；若使用ffgmx力场无法正确根据距离判断成键，应换用其他力场。

---

## 6. Gromacs中x2top自动添加力场参数的默认行为

x2top默认自动在.top里添加力场参数，平衡距离/键角/二面角取自tube.pdb中的几何数值，键/键角/二面角力常数默认值分别为400000/400/5。可以使用-kb、-kt、-kp参数设定这些力常数，或使用-noparam参数阻止自动添加参数。

---

## 7. Gromacs中碳纳米管力场参数的补充方法

若将C原子设为力场中没有的CX类型，需在ffgmx2nb.itp的[atomtypes]和[nonbond_params]中添加VDW参数。若使用了-noparam，还需在.top文件内直接添加或通过include.itp文件在[bondtypes]、[angletypes]、[dihedraltypes]中添加键结参数。

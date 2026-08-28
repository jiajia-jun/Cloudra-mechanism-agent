---
id: 39
title: Amber与Gromacs读入碳纳米管的方法
url: http://sobereva.com/39
domain: 分子动力学与力场
topic: Amber与Gromacs构建碳纳米管拓扑
cards: 1
---

# Amber与Gromacs构建碳纳米管拓扑 — 知识卡片

## 1. Amber中碳纳米管原子的近似电荷处理

碳纳米管结构大且仅含C原子，若不考虑边界问题，可将全部电荷设为0，这种近似对结果真实性影响不大。碳纳米管适合当作一般小分子处理，不宜也没必要使用antechamber。

## Amber中重命名碳纳米管原子名的列操作方法
Amber的leap要求同一残基中每个原子有独立的名字，需使用Ultraedit的列模式重命名。操作步骤为开启列模式，选定从第1个原子到最后一个原子的第15和16列（即原子名C后面的两列），选Column-Insert Number，将原子名改为C1至C240，保存为tubename.pdb。

## Amber中碳纳米管的结构加载与成键命令
将C原子使用gaff力场的c2原子类型对应参数，依次运行xleap -f leaprc.gaff、a=loadpdb /sob/tubename.pdb、bondbydistance a。bondbydistance默认在2埃内成键，碳纳米管的碳原子会正常成键，可用edit a检查。

## Amber中批量设置碳纳米管原子类型的脚本生成
将碳纳米管内全部240个原子设成c2原子类型需生成脚本，因leap不支持shell循环。写脚本for ((i=1;i<=240;i=i+1)); do echo "set a.1.$i type c2" >> leapdo; done，在shell下运行得到leapdo，然后在leap里运行source leapdo。

## Amber中碳纳米管力场参数的检查与保存
在leap中运行check a进行参数检查，若需修改力场参数或缺少参数，可edit gaff添加和修改。最后运行saveamberparm a tube.top tube.inpcrd保存文件。

## Gromacs中使用x2top处理碳纳米管
小分子常用的prodrg不适合处理碳纳米管，应使用x2top工具，它专用于构建结构规律性很强的体系。不同版本x2top的bug和“规矩”不同，此处使用gromacs4.0.4的x2top。

## Gromacs中x2top的n2t文件格式定义
n2t文件用于定义原子类型判断，例如C CX 0.0 12.011 3 C 0.14 C 0.14 C 0.14。含义为如果C原子与周围3个C原子的距离都在0.14nm左右（约正负10%），则视为CX原子类型，电荷0.0，相对原子质量12.011，行数对应配位数。

## Gromacs中x2top的运行命令与常见问题
运行命令为x2top -f tube.pdb -o tube.top -ff gmx2，-ff代表力场。若程序卡住不动，可尝试加-noparam解决；若使用ffgmx力场可能无法正确根据距离判断成键，应换用别的力场执行。

## Gromacs中x2top自动添加力场参数的默认值
x2top默认在.top里根据tube.pdb中的几何结构添加力场参数，平衡距离/键角/二面角取自结构文件。键/键角/二面角力常数默认为400000/400/5，可分别用-kb、-kt、-kp设定，若不想自动添加可加-noparam。

## Gromacs中碳纳米管VDW参数与键结参数的定义方法
若n2t定义了力场中没有的原子类型CX，需在ffgmx2nb.itp的[atomtypes]和[nonbond_params]里添加VDW参数。若加了-noparam，需在.top里逐项添加键结参数，或单独写.itp文件include进.top，详细讨论见《gromacs决定力场参数的方式》（http://sobereva.com/4）。

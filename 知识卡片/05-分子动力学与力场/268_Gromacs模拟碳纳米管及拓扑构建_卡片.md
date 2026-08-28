---
id: 268
title: 使用Gromacs模拟碳纳米管的一个简单例子
url: http://sobereva.com/268
domain: 分子动力学与力场
topic: Gromacs模拟碳纳米管及拓扑构建
cards: 12
---

# Gromacs模拟碳纳米管及拓扑构建 — 知识卡片

## 1. 碳纳米管模拟方法现状

本文的做法如今已经完全过时，如今强烈建议用Sobtop建立纳米球/管/板的拓扑文件，比x2top灵活得多，参考网页里的例子。北京科音分子动力学与GROMACS培训班里有模拟纳米管、纳米板的完整讲解和详细的例子。

---

## 2. 示例文件与版本信息

本文使用Gromacs 4.6.5，文中的CNT10指的是一个普通的碳纳米管，cnt10.pdb是其结构文件。结构文件可以用Nanotube Modeler很容易地产生，文中涉及到的文件存放在指定的rar压缩包中。

---

## 3. 自定义力场识别规则文件

在gromacs目录下的"share/gromacs/top/gromos54a7.ff"文件夹中新建文件atomname2type.n2t，并复制指定内容。这意味着当在G54A7力场下使用x2top生成拓扑文件时，如果一个碳原子有一个或两个或三个距离约为0.142nm的邻居，该碳原子将被识别为CR1原子。

---

## 4. 原子类型CR1的物理意义

CR1原子类型对应G54A7力场中芳香族CH基团中的碳原子。该原子类型适用于表示碳纳米管碳原子与环境原子之间的范德华相互作用。

---

## 5. 使用x2top生成拓扑文件

运行命令`g_x2top -f cnt10.pdb -o CNT10.top -ff select -nopbc -name CNT10 -kb 400000 -kt 600 -kp 150`以生成CNT10.top。从力场列表中选择G54A7，当前文件夹下将生成分子名称为CNT10的拓扑文件，必须指定-nopbc，否则x2top无法正常工作。

---

## 6. x2top命令参数含义

-kb、-kt和-kp参数用于定义键、角和二面角项的力常数。这些力常数主要用于在模拟过程中保持碳纳米管的近似刚性结构，因此可以简单地设置为一个较大的值。

---

## 7. 拓扑文件中的键参数格式

在CNT10.top的[ bonds ]字段中，第4列是基于输入几何结构确定的平衡长度，第5列是由-kb设置的力常数。最后两列是冗余的，可以直接忽略甚至删除，[ angles ]和[ dihedrals ]字段的内容与[ bonds ]类似。

---

## 8. 力常数的设置注意事项

如果希望碳纳米管更灵活（或刚性），可以减小（或增加）二面角力常数。据目前所知，没有力场包含专门为碳纳米管建模优化的键、角和二面角参数。

---

## 9. 真空中的MD模拟步骤

运行`grompp -f md_vacuum.mdp -c cnt10.pdb -p CNT10.top -o md_vacuum.tpr`和`mdrun -v -deffnm md_vacuum`来进行真空中的分子动力学模拟。

---

## 10. 溶剂化盒子构建命令

运行`editconf -bt triclinic -f cnt10.pdb -o cnt10_box.gro -d 2`构建三斜盒子，运行`genbox -cp cnt10_box.gro -cs spc216.gro -o cnt10_wat.gro -p CNT10.top`添加溶剂。在CNT10.top的头部添加句子`#include "gromos54a7.ff/spce.itp"`以引入水模型。

---

## 11. 溶液中的MD模拟步骤

运行`grompp -f md.mdp -c cnt10_wat.gro -p CNT10.top -o md.tpr`和`mdrun -v -deffnm md`来开始溶液中的分子动力学模拟。

---

## 12. 碳纳米材料模拟的通用性

模拟石墨烯和碳球的过程与本文描述的碳纳米管模拟没有任何区别，只需将文中的cnt10.pdb替换为相应的结构文件即可。石墨烯结构可由Nanotube Modeler产生，富勒烯结构可利用其自带的库或CaGe软件生成。

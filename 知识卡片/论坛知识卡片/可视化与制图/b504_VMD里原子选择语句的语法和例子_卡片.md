---
key: b504
title: VMD里原子选择语句的语法和例子
url: http://sobereva.com/504
domain: 可视化与制图
source: blog
year: 2019
cards: 8
---

# VMD里原子选择语句的语法和例子 — 知识卡片

## 1. VMD原子选择语句功能与应用场景

VMD原子选择语句用于选择满足特定要求的原子，是图形窗口显示特定区域、保存坐标文件及编写分析脚本的基础功能。该语句在Graphics-Representation、File-Save coordinates及Radial Pair Distribution Function等插件中广泛应用，能够创建atomselect对象或作为命令参数。VMD的选择语句与GROMACS的selections语法高度一致，但在具体细节上存在差异。

---

## 2. VMD常用单关键词

VMD提供单关键词直接选择特定原子，例如all（所有原子）、noh（氢以外的原子）、protein（蛋白）、nucleic（核酸）、water（水）以及carbon、oxygen等元素名。部分单关键词如hetero实际上是复合选择语句（如not (protein or nucleic)）。若输入文件中残基名非标准（如FFF），water等关键词可能无法正确识别对应区域。

---

## 3. VMD一般关键词与属性参数

一般关键词通过属性选取原子并需接参数，包括name（原子名）、index/serial（原子序号，分别从0/1开始）、resname（残基名）、residue/resid（残基编号，分别从0/1开始）、chain（链名）以及x、y、z（坐标）等。属性可用值可在Selections标签页查看，不同属性对输入文件格式有特定要求，如charge需mol2/pqr文件，beta需pdb文件，type需拓扑文件。

---

## 4. VMD选择语句逻辑与运算规则

选择语句支持使用and、or、not逻辑关系及括号指定优先级，并可用空格分隔多个参数或使用to选择范围（如index 5 to 200）。语句支持数学函数（sqrt, abs, sin等）、运算符（+ - * /, **）及比较符（<, <=, =, >=, >, !=）。双引号内字符视为整体且支持正则表达式，单引号用于避免特殊字符（如*或+）被转义。

---

## 5. VMD选择语句示例（名称与残基）

通过name和resname组合可选取特定原子或残基，例如name CA CB、name "CA|CB"、name "C[AB]"选取CA和CB原子，resname ALA CYS ARG选取丙氨酸、半胱氨酸和精氨酸。对于含特殊字符的名称，如name 'O5*'或resname 'CA2+'，必须使用单引号括住以避免转义。

---

## 6. VMD选择语句示例（坐标与几何区域）

利用坐标变量和数学公式可定义几何区域，例如x>1 and x<8 and y>24 and y<35 and z>1 and z<5选取矩形区域原子，sqr(x-5)+sqr(y+4)+sqr(z) < sqr(5)选取球体区域原子，((x-33)^2+(y-14.5)^2)<12^2 and z<40 and z>10选取柱形区域原子，x+y+z<80选取斜切面内侧原子。

---

## 7. VMD选择语句示例（距离与拓扑关系）

使用within、exwithin、withinbonds可基于距离或键数选择原子，例如within 6 of protein选取蛋白质6埃以内原子，water within 5 of residue 8 to 44选取距离8-44号残基5埃以内的水，not {oxygen and numbonds=0}扣除孤立氧原子，maxringsize 6 from protein选取蛋白中六元及以下环上的原子。

---

## 8. VMD选择语句中的same与动态更新机制

same关键字用于根据属性扩展选区，例如same residue as {protein within 5 of nucleic}将与核酸距离5埃以内的蛋白原子所在的完整残基全部选中。涉及坐标、速度等变量的选择属于动态选区，需在Representation界面的Trajectory标签页勾选Update Selection Every Frame或在相关插件中勾选Update Selections，以使选区随轨迹帧号动态更新。

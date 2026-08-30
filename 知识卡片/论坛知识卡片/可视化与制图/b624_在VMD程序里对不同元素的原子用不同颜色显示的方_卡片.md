---
key: b624
title: 在VMD程序里对不同元素的原子用不同颜色显示的方法
url: http://sobereva.com/624
domain: 可视化与制图
source: blog
year: 2021
cards: 11
---

# 在VMD程序里对不同元素的原子用不同颜色显示的方法 — 知识卡片

## 1. VMD原子的name与element属性

VMD中每个原子具有name和element两种属性，name指代原子名称，element指代元素周期表中的元素符号。在VMD文本窗口输入[atomselect top all] get name可列出所有原子的name属性，输入[atomselect top all] get element可列出所有原子的element属性，输出顺序均按原子序号排列。

---

## 2. xyz文件在VMD中的属性读取

标准xyz文件第一列为元素符号，载入VMD后name和element属性值均为元素符号。若xyz文件记录的是原子名（如HG3），载入后name为原子名，element由VMD根据字母猜测（如HG3被猜为Hg），若无法猜测则element为X。VMD通过原子名猜测元素容易出错（如CA会被误认为钙Ca）。

---

## 3. gro和mol2文件在VMD中的属性读取

gro文件（GROMACS结构文件）和mol2文件记录的是原子名（如CA、CB、CG），载入VMD后name属性为这些原子名，element属性均为X。

---

## 4. pdb文件在VMD中的属性读取

标准pdb文件第三列为原子名，最后一列为元素符号，载入VMD后可分别提供name和element信息，element无需猜测。若pdb文件缺少记录元素符号的最后一列，载入后element属性均为X。

---

## 5. cub文件在VMD中的属性读取

cub文件不记录原子名但记录原子序数，载入VMD后name和element属性均为元素符号。

---

## 6. VMD原子的type属性

VMD原子具有type属性记录原子类型，可用[atomselect top all] get type查询。载入amber拓扑文件prmtop或mol2文件后，type属性为文件记录的原子类型；载入xyz、gro、pdb文件后，type属性与name相同；载入cub文件后，type、name和element属性均相同。

---

## 7. VMD中Name着色方法的默认逻辑

在VMD的Graphics - Representation中，默认Coloring method为Name，即根据原子name属性决定颜色。查看Graphics - Colors的Categories下的Name设置可见，只要name首字母相同（如C和Cl）就会使用相同颜色（如cyan），导致不同元素颜色无法区分。

---

## 8. VMD中按Element着色的操作

在Graphics - Representation中将Coloring method改为Element，即可根据元素属性对不同元素进行着色区分。若需修改特定元素颜色，可进入Graphics - Colors，在Categories选Element，点击对应元素（如Cl）并选择颜色（如green）。

---

## 9. 按Element着色对输入文件的要求

只有载入能直接提供元素信息的文件（如pdb、xyz），才能在VMD中按照element属性进行着色。gro文件因无法提供元素信息只能按name着色，若需按元素着色需将其转为符合规范的pdb文件（补上元素信息列），或利用gmx editconf将含元素信息的tpr文件转为pdb文件载入。

---

## 10. 通过vmd.rc设置VMD默认着色方式

在vmd.rc文件末尾添加mol default color Element和color Element Cl green，可将默认着色方式设为Element且Cl元素默认为绿色。添加mol default style CPK可设置默认显示方式为CPK。

---

## 11. VMD着色规则文件colordefs.dat

VMD的colordefs.dat文件记录了默认着色规则，Windows版位于VMD\scripts\vmd，Linux默认安装版位于/usr/local/lib/vmd/scripts/vmd。该文件包含Name和Element的颜色定义，可直接修改（如将Element Cl ochre改为Element Cl green），但此设置优先级低于vmd.rc中的命令。

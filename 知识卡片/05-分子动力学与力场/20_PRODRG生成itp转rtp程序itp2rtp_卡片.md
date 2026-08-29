---
id: 20
title: 将prodrg得到的itp转化为rtp的程序itp2rtp V1.0
domain: 分子动力学与力场
topic: PRODRG生成itp转rtp程序itp2rtp
cards: 3
---

## 1. itp2rtp V1.0程序功能与用途
itp2rtp V1.0用于将prodrg生成的.itp文件转换为.rtp文件。通过prodrg获得的小分子.itp文件中原子顺序总是发生变化，无法直接include使用；对于分子数众多的磷脂层等情况手动修改十分麻烦。此程序对.itp格式进行简单转换，输入.itp文件得到result.rtp，将其内容拷进力场的.rtp中，即可使pdb2gmx识别该分子。

---

## 2. 转换原理与原子顺序匹配
pdb2gmx读取的结构如果原子顺序和itp中不符，输出的结构会按照rtp中的顺序进行排列，从而与itp相符。使用这样排列的结构，就可以直接在拓扑文件中include小分子的.itp文件。

---

## 3. 程序使用方法与输入要求
使用方法为输入文件名即可，例如c:\pop.itp。输入文件pop.itp必须是由prodrg得到的.itp文件，不要修改其格式。

---
id: 523
title: 将Multiwfn计算的键级直接标注在分子结构图上的方法
domain: 可视化与制图
topic: Multiwfn与GaussView标注键级
cards: 6
---

## 1. 软件版本要求
将Multiwfn计算的键级标注在分子结构图上需要使用特定版本的软件：Multiwfn必须使用2019-Dec-4及以后更新的版本，GaussView必须使用>=6.0的版本（本演示用的是GaussView 6.0.16）。

---

## 2. 环庚三烯拉普拉斯键级计算操作步骤
在Multiwfn中计算环庚三烯分子的拉普拉斯键级并导出文件的命令序列如下：输入`examples\cycloheptatriene.fch`，依次输入`9`（键级计算）、`8`（拉普拉斯键级）、`y`（将键级矩阵导出为当前目录下的bndmat.txt）、`0`（返回主菜单）、`1000`（隐藏选项）、`13`（将当前目录下的bndmat.txt转化为带有键级信息的Gaussian输入文件）。

---

## 3. 生成的gau.gjf文件格式
当前目录下生成的gau.gjf文件内容包含Gaussian标题行和电荷/自旋多重度，坐标部分之后带有原子连接关系段落，其中记录了bndmat.txt里的键级数值，格式示例如下：`1 2 1.7363 4 1.3325 8 0.8040`。

---

## 4. 键连原子的判断规则
gau.gjf文件连接关系段落中，只有被Multiwfn判断为键连的原子间才记录键级数值；若输入文件是.mol、.mol2等，连接关系与原文件一致；若输入文件是.fch、.wfn、.molden，则连接关系是Multiwfn根据原子间距离自动猜测的。

---

## 5. GaussView显示键级设置方法
将gau.gjf载入GaussView后，进入Results - Bond properties，将Name改为Bond order，勾选Show Numbers和Show Colors复选框；按Ctrl+D打开Display Format界面调整文字标签，建议在Molecule标签页里把Scale Radii by改小以避免遮挡标签。

---

## 6. 键级图示颜色含义
在GaussView中显示键级时，不仅通过文字标注，还通过颜色体现键级大小：颜色越绿代表键级越大，颜色越红代表键级越小。

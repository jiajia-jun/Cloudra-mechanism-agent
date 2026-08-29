---
key: b523
title: 将Multiwfn计算的键级直接标注在分子结构图上的方法
url: http://sobereva.com/523
domain: 可视化与制图
source: blog
year: 2019
cards: 6
---

# 将Multiwfn计算的键级直接标注在分子结构图上的方法 — 知识卡片

## 1. 键级结构图标注的软件与版本要求

将Multiwfn与GaussView结合使用可将计算的键级直接标注在分子结构图上。实现此功能必须使用2019年12月4日及以后更新的Multiwfn版本，且GaussView版本需大于等于6.0。

---

## 2. 键级计算与导出操作步骤

在Multiwfn中通过依次输入主菜单9（键级计算）、8（拉普拉斯键级）及y（导出键级矩阵）可生成bndmat.txt文件。随后输入主菜单1000（隐藏选项）及13，可将当前目录下的bndmat.txt转化为带有键级信息的Gaussian输入文件gau.gjf。

---

## 3. 生成的gau.gjf文件格式说明

生成的gau.gjf文件内容包含Gaussian计算路由行、电荷及自旋多重度、原子坐标以及原子连接关系段落。原子连接关系段落中记录了bndmat.txt里的键级数值，仅记录被Multiwfn判断为成键的原子间数据。

---

## 4. 键级连接关系的判断依据

若输入文件为.mol或.mol2等自带连接关系的文件，gau.gjf中的连接关系将与原文件保持一致。若输入文件为.fch、.wfn或.molden，连接关系则由Multiwfn根据原子间距离自动判断生成。

---

## 5. GaussView中键级显示设置方法

将gau.gjf载入GaussView后，进入Results - Bond properties界面，将Name改为Bond order，并勾选Show Numbers和Show Colors复选框。键级大小通过文字标注和颜色（越绿键级越大、越红键级越小）共同展示。

---

## 6. 结构图的显示调整建议

在GaussView中按Ctrl+D打开Display Format界面可调整文字标签显示效果。建议在Molecule标签页中将Scale Radii by参数改小以缩小原子球半径，从而避免原子球遮挡键级标签。

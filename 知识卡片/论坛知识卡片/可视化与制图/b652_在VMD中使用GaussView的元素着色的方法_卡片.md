---
key: b652
title: 在VMD中使用GaussView的元素着色的方法
url: http://sobereva.com/652
domain: 可视化与制图
source: blog
year: 2022
cards: 6
---

# 在VMD中使用GaussView的元素着色的方法 — 知识卡片

## 1. GaussView的元素配色方案

GaussView在File - Preference - Colors - Element Colors中提供了对所有元素定义的唯一颜色配色方案。
- 该配色方案总体上较为美观，且能区分不同元素。
- 相比之下，VMD自带的元素着色定义较少，大多数元素默认显示为褐色，区分度不足。
- 借助脚本可以在VMD中应用GaussView的元素颜色定义。

---

## 2. GaussView配色方案在VMD中的配置文件

从http://原作者.com/attach/652/gview_color.tcl下载gview_color.tcl文件。
- 将该文件放置在VMD的工作目录下（即VMD启动后输入pwd命令显示的目录）。
- 在VMD的vmd.rc文件末尾添加一行代码：`proc gview {} {source gview_color.tcl}`。
- 保存配置文件后，该函数即可在VMD中调用。

---

## 3. 在VMD中加载GaussView配色方案

启动VMD后，在文本窗口（Tk Console）中输入命令`gview`。
- 执行该命令会将VMD默认的元素着色方案替换为与GaussView相同的配色。
- 载入含有元素信息的结构文件（如pdb、xyz格式）后，需在Graphics - Representation中将Coloring Method设为Element。
- 此时即可看到按GaussView颜色方案着色的分子结构。

---

## 4. VMD模拟GaussView基本显示效果的参数设置

在Graphics - Representation中进行设置以尽可能接近GaussView的图像特征。
- 将Drawing Method设为CPK。
- 将Bond Radius设为0.2。
- 将Material设为AOShiny。
- 使用上述参数配合GaussView配色方案，可使VMD的显示效果与GaussView较为接近。

---

## 5. VMD中模拟GaussView白色键的显示方法

VMD默认键的颜色由两端原子的颜色决定，而GaussView中的键显示为白色。
- 若要在VMD中统一为白色键，需将当前Representation的Bond Radius设为0以隐藏默认键。
- 新建一个Representation，将Drawing Method设为CPK，Sphere Scale设为0。
- 将新Representation的Bond Radius设为0.15，Coloring Method选ColorID并指定为白色。
- 此设置可使键显示为白色，从而在键的着色上与GaussView保持一致。

---

## 6. VMD与GaussView显示效果的差异

通过微调原子半径、光源方向和材质参数，VMD的显示效果可以进一步接近GaussView。
- VMD无法完全模仿GaussView对多重键（如双键、三键）的特定显示效果。
- 尽管在元素颜色和键的样式上可以高度相似，但多重键的渲染存在本质差异。

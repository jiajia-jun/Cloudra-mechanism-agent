---
key: t57700
title: ��GaussView�����Զ������ģ��
url: http://bbs.keinsci.com/thread-57700-1-1.html
domain: Gaussian使用
source: keinsci
year: 2026
cards: 11
---

# ��GaussView�����Զ������ģ�� — 知识卡片

## 1. GaussView 内置碎片类型与功能

GaussView 内置的常用结构模型主要分为 Ring fragment、R-group fragment 和 Biological fragment 三类，分别对应界面上的不同图标。虽然实际工作中可能缺少特定的碎片，但通过添加自定义碎片可以更便捷地构建特定体系的模型。

---

## 2. Custom fragment 功能简介

GaussView 官方推荐使用 Custom fragment 功能来添加自定义模型，使用方法详见 GaussView 帮助文件。Custom fragment 允许用户向图库中添加自定义模板，一旦添加完成，再次点击对应图标时即可直接使用该新碎片。该功能在 Linux 和 MacOS 系统的 GaussView 6 以及 Windows 版本上均可使用。

---

## 3. GaussView 碎片文件的存储路径

GaussView 的碎片模板文件存储在软件安装目录下的特定子文件夹中，分别对应界面上的 Ring fragment、R-group fragment 和 Biological fragment 按钮。具体路径为 gv/data/rings、gv/data/rgroups 和 gv/data/biofrags。

---

## 4. rings.ftb 文件格式与结构

以 gv/data/rings 为例，该目录包含 bitmaps 和 fragments 子文件夹以及 rings.ftb 文件。rings.ftb 文件包含约 36 个常用环状结构模板，格式规范包括名称、位图文件、结构文件、行号和列号等信息。文件中的行号和列号从 0 开始计数，例如 "0 0" 表示图库中的第 1 行第 1 列。

---

## 5. 向 rings.ftb 添加新碎片的语法

若要向 ring fragment 中添加一个酞菁铁模板，需修改 rings.ftb 中的 nItems 数量（如改为 37），并追加一行定义。新增行的语法为 `"name" pixmap.frg fragment.frg row col`，例如 `"ironpc" ironpc.xbm ironpc.frg 6 0` 表示将新碎片添加到第 7 行第 1 列。

---

## 6. .xbm 位图文件格式与转换

.xbm 是一种 X11 系统位图文件格式，用于在 GaussView 中显示碎片的图标。如果原始结构图是 .png、.jpg 或 .tif 格式，需先转换为 .xbm 格式。文中提供的 mkxbm.py 脚本可用于执行此转换，例如命令 `python mkxbm.py ironpc.png`。

---

## 7. ironpc.xbm 文件的存放位置

将 ironpc.png 转换得到的 ironpc.xbm 文件，需放置在特定的目录路径下以便 GaussView 识别。该文件的正确存放路径为 gv/data/rings/bitmaps/ironpc.xbm。

---

## 8. .frg 结构文件格式与生成

.frg 是 GaussView 专用的碎片文件格式，用于描述原子之间的连接关系。构建酞菁铁结构时，可先保存为 .mol2 格式文件，文中提供的 mkfrg.py 脚本可将其转换为 .frg 格式，命令为 `python mkfrg.py ironpc.mol2`。

---

## 9. .mol2 文件中芳香键的注意事项

准备用于转换为 .frg 的 .mol2 格式文件时，若包含芳香键（如苯环中的 C-C 键），其键类型应标记为 ar。GaussView 读取 .mol2 文件时会将 Ar 类型识别为芳香键，并在 .frg 格式中记录为键级 4。

---

## 10. ironpc.frg 文件的存放位置

使用 mkfrg.py 脚本生成的 ironpc.frg 文件，需放置在指定的目录路径中才能被 GaussView 正确加载。该文件的存放路径应为 gv/data/rings/fragments/ironpc.frg。

---

## 11. 碎片位图显示的常见问题

在 GaussView 界面中，新添加的 ring fragment 下方会出现酞菁铁碎片模板。如果模板看起来比较潦草，可能是在转换为位图时出现了问题，建议在最初提供图片时就注意清晰度。只要能被识别，通常不影响化学结构的准确性。批量编写碎片定义时，可利用 for 循环提高效率。

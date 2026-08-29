---
key: t14175
title: Foldit standalone: ǿ��Ľ���ʽ������ƴ���
url: http://bbs.keinsci.com/thread-14175-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2019
cards: 22
---

# Foldit standalone: ǿ��Ľ���ʽ������ƴ��� — 知识卡片

## 1. Foldit Standalone 简介

Foldit 是一款基于 Rosetta 代码开发的众包科学游戏。该工具允许用户通过图形界面进行蛋白质结构的操纵与预测，同时也支持 DNA、RNA 以及小分子结构的编辑和移动。

---

## 2. Foldit Standalone 功能兼容性

除了具备 PyMOL、VMD 等“意图式预测工具”的基础显示和追踪功能外，Foldit Standalone 增加了对结构进行修改和操作的能力。这使得用户可以在图形界面中直观地调整分子构象。

---

## 3. Foldit Standalone 软件下载

Foldit Standalone 提供 Windows、Linux 和 macOS 版本的下载。Windows 版本运行较为稳定，而 macOS 版本可能相对不稳定。

---

## 4. Foldit Standalone 文件导入

双击启动 Foldit Standalone 后，用户可以通过主菜单导入 PDB 文件、FASTA 文件或 Foldit 的 Session 文件。软件启动后会进入关卡选择界面，随后即可加载指定的分子结构文件。

---

## 5. 结构预测与 Clash 检测

Foldit 可以用于对未知结构的蛋白进行预测，并会自动检测结构中存在的原子重叠问题。Clash（冲突）在视图中会以特定的图形指示标示出来，提示用户当前结构存在不合理之处。

---

## 6. 视图模式与快捷键

软件底部菜单提供了 View 选项，用于切换不同的显示模式。用户可以通过快捷键快速操作：Shift+A 显示所有非氢原子结构，Shift+T 显示 CB 原子，Shift+D 隐藏所有原子，Home 键用于重置视图。

---

## 7. Pull Mode 基础操作

Pull Mode（拖拽模式）是编辑结构的主要方式，对应快捷键为“1”。在该模式下，用户可以通过鼠标右键拖拽原子或骨架，调整残基位置或骨架走向。

---

## 8. 侧链重打包

在 Pull Mode 下，双击残基可自动进行侧链重打包，以优化侧链构象。此功能旨在寻找能量最低的侧链旋转异构体组合，类似于 Pymol 中的全 Clanster 实时优化。

---

## 9. 结构最小化

当侧链或主链存在 Clash（冲突）时，可使用 Actions 菜单中的 min_sidechain（最小化侧链）、min_backbone（最小化主链）或 min_all（最小化全部）进行优化。该过程会通过调整原子位置降低体系能量以消除冲突。

---

## 10. Constraints（约束）功能

若需要固定某原子与另一原子之间的相对距离或角度，可以使用 Constraint 功能。选中原子后按 Shift 并拖动鼠标，可连接两个原子并设定约束条件，使其在后续操作中保持特定距离或角度。

---

## 11. 约束的设置与删除

约束的强度等参数可以通过右键点击连接原子的红色虚线进行修改。如需删除约束，可通过 Actions 菜单选择 Remove Constraint 选项。

---

## 12. 原子与结构冻结

按下 Shift+鼠标左键并拖动可对某一片段进行冻结，Shift+鼠标右键双击可直接选中整个二级结构进行冻结。被冻结的部分将无法移动，呈现冻结状态；若要解冻，需通过 Actions-Unfreeze Protein 操作。

---

## 13. Cut Point（切断点）设置

在骨架结构上可以设置切断点（Cut Point），即在 Foldtree 中定义切断位置。设置后，切断点两侧的骨架片段可以独立移动，互不干扰。

---

## 14. Tweak 功能操作

Tweak 功能用于局部扭曲结构：可以对螺旋结构进行扭转，或对折叠片结构进行调整。该操作有助于对局部构象进行精细的修整。

---

## 15. Design Mode（突变模式）

Design Mode（快捷键“4”）允许用户直接进行氨基酸的点突变。选中特定残基后，通过右键菜单或 Actions-Mutate 即可将其突变为其他种类的氨基酸。

---

## 16. 批量突变与 FastDesign

用户可以通过 Actions-Mutate 对所有非极性氨基酸进行批量突变。此外，结合冻结功能，可以限定突变范围（如仅针对水溶性氨基酸或特定残基），并结合 Rosetta-TaskOperation 实现类似 FastDesign 的优化流程。

---

## 17. 结构模式与二级结构指定

Structure Mode（快捷键“2”）用于改变骨架的二级结构状态。操作方法为：切换至 Structure Mode，右键点击骨架选择 assign helix 指定为螺旋，随后切换回 Pull Mode 右键点击并选择 ideal SS 即可理想化该结构。

---

## 18. BluePrint 功能

Actions 菜单中的 BluePrint 系统允许用户基于已知的二级结构序列构建蛋白质，特别是用于 Loop 区域的构建。该功能通过输入蓝图文件来引导结构的生成。

---

## 19. Note Mode（标注模式）

Note Mode（快捷键“3”）是一个辅助功能，允许用户在结构特定位置添加文字标注。该功能主要用于记录信息，对计算过程本身无实质性影响。

---

## 20. Undo 功能

Foldit 的 Undo 功能比 PyMOL 更为强大，支持 Ctrl+Z 撤销和 Ctrl+Y 重做。软件还保留了操作历史轨迹，并提供了恢复至最低能量分数状态的功能。

---

## 21. 文件保存与 RosettaScript

在 Menu 菜单中，除了保存 Session 文件和导出 PDB 结构外，还支持运行 RosettaScript。这允许用户通过编写脚本调用更高级的逻辑功能来扩展软件用途。

---

## 22. 评分标准

进行任何结构的移动或突变操作后，必须关注体系 Energy（能量）的变化。好的结构模型应当具有更低的能量分数。

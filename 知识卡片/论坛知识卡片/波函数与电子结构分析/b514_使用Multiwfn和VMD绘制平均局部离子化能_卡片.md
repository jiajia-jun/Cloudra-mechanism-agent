---
key: b514
title: 使用Multiwfn和VMD绘制平均局部离子化能(ALIE)着色的分子表面图（含视频演示）
url: http://sobereva.com/514
domain: 波函数与电子结构分析
source: blog
year: 2019
cards: 11
---

# 使用Multiwfn和VMD绘制平均局部离子化能(ALIE)着色的分子表面图（含视频演示） — 知识卡片

## 1. 平均局部离子化能(ALIE)的定义与应用

平均局部离子化能(ALIE)是考察分子亲电反应位点及活性的重要指标，通常分析其在分子表面的分布以评估反应性。ALIE 与局部电子附着能(LEAE)具有关键性的互补关系。不熟悉 ALIE 的使用者建议查阅相关综述文章或介绍性文献。

---

## 2. 绘制ALIE分子表面图的所需软件与版本

使用 Multiwfn 程序计算 ALIE 并结合 VMD 程序进行可视化，此组合被评价为方便、灵活且强大。绘制 ALIE 着色分子表面图需要 Multiwfn 2019-Sep-17 及之后更新的版本（之前版本缺少所需脚本）。资料示例使用的 VMD 版本为 1.9.3。

---

## 3. 绘制ALIE分子表面图的脚本与文件准备

将 Multiwfn 目录 `examples\scripts` 下的 `ALIE.vmd` 复制到 VMD 安装目录下。将 `examples\scripts` 下的 `ALIE_isoext.bat` 和 `ALIE_isoext.txt` 复制到 `Multiwfn.exe` 所在目录下。输入文件支持 `.wfn`、`.fch`、`.molden` 等格式。

---

## 4. 绘制ALIE分子表面图的批处理操作步骤

编辑 `ALIE_isoext.bat` 文件，将其中的文件路径和 VMD 路径修改为实际路径。双击运行 `ALIE_isoext.bat`，Multiwfn 将自动调用计算并生成 `avglocion.cub`、`density.cub`、`surfanalysis.pdb` 文件至 VMD 目录。

---

## 5. VMD中生成ALIE图像的操作命令

启动 VMD 程序，在 VMD 命令行窗口输入 `source ALIE.vmd` 即可加载并显示 ALIE 着色的分子表面图。若追求更好的渲染效果，可使用 Tachyon 渲染器进行渲染。

---

## 6. ALIE分子表面图的等值面数值选择

绘制 ALIE 分子表面图时通常采用电子密度为 0.0005 a.u. 的等值面，而非常用的 0.001 a.u.（范德华表面定义）。选择 0.0005 a.u. 是因为常用的 0.001 a.u. 会导致 ALIE 着色效果不佳，难以通过颜色区分不同区域的 ALIE 分布差异。

---

## 7. ALIE图像的色谱与极值点含义

ALIE 着色按照蓝-白-红的色彩过渡方式，蓝色区域代表 ALIE 值较小，电子较易参与反应。图中的青色圆球表示分子表面上的 ALIE 极小点，这些位置电子束缚极弱，体现为容易发生亲电反应的位点。

---

## 8. VMD中调整ALIE色彩刻度范围的方法

若分子表面颜色单一或无法区分 ALIE 相对大小，需调整色彩刻度范围。可在 VMD 命令行输入 `mol scaleminmax 0 1 0.31 0.37`，其中 0.31 和 0.37 分别为刻度下限和上限；也可在图形界面 Graphics - Representations - Trajectory 标签页中输入数值后按回车修改。

---

## 9. ALIE色彩刻度极值的确定技巧

色彩刻度范围建议设置为分子表面 ALIE 的实际最小值和最大值，以完整表现分布。通过在 `ALIE_isoext.bat` 第一行末尾加 ` > out.txt` 导出输出信息，搜索 `Minimal value:` 和 `Maximal value:` 获取数值，并手动除以 27.2114 换算为 Hartree 单位后作为刻度界限。

---

## 10. 平面体系的VMD正交视角设置

对于平面体系，为准确考察 ALIE 极值点与原子或键的相对位置，应选择正交视角以避免透视导致的近大远小误判。在 VMD 中通过菜单 Display - Orthographic 切换至正交视角，位于蓝色区域的原子或键易发生亲电反应。

---

## 11. 色彩刻度轴绘制与极值点查询

绘制色彩刻度轴可参照静电势绘制文章中的方法操作。查询分子表面 ALIE 极值点的具体数值亦可参照该文章中的做法执行。

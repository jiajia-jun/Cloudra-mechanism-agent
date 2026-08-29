---
key: t13838
title: ��Multiwfn��Surfer���ã���һ�źÿ���Contourͼ
url: http://bbs.keinsci.com/thread-13838-1-1.html
domain: 可视化与制图
source: keinsci
year: 2019
cards: 17
---

# ��Multiwfn��Surfer���ã���һ�źÿ���Contourͼ — 知识卡片

## 1. Multiwfn 与 Surfer 绘图流程概述

Multiwfn 与 Surfer 联合可用于绘制高质量的等值面图，该流程适用于高斯计算结果的可视化。Surfer 在三维绘图方面优于 Origin，操作便捷且视觉表现力强。此方法通过 Multiwfn 提取平面数据，利用 Surfer 进行网格化处理和渲染。

---

## 2. 准备工作与配置

绘制前需准备好 Multiwfn（推荐 v3.6 版本）、Surfer（推荐 v15.3.307 版本）和 Excel 软件。需修改 Multiwfn 目录下的 settings.ini 文件，将 iuserfunc 参数设置为 -1，以启用用户自定义函数功能。

---

## 3. Multiwfn 提取平面数据步骤

在 Multiwfn 中打开 sample.cube 文件，依次选择功能 4 (Output and plot specific property in a plane) 和子功能 100 (User-defined real space function, iuserfunc= -1)。在绘图选项中选择 1 (Color-filled map)。

---

## 4. 设置绘图平面与网格

在定义网格数量时直接回车，默认选择 200x200。在定义平面时，选择 1，并依次输入坐标为 4、5；输入 Z 值为 0.0，即定义通过原点的 XOY 平面。

---

## 5. 导出绘图数据

在预览窗口中选择功能 -8 将图形单位转换为埃（Angstrom），随后选择功能 -6 将计算得到的平面数据导出为 plane.txt 文件并保存至当前文件夹。

---

## 6. Excel 数据预处理

使用 Excel 打开生成的 plane.txt 文件，通过分列功能处理数据。数据整理后，A 列和 B 列分别为 x/y 坐标，D 列为函数值，将文件另存为 sample.xls 格式。

---

## 7. Surfer 数据网格化

在 Surfer 中使用 Grids - Grid Data 功能，打开 sample.xls 文件，分别指定 X、Y、Z 数据列为 Column A、B、D。确认后生成名为 sample.grd 的网格文件，该文件与源文件位于同一目录下。

---

## 8. Surfer 绘制等值线图

选择 Home - Contour，打开 sample.grd 文件生成初始等值线图。在对象管理器中右键点击 Contour.grd 选择 Free Rotate，通过拖拽调整等值线的观察角度，并关闭所有坐标轴显示。

---

## 9. Surfer 等值线图属性平滑

在 Properties 窗口的 General 选项卡中，可以通过调整 Smoothing 选项对等值线图进行平滑处理，以优化视觉效果。

---

## 10. Surfer 等值线图层级与填充设置

在 Properties 窗口的 Levels 选项卡中，设置等值线的最小值、最大值和间隔。勾选 Fills Contours 和 Color Scale，在 Fill Color 中选择颜色方案，并分别设定 Major Contours 和 Minor Contours 的线型、颜色等属性。

---

## 11. 保存 Surfer 图像

完成设置后，通过 File - Save As 保存为 srf 文件以便后续修改，或通过 File - Export 导出高质量图片。

---

## 12. VMD 绘制等值面截断图

VMD 可用于绘制具有特定数值的等值面截断图，常用等值面数值包括 -16, -8, -4, -2, -1, 1, 2, 4。制作截断图时建议选取 1.8.7 版本的 VMD，因为不同版本在渲染上可能存在微小差异。

---

## 13. VMD 创建等值面显示

在 VMD 中加载 cube 文件，通过 Graphics - representations 创建新表示。将 Drawing Method 设为 Isosurface，Isovalue 设为 -16（数值越小结构越细），Draw 设为 Solid surface，Show 设为 Isosurface，Coloring Method 设为 ColorID 并选择如 Mauve 的颜色。

---

## 14. VMD 添加多层等值面

重复创建表示的步骤以添加多个等值面，需注意每个表示的 Isovalue 和 ColorID 设置应各不相同，以区分不同数值的等值面。

---

## 15. VMD 设置裁剪平面

选择 Extensions - Visualization - Clipping plane tool，在 Active Clipping Planes 和 Edit Clipping Planes 中均选择 0。勾选 Normal follow view，设置法向量为 1.0 0.0 0.0 以设定与 YZ 平面相交的截面，调整 Distance 值移动截断位置。

---

## 16. VMD 调整分子结构显示

将分子结构的 Drawing Method 从默认改为 Lines，或者切换为其他显示方式如 CPK。若使用 CPK 模式，需将 Sphere Resolution 和 Bond Resolution 参数调整至 30 或 20 以获得更精细的显示效果。

---

## 17. VMD 背景与视角设置

在 VMD 控制台中输入命令 `color Display Background white` 将背景设为白色。通过 Display 菜单调整透视、深度暗示及光源位置，并配合鼠标拖拽、旋转和缩放功能，调整至最佳视角和构图。

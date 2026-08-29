---
key: t55821
title: ��Qbics-MolStar�̳�2���ۿ��켣��һ����������
url: http://bbs.keinsci.com/thread-55821-1-1.html
domain: 可视化与制图
source: keinsci
year: 2025
cards: 9
---

# ��Qbics-MolStar�̳�2���ۿ��켣��һ���������� — 知识卡片

## 1. Qbics-MolStar 简介

Qbics-MolStar 是一款基于开源 Mol* 框架开发的可视化与建模工具，专为计算化学研究人员设计。该工具支持化学体系的可视化、轨迹播放、结构建模，并集成了大部分常用计算化学软件的功能，旨在作为 VMD、PyMOL、GaussView 和 Multiwfn 等软件的替代方案，以降低学习门槛。

---

## 2. Qbics-MolStar 轨迹导出功能

Qbics-MolStar 支持查看和导出轨迹文件，可处理多种格式（如文本格式、图片格式等），并能将轨迹导出为 MP4、GIF 等视频文件。轨迹导出和渲染功能依赖于后端配置的开源工具 FFmpeg。

---

## 3. 使用 XYZ 文件查看轨迹

加载 .xyz 文件后，Qbics-MolStar 会自动显示并渲染结构；若文件包含多帧信息，则可用于查看轨迹。用户可通过勾选 Dynamic Bonds 按钮动态观察化学键的变化。

---

## 4. XYZ 轨迹动画播放设置

在界面右上角点击 Select Animation 按钮，可选择不同的轨迹场景和显示方式，系统默认选项为 Animate Trajectory，用于播放模拟轨迹。点击 Start 按钮即可开始渲染和播放轨迹。

---

## 5. 导出 XYZ 轨迹动画

点击 Export Animation 按钮可实现轨迹导出功能，需确保 Select Animation 下的选项与播放设置一致。点击 Render 按钮开始渲染，屏幕显示 Rendering successful 提示后，可点击 Clear 清除缓存。

---

## 6. 保存动画文件

渲染完成后会生成 4 个文件，用户可选择导出为 MP4、AVI、GIF 或 MKV 格式。确认文件格式后，点击 Save Animation 即可完成保存。

---

## 7. 使用 GRO + XTC 文件查看轨迹

XTC 是 GROMACS 压缩格式，常用于分子动力学模拟轨迹，虽不包含拓扑信息，但可结合包含结构信息的 GRO 文件使用。在 Qbics-MolStar 中，需分别加载 .gro 文件作为初始结构、.xtc 文件提取轨迹信息，最后点击 Apply 进行渲染。

---

## 8. PDB 数据库加载与结构获取

在指定位置输入 PDB ID（例如 3KB0）并点击 Apply，即可获取并渲染相应的蛋白质结构文件。

---

## 9. 旋转视角动画制作

加载蛋白质结构后，在 Animation 选项中选择 Camera Spin 模式，可让视角自动旋转。在 Export Animation 部分，需将默认的 Animate Trajectory 切换为 Camera Spin 模式以匹配渲染设置。

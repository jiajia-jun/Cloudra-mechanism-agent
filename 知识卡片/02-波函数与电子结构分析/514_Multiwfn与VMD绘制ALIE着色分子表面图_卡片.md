---
id: 514
title: 使用Multiwfn和VMD绘制平均局部离子化能(ALIE)着色的分子表面图（含视频演示）
url: http://sobereva.com/514
domain: 波函数与电子结构分析
topic: Multiwfn与VMD绘制ALIE着色分子表面图
cards: 8
---

# Multiwfn与VMD绘制ALIE着色分子表面图 — 知识卡片

## 1. ALIE函数的应用价值与简介

平均局部离子化能(ALIE)是考察分子亲电反应位点及活性的重要指标，通过分析其在分子表面的分布可以揭示反应活性区域。不熟悉ALIE的用户建议阅读《静电势与平均局部离子化能综述合集》。相关补充函数LEAE详见文章《使用Multiwfn通过局部电子附着能(LEAE)考察亲核反应位点、难易及弱相互作用》。
- ALIE常用于分析亲电反应位点
- 推荐阅读互补文献：http://sobereva.com/676
- 综述合集链接：http://bbs.keinsci.com/thread-219-1-1.html

---

## 2. 绘制ALIE图的软件版本与环境要求

使用Multiwfn和VMD绘制ALIE着色分子表面图需要特定版本的软件支持，本文基于Windows环境演示。必须使用2019年9月17日及之后更新的Multiwfn版本以获取所需脚本。VMD版本本文使用的是1.9.3，Linux用户需灵活变通实现。
- Multiwfn版本要求：2019-Sep-17及之后
- VMD版本示例：1.9.3
- 下载地址：Multiwfn在http://sobereva.com/multiwfn，VMD在http://www.ks.uiuc.edu/Research/vmd/

---

## 3. 绘制ALIE图的脚本文件准备与配置

将Multiwfn和VMD的示例脚本复制到相应目录并配置路径是自动绘图的关键步骤。需将examples\scripts下的ALIE.vmd复制到VMD目录，ALIE_isoext.bat和ALIE_isoext.txt复制到Multiwfn.exe所在目录。必须编辑ALIE_isoext.bat，修改其中的输入文件路径和VMD路径为实际路径。
- 输入文件格式支持：.wfn、.fch、.molden等
- 脚本操作：复制文件并编辑ALIE_isoext.bat中的路径

---

## 4. ALIE图的自动计算与可视化生成

运行配置好的批处理文件可自动调用Multiwfn进行计算，并生成VMD所需的输出文件。双击ALIE_isoext.bat后，计算会在VMD目录下生成avglocion.cub、density.cub和surfanalysis.pdb。启动VMD并在命令行输入source ALIE.vmd即可加载生成图像。
- 输出文件：avglocion.cub、density.cub、surfanalysis.pdb
- VMD加载命令：source ALIE.vmd

---

## 5. 分子表面等值面的选择与ALIE着色逻辑

绘制ALIE图时推荐使用电子密度为0.0005 a.u.的等值面，而非常用的0.001 a.u.范德华表面定义，以便更好地区分ALIE分布差异。图像采用蓝-白-红的色彩过渡方式，蓝色区域代表ALIE较小、电子易参与反应的区域。青色圆球标示分子表面上ALIE的极小点，即电子束缚极弱、易发生亲电反应的位点。
- 推荐等值面值：0.0005 a.u.
- 颜色含义：蓝色为低ALIE区域（高活性），红色为高ALIE区域
- 极小点标识：青色圆球

---

## 6. 图像渲染与色彩刻度范围调整

若色彩无法区分ALIE差异或颜色单一，说明色彩刻度范围不合适，需手动调整下限和上限。可以在VMD命令行输入mol scaleminmax 0 1 0.31 0.37（示例数值）进行设置，或在Graphics - Representations - Trajectory中修改。建议将刻度设为分子表面ALIE的实际最小值和最大值，这些数值可在Multiwfn输出信息中搜索"Minimal value:"和"Maximal value:"获得，并除以27.2114换算为Hartree单位。
- 调整命令：mol scaleminmax 0 1 [下限] [上限]
- 数据获取：在Multiwfn输出中搜索"Minimal value:"和"Maximal value:"
- 单位换算：数值除以27.2114转换为Hartree

---

## 7. 平面体系的视角校正与极值点分析

对于平面体系，准确考察ALIE极值点位置应选择正交视角以避免近大远小的透视误差。在VMD中选择Display - Orthographic即可切换为正交视角。图像中位于蓝色区域的原子或键容易参与亲电反应。
- 操作路径：Display - Orthographic
- 目的：消除透视变形，准确判断极值点位置
- 活性位点判定：位于蓝色区域

---

## 8. 色彩刻度轴绘制与极值点查询

若需要在图像上绘制色彩刻度轴或查询分子表面ALIE极值点的具体数值，可参考《使用Multiwfn+VMD快速地绘制静电势着色的分子范德华表面图和分子间穿透图》一文中的具体操作方法。
- 参考文献链接：http://sobereva.com/443
- 功能包含：绘制色彩刻度轴、查询具体极值点数值

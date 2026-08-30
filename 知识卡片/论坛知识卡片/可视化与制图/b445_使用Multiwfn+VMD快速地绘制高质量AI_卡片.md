---
key: b445
title: 使用Multiwfn+VMD快速地绘制高质量AIM拓扑分析图（含视频）
url: http://sobereva.com/445
domain: 可视化与制图
source: blog
year: 2018
cards: 18
---

# 使用Multiwfn+VMD快速地绘制高质量AIM拓扑分析图（含视频） — 知识卡片

## 1. AIM拓扑分析视频演示资源

资料操作步骤配有对应的视频演示，若按照文本步骤操作遇到困难，可观看视频辅助学习。视频链接为 https://www.bilibili.com/video/av33724816/。

---

## 2. Multiwfn与VMD结合绘制AIM拓扑图

结合Multiwfn与VMD绘制AIM拓扑分析图（含临界点、键径、分子结构）效果良好，过程极其简单。该基于脚本的方法适合零基础初学者，且在VMD图形窗口中便于寻找感兴趣的临界点编号。

---

## 3. 文件准备工作

将Multiwfn的examples\scripts目录下的AIM.bat和AIM.txt拷至Multiwfn可执行文件所在目录。编辑AIM.bat，将Multiwfn后的文件名设为待分析文件的路径，并修改其中的VMD路径为实际路径。

---

## 4. VMD脚本配置

将AIM.vmd文件拷到VMD目录下，并在VMD目录下的vmd.rc文件末尾加入一行proc aim {} {source AIM.vmd}。此操作使得在VMD命令行输入aim即可调用AIM.vmd进行绘图。

---

## 5. 批处理与输入流文件说明

AIM.bat是Windows批处理文件，用于启动Multiwfn并按照AIM.txt里的命令进行计算。AIM.txt是输入流文件，每一行对应Multiwfn界面中需要输入的一个命令。

---

## 6. AIM.txt脚本的功能

AIM.txt指挥Multiwfn进入拓扑分析功能并搜索临界点（使用选项2、3、4、5），随后通过选项8产生拓扑路径。脚本将临界点导出至CPs.pdb，拓扑路径导出至paths.pdb，结构导出至mol.pdb，并将临界点属性导出至CPprop.txt。

---

## 7. 临界点属性计算配置

脚本默认不计算静电势以节省时间，若需计算可将AIM.txt里的-1改为1。所有Multiwfn支持的含波函数信息的文件均可用作输入文件。

---

## 8. 实例操作步骤

以GC.wfn为例，将其拷至Multiwfn目录并修改AIM.bat中的路径。双击AIM.bat运行，计算完成后若当前目录下出现内容非空的CPprop.txt即表示正常结束。

---

## 9. VMD绘图启动

启动VMD后，在命令行窗口输入aim，AIM.vmd脚本会自动载入并显示CPs.pdb、paths.pdb和mol.pdb。图像可使用VMD自带的Tachyon渲染器进行渲染以获得抗锯齿效果。

---

## 10. 临界点与键径的颜色标识

图中紫、桔黄、黄球分别代表(3,-3)、(3,-1)和(3,+1)临界点，绿球代表(3,+3)临界点（如有）。桔黄色曲线对应键径，颜色和粗细可通过编辑AIM.vmd修改。

---

## 11. 分子结构的显示

分子结构文件虽已载入VMD，但默认不显示。在VMD Main窗口中双击D标签使其变黑，即可显示分子结构。

---

## 12. 临界点序号查询方法

在VMD中取消显示键径以避免干扰，按键盘0键进入查询模式，点击临界点中心。命令行窗口显示的index值加1即为Multiwfn输出文件CPprop.txt中对应的临界点序号。

---

## 13. 批量显示临界点序号命令

VMD中定义了labcp命令用于批量显示临界点序号，用法为labcp [类型] [文字尺寸] [偏移量X] [偏移量Y]。类型可选all、3n3、3n1、3p1、3p3、no，分别对应不同临界点。

---

## 14. 标记特定临界点序号命令

VMD中定义了labcpidx命令用于标记特定序号的临界点，用法为labcp [序号] [文字尺寸] [偏移量X] [偏移量Y]。例如labcpidx "3 6 to 8 12 15" 2.1可显示指定序号的标签。

---

## 15. 标签显示调整

若标签位置不佳或被遮挡，可通过缩放/旋转视角、调整位移值或增大标签尺寸解决。若需标签完全不被遮挡，需使用图像处理软件进行后期处理。

---

## 16. 大体系计算加速

对于大体系，可删除AIM.txt的第4、5行，使Multiwfn仅通过原子核位置和双原子中点作为初猜寻找临界点。此方法可节约时间，但极少数情况下可能漏掉个别临界点。

---

## 17. VMD中筛选显示特定临界点

进入VMD的Graphics - Representation界面，选择CPs.pdb，通过name（C/N/O/F对应不同类型临界点）和serial进行筛选。例如name N and serial 1 4 6 to 8表示仅显示指定序号的(3,-1)临界点。

---

## 18. VMD中筛选显示特定键径

paths.pdb中不同的拓扑路径对应不同的残基号，可通过resid筛选键径。例如在Selected Atoms文本框输入not resid 3 7可隐藏3号和7号键径。按0键点击键径上的点可查询其残基号。

---
id: 617
title: 使用Multiwfn计算晶体结构中自由区域的体积、图形化展现自由区域
url: http://sobereva.com/617
domain: 可视化与制图
topic: Multiwfn计算晶体自由体积及VESTA可视化
cards: 13
---

# Multiwfn计算晶体自由体积及VESTA可视化 — 知识卡片

## 1. 适用Multiwfn版本及文献引用要求

使用本文介绍的功能需使用2021-Sep-14及以后更新的Multiwfn。使用本文方法发表文章时请记得按照Multiwfn启动时的提示恰当引用程序。

---

## 2. 支持晶胞信息的输入文件格式

使用本文介绍的功能可以用各种Multiwfn支持的包含晶胞信息的文件作为输入文件，例如含有CRYST1字段的pdb文件、GROMACS程序的gro文件、cif文件、VASP的POSCAR、CP2K的restart文件、含有平移矢量（Tv）的Gaussian输入文件。

---

## 3. 计算有机共价框架化合物自由区域体积的操作

载入COF的cif文件后，在Multiwfn中依次输入300（其它功能）、1（计算自由区域体积、可视化自由区域）、1（设置格点并开始计算）。起点使用默认的(0,0,0)，计算范围使用晶胞的三个边长，格点间距使用默认的0.25埃。计算屏幕会显示：Volume of entire box: 2996.151 Angstrom^3，Free volume: 1953.217 Angstrom^3, corresponding to 65.19 % of whole space。

---

## 4. 使用VMD绘制自由区域等值面

将Multiwfn程序包examples\scripts目录下的showcub.vmd复制到VMD目录，编辑vmd.rc并在末尾插入source showcub.vmd。将free_smooth.cub移至VMD目录，启动VMD后在文本窗口输入cub free_smooth 0.5显示数值为0.5的等值面，输入pbc box显示边框。在Display菜单选择Orthographic可切换为正交视角。

---

## 5. VMD中调整等值面数值与范德华表面对比

在VMD的"Graphics" - "Representation"里把显示体系结构的Drawing method改为VDW可显示范德华表面，其与等值面几乎精确贴合。修改Representation里第二项的isovalue值，越接近1自由区域显得越大，越接近0则显得越小。

---

## 6. 使用VESTA绘制自由区域等值面

启动VESTA后载入free_smooth.cub，确保左侧Style标签页里的Show isosurfaces被选中。点击左下角Properties，选择Isosurfaces标签页，将Isosurface level设为0.5，Opacity 1后面的值设为220。

---

## 7. 自由区域等值面边界封闭状态的切换

Multiwfn默认设置下等值面在盒子边缘处是封闭的，若不希望边界被封闭，在主功能300的子功能1界面选“5 Toggle making isosurface closed at boundary”将其状态切换为No。在VESTA中显示时取消Show sections复选框可看到不封闭的等值面效果。

---

## 8. VESTA中自由区域的填充与网格显示

在VESTA中点击左侧的Show sections开启section的显示，可将自由区域填充显示，占据区域与自由区域之间的过渡区域用色彩渐变展示。将等值面显示风格设为Wireframe，在Properties的Sections标签页里修改透明度、显示等值线、色彩刻度改为R-G-B，可显示漂亮的网格图像。

---

## 9. C60晶体自由区域体积计算与绘图

计算C60晶体时，载入cif文件后进入功能300-1-1，格点间距设为0.15埃以获得更平滑的图像。计算显示自由区域占整个晶胞的27.9%。由于晶胞是正交的，可在后处理菜单选3并勾选Show cell直接在Multiwfn里显示等值面，或导出free_smooth.cub用VESTA以Stick方式显示结构。

---

## 10. 硫花晶体计算前的超胞构建

载入硫花cif文件后，为观察孔洞与分子位置的相对关系，需构建超胞。输入300（其它功能）、7（几何操作）、19（构造超胞），将三个方向分别延展成原先的3倍、1倍、2倍。

---

## 11. 硫花晶体自由区域的可视化

对构建好的硫花超胞计算自由区域格点数据，用VESTA绘图可见硫花堆叠方向没有自由区域，而侧向接触区域有明显的自由区域。

---

## 12. 平滑函数与等值面数值的调节

使用默认的基于误差函数（scale factor为1）产生的平滑化格点数据不一定总是图像效果最理想，有时切换成其它函数做平滑效果更好。0.5的等值面对自由区域的展现也不一定最理想，可根据实际情况进行适当调节。

---

## 13. 晶体自由区域与分子孔洞功能的区别

若想展现笼状、环状分子里的孔洞并计算其体积，不要用本文针对晶胞或盒子的做法，而应使用专门的文章《使用Multiwfn可视化分子孔洞并计算孔洞体积》介绍的方法。
---

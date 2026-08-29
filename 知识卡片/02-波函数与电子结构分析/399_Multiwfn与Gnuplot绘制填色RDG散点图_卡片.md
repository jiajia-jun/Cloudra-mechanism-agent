---
id: 399
title: 绘制有填色效果的用于弱相互作用分析的RDG散点图的方法
domain: 波函数与电子结构分析
topic: Multiwfn与Gnuplot绘制填色RDG散点图
cards: 9
---

## 1. RDG方法定义与综述文献
RDG方法（又称NCI方法）于2010年提出，用于分析分子间和分子内弱相互作用。
- Multiwfn是进行RDG分析最为流行、强大且好用的程序。
- 更多细节见《使用Multiwfn图形化研究弱相互作用》。

---

## 2. 手动制作RDG填色散点图的Photoshop方法
利用Photoshop将VMD的色彩刻度条拉伸至与散点图作图范围相同大小，垫在Multiwfn输出的散点图下方图层；将散点图图层作图区域的黑色部分通过色彩范围选中并删除，即可透出下层色彩。
- 此法需具备Photoshop使用技能，操作相对繁琐。
- 填色效果便于将散点图的spike与RDG填色等值面图颜色对应讨论。

---

## 3. Multiwfn导出RDG散点数据的操作步骤
启动Multiwfn，依次输入命令：`examples\PhenolDimer.wfn`、`20`（弱相互作用图形化分析）、`1`（NCI分析）、`3`（高质量格点）、`2`（导出散点数据）。
- 该操作将RDG vs sign(lambda2)rho的散点数据导出至当前目录下的output.txt文件中。
可参考《使用Multiwfn做NCI分析展现分子内和分子间弱相互作用》一文。

---

## 4. 使用gnuplot绘制RDG填色散点图的文件准备
需使用gnuplot 5.4 Windows版；将Multiwfn导出的output.txt和绘图脚本`examples\scripts\RDGscatter.gnu`放入gnuplot目录下的bin子目录中。
- 开启命令行模式（如cmd）进入该目录，运行命令`gnuplot RDGscatter.gnu`。
- Windows用户也可直接将RDGscatter.gnu拖拽到gnuplot.exe图标上运行。

---

## 5. RDG填色散点图输出格式与查看
运行绘图脚本后生成RDGscatter.ps文件，这是一种矢量图形格式，支持无损缩放。
- 该文件可用Adobe Acrobat直接打开查看。
- 可用Photoshop打开并选择像素大小进行转换，或配合ghostscript用irfanview观看。

---

## 6. RDGscatter.gnu脚本关键参数设置
脚本中可设定X/Y/色彩刻度轴的上下限（x/y/cbrange后的值）、标签数值范围和步长（x/y/cbtic后的值）、散点大小（pointsize后的值）及色彩刻度定义。
- 脚本中默认色彩刻度定义为`set palette defined (-0.035 "blue",-0.0075 "green", 0.02 "red")`。
- 该刻度对应VMD中-0.035~0.02的着色范围（蓝-绿-红）。

---

## 7. RDG散点图与等值面图色彩刻度一致性要求
若将填色散点图与VMD绘制的填色RDG等值面图对照，二者色彩刻度设定必须严格一致。
- VMD脚本`examples\RDGfill.vmd`中的`mol scaleminmax top 1`行后应设为-0.035 0.02。
- 一致设定下，散点图spike位置与等值面颜色可一一对应。

---

## 8. IRI方法绘制填色散点图的扩展
IRI方法比RDG方法更强大，可展现弱相互作用及化学键区域，建议使用IRI取代RDG；Multiwfn中可导出IRI vs sign(lambda2)rho散点数据至output.txt。
- 使用`examples\scripts\IRIscatter.gnu`脚本（需2022-Jul-16及以后更新的Multiwfn）替代RDGscatter.gnu即可绘制填色散点图。
- 将横坐标范围设大（如-0.05到0.03）可展现化学键作用区域的spike，例子见Multiwfn手册4.20.4节。

---

## 9. IGMH方法绘制填色散点图
IGMH方法比RDG更适合专门考察片段间的弱相互作用，可参考《使用Multiwfn做IGMH分析非常清晰直观地展现化学体系中的相互作用》一文。
- IGMH方法可以绘制填色散点图。
- 具体例子参考该资料提及的IGMH官方教程。

---
id: 14
title: VMD显示轨迹中粒子的空间密度分布的两种方法
domain: 可视化与制图
topic: VMD显示轨迹粒子空间密度分布
cards: 4
---

## 1. VMD显示粒子空间密度的颜色深浅法
第一种方法利用颜色深浅显示原子在不同位置出现的概率，适合描述少数几个粒子的密度分布，效果比较柔和。渲染模式需开启GLSL，将Materials对话框中Transparent材质复制到新材质a，把a的Ambient设为最大，Opacity设为0.03，然后在文本控制台source dis.tcl脚本。运行draw material a，再输入dis命令，例如查看index 444原子在前4444帧内的空间分布状况，输入dis 444 4444。
- 原理是GLSL渲染模式支持透明色，每次出现用一个透明的白色球表示，叠加次数越多该处越不透明，颜色越深说明出现概率越大。球半径0.13是图像效果较好的参数，若不满意可调整Opacity或运行draw delete all删除重绘。

---

## 2. 空间密度分布显示脚本dis.tcl的内容
dis.tcl脚本通过循环遍历每一帧，获取指定原子的坐标并在该位置绘制一个球体，用于通过颜色深浅法可视化原子轨迹。脚本内容如下
proc dis {atom fps} {
draw color white
for {set i 0} {$i<$fps} {incr i 1} {
set nowselect [atomselect top "index $atom" frame $i]
set x [$nowselect get {x}]
set y [$nowselect get {y}]
set z [$nowselect get {z}]
draw sphere "$x $y $z" radius 0.13
- 运行此脚本前需要先设置好材质并执行draw material a命令。

---

## 3. 等值面法显示粒子空间密度的准备工作
第二种方法是用等值面显示，适合描述大量粒子的空间分布，需使用g_spatial计算某个group在空间中每个点的出现几率。首先使用trjconv -f a-sol.trr -s a-sol.gro -fit rot+trans按照参考结构（如蛋白）进行align，以蛋白不发生整体运动为依据改变整个轨迹中的原子坐标。然后运行g_spatial -s a-sol.tpr -f a-sol.trr -n index.ndx计算空间几率并存为grid.cube文件。
- 如果遇到内存分配不够或段错误，使用-nab参数，设100一般够了；使用bin参数控制格点宽度，默认是0.05，设为0.03时文件会变得很大。

---

## 4. g_spatial选择group对输出结果的决定性作用
g_spatial第一次选择的group决定了空间格点各个值的大小，即决定了grid.cube的数据部分，最终得到的等值面图样完全取决于第一次选择的group。第二次选择group实际上是选择输出哪些原子到grid.cube头部的原子叙述部分，完全不影响结果，可随便设，一般设成溶质。例如第一组设为溶剂，第二组设为溶质，读进VMD后，用CPK模式看到的是溶质结构，用isosurface模式看到的是溶剂出现密度的等值面。

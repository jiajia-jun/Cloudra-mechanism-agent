---
id: 274
title: 将分子结构图和Multiwfn绘制的平面图准确合并的方法
domain: 可视化与制图
topic: Multiwfn平面图与分子结构图准确合并
cards: 9
---

## 1. Multiwfn绘制平面图与分子结构合并需求
Multiwfn主功能4可对实空间函数绘制填色图和等值线图，但图中只显示元素名或序号，不显示分子结构。将分子结构附上能令图像更直观，但若作图平面是斜面而非XY/YZ/XZ平面，直接合并难以对应，需借助技巧进行精确对齐。

---

## 2. Multiwfn版本更新说明
从Multiwfn 3.6版开始，在绘制平面图（地形图除外）的后处理菜单中增加了选项8，可以直接将化学键绘制成连线。

---

## 3. Gaussian计算输入文件示例
使用Gaussian计算CH3NH2的fch文件，计算 level 为B3LYP/6-31G(d)，chk文件路径为C:\gtest\CH3NH2.chk。分子坐标为：C 0.05159500 0.70381800 0.00000000，H 0.59439800 1.06209400 0.88166000，H 0.59439800 1.06209400 -0.88166000，H -0.94293100 1.18451300 0.00000000，N 0.05159500 -0.76078400 0.00000000，H -0.45830300 -1.10306000 0.81258800，H -0.45830300 -1.10306000 -0.81258800。

---

## 4. Multiwfn绘制平面图并调整原子标签显示
在Multiwfn中载入fch文件，依次输入4（主功能）、9（ELF）、2（等值线图）、[回车]、4（自定义平面）、1,5,6（C1-N5-H6平面）。若部分原子因距离作图平面太远未显示，选17修改原子标签显示范围，输入阈值10（显示10埃以内的原子标签），输入y或n决定是否用细体显示超阈值原子，随后选0保存图像为DISLIN.PNG用于定位。

---

## 5. 输出不含标签的Multiwfn平面图
在Multiwfn中选1关闭原子标签显示，再次选0输出图像保存为DISLIN_1.PNG，该图像用于后续与分子结构图合并。

---

## 6. VMD alignplane脚本代码
将以下代码拷贝到VMD文本窗口以定义alignplane命令，用于将指定平面旋转至XY平面：proc alignplane {ind1 ind2 ind3} { set atm1 [atomselect top "serial $ind1"]; set atm2 [atomselect top "serial $ind2"]; set atm3 [atomselect top "serial $ind3"]; set vec1x [expr [$atm2 get x] - [$atm1 get x]]; set vec1y [expr [$atm2 get y] - [$atm1 get y]]; set vec1z [expr [$atm2 get z] - [$atm1 get z]]; set vec2x [expr [$atm3 get x] - [$atm1 get x]]; set vec2y [expr [$atm3 get y] - [$atm1 get y]]; set vec2z [expr [$atm3 get z] - [$atm1 get z]]; set sel [atomselect top all]; $sel move [transvecinv [veccross "$vec1x $vec1y $vec1z" "$vec2x $vec2y $vec2z"]]; $sel move [transaxis y 90] }。

---

## 7. 使用VMD精确调整分子视角
启动VMD载入结构文件（如pdb或xyz格式），执行alignplane 1 5 6命令使C1-N5-H6平面平行于屏幕。选择Display-orthographic使用正交视角，选Display-Axes-off关闭坐标轴，在Graphics-Representation调节显示方式，放大窗口后选File-Render，使用tachyon (internal)渲染图像。

---

## 8. Photoshop合并对齐分子结构与平面图
将DISLIN.png和DISLIN_1.png在PS中作为图层打开，显示带标签图层。将VMD渲染图置入PS，使用“选择-色彩范围”点击黑色背景并反相选中分子结构，复制粘贴到平面图上并降低透明度。使用Ctrl+T对分子结构进行旋转、缩放，直至原子核位置与Multiwfn平面图的原子标签准确对应。

---

## 9. 合并图像的最终处理与微调
关闭PS中带标签的图层，将分子结构图层恢复为完全不透明，即可得到最终合并图像。可通过PS将位于绘图平面下方的化学键（如N-H键）修改为透明以增强立体感，具体操作需根据实际结构摸索调整。

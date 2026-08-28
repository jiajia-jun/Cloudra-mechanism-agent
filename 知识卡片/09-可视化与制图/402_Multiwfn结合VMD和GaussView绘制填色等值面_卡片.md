---
id: 402
title: 基于Multiwfn产生的cube文件在VMD和GaussView中绘制填色等值面图的方法
url: http://sobereva.com/402
domain: 可视化与制图
topic: Multiwfn结合VMD和GaussView绘制填色等值面
cards: 8
---

# Multiwfn结合VMD和GaussView绘制填色等值面 — 知识卡片

## 1. 填色等值面图原理与应用

填色等值面图将一个实空间函数的数值通过颜色映射在另一个函数的等值面上，例如将静电势、福井函数、HOMO/LUMO轨道波函数等投影到电子密度等值面上以预测反应位点。绘制时需利用Multiwfn分别计算定义等值面的函数和被投影函数的格点数据并导出为cube文件，随后将两个cube文件载入VMD或GaussView等程序中生成图像。
- Multiwfn可对任意实空间函数构造等值面顶点并计算其值
- 适用函数包括静电势、福井函数、双描述符、ALIE、EDR等

---

## 2. 使用Multiwfn计算晕苯福井函数的cube文件步骤

以晕苯的福井函数f-在电子密度等值面上的填色图为例，需先在Gaussian中优化中性结构得到N.fch，再基于中性结构计算+1阳离子态单点得到N-1.fch。在Multiwfn中依次计算电子密度格点数据导出为N.cub，以及通过N.fch减去N-1.fch计算电子密度差值（即f-）导出为f-.cub，两次格点设定必须严格一致。
- Gaussian计算等级为B3LYP/6-31G*
- 阳离子态电荷与自旋多重度设为1 2
- Multiwfn格点质量选中等（大体系建议选high quality）

---

## 3. Multiwfn生成cube文件的具体操作指令

启动Multiwfn后，首先输入N.fch，选择计算格点数据及电子密度，设置格点质量并导出density.cub（改名为N.cub）；随后返回主菜单，选自定义运算，输入-,N-1.fch执行减法操作，再次计算电子密度格点数据，使用相同的格点设定并导出density.cub（改名为f-.cub）。
- 计算电子密度路径：5 -> 1 -> 2 -> 2
- 自定义运算路径：5 -> 0 -> 1 -> -,N-1.fch -> 1 -> 2 -> 2

---

## 4. 在GaussView中绘制填色等值面图的操作流程

将N.cub拖入GaussView，通过Results - Surfaces/Contours菜单载入f-.cub，选中第一套数据将Density数值改为0.01，选择New Mapped Surface生成映射表面。将背景色设为白色，此时屏幕显示电子密度为0.01 a.u.的等值面，颜色对应f-数值，色彩刻度按红-绿-蓝顺序对应数值由负到正。
- 默认色彩刻度下限为-0.00104 a.u.，上限为0.00104 a.u.
- Surface Actions - New Mapped Surface - OK

---

## 5. GaussView中填色等值面图的图像优化

在图像上右键选择View - Display Format，切换到Surface标签页，将Format选为Transparent并选中Fade mapped surface values，调节Transparent滑杆使色彩浓度合适且图像通透。在色彩刻度上下限文本框中分别输入-0.001和0.001并按回车，使刻度为整数以便观察。
- 越蓝的区域代表f-越大，亲电反应活性越高
- File - Preference - Display Format可修改背景颜色

---

## 6. 在GaussView中单独显示f-.cub等值面的方法

将f-.cub拖入GaussView，选Results - Surfaces/Contours，将Density设为0.002，选Surface Actions - New Surface生成等值面图，紫色和青色分别对应等值面为正和为负的区域。修改颜色需进入File - Preferences - Colors - Surface Colors，选Default项进行设置。
- Density示例值为0.002

---

## 7. 在VMD中绘制填色等值面图的设置步骤

启动VMD后设置渲染模式为GLSL并关闭雾化和坐标轴，将N.cub拖入Main窗口并利用Load Data into Molecule载入f-.cub。在Graphics - Representation中将Drawing Method设为CPK，新建层后设为Isosurface，Isovalue设为0.01，Vol选N.cub，Draw选Solid Surface，Show选Isosurface。将Coloring Method改为Volume对应f-.cub，Material改为Transparent。
- Display - Rendermode - GLSL
- Isovalue设为0.01
- 命令行输入color Display Background white修改背景

---

## 8. VMD中色彩刻度与材质的调节

在Graphics - Representation的Trajectory标签页下，将Color Scale Data Range的两个框分别设为-0.001和0.001，输入完毕后按回车。进入Graphics - Materials选Transparent，将Opacity滑杆向右拉动降低透明度，使表面颜色更明显，最终图像中越蓝说明f-越正。
- 刻度范围需输入两个数值后统一按一次回车
- 越蓝代表f-数值越正

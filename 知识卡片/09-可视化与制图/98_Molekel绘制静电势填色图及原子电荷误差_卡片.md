---
id: 98
title: 谈谈Molekel做静电势填色等值面图的方法及误区
url: http://sobereva.com/98
domain: 可视化与制图
topic: Molekel绘制静电势填色图及原子电荷误差
cards: 11
---

# Molekel绘制静电势填色图及原子电荷误差 — 知识卡片

## 1. Molekel做静电势填色图的优势

Molekel 4.x版本在绘制填色等值面图时具有独特的优势，即能让色彩刻度离散化，并且在每种色彩过渡区域都能显示黑线。这种表现形式类似于在填色等值面图上叠加等值线，使得对分子静电势的分析更容易定量化。相比之下，Molekel 5.x版本不支持色彩刻度离散化，无法替代4.x版实现此功能。

---

## 2. Molekel 5.4绘制静电势填色图的操作步骤

在Gaussian 03计算时必须加上gfoldprint pop=full关键词以输出足够信息。在Molekel 5.4中载入g03 output文件后，选择Surfaces-Electron Density，勾选Density Matrix和Map Molecular Electrostatic Potential，Isosurface Value输入0.001。调整Bounding Box的x,y,z中心及dx,dy,dz延展距离以避免等值面被截断，点击Generate生成图像。

---

## 3. Molekel 5.4图像显示设置

在Molekel 5.4中，通过选Display-Background并将背景设为白色；选Display-Hide Bounding Boxes去掉分子周围的方框；选Display-Show MEP Scalar Bar显示并可用鼠标拖动色彩刻度条。若想使等值面透明，需再次进入Surfaces-Electron Density，点击Transparency并调大Density Matrix的数值。

---

## 4. Molekel 4.3载入Gaussian输出文件的修改要求

Molekel 4.x面向Gaussian 98，载入Gaussian 03输出文件前必须手动修改：将文件开头的"Gaussian 03"改为"Gaussian 98"，否则分子会变成平面的；将布居分析中的"Mulliken atomic charges"改为"Total"，否则Molekel找不到原子电荷条目，无法计算静电势。如果是多步任务如几何优化，需修改最后一次出现的Mulliken atomic charges。

---

## 5. Molekel 4.3生成电子密度等值面

在Molekel 4.3主窗口点右键选Compute-El. density生成电子密度格点数据，然后选Surface将cutoff设为0.001并点Create surface。如果等值面在边缘有窟窿，说明格点数据空间范围太小，需通过Compute-Adjust box调大x,y,z的上下限，并重新生成电子密度格点数据。

---

## 6. Molekel 4.3绘制静电势及设置背景

在Molekel 4.3中生成电子密度等值面后，点右键选Compute-MEP，选map to surface并点OK，即可在等值面上显示静电势色彩投影。将背景设为白色需在右键菜单选Color，将Diffuse color的r,g,b都设为1并点background下的top和bottom按钮；若要将色彩刻度条文字改为黑色，需将r,g,b都设为0后点label按钮。

---

## 7. Molekel 4.3中Texture功能的使用

Molekel 4.3中用黑线分隔离散色彩刻度的功能叫做Texture，去掉main interface窗口中texture的勾选可使色彩连续化。通过右键菜单选Texture，点击tex list up/down按钮可切换预设的四种texture；在add texture to下点击surface并点击主窗口中的等值面即可套用texture；texture properties框可调节细节及设定显示的刻度区间。

---

## 8. Molekel 4.3绘制精确静电势图的数据要求

精确绘制静电势图需要从外部载入电子密度格点文件和精确计算的静电势格点文件，且两个格点文件的格点设定必须完全一致。这两个文件可用Gaussian自带的cubegen或Multiwfn生成，其中Multiwfn使用核吸引势积分方法计算静电势，是完全精确的。

---

## 9. Molekel 4.3载入Cube文件绘制精确图的步骤

将电子密度和静电势文件后缀改为cube并置于Molekel目录下，在主窗口右键选Load-gaussian cube载入文件以读取结构信息。选Surface将类型选为gaussian cube，点Load载入电子密度文件，设cutoff为0.001并点create surface生成等值面。再次点Load载入静电势文件，点grid value和OK，即可将精确静电势数据投影到等值面上。

---

## 10. 原子电荷计算静电势的局限性

原子电荷模型将静电势视为点电荷球型势的叠加，忽略了原子核附近电子分布的各向异性（如pi键、孤对电子）。在F2分子中，由于对称性原子电荷为0，导致用其计算的静电势处处为0，掩盖了轴线端点的正值区域和侧面的负值区域，无法反映真实的静电势分布信息。

---

## 11. Mulliken电荷用于静电势分析的缺陷

Mulliken电荷对精确静电势的重现性很差，偏差通常是拟合静电势电荷的2~3倍。此外，Mulliken电荷存在交叉项平分缺乏物理意义、结果不随基组质量提高而收敛、在含弥散函数基组下容易出现荒谬结果等问题。因此，不建议使用Mulliken电荷来产生静电势，Molekel内置计算的静电势顶多作为定性参考。

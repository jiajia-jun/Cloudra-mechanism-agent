---
id: 291
title: 用Multiwfn+VMD做RDG分析时的一些要点和常见问题
domain: 波函数与电子结构分析
topic: Multiwfn结合VMD绘制RDG图的要点与常见问题
cards: 24
---

## 1. RDG分析背景与相关方法介绍
用量子化学输出文件结合VMD绘制RDG填色等值面图是研究弱相互作用的常用方法，详见《使用Multiwfn图形化研究弱相互作用》。文中讨论的很多问题对于绘制IGM图、IGMH图、IRI图也是通用的，相关方法介绍见《通过独立梯度模型(IGM)考察分子间弱相互作用》、《使用Multiwfn做IGMH分析非常清晰直观地展现化学体系中的相互作用》和《使用IRI方法图形化考察化学体系中的化学键和弱相互作用》。所有这些方法的全面介绍见《一篇最全面介绍各种弱相互作用可视化分析方法的文章已发表！》和《Angew. Chem.上发表了全面介绍各种共价和非共价相互作用可视化分析方法的综述》。

---

## 2. 关闭VMD的Depth cueing以提升白背景图像通透度
默认情况下VMD开启Depth cueing会使距离观测者越远的部分被雾化得越重，在白背景下绘制RDG图会使图像变得朦胧。建议选择Display-Depth cueing将此设定关掉，图像会变得鲜艳、通透。注：目前最新版本的Multiwfn里自带的RDG作图脚本默认就是将Depth cueing关闭的。

---

## 3. 开启VMD抗锯齿以消除等值面边缘锯齿
VMD显示的图形在白背景下边缘的锯齿看起来往往比较明显，建议开启抗锯齿。如果Display里能选Antialiasing，点它即可；如果是灰色的，可以在显卡驱动面板里强行开启抗锯齿，或者使用Tachyon渲染器渲染。此外，获得大尺寸图像后用PS等程序缩小也能等效实现抗锯齿效果。

---

## 4. 调整VMD光源以照亮等值面暗处
默认光源设定下，有些等值面可能看起来偏黑，不好看甚至影响对颜色的判断。此时可以选Display里面的Light 2或3开启没使用的光源，并使用Mouse - Move Light移动光源。注：目前最新版本的Multiwfn里自带的RDG作图脚本默认就是开启Light 3光源的。

---

## 5. 使用Tachyon渲染器获得高分辨率RDG图像
作RDG图推荐用VMD自带的Tachyon渲染器，选File-Render-Tachyon (internal, in-memory rendering)可直接调用Tachyon渲染当前窗口得到.tga文件。若想渲染出更大尺寸的图像，选择Tachyon并Start Rendering得到vmdscene.dat文件，然后建立.bat文件运行命令：`tachyon_WIN32.exe vmdscene.dat -aasamples 24 -mediumshade -trans_vmd -res 1024 768 -format BMP -o vmdscene.bmp`。其中-res控制分辨率，-aasamples越大锯齿越不明显，修改vmdscene.dat里的zoom可调节图像内体系的尺寸。

---

## 6. 通过调整格点间距解决RDG等值面锯齿和窟窿问题
格点间距越小，等值面边缘越平滑，中间有窟窿的可能性越低。建议指定更高数目的格点或更小的格点间距，在RDG分析界面选择"4 Input the number of points or grid spacing in X,Y,Z, covering whole system"输入恰当的格点间距（如0.08 Bohr）。对于大体系，即便high quality grid对应的格点间距也可能偏大，此时自设格点间距尤为重要。

---

## 7. RDG分析色彩刻度的合理设定范围
RDG的色彩刻度选择具有任意性，一般建议用-0.035~0.02，或者-0.03~0.02。下限越接近0，吸引作用区域越容易显蓝色；反之越容易显绿色。虽然-0.04~0.02很常用，但这样设定下一些偏弱的氢键区域就不怎么显蓝色了。

---

## 8. 将不同体系的RDG散点图合并绘制
对每个体系分别计算sign(lambda2)rho和RDG数据，在Multiwfn后处理界面选2 Output scatter points to output.txt导出散点数据。将多个体系的数据导入Origin，设定多个Layer，一个Layer对应一个体系，并用不同颜色区分即可作到一起。

---

## 9. 在VMD中分别计算并显示体系不同区域的RDG等值面
计算时通过合理设定格点数据的计算范围只计算不同区域。在VMD中，将func2.cub拖进产生一个id，载入func1.cub时选择载入到该id里。在Graphics-Representation新建等值面层，设置Drawing method为isosurface，isovalue一般为0.5，Show为Isosurface，Draw为Solid Surface，Coloring method为Volume并选择func1.cub，设置Color Scale Date Range。对体系其它部分重复此操作，多个id对应的填色等值面即可显示不同区域。

---

## 10. RDG散点图中未完全触底spike的物理意义
散点图中一些未完全戳到底但离底部很近的spike是合理的，一般也有意义。这些弱相互作用用AIM分析可能无法展现（不会出现临界点），但RDG方法可以表现出来，这是RDG相对于AIM的一个优势。相关讨论见Chemistry—Methods, 1, 231-239 (2021) DOI: 10.1002/cmtd.202100007的2.4节。

---

## 11. RDG分析的定量化方法
RDG定量讨论可看spike的位置，或结合AIM定量分析（见《AIM学习资料和重要文献合集》）。氢键靠AIM理论可以准确地估计作用能，见《透彻认识氢键本质、简单可靠地估计氢键强度：一篇2019年JCC上的重要研究文章介绍》。还有人提出积分RDG等值面内部区域的做法（J. Phys. Chem. A, 115, 12983 (2011)），可通过Multiwfn的域分析功能实现（见手册4.200.14.1节）。

---

## 12. 绘制周期性体系RDG图的方法与限制
从Multiwfn 3.8版开始支持绘制周期性体系的RDG图，通常建议结合CP2K实现，详情见《使用Multiwfn结合CP2K通过NCI和IGM方法图形化考察固体和表面的弱相互作用》。对于Multiwfn不直接支持的程序，可以基于promolecular近似作RDG图，仅需坐标信息（.pdb、.xyz等格式），结果定性正确但不如基于波函数准确。

---

## 13. 处理大体系RDG等值面过多不便分析的方法
处理大体系RDG等值面过多的方法包括：用Multiwfn主功能13处理RDG格点数据屏蔽不感兴趣的部分（见手册4.13.4节）；设置格点时让空间范围只涵盖感兴趣区域；借助第三方程序控制每个单独的等值面显示。更推荐改用IGMH方法直接指定考虑哪些部分间的相互作用，见《使用Multiwfn做IGMH分析非常清晰直观地展现化学体系中的相互作用》。

---

## 14. 区分散点图中不同spike对应的相互作用
区分散点图spike对应相互作用的方法有：(1)用Multiwfn做AIM分析得到BCP的sign(lambda2)rho值并与散点图对照；(2)设定格点数据计算范围仅囊括某个弱相互作用区域；(3)在Multiwfn中选择"Set function2 value where the value of function1 is out of a certain range"屏蔽特定sign(lambda2)rho范围的格点，仅显示特定spike对应的等值面；(4)绘制带有填色效果的散点图对比等值面颜色（见）。

---

## 15. 判断弱相互作用应优先查看RDG填色等值面图
判断弱相互作用绝对不要光看散点图，应优先查看RDG填色等值面图，因为弱相互作用的位置和特征在等值面图上一目了然。散点图过于抽象，且仅当需要定量考察、对比时才应结合散点图一起看。

---

## 16. 使用VMD以外的程序绘制RDG图的可行性
VMD作RDG填色等值面图效果最好且方便。Chemcraft也能作但效果难看；Jmol、Gabedit、AIMALL等开始支持但效果差、速度慢且功能不全。Multiwfn+VMD是RDG分析的黄金组合。此外，基于Multiwfn输出的格点文件用Pymol也可以绘制，着色效果更鲜亮。

---

## 17. RDG图中出现蓝内红外环状等值面的原因
相互作用很强的两个原子间，中央部分电子密度可能超过默认阈值0.05 a.u.而被屏蔽，只剩外围一圈形成环状。settings.ini文件的默认设置RDG_maxrho=0.05旨在展现弱相互作用（低电子密度区域）。这种情况可视作较弱化学键，若想展现完整等值面可将RDG_maxrho设为0，但化学键区域会出现无意义的等值面。强烈建议使用IRI方法展现所有类型相互作用，见《使用IRI方法图形化考察化学体系中的化学键和弱相互作用》。

---

## 18. 蓝色等值面外圈出现红色无化学意义的原因
蓝色等值面外圈出现红色是由于投影函数sign(lambda2)rho自身的特征所致。在lambda2数值非常接近0的地方，轻微变化就会引起符号突变，导致颜色突变。这圈红色没有化学意义，无法解释，直接无视即可。若想避免，可加大RDG等值面数值使等值面收缩，避免涉及到sign(lambda2)rho为正的区域。

---

## 19. 弱相互作用区域未显示出来的原因及解决
弱相互作用区域未显示可能是因为相互作用强度很强（如键能超过100 kJ/mol），区域电子密度超过默认RDG_maxrho=0.05而被屏蔽。此时应适当调大RDG_maxrho重新作图，或改用IRI方法。此外，使用RDG方法前必须优化结构，特别是晶体结构中的氢原子位置不准会导致电子密度被高估，从而无法显示等值面。

---

## 20. 在第三方程序中绘制RDG散点图的方法
在Origin里绘制RDG散点图的方法可参考《用Multiwfn+Origin绘制RDG(NCI)方法的散点图》。更推荐使用gnuplot绘制，因其方便、免费且有着色效果，可参考《绘制有填色效果的用于弱相互作用分析的RDG散点图的方法》。

---

## 21. RDG散点图spike上点比较散的原因
散点图spike上的点比较散不体现化学意义，仅说明落在弱相互作用区域的格点比较少。原因可能是格点间距偏大或弱相互作用区域比较小。解决方法包括：在第三方程序里加大点的尺寸，或者在RDG分析前把弱相互作用区域的格点间距改小一些。格点设定知识见《Multiwfn FAQ》第3节。

---

## 22. RDG等值面显示为灰色或黑色的排查方法
RDG等值面显示为灰色或黑色有三种可能：(1)VMD和显卡兼容性问题，尝试更新显卡驱动、换机子尝试或用Tachyon渲染器（纯软件渲染）；(2)cub文件太大而用了Windows 32bit版VMD导致内存不足，改用64bit版VMD；(3)cub文件有问题，检查文件名、目录、大小和内容是否正常。

---

## 23. 获取高清晰度色彩刻度条用于文章的方法
最新版Multiwfn程序包的examples目录下已提供高清晰度色彩刻度条文件（RGB_bar.png）。

---

## 24. RDG、IGM、IGMH、IRI图形化方法的选用建议
关于RDG、IGM、IGMH、IRI这些图形化相互作用分析方法的选用，可参考《使用Multiwfn做IGMH分析非常清晰直观地展现化学体系中的相互作用》第3节的详细讨论。

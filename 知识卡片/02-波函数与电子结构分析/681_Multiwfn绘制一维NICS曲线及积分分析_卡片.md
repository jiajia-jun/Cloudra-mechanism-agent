---
id: 681
title: 使用Multiwfn绘制一维NICS曲线并通过积分衡量芳香性
domain: 波函数与电子结构分析
topic: Multiwfn绘制一维NICS曲线及积分分析
cards: 9
---

## 1. NICS曲线积分与INICS指数
NICS曲线积分是指从环中心开始在垂直于环方向上对NICS_ZZ进行扫描并积分，该积分值被称为INICS指数。根据J. Phys. Chem. A, 123, 3922 (2019)和J. Phys. Chem. A, 126, 3433 (2022)的研究，INICS比考察个别点的NICS(0)ZZ或NICS(1)ZZ在衡量芳香性上更严格可靠。垂直穿越某环的NICS_ZZ曲线积分值为明显负值、接近0、明显正值分别说明相应的环表现芳香性、非芳香性和反芳香性。

---

## 2. 一维NICS曲线功能相比ICSS的优势
Multiwfn的一维NICS曲线计算功能相比ICSS格点数据计算具有明显优势：计算耗时少，笔记本即可完成；支持NICS分解成轨道贡献（如分离sigma和pi电子贡献），这解决了ICSS模块因Ghost原子多导致卡顿无法分解的技术限制；支持考察任意方向NICS分量，例如垂直于某个倾斜的环方向的分量。

---

## 3. 苯分子的一维NICS扫描与积分操作
对苯分子进行一维NICS扫描需在Multiwfn中依次输入：examples\NICS_scan\benzene.pdb -> 25 -> 13 -> 2 -> 1-6 -> [回车] -> 10 -> 10 -> 200 -> 1 -> examples\NICS_scan\template_NMR.gjf。产生的NICS_1D.gjf文件经Gaussian计算后，载入结果文件benzene_NICS_1D.out，选1可绘图，选4可计算积分值。苯分子在环平面上方和下方0.955埃处NICS最小值为-28.7 ppm，双侧积分值为-140.78 ppm*Angstrom。

---

## 4. C5H5-、C7H7+与苯的NICS曲线对比
C5H5-和C7H7+的NICS积分值分别为-152.70 ppm*Angstrom和-142.06 ppm*Angstrom，苯为-140.78 ppm*Angstrom。从全电子NICS扫描角度看C5H5-芳香性最强，但这并不准确，因为对芳香性无贡献的sigma电子对距离平面较近处的NICS有影响，需要单独考察pi电子贡献才能严格对比。

---

## 5. 利用Gaussian CSGT接口计算NICS轨道贡献
计算特定轨道（如pi轨道）对NICS的贡献需使用Gaussian的CSGT接口。在模板文件中写入#p b3lyp/6-31+G* nmr=csgt iop(10/93=2)并在末尾添加轨道序号（如苯的pi轨道为17,20,21）。轨道序号可通过Multiwfn主功能0查看fch文件获得，或参考《在Multiwfn中单独考察pi电子结构特征》自动判断。注意NMR=CSGT与默认GIAO方式结果有定量差异（如苯NICS(1)ZZ分别为-27.13和-28.76 ppm），不适合直接对比。

---

## 6. 苯、C5H5-和C7H7+的NICS-sigma与NICS-pi对比
只考虑pi轨道贡献时，NICS曲线处处为负；sigma电子对距离平面很近区域贡献明显为正。通过积分值对比pi芳香性，顺序为C7H7+ >= benzene > C5H5-。具体积分值为：benzene sigma: 14.82 pi: -142.45；C5H5- sigma: -0.38 pi: -134.85；C7H7+ sigma: 14.64 pi: -145.02。此结果与J. Phys. Chem. A, 123, 3922 (2019)文献一致。

---

## 7. 倾斜扭曲环的一维NICS扫描设置
对于倾斜或扭曲的环（如无穷烯中间的环），若无法双侧扫描，可设置单侧扫描。在Multiwfn中定义环原子后，设置一个端点距离（如下方10埃）和另一个端点距离（如上方0埃），点数可选默认推荐值。若Bq分布方向与预期相反，需交换上下距离重新产生输入文件。扫描无穷烯中间环单侧10埃得到的NICS积分值为-96.46 ppm*Angstrom。

---

## 8. NICS计算中基组的选择与弥散函数的影响
是否带弥散函数对NICS曲线影响甚微，但计算耗时差异巨大。以无穷烯体系为例，6-31G*和6-31+G*在96核机上计算耗时分别为1m6s和4m37s，积分值分别为-96.46和-96.19 ppm*Angstrom。对于中性体系，计算NICS时没太大必要带弥散函数，若追求更好结果可用3-zeta档次基组。

---

## 9. 注意事项与文献引用建议
使用Multiwfn产生NICS扫描的gjf文件后，建议放入GaussView检查Bq位置是否正确。相邻环产生的磁屏蔽效果会产生叠加，可能导致某环积分值偏高，此时应结合多中心键级或AV1245指数等其他指标综合判断芳香性。发表文章时请按Multiwfn启动后显示的信息恰当引用Multiwfn原文，并建议引用Chem. Eur. J., 30, e202403369 (2024)等应用了该方法的文章。

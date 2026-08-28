---
id: 724
title: 使用Multiwfn计算FiPC-NICS芳香性指数
url: http://sobereva.com/724
domain: 波函数与电子结构分析
topic: Multiwfn计算FiPC-NICS芳香性指数
cards: 8
---

# Multiwfn计算FiPC-NICS芳香性指数 — 知识卡片

## 1. FiPC-NICS的定义与原理

FiPC-NICS是一种基于NICS的芳香性指数，定义为从环中心出发垂直于环的扫描路径上NICS_in为0的位置的NICS_out值，旨在排除定域化电子的影响。NICS可分解为平行于环的in-plane分量(NICS_in)和垂直于环的out-of-plane分量(NICS_out)，其中NICS=(NICS_XX+NICS_YY+NICS_ZZ)/3，NICS_in=(NICS_XX+NICS_YY)/3，NICS_out=NICS_ZZ/3。该指数由Inorg. Chem., 53, 3579 (2014)提出。

---

## 2. FiPC-NICS与NICS(1)ZZ的关系及对比

根据原文测试，对于碳环体系，NICS_in为0的位置距离环中心约1.2埃，这与计算NICS(1)ZZ所用的1埃距离相近。对于非碳环类体系，考虑到不同元素原子大小的差异，使用FiPC-NICS对比芳香性比使用NICS(1)ZZ更为严格。只考虑pi电子贡献的NICS(1)ZZ在衡量碳环芳香性上可能比FiPC-NICS更理想，但FiPC-NICS在程序实现上更容易。

---

## 3. NICS_in与NICS_out相关图特征

将NICS_in作为横坐标、NICS_out作为纵坐标绘制扫描路径上的点，不同芳香性分子的曲线特征截然不同。典型芳香性分子苯的曲线是下凹的，典型反芳香性分子环丁二烯的曲线是上凸的，非芳香性分子的曲线接近直线。所有体系的曲线最终都会收敛到(0,0)，因为距离环中心很远处NICS的各个分量都收敛到0。

---

## 4. Multiwfn计算FiPC-NICS的操作步骤

启动Multiwfn并输入优化后的输出文件(如opt.out)，选择主功能25(芳香性与离域性分析)及子功能13(NICS-1D扫描、积分与FiPC-NICS计算)。选择通过一批原子定义环的模式，输入原子序号(如1-6)定义环，设置首端位于环中心，另一端位于环上方10埃处，扫描点数设为200。随后选择产生Gaussian输入文件并指定模板文件(如template_NMR_6-311++Gxx.gjf)。

---

## 5. Multiwfn计算FiPC-NICS的后处理步骤

运行Gaussian计算生成的NICS_1D.gjf文件得到NICS_1D.out后，在Multiwfn中选择读取NICS-1D扫描结果并输入该文件名。接着选择计算FiPC-NICS功能，屏幕将显示结果及位置信息。程序还会输出FiPC-NICS.txt文件，包含扫描点序号、距离环中心的距离、NICS_in和NICS_out数值。

---

## 6. 苯分子FiPC-NICS计算实例验证

使用Gaussian 16 C.02版和Multiwfn 2024-Jul-13版，在PBE0/6-311++G**级别下计算苯的FiPC-NICS，结果为-9.58 ppm，位置在苯环中央上方1.192埃处。该结果与FiPC-NICS原文(Inorg. Chem., 53, 3579)中的-9.59 ppm、1.18埃高度吻合。根据输出文件绘制的NICS_in vs NICS_out曲线与原文图1中的苯曲线完全一致。

---

## 7. 计算FiPC-NICS的几何限制与注意事项

使用Multiwfn计算FiPC-NICS时，扫描路径必须平行于X、Y或Z轴。如果环平面不平行于某个笛卡尔平面，需要利用几何操作功能将考察的环平行于某个笛卡尔平面。Gaussian输入模板文件中应带上nosymm关键词，以避免Gaussian自动旋转分子朝向。

---

## 8. Multiwfn功能引用要求

使用Multiwfn计算FiPC-NICS用于发表文章时，必须按照Multiwfn启动时的提示恰当引用Multiwfn的原文。给别人代算时也必须明确告知这一点。

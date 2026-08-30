---
key: b724
title: 使用Multiwfn计算FiPC-NICS芳香性指数
url: http://sobereva.com/724
domain: 波函数与电子结构分析
source: blog
year: 2024
cards: 10
---

# 使用Multiwfn计算FiPC-NICS芳香性指数 — 知识卡片

## 1. FiPC-NICS 指数定义与来源

FiPC-NICS (free of in-plane component NICS) 是一种由 Inorg. Chem., 53, 3579 (2014) 提出的芳香性指数，旨在消除定域电子（如内核电子、sigma键电子）对 NICS 计算的影响。该指数定义为从环中心出发垂直于环的扫描路径上，NICS_in 分量为 0 时的 NICS_out 值。Multiwfn 程序已扩展支持在后处理菜单中计算该指数。

---

## 2. NICS 的平面内与平面外分量分解

对于环平面平行于 XY 平面的体系，任意点的 NICS 可分解为平行于环的 in-plane 分量 (NICS_in) 和垂直于环的 out-of-plane 分量 (NICS_out)。计算公式为：NICS = NICS_in + NICS_out = (NICS_XX + NICS_YY + NICS_ZZ)/3，其中 NICS_in = (NICS_XX + NICS_YY)/3，NICS_out = NICS_ZZ/3。NICS_ZZ 等于相应位置磁屏蔽张量 ZZ 分量的负值。

---

## 3. FiPC-NICS 的物理原理

定域电子对芳香性无实质贡献，但会影响 NICS_in，若距离环中心过近还会“污染” NICS_out。FiPC-NICS 通过在垂直于环的路径上寻找 NICS_in 恰好为 0 的位置，并取该处的 NICS_out 值，从而最大程度避免定域电子的影响，严格利用 NICS 思想衡量芳香性。

---

## 4. FiPC-NICS 与 NICS(1)_ZZ 的关系

FiPC-NICS 与常用的 NICS(1)_ZZ 指数密切相关。对于碳环体系，NICS_in 为 0 的位置距离环中心约 1.2 埃，与 NICS(1)_ZZ 使用的 1 埃距离相近，这体现了 NICS(1)_ZZ 的内在合理性。对于非碳环类体系，考虑原子大小差异，使用 FiPC-NICS 对比芳香性比 NICS(1)_ZZ 更为严格。

---

## 5. NICS_in 与 NICS_out 相关性图特征

将垂直于环扫描路径上各点的 NICS_in (横坐标) 与 NICS_out (纵坐标) 绘制成图，可区分不同芳香性特征。典型芳香性分子苯的曲线呈下凹状，反芳香性分子环丁二烯呈上凸状，非芳香性分子曲线接近直线。所有曲线随距离增加最终收敛于 (0,0)。

---

## 6. 使用 Multiwfn 生成 NICS-1D 扫描输入文件

在 Multiwfn 主功能菜单选择 25 (芳香性与离域性分析) 和 13 (NICS-1D 扫描、积分与 FiPC-NICS 计算)。选择通过原子定义环模式，输入原子序号（如苯为 1-6），定义端点距离（如 0 到 10 埃）和扫描点数（如 200）。选择产生 Gaussian 输入文件，并指定包含 [geometry] 占位符的模板文件（如 template_NMR_6-311++Gxx.gjf）。

---

## 7. 计算 FiPC-NICS 的步骤

运行生成的 NICS_1D.gjf 得到 NICS_1D.out 后，在 Multiwfn 中选择 2 (读取 NICS-1D 扫描结果) 并指定输出文件。接着选择 6 (计算 FiPC-NICS)，程序将输出 FiPC-NICS 值及其对应的距离环中心的高度。对于苯在 PBE0/6-311++G** 级别下，结果为 -9.58 ppm，位于环中心上方 1.192 埃处。

---

## 8. FiPC-NICS 计算的输出文件

Multiwfn 完成计算后会生成 FiPC-NICS.txt 文件，其中包含扫描点的序号、距离环中心的距离、NICS_in 值和 NICS_out 值。该文件的数据可用于绘制 NICS_in vs NICS_out 的散点连线图，曲线形态应与文献中的理论图完全吻合。

---

## 9. FiPC-NICS 计算的几何要求与注意事项

使用该功能时，扫描路径必须平行于 X、Y 或 Z 轴。如果环平面不平行于笛卡尔平面，需先利用 Multiwfn 的几何操作功能将环调整至平行。Gaussian 计算模板文件中应包含 nosymm 关键词以防止程序自动旋转分子朝向。

---

## 10. 引用要求

使用 Multiwfn 计算 FiPC-NICS 并用于发表文章时，必须按照程序启动时的提示恰当引用 Multiwfn 的原文。

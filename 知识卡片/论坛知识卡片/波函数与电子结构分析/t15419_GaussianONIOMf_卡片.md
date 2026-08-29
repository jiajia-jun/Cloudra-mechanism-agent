---
key: t15419
title: ��Gaussian��ONIOM������fch�ļ���Multiwfn������������Ҫע�������
url: http://bbs.keinsci.com/thread-15419-1-1.html
domain: 波函数与电子结构分析
source: keinsci
year: 2019
cards: 6
---

# ��Gaussian��ONIOM������fch�ļ���Multiwfn������������Ҫע������� — 知识卡片

## 1. ONIOM 检查点文件的电荷信息缺失问题

Gaussian 进行 ONIOM 计算产生的 chk 或 fch 文件中，电荷信息通常仅包含低层 (Low layer) 体系的数据。这种文件若直接输入 Multiwfn，程序会将其视为仅有低层体系的普通波函数文件进行处理。

---

## 2. ONIOM 文件中波函数与层级的对应关系

在 ONIOM(H:L) 模式下，Gaussian 会针对整个体系生成波函数，但最终写入 chk 文件的波函数实质上对应的是 Low layer。若 Low layer 包含虚原子，Multiwfn 无法直接处理此类波函数，导致对电子结构的分析功能失效。

---

## 3. 电子结构分析对波函数方法的要求

若 ONIOM 计算的高层 (High layer) 采用纯 DFT 方法，chk 文件中的波函数即为 DFT 波函数。此时 Multiwfn 可以正常进行电子结构分析，且对于高层原子的分析，其结果即为 DFT 水平下的结果，准确性有保障。

---

## 4. 处理包含虚原子的 ONIOM 体系结构分析

若研究对象仅涉及结构的几何分析，而非波函数分析，可直接使用包含虚原子的 Low layer 波函数。若必须对包含虚原子的体系进行电子结构分析，需将高层原子再次导出并进行单点计算，以获得可被 Multiwfn 识别的标准波函数文件。

---

## 5. 包含 MM 原子的 ONIOM 体系电荷计算策略

若 ONIOM 体系的低层包含 MM 原子，这些原子的存在会影响高层原子的电荷分布。为了准确计算高层原子的电荷，应在计算时将 MM 原子再次设定为可观测的体系，并使用电荷关键词（如 CHELPG 或 MK）进行拟合计算，生成的电荷位置即对应低层原子（原 MM 原子）的位置。

---

## 6. ONIOM 计算中 out=wfn 关键字的注意事项

在 Gaussian 09 和 Gaussian 16 A.03 及之前的版本中，ONIOM 计算时使用 `out=wfn` 关键字存在程序崩溃的 Bug。由于 Multiwfn 可以直接读取 fch 文件，因此没有必要在 ONIOM 计算中输出 wfn 文件。

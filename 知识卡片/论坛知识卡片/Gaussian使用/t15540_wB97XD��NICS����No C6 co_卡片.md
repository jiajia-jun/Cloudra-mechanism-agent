---
key: t15540
title: wB97XD��NICS����No C6 coefficient available for IA=  0�Ľ������
url: http://bbs.keinsci.com/thread-15540-1-1.html
domain: Gaussian使用
source: keinsci
year: 2019
cards: 4
---

# wB97XD��NICS����No C6 coefficient available for IA=  0�Ľ������ — 知识卡片

## 1. 计算NMR和NICS时的色散修正错误处理

在进行NICS计算时需要引入Bq原子作为探针，而Bq原子在色散校正参数表中没有定义，导致Gaussian报错“No C6 coefficient available for IA= 0”。Gaussian 16 B.01版本引入该问题，而C.01版本已修复，无需额外处理即可计算含色散校正的方法。
- 报错原因：Bq原子（IA=0）缺乏C6系数。
- 版本差异：G16 C.01已修复此Bug。

---

## 2. Gaussian 16 B.01版本的色散修正绕过方法

对于Gaussian 16 B.01版本，可以通过添加`empiricaldispersion`关键字来解决Bq原子缺乏色散系数的问题。该关键字允许程序在不依赖预设原子色散参数的情况下进行计算。
- 适用版本：Gaussian 16 B.01。
- 解决方案：输入文件中加入`empicaldispersion`。

---

## 3. 强制关闭色散校正的IOp参数设置

若上述方法无效，可通过设置`IOp(3/124=4)`来强制关闭色散校正。关闭后，wB97XD等含色散的方法将退化为其不含色散的版本（如wB97X）。虽然此方法会影响体系的能量数据，但对NMR和NICS的化学位移计算影响极小。
- 关键命令：`IOp(3/124=4)`。
- 结果影响：NMR/NICS数据精度基本保持不变，能量数据受影响。

---

## 4. wB97XD与wB97X的功能差异及对NMR的影响

wB97XD是在wB97X基础上加入了色散校正，二者在能量计算上存在差异。但在进行NMR或NICS计算时，主要关注磁屏蔽常数，此时使用wB97X（即关闭DFT-D色散）与wB97XD的结果差异极小。
- 核心差异：DFT-D色散校正的存在与否。
- 计算建议：NMR/NICS计算中可忽略色散校正的影响。

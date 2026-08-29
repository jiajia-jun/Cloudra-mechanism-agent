---
key: t17030
title: ��Gaussian 16�������������������DFT��SODFT������
url: http://bbs.keinsci.com/thread-17030-1-1.html
domain: Gaussian使用
source: keinsci
year: 2020
cards: 18
---

# ��Gaussian 16�������������������DFT��SODFT������ — 知识卡片

## 1. SODFT 软件支持现状

NWChem 支持 SODFT。Turbomole 支持含标量相对论效应的 TDDFT 及 MP2、CC2 等方法，但目前不支持 SODFT。Dirac 程序支持 SODFT 且功能强大。

---

## 2. Gaussian 支持相对论计算的时间点

Gaussian 从 16 版本开始支持含 SO 耦合的 HF 和 DFT 计算。Gaussian 安装包的 tests 目录下的 test1198 是一个针对 Tl 原子的多电子 SOHF 测试例子。

---

## 3. 多电子 SO 效应计算的输入文件基本设置

多电子 SCF 计算需在常规 HF/DFT 关键词前加前缀 g。Gaussian 的多电子 SCF 计算属于 GHF/GKS non-collinear 框架，未指定时间反演对称性，也利用了点群对称性。

---

## 4. 含重元素分子的几何对称性限制

GHF/GKS 处理分子的几何对称性较为严格。如果需要降低对称性，需在分子坐标系中将 Z 轴选为主轴，并在计算路径中使用 opt(z-mat)。

---

## 5. GHF/GKS 的频率计算方式

GHF/GKS 没有解析频率计算功能。若需计算频率，必须使用数值微分方法。

---

## 6. 相对论效应对 GHF/GKS 计算的影响

GHF/GKS 计算包含标量相对论效应。对于 L > 0 的元素，建议使用基组文件或赝势文件来定义相对论有效势。

---

## 7. Gaussian 中相对论基组的定义格式

Gaussian 支持自定义基组格式。用户可通过 genecp 或 gen pseudo 选项手动输入相对论基组数据。大多数标准数据库基组不支持 Gaussian 格式的多电子基组定义，需手动输入相关参数。

---

## 8. 相对论有效基组与标量相对论方法的兼容性

Clarkson 大学网站提供相对论有效基组下载。若未进行标量相对论计算，无需选择 pseudo=soscal 选项。该网站资源适用于 Gaussian 和 COLUMBUS 程序包。

---

## 9. TlCl 体系计算的基组与赝势选择

在 TlCl 体系计算中，Cl 原子未考虑相对论效应，使用了 cc-pVDZ 基组。Tl 原子使用 dhf-SVP 基组，也可选用 cep-4g、lanl2dz 或 sddall 基组，但需全电子基组或配合 x2c、dk、zora 等方法。

---

## 10. GHF/GKS 计算的关键词限制

GHF/GKS 支持部分积分交换格式，但不支持部分密度拟合格式。计算时需注意关键词的兼容性。

---

## 11. 多电子 SCF 计算的自旋态检查

在多电子 SCF 计算中，需重点检查 `<S**2>` 和 S 是否符合预期。计算结果的 `<S**2>` 值可能与预设不符，需结合自旋-轨道耦合进行分析。

---

## 12. GHF/GKS 计算的收敛性

GHF/GKS 计算对初始猜测敏感。从实数 SCF 获得的初始猜测可能不合适，需调整 SCF 初始猜测以提高收敛效果。

---

## 13. GHF/GKS 计算的态与轨道限制

GHF/GKS 计算仅适用于计算单态。该方法无法直接计算激发态，也无法处理开壳层体系。

---

## 14. TlCl 计算输入文件参数示例

TlCl 体系计算使用 8GB 内存和 4 个共享处理器。计算方法为 gb3lyp，结合 genecp 基组选项，执行几何优化和数值频率计算。

---

## 15. TlCl 分子几何定义

TlCl 分子初始键长设为 2.485。分子坐标采用内坐标格式定义，Tl 为原子 1，Cl 为原子 2，两者相连。

---

## 16. Cl 原子基组定义

Cl 原子使用 cc-pvdZ 基组。基组定义包含 S、P、D 轨道函数，具体指数和系数按标准格式输入。

---

## 17. Tl 原子基组定义

Tl 原子使用自定义相对论基组。基组包含 S、P、D 轨道函数，具体指数和系数在输入文件中逐行列出。

---

## 18. Tl 原子赝势定义

Tl 原子使用 TL-ECP 赝势，对应 5 个电子层和 60 个核心电子。赝势定义包含 h POTENTIAL、s-h POTENTIAL、p-h POTENTIAL、d-h POTENTIAL、f-h POTENTIAL 和 g-h POTENTIAL 部分，具体参数按格式给出。

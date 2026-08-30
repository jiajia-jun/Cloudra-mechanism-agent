---
key: t48286
title: MOKIT�Զ���ο����㲻����Gaussian�ļ���
url: http://bbs.keinsci.com/thread-48286-1-1.html
domain: 其他量化软件
source: keinsci
year: 2024
cards: 18
---

# MOKIT�Զ���ο����㲻����Gaussian�ļ��� — 知识卡片

## 1. MOKIT 解决 Gaussian 环境依赖与限制

MOKIT 可用于解决计算化学中遇到的环境限制问题，包括个人电脑或节点未安装 Gaussian 软件的情况，以及单位或节点被 Gaussian 公司禁止使用的情况。对于不方便安装或使用另一套商业或免费软件的场景，MOKIT 提供了一套解决方案。该工具允许利用已有的软件环境完成原本依赖 Gaussian 的任务，例如使用 sfX2C 精确标量相对论密度或特定基组。

---

## 2. MOKIT CASSCF 输入文件基本示例

使用 MOKIT 进行水分子 O-H 键断裂的 CASSCF 计算时，输入文件（gjf 格式）需包含内存、线程、方法和基组设置。在 Route Section 中需指定 CASSCF/cc-pVDZ 方法，并添加 `mokit{}` 关键字以调用 MOKIT 功能。分子几何坐标部分需遵循标准的 Gaussian 坐标格式，包含原子符号及 xyz 坐标。以下为具体输入文件示例：
```
%mem=4GB
%nprocshared=2
#p CASSCF/cc-pVDZ

mokit{}

0 1
O -0.23497692 0.90193619 -0.068688
H 1.26502308 0.90193619 -0.068688
H -0.73568721 2.31589843 -0.068688
```

---

## 3. automr 命令执行方式

MOKIT 提供了自动构造激发态/基态参考态的命令行工具 automr，可直接处理 gjf 输入文件并输出结果。提交计算的标准方式是在终端执行命令，将标准输出和错误重定向到日志文件中。例如，对于输入文件 h2o.gjf，执行命令为 `automr h2o.gjf >h2o.out 2>&1`。

---

## 4. automr 初始 SCF 计算与波函数稳定性判断

automr 在处理基态体系时，默认调用 Gaussian 进行 RHF 或 UHF 计算。程序会自动检测 UHF 解的稳定性，如果 UHF 不稳定或误差较大，则会尝试 RHF 计算，并选择两者中能量较低的结果。对于激发态或由用户提供初始猜想的计算，通常具有强烈的参考态特性，此时会优先使用 UHF 进行计算。

---

## 5. UNO 生成与 GVB 初始化流程

automr 会将计算得到的 UHF 轨道变换为 1 电子 UNO（自然轨道），并对 UNO 中的轨道占据数进行简化处理。简化后的占据数接近双占据（约 2.0）的轨道被视为 GVB 的初始轨道。这些 UNO 及其占据数矩阵将用于后续的 GVB 计算初始化。

---

## 6. GVB 计算与 CASSCF 活空间自动确定

automr 在第二步调用 GAMESS 进行 GVB 计算，GVB 计算本身是一个 SCF 过程，轨道会被优化。若 GVB 计算成功，程序会检查轨道占据数，若占据数落在 [0.02, 1.98] 区间内，则该轨道会被自动选入 CASSCF 的活动空间。每个 GVB pair 对应 2 个轨道，体系的活动电子数也在此时确定，过程兼顾了单占据和双占据的情况。

---

## 7. CASSCF 计算与结果文件输出

在第三步中，automr 调用 PySCF 执行 CASSCF 计算。计算成功完成后，会生成一个名为 xxx_CASSCF_NO.fch 的文件（例如水分子计算结果）。该文件包含了 CASSCF 的自然轨道及波函数信息，用户可直接使用可视化软件（如 Multiwfn）查看轨道或进行后续分析。对于水分子 O-H 键断裂示例，程序自动确定了 CASSCF(4,4) 的活动空间。

---

## 8. mokit{} 关键字的默认程序配置

在 gjf 文件中，`mokit{}` 关键字实际上对应了一组默认的程序调用配置。默认配置下，HF 计算由 Gaussian 执行，GVB 计算由 GAMESS 执行，CASSCF 计算由 PySCF 执行。用户也可以显式写出这些默认参数，格式如下：
```
mokit{HF_prog=Gaussian,GVB_prog=GAMESS,CASSCF_prog=PySCF}
```

---

## 9. 指定 HF 程序为 PySCF

用户可以通过修改 `mokit{}` 中的参数来改变不同阶段的计算程序。若不希望使用 Gaussian 进行 HF 计算，可利用 `HF_prog` 关键字指定 PySCF 作为 HF 程序。相应的输入文件示例如下：
```
%mem=4GB
%nprocshared=2
#p CASSCF/cc-pVDZ

mokit{HF_prog=PySCF}

0 1
O -0.23497692 0.90193619 -0.068688
H 1.26502308 0.90193619 -0.068688
H -0.73568721 2.31589843 -0.068688
```
使用此功能需安装 MOKIT-v1.2.6rc26 或更高版本。MOKIT 能处理不同程序间的轨道和波函数转换，生成统一的 .fch 文件以便于可视化分析。

---

## 10. 指定 HF 程序为 ORCA

除了 PySCF，用户也可以指定使用 ORCA 进行 HF 计算。只需在 `mokit{}` 关键字中设置 `HF_prog=ORCA`。具体的输入文件示例如下：
```
%mem=4GB
%nprocshared=2
#p CASSCF/cc-pVDZ

mokit{HF_prog=ORCA}

0 1
O -0.23497692 0.90193619 -0.068688
H 1.26502308 0.90193619 -0.068688
H -0.73568721 2.31589843 -0.068688
```
使用 ORCA 进行 HF 计算需要安装 MOKIT-v1.2.6rc38 或更高版本。

---

## 11. Gaussian 中使用 sfX2C 相对论方法的限制

Gaussian 目前不支持 sfX2C（精确标量相对论）哈密顿量以及 x2c-SVPall、x2c-TZVPall 等对应基组。如果计算需要使用这些相对论方法和基组，必须借助 MOKIT 调用其他支持该功能的软件。

---

## 12. 使用 PySCF 进行 sfX2C 相对论计算

若需使用 sfX2C 哈密顿量及 x2c-SVPall 等基组，可以在 gjf 文件中设置基组为 `CASSCF/x2c-SVPall`，并在 `mokit{}` 中添加 `X2C` 关键字。由于 Gaussian 不支持该功能，必须显式或隐式地指定 `HF_prog=PySCF` 以利用 PySCF 进行支持 X2C 的 HF 计算。输入文件示例如下：
```
%mem=4GB
%nprocshared=2
#p CASSCF/x2c-SVPall

mokit{HF_prog=PySCF,X2C}

0 1
O -0.23497692 0.90193619 -0.068688
H 1.26502308 0.90193619 -0.068688
H -0.73568721 2.31589843 -0.068688
```
此时 automr 检测到 X2C 关键字且知道 Gaussian 不支持，会自动切换到 PySCF 进行 HF 计算。此功能从 MOKIT-v1.2.6rc26 开始支持。

---

## 13. 使用 ORCA 进行 sfX2C 相对论计算

如果尝试使用 ORCA 6 支持的 sfX2C 功能，可以在 `mokit{}` 中写 `HF_prog=ORCA` 并配合 X2C 相关参数。MOKIT 支持利用 ORCA 处理此类相对论计算。此功能从 MOKIT-v1.2.6rc39 版本开始支持。

---

## 14. GVB 程序与 CASSCF 程序的可选范围

用户可以灵活更改 GVB 和 CASSCF 计算所使用的程序。`GVB_prog` 可以设置为 Gaussian 或 QChem。`CASSCF_prog` 支持多种程序，包括 OpenMolcas, ORCA, Molpro, GAMESS, Gaussian, BDF, PSI4, Dalton 等。用户可以根据个人偏好或软件授权情况选择合适的程序组合。

---

## 15. MOKIT 默认程序选择的策略

automr 工具默认的程序选择是基于计算效率和通用性综合考虑的。通常情况下，不建议用户随意更改默认设置（除非涉及特殊功能如 sfX2C）。MOKIT 默认的各个程序选择是在该程序发布当时性能较优的版本，且各程序间接口的稳定性经过了测试。由于各软件发展迅速，可能会出现新的强迫性功能或算法，MOKIT 的默认配置未来可能会随之调整。

---

## 16. MOKIT 对 Gaussian 用户的功能扩展

通过 MOKIT，用户可以在熟悉的 Gaussian gjf 文件语法中调用 Gaussian 原本不具备的功能（如 PySCF 支持的特定基组或相对论方法）。这种设计允许 Gaussian 用户在不学习新软件输入格式的情况下扩展功能，并节省学习新程序的时间。例如，x2c-SVPall 基组在 Gaussian 中不可用，但可通过 MOKIT 调用 PySCF 实现。

---

## 17. 使用 DKH2 相对论方法

若需使用 DKH2 标量相对论哈密顿量及相应基组（如 DKH-def2-SVP），可以在 `mokit{}` 中添加 `DKH2` 关键字。由于 PySCF 目前不支持 DKH2，建议指定支持该功能的程序（如 ORCA）进行 CASSCF 计算。输入文件示例如下：
```
%mem=4GB
%nprocshared=2
#p CASSCF/DKH-def2-SVP

mokit{DKH2,CASSCF_prog=ORCA}

0 1
O -0.23497692 0.90193619 -0.068688
H 1.26502308 0.90193619 -0.068688
H -0.73568721 2.31589843 -0.068688
```
在此情况下，流程将跳过 Gaussian 的 HF 计算，直接使用 ORCA 完成支持 DKH2 的后续计算。

---

## 18. MOKIT 资源链接

MOKIT 的 GitLab 仓库地址为：https://gitlab.com/jxzou/mokit
MOKIT 的在线文档地址为：https://jeanwsr.gitlab.io/mokit-doc-mdbook
MOKIT 的引用文献页面地址为：https://jeanwsr.gitlab.io/mokit-doc-mdbook/citing.html

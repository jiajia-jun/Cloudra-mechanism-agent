---
key: t28370
title: ʹ��adcc��pyscf����ADC����ĵ�����̬�ܼ�(for MR-TADF)
url: http://bbs.keinsci.com/thread-28370-1-1.html
domain: 激发态与光谱
source: keinsci
year: 2022
cards: 11
---

# ʹ��adcc��pyscf����ADC����ĵ�����̬�ܼ�(for MR-TADF) — 知识卡片

## 1. ADC方法软件支持比较

Turbomole 支持基于 RI 近似的 scs-cc2 方法，但属于商业收费软件。eT 是专门用于 multilevel-cc 计算的软件，且支持多激发态计算。ORCA 软件支持 ADC 计算及多激发态，其 DLPNO-STEOM-CCSD 方法速度较快，但同样是商业软件。MRCC 是商业软件，功能强大。

---

## 2. PySCF 和 adcc 的安装流程

安装 Anaconda 或 Miniconda 后，可通过 conda 命令创建并激活名为 pyscf 的环境来安装 PySCF 和 adcc。安装命令依次为 `conda create -n pyscf -c pyscf pyscf`、`conda activate pyscf` 以及 `conda install -c conda-forge adcc`。用户也可以选择使用 pip 方式进行安装，具体步骤可参考 adc-connect.org 和 pyscf.org 官方文档。

---

## 3. 输入结构文件准备

准备一个优化好的 xyz 文件，可以直接使用优化程序输出的 xyz 文件，也可以使用 Multiwfn 将其他格式的结构文件（如波函数文件）转换为 xyz 格式。示例中的 BN 分子结构为一个 MR-TADF 分子。该结构文件将作为后续 PySCF 计算的几何输入。

---

## 4. PySCF/adcc 单重态与三重态计算脚本配置

在 Python 脚本中，需设置 OpenMP 线程数（例如 12），并使用 PySCF 读取 xyz 文件（如 "BN.xyz"）进行 RHF 计算以获得波函数。随后调用 adcc 进行激发态计算，如 `adcc.adc2(scfres, n_triplets=1)` 用于计算 1 个三重态，若计算单重态则将参数改为 `n_singlets=5`。计算基组需在 gto.M 中指定，示例中使用的是 'cc-pvdz'。

---

## 5. adcc 计算任务的提交与缓存设置

提交计算前建议设置缓存目录变量 `export PYSCF_TMPDIR=/tmp` 以避免系统能耗问题，并将目录指向高速存储硬件。运行命令为 `conda activate pyscf` 激活环境后，执行 `python BN.py | tee BN.out`。该命令会运行脚本并将输出结果同时显示在屏幕和保存到 BN.out 文件中。

---

## 6. ADC2 计算结果解读

ADC2 计算输出包含 SCF 收敛能量、迭代收敛信息（如残差、Ritz 值）和最终的激发态数据。结果表单列出了激发态序号、激发能（原子单位 a.u. 和电子伏特 eV）、振子强度 osc str 以及单/双激发贡献 `|v1|^2` 和 `|v2|^2`。示例中计算出的三重态激发能约为 0.1174 a.u. (3.20 eV)，且主要贡献为单激发。

---

## 7. 计算速度与精度的参数调优

影响计算速度的主要参数包括 `n_guesses`（初始猜测向量数，默认为计算态数的 2 倍）、`conv_tol`（收敛标准，默认比 SCF 精度高 10 倍或 1e-6）、`frozen_core`（冻结核心轨道数）和 `frozen_virtual`（冻结高能虚轨道数）。调整这些参数可以显著改变计算耗时。例如，适当降低 `conv_tol` 至 1e-4 可大幅节省时间且对能量影响较小，而增加 `n_guesses` 会增加时间但对精度影响微弱。

---

## 8. frozen_core 与 frozen_virtual 的影响分析

冻结核心轨道 (`frozen_core`) 能显著节省计算时间，且对激发能结果影响极小（通常小于 0.01 eV）。冻结高能虚轨道 (`frozen_virtual`) 也能大幅减少计算时间，但对激发能结果影响较大（偏差可达 0.01 eV 以上）。综合考虑，建议保持默认的 `conv_tol`，适当微调 `n_guesses`，较为安全地冻结深层核心轨道，而对 `frozen_virtual` 的使用需谨慎。

---

## 9. 基于轨道能量的自动冻结脚本逻辑

编写脚本可根据 HOMO 和 LUMO 轨道能量自动确定需要冻结的轨道数量。脚本设定阈值（如 HOMO 以下 3 Ha 和 LUMO 以上 5 Ha），统计能量低于和高于这些阈值的轨道数 `fo` 和 `fv`。然后将统计结果（转换为 eV 单位）打印出来，并将这两个数值作为 `frozen_core` 和 `frozen_virtual` 参数传递给 adcc 计算模块。

---

## 10. 自动冻结参数的经验设置

对于中小体系，将冻结阈值设为 4 Ha（即 HOMO 以下 4 Ha 和 LUMO 以上 4 Ha）时，计算精度与无冻结结果接近，误差在 0.01 eV 以内。若将阈值设为 3 Ha 和 1 Ha，误差可能增大至 0.1 eV。用户可根据体系大小和对精度的需求，在脚本头部修改 `occ_threash` 和 `virtual_threash` 变量来平衡速度与精度。

---

## 11. ADC2 与 STEOM-DLPNO-CCSD 的基准比较

在 MR-TADF 分子的 Benchmark 中，ADC2 方法计算得到的激发能结果与 ORCA 的 STEOM-DLPNO-CCSD 结果吻合较好。含有较低 Hartree-Fock 交换成分的泛函（如 B3LYP）因会导致下凹的 T1 态面，不适合用于计算 ES。高 HF 交换成分的杂化泛函或双杂化泛函（如 SOS-PBE-QIDH, SOS-RSX-QIDH）能提供更准确的 S1 激发能。数据表明实验结论可能仅针对当前测试分子，其他体系需另行验证。

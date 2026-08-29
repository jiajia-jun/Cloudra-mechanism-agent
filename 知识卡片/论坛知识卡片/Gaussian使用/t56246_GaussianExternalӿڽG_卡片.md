---
key: t56246
title: Gaussian��External�ӿڽ��GPU4PySCF���нṹ�Ż�
url: http://bbs.keinsci.com/thread-56246-1-1.html
domain: Gaussian使用
source: keinsci
year: 2025
cards: 10
---

# Gaussian��External�ӿڽ��GPU4PySCF���нṹ�Ż� — 知识卡片

## 1. GPU 加速 PySCF 在 BDF 结构优化中的应用

在结构优化过程中，若仅迁移计算部分而保持 BDF 原生优化步长，无法直接显著提升整体效率。通过在 BDF 中编写 external Python 脚本调用 GPU4PySCF 进行能量和梯度计算，可以加速 SCF 过程，从而有效缩短结构优化时间。该方法适用于 SCF 计算耗时占比较大的体系。

---

## 2. B3LYP/def2-SVP 结构优化性能对比测试

针对包含 110 个原子的体系，使用 B3LYP/def2-SVP 方法进行结构优化测试。测试场景分为纯 Gaussian16 计算、纯 GPU4PySCF 计算、以及 Gaussian16 优化步骤结合 GPU4PySCF SCF 计算三种模式。测试旨在评估混合计算模式在处理较大体系时的性能表现。

---

## 3. 混合计算模式的硬件环境配置

Gaussian16 几何优化步骤运行在 AMD Ryzen 9 7950X 16-Core Processor（16 核，64G 内存，实际调用 16 核，60G 内存）上。GPU4PySCF 计算部分运行在 Intel i7-7900X @ 3.30GHz（10 核，64G 内存，实际调用 1 核，16G 内存）并配备 1 块 V100-16G 显卡的设备上。

---

## 4. 混合计算模式的时间消耗分析

在 Gaussian 优化步骤时间与 PySCF 优化步骤时间差异不大的情况下，如果 PySCF 的单步计算耗电量更多，混合模式的最终总耗电量可能高于纯 Gaussian 计算。尽管混合模式利用 GPU 加速了计算过程，但由于单步能耗较高，需在计算速度与能源消耗之间进行权衡。

---

## 5. Gaussian 调用外部 Python 脚本的命令格式

通过在 Gaussian 输入文件中使用 `# External='python /path/to/script.py [args]'` 指令，可以调用外部 Python 脚本执行计算。示例中的参数包括交换相关泛函 `--xc b3lyp`、基组 `--basis def2-svp`、色散校正 `--disp d3bj`、GPU 设备 ID `--gpu 0` 以及溶剂模型 `--pcm IEFPCM` 等。该指令通常配合 `opt(nomicro)` 关键字使用。

---

## 6. 外部脚本参数列表（泛函与基组）

`external_pyscf.py` 脚本支持多种命令行参数以控制计算设置。`--xc` 用于指定 DFT 泛函，默认为 b3lyp；`--basis` 用于指定基组，默认为 6-31g**。这两个参数决定了计算的理论水平。

---

## 7. 外部脚本参数列表（色散与加速）

`--disp` 参数用于指定色散校正方法，默认为 d3bj。`--gpu` 参数用于指定 GPU 设备 ID，默认为 0；若不使用该参数，脚本将调用 CPU 版 PySCF 进行计算。在仅有一张显卡的情况下，若不指定此参数则无法利用 GPU 加速。

---

## 8. 外部脚本参数列表（SCF 控制与精度）

`--maxscf` 参数用于设置最大 SCF 循环次数，默认为 50。`--grid` 参数用于设置 DFT 积分网格级别，默认为 3。`--conv` 参数用于设置 DFT 收敛阈值，默认为 1E-9。`--ri` 参数用于开启密度拟合加速计算。

---

## 9. 外部脚本参数列表（文件与输出控制）

`--nocheckpoint` 参数用于禁止生成 Checkpoint 文件，适用于长时计算以避免文件过大。`--chkdir` 参数指定 Checkpoint 文件的存储目录。`--nofchk` 参数禁止生成 fchk 文件，通常用于减少 Gaussian 读取文件时的路径问题或节省空间。`--verbose` 参数用于输出详细运行信息。

---

## 10. 外部脚本参数列表（溶剂模型）

脚本支持隐式溶剂模型计算。`--solvent` 参数通过溶剂名称指定介电常数。`--eps` 参数直接指定介电常数值。`--pcm` 参数指定溶剂模型类型，默认为 IEFPCM，同时也支持 CPCM 和 SMD 模型。

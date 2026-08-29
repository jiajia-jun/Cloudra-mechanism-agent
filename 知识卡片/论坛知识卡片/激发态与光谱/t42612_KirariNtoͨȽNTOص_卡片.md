---
key: t42612
title: KirariNto��ͨ���Ƚ�NTO�ص���ʵ�ּ���̬���ٵĳ���
url: http://bbs.keinsci.com/thread-42612-1-1.html
domain: 激发态与光谱
source: keinsci
year: 2024
cards: 9
---

# KirariNto��ͨ���Ƚ�NTO�ص���ʵ�ּ���̬���ٵĳ��� — 知识卡片

## 1. KirariNto 简介

KirariNto 是基于自然跃迁轨道(NTO)重叠度算法的激发态几何优化程序。该程序主要用于在势能面上追踪激发态轨迹，以维持激子态分布。相关算法原理和实现细节可参考 DOI: 10.1002/jcc.26162 对应的文献。

---

## 2. KirariNto 追踪目标激发态的原理

KirariNto 在每一步优化中都会进行一次 TD-DFT 计算，并将当前的各个激发态与上一步选定的目标激发态进行 NTO 对比。程序通过计算当前激发态与前一目标态的 NTO 重叠值，选取重叠程度最大的模态作为下一步优化的目标激发态。这些计算步骤主要通过调用 Multiwfn 完成。

---

## 3. NTO 重叠值的计算步骤

计算两个激发态 A 与 B 之间 NTO 重叠值的具体步骤如下：首先需要准备用于计算分子波函数的文件结构；其次分别获得 A 和 B 的 NTO 轨道及其系数；然后提取 A 和 B 各自的 NTO-hole 和 NTO-electron 轨道，将空间重叠数值作为特征值并生成 4 个 fchk 文件；最后分别基于这 4 个 fchk 文件计算电子密度，通过 hole-hole 和 electron-electron 的方式得到重叠数值分布。

---

## 4. 软件依赖与环境配置

KirariNto 依赖 Linux 操作系统、Python 科学计算库 Numpy、PySCF 以及 geomeTRIC 几何优化器，其中 geomeTRIC 可通过 pip3 install geometric 安装。运行前需配置环境变量，指定 Multiwfn、Gaussian 和 ORCA 的可执行文件路径，包括 KIRARINTO_MULTIWFN、KIRARINTO_GAUSSIAN、KIRARINTO_FORMCHK、KIRARINTO_ORCA 和 KIRARINTO_ORCA2MKL。

---

## 5. KirariNto 命令行参数说明

运行脚本为 kirariNto.py，输入参数为初始几何结构的 TD-DFT 计算文件。可选参数包括：-c 指定遵循 PySCF 格式的外部几何约束文件；-p 指定使用的程序（Gaussian 或 ORCA，默认根据扩展名识别）；-d 设置是否在每步后删除 .chk 或 .gbw 文件（默认 yes）；-g 设置积分网格精度（1, 2 或 3，默认为 2，数值越大网格越密）。

---

## 6. Gaussian 输入文件格式要求

使用 Gaussian 作为后端时，需准备包含 TD-DFT 计算的输入文件，并必须指定 nstates 和 root 参数（例如 nstates=3, root=1）。示例中使用的计算级别为 b3lyp em=gd3bj，并包含 iop(9/40=4) 关键词，基组部分通过 gen 关键字自定义。

---

## 7. ORCA 输入文件格式要求

使用 ORCA 作为后端时，输入文件需在 %tddft 模块中指定 nroots 和 iroot 参数（例如 nroots 5 iroot 1）。示例中使用的理论方法为 blyp，基组为 def2-sv(p) 和 def2/j，并使用 %pal 模块指定并行进程数。

---

## 8. 程序执行与输出目录

执行命令格式为 python3 kirariNto.py task.gjf。程序会在当前目录下自动创建一个 JOBS 目录，用于存储优化过程中每一步的计算文件。输出信息会显示当前步的梯度、能量、Hessian 特征值，以及当前各个态与上一目标态之间的 NTO 重叠度，并自动确定下一步优化的目标态。

---

## 9. 收敛判断与默认步数限制

程序默认将优化步数限制为 10 步。当达到收敛标准时，屏幕会显示 "Converged!" 并输出最终的位移、信任半径、梯度和能量变化值等信息；若未收敛，达到默认步数后会根据 Gaussian 的默认设置停止（可能与用户的期望不同）。

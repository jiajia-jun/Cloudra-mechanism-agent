---
key: t10682
title: Multiwfn���ѿ��Ե���cubegenʹ�����Ʒ�����ʱ�з�Ծʽ���½���
url: http://bbs.keinsci.com/thread-10682-1-1.html
domain: 波函数与电子结构分析
source: keinsci
year: 2018
cards: 14
---

# Multiwfn���ѿ��Ե���cubegenʹ�����Ʒ�����ʱ�з�Ծʽ���½��� — 知识卡片

## 1. Multiwfn 静电势计算速度

2020年7月4日发布的 Multiwfn 版本在计算静电势方面的速度相比之前版本有巨大提升，尤其是大体系计算效率提高显著。此前 Multiwfn 计算静电势的内部算法已在 *Phys. Chem. Chem. Phys.* 期刊发表。相比 Gaussian 的 cubegen 程序，Multiwfn 在计算静电势数据时具有明显的速度优势，特别是在仅计算几个点时差异巨大。

---

## 2. 适用场景分析

在仅需要计算少数几个点（如 5 个）的静电势数据时，直接使用 cubegen 可能更方便。但当需要计算大量点（例如 17 个静电势数据）以获得精确空间分布数据，或者需要基于静电势计算拟合电荷（如 MK、CHELPG）时，建议使用 Multiwfn 以大幅节省计算时间。

---

## 3. ORCA 用户解决方案

对于使用 ORCA 等非 Gaussian 软件且 CPU 核数较少或缺乏 Gaussian 授权的用户，可以使用 Multiwfn 内置的快速算法计算静电势。ORCA 用户可以将波函数文件转换为 Multiwfn 支持的格式，利用 Multiwfn 计算静电势以节省时间。

---

## 4. cubegen 集成机制

Multiwfn 3.6(dev) 版本开始支持自动调用 Gaussian 的 cubegen 程序进行积分计算。通过在 settings.ini 文件中设置 cubegenpath 参数，用户可以指定 cubegen 的路径。Windows 下的路径格式示例为 "D:\study\G16W\cubegen.exe"，Linux 下为 "/sob/g09/cubegen"。

---

## 5. 自动调用与效率提升

当输入文件为 fch 或 fchk 格式时，Multiwfn 会在需要计算积分时自动调用 cubegen。这种机制利用 cubegen 进行部分计算，从而显著减少总耗时，尤其是在大体系计算中效果明显。

---

## 6. 适用功能列表

Multiwfn 在执行以下功能时会调用 cubegen 以提升效率：(1) 绘制静电势着色图（主功能 3）；(2) 绘制静电势平面图（主功能 4）；(3) 计算大量静电势点（超过 5 个）；(4) 拟合静电势电荷（MK、CHELPG、RESP 等）；(5) TrEsp 原子间跃迁偶极计算（子功能 4.A.9）；(6) 基于静电势的亲电指数计算（子功能 12）。

---

## 7. cubegen 路径设置与版本检测

Multiwfn 通过判断 cubegenpath 路径中是否包含 "g16" 或 "G16" 字样来区分 Gaussian 09 和 Gaussian 16 的 cubegen 程序。对于 G09 的 cubegen，程序会采用多线程计算；对于 G16 的 cubegen，则不会采用多线程方式（除非 settings.ini 中设置了 nthreads）。

---

## 8. 非 Gaussian 用户文件格式

非 Gaussian 用户（如使用 GAMESS-US、Firefly）可以将波函数文件（如 .molden、.gms）转换为 Multiwfn 支持的 .fch 格式。转换后的 .fch 文件可作为输入文件，使 Multiwfn 能够自动调用 cubegen 进行积分计算。

---

## 9. 算法速度对比

cubegen 支持的大部分实空间函数计算速度均慢于 Multiwfn 的内置算法。对于电子密度、电子密度梯度、Laplacian of electron density、缩减密度梯度（RDG）等函数，Multiwfn 的计算速度远超 cubegen。Multiwfn 仅在计算静电势相关功能时会考虑调用 cubegen。

---

## 10. cubegen 调用的历史变更

目前 Multiwfn 已支持直接调用 cubegen。此前版本（如 4.12.7）介绍的需用户手动生成 cubegen 输入流并借助管道传递以节省时间的方法已不再支持，相关章节已被删除。

---

## 11. 内存不足问题解决

在处理大体系静电势绘图或生成时，若遇到 cubegen 内存不足报错，可通过设置环境变量 GAUSS_MEMDEF 来增加 cubegen 可用的内存。

---

## 12. 密度矩阵类型选择

cubegen 计算积分时默认使用 SCF 密度矩阵。对于 MP2 或 TDDFT 等计算，若需使用对应级别（如 MP2）的密度矩阵生成静电势图，需修改 settings.ini 中的 cubegendenstype 参数为相应的密度矩阵标识。若不修改，cubegen 将基于 SCF 密度（如 HF 密度）进行计算。

---

## 13. 参数修改与计算基准

若通过 Multiwfn 修改了计算参数（如主功能 6 子功能 26 修改构型或网格设置），再通过调用 cubegen 计算积分，结果将对应修改后的参数。若需基于原始参数计算，应确保未在 Multiwfn 中进行修改，或者重新读取原始文件。

---

## 14. Multiwfn 直接计算的优势

直接使用 Multiwfn 计算积分而非调用 cubegen 生成 .cub 文件具有以下优势：(1) Multiwfn 全程交互式操作，无需繁琐命令行输入；(2) Multiwfn 设定计算方式灵活，选择丰富；(3) Multiwfn 在计算静电势数据后可直接进行后处理或可视化，无需额外的数据转换步骤。

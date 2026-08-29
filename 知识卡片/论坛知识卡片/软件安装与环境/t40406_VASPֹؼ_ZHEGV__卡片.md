---
key: t40406
title: ����VASP���ֹؼ���"ZHEGV"��ر����ı���ԭ�򼰽����ʽ����
url: http://bbs.keinsci.com/thread-40406-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 8
---

# ����VASP���ֹؼ���"ZHEGV"��ر����ı���ԭ�򼰽����ʽ���� — 知识卡片

## 1. ZHEGV 警告与错误的定义

VASP 计算中可能出现 `Warning In EDDRMM: call to ZHEGV failed` 或 `Error In EDDDAV: Call to ZHEGV failed` 的提示。这类信息涉及 LAPACK 子程序 ZHEGV 的调用失败，该子程序用于计算复广义厄米特特征值问题。该提示可能是警告也可能是严重错误，取决于具体报错类型。

---

## 2. ZHEGV 警告的含义与处理

当出现 Warning In EDDRMM 时，这只是一个警告而非报错。该现象在使用 RMM-DIIS 算法且计算精度接近机器极限时发生，意味着单带迭代仅产生随机进展，无法进一步优化该能带。程序内部会自动停止更新波函数并继续处理下一个能带，用户可以直接忽略此警告。

---

## 3. ZHEGV 报错原因：算法不稳定

ZHEGV 报错可能是由于 RMM-DIIS 对角化算法对特定计算设置不稳定所致。解决方法是将 `ALGO` 参数设置为 `Normal`（使用 Blocked Davidson 算法）或 `Fast`（5步 Blocked Davidson 后接 RMM-DIIS）。修改算法通常能解决因算法不稳定性导致的 ZHEGV 失败。

---

## 4. ZHEGV 报错原因：初始或优化后的几何结构不合理

输入的初始几何结构不合理（报错发生在第一步离子步）或离子松弛最后一步导致了几何结构不合理，均可能引发 ZHEGV 报错。检查初始结构需查看 `OUTCAR` 文件中的几何数据；检查松弛过程需对比 `XDATCAR` 中最后几步的输入和输出结构。

---

## 5. 结构不合理导致的解决策略

若几何结构在松弛过程中变得不合理，可以尝试切换到不同的松弛算法（修改 `IBRION` 参数）。另一种方法是通过设置比默认值更小的 `POTIM` 参数来减小第一步的步长。这两种策略有助于避免因结构剧烈变化导致的 ZHEGV 报错。

---

## 6. ZHEGV 报错原因：LAPACK 库安装问题

ZHEGV 报错可能源于机器上 LAPACK 的安装不正确。建议使用 VASP 代码自带的 LAPACK 库（路径为 `vasp.4.lib/lapack_double.o`）。更换为代码自带的数学库通常能解决因第三方库安装配置不当引起的问题。

---

## 7. 特定架构下的编译修改方案

在某些架构（特别是 SGI）上，即使切换到 Davidson 算法，LAPACK 例程仍可能无法正常工作。可以通过在 `davidson.F`、`subrot.F` 和 `wavpre_noio.F` 文件中注释掉 `#define USE_ZHEEVX` 这一行，然后重新编译 VASP 来避免使用 ZHEGV 子程序。

---

## 8. ZHEGV 问题的排查优先级

处理 ZHEGV 问题时，若为 Warning 可以忽略；若为 Error，则优先检查 `ALGO` 设置和几何结构合理性。如果调整算法和结构后问题依然存在，再检查 LAPACK 安装或考虑修改编译选项避开特定子程序调用。静电相互作用可能是潜在的相关因素之一。

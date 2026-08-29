---
key: t56033
title: NAMD�����ܼ���̡̳�2����WTM-��ABF���������������ܼ���
url: http://bbs.keinsci.com/thread-56033-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2025
cards: 11
---

# NAMD�����ܼ���̡̳�2����WTM-��ABF���������������ܼ��� — 知识卡片

## 1. WTM-eABF 在 NAMD 中的应用

WTM-eABF (Well-Tempered Metadynamics enhanced eABF) 是一种结合了 WTMd 和 eABF 的增强采样算法，适用于 NAMD 分子动力学软件的 alchemical transformation 计算。该方法将 alchemical 过程视为一维扩展体系进行模拟，通过计算偏导数 ∂U'/∂λ 来获取扩展系在反应坐标上的自由能。此算法增强了采样效率，能够计算溶剂化自由能、结合自由能及 pKa 等热力学量。

---

## 2. WTM-eABF 相对于传统方法的优势

WTM-eABF 相比于传统的 FEP 和 TI 方法具有显著优势，包括增强型算法的加速作用使得体系跨越反应能垒更高效，以及减少了溶剂相 alchemical transformation 中因原子产生/消失导致的中间态微态采样困难。此外，由于增强了反方向的采样，该方法能更好地探测体系结构变化，避免了 FEP/TI 在不同 λ-中间态下进行多次模拟的繁琐流程。

---

## 3. Alchemical Transformation 定义

Alchemical transformation 是一种热力学计算方法，通过计算将体系中的一个原子或基团消失或转化为另一个原子或基团过程中的自由能变化，来求解总自由能。该方法广泛应用于计算溶剂化自由能、结合自由能以及 pKa 等重要化学性质，常用方法包括 FEP 和 TI。

---

## 4. 计算案例：水分子溶剂化自由能

计算水分子在纯水溶剂中的溶剂化自由能是验证 WTM-eABF 方法的典型案例。该过程计算将一个水分子从真空转移到溶剂中的自由能变化，通过微量调整 λ 值来控制相互作用，最终得出水分子完全消失时的自由能变化数值，并与理论值进行对比。

---

## 5. NAMD 中 Alchemical Transformation 的 PDB 准备

在 NAMD 中实现 alchemical transformation 需要准备一个 PDB 文件，其中原子 B 列用于标记原子的状态。需要消失的原子其 B 列设为 -1，需要生成的原子其 B 列设为 1，不参与变化的原子 B 列为 0。例如，计算水分子溶剂化自由能时，需标记该水分子中的原子。

---

## 6. NAMD 配置文件 alchem.conf 关键参数

在 NAMD 的 alchem.conf 配置文件中，需开启 alchemical transformation 并设置相关参数。关键参数包括 `computeEnergies 1`、`alchType TI`、`alchFile alchem.pdb`、`alchCol B` 以及输出文件设置。此外，需设置 `alchVdwLambdaEnd 0.7` 和 `alchElecLambdaStart 0.5` 来控制原子在 λ 变化过程中的消失或生成时机，并使用 `alchDecouple on` 和 `alchlambda 0` 进行解耦和初始值设定。

---

## 7. 范德华与静电相互作用消失的参数控制

NAMD 通过 `alchVdwLambdaEnd` 和 `alchElecLambdaStart` 两个参数精确控制原子在 alchemical 过程中范德华和静电相互作用的消失或生成。例如，设置 `alchVdwLambdaEnd 0.7` 表示在 lambda=0.3 时开始消失范德华或库仑相互作用，lambda=1 时完全消失；`alchElecLambdaStart 0.5` 表示 lambda=0 时开始消失库仑相互作用，lambda=0.5 时完全消失。消失过程则与此相反。

---

## 8. Colvars 配置文件 colvars.in 设置

Colvars 配置文件用于定义 λ 对应的集合变量，需设置 `extendedLagrangian on`、`lowerBoundary 0`、`upperBoundary 1` 以及反射边界条件。关键参数 `width 0.005` 定义了窗口的宽度，较小的宽度有利于提高中间态的采样精度，建议根据需要调整。

---

## 9. ABF 和 Metadynamics 偏置设置

在配置文件中添加 ABF 和 Metadynamics 模块以应用 WTM-eABF 偏置。ABF 设置包括 `colvars l`、`FullSamples 10000` 和 `historyfreq 50000`；Metadynamics 设置包括 `hillWidth 3.0`、`hillWeight 0.05`、`wellTempered on` 和 `biasTemperature 4000`。这些参数共同作用以增强采样效率。

---

## 10. 结果输出与自由能数值读取

模拟运行后，结果输出在 `alchem.abf1.pmf` 文件中，可以读取到自由能变化曲线。通过对比 λ=0 和 λ=1 时的自由能差值，可以获得计算结果。例如，在演示案例中计算得到的自由能差值为 6.2 kcal/mol，与实验值 -6.3 kcal/mol 接近（注：原文数值符号存在差异）。

---

## 11. 参考文献与资源

该方法的相关参考资料包括 *J. Phys. Chem. Lett.* 2025, 16, 4419–4427 和 *Acc. Chem. Res.* 2025, DOI:10.1021/acs.accounts.5c00666。相关教程文件 `tutorial_wtm-eabf.7z` 提供了完整的输入文件示例。

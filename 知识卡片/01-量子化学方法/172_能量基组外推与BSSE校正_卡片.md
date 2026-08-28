---
id: 172
title: 谈谈能量的基组外推
url: http://sobereva.com/172
domain: 量子化学方法
topic: 能量基组外推与BSSE校正
cards: 1
---

# 能量基组外推与BSSE校正 — 知识卡片

## 1. HF/DFT能量的基组外推

对于Dunning相关一致性基组（或ANO系列），SCF能量收敛趋势符合指数关系，通过两个相邻基组能量外推CBS，公式为 E_SCF(∞)=[E_SCF(M)*exp(-α*√N)-E_SCF(N)*exp(-α*√M)]/[exp(-α*√N)-exp(-α*√M)]；使用DZ/TZ/QZ计算通常足以满足精度要求；对于cc-pVnZ系列，L=2/3的外推α=4.42，L=3/4的外推α=5.46；对于def2系列，L=2/3的外推α=10.39，L=3/4的外推α=7.88。

## 相关能的外推
电子相关能随基组收敛较慢，需单独外推；Klopper-Helgaker形式是最常用的外推方法，公式为 E_corr(∞)=[E_corr(N)*N^3-E_corr(M)*M^3]/(N^3-M^3)；也可以使用Truhlar等人的广义形式 E_corr(M)=E_corr(∞)+A*M^(-β)，对于cc-pVnZ系列，L=2/3的外推β=2.46，L=3/4的外推β=3.05；对于def2系列，L=2/3的外推β=2.4，L=3/4的外推β=2.97。

## 间接获得CCSD(T)/CBS相关能的方法
近似获得CCSD(T)下外推到CBS的相关能的方法是 E_corr(∞)_CCSD(T)≈E_corr(∞)_MP2+[E_corr(Small)_CCSD(T)-E_corr(Small)_MP2]；这个近似成立的条件是CCSD(T)和MP2的相关能差异受基组影响不大。

## 考虑基组重叠误差(BSSE)时的外推
计算E_AB'需使用Counterpoise方法校正BSSE，公式为 E_AB'=E_AB+E_BSSE，E_BSSE=(E_A-E_A,bAB)+(E_B-E_B,bAB)；对于后HF外推，BSSE校正分为对HF能量的校正E_BSSE_HF和对相关能的校正E_BSSE_corr，分别计算；建议使用Ghost原子的方法手动计算A、B、A,bAB、B,bAB体系，而不要靠counterpoise关键词。

## 分子间相互作用能的外推原则
求差值时要么所有体系都做外推（且用相同基组），要么都不外推；如果有的外推有的不外推，结果误差会巨大。

---
key: t11795
title: MOLCAS XMS-CASPT2����
url: http://bbs.keinsci.com/thread-11795-1-1.html
domain: 激发态与光谱
source: keinsci
year: 2018
cards: 5
---

# MOLCAS XMS-CASPT2���� — 知识卡片

## 1. 态交叉点处的计算偏差

在势能曲线交叉或接近交叉区域，使用CASSCF参考态进行MS-CASPT2计算可能导致结果出现显著偏差。这是由于该区域参考波函数的不稳定性所引发的。

---

## 2. XMCQDPT2 方法实现

Firefly (PC-GAMESS) 软件基于 Granovsky 于2011年发表的理论实现了 XMCQDPT2 方法，相关文献见 J. Chem. Phys. 134, 214113, 2011。

---

## 3. XMS-CASPT2 方法实现

Molpro 软件实现了 XMS-CASPT2 方法，相关文献见 J. Chem. Phys. 135, 081106, 2011。

---

## 4. XMS-CASPT2 在 MOLCAS/OpenMOLCAS 中的实现与对比

MOLCAS 及 OpenMOLCAS 已包含 XMS-CASPT2 功能。对 ScO 分子的十多个低激发态计算测试显示，OpenMOLCAS 中的 XMS-CASPT2 结果与 MS-CASPT2 结果一致。测试过程使用了相同的 CASSCF 参考态，表明 OpenMOLCAS 可能默认采用 XMS-CASPT2 处理。

---

## 5. MS-CASPT2 的适用键长范围

经验表明，MS-CASPT2 计算在键长小于 1.9 Angstrom 时适用性较好。

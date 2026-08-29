---
key: t59859
title: ����cp2k�Խǻ�������scf��������һЩ���˾���
url: http://bbs.keinsci.com/thread-59859-1-1.html
domain: 其他量化软件
source: keinsci
year: 2026
cards: 9
---

# ����cp2k�Խǻ�������scf��������һЩ���˾��� — 知识卡片

## 1. 金属表面吸附体系的基组选择

金属元素（如 Pt 等）推荐使用赝势基组（DZVP-MOLOPT-SR-GTH/TZV2P-MOLOPT-PBE-GTH）。非金属元素（C, H, O 等）推荐使用全电子基组（SVP-MOLOPT-PBE-ae/TZVPP-MOLOPT-PBE-ae）。

---

## 2. Pt_111 表面吸附体系的 SCF 收敛难题

使用 TZV2P 基组时，Pt_111 表面吸附 O2 体系的初始结构可能无法收敛。对于包含过渡金属的复杂体系，直接进行 SCF 计算往往难以获得收敛解。

---

## 3. 金属体系 SCF 收敛辅助方法

针对金属基底的计算，建议使用 smear 和 k 点设置。由于 OT 方法不适用于 smear，此类体系只能使用传统对角化方法进行计算。

---

## 4. DIIS 收敛参数设置

使用 DIIS 时，需将 EPS_DIIS 值设置小于 1.0E-04。若 EPS_DIIS 值过大，计算容易发散。

---

## 5. DIRECT_P_MIXING 收敛性能

DIRECT_P_MIXING 的收敛效果较差，且无法保证每次都能收敛。使用该方法可能导致计算反复震荡，在结构优化（opt）和频率计算（freq）中效率极低且不可接受。

---

## 6. Kerker 混合与 GMIX_P 设置

对于金属体系，建议开启 GMIX_P T 关键字。结合 Kerker mixing 使用（设置 MAX_GVEC_EXP 3.0），可以处理金属体系密度变化剧烈的问题，有助于提升 SCF 稳定性并降低计算耗时。

---

## 7. 大基组全电子计算收敛方案

使用 TZVPP-MOLOPT-PBE-ae 等大基组进行全电子计算时，收敛难度较高。建议关闭 CHOLESKY（设置 CHOLESKY OFF），将 EPS_EIGVAL 设为 1.0E-5，并在前几步（NSIMPLEMIX）使用 Kerker mixing，随后转入 BROYDEN 混合。

---

## 8. 极高精度 SCF 收敛设置

对于 EPS_SCF 达到 1.0E-07 的高精度收敛需求（如 UKS 自旋态变化分析），推荐使用 MODIFIED_BROYDEN_MIXING 方法。此方法能提供比 OT 方法更稳定的收敛性能。

---

## 9. MODIFIED_BROYDEN_MIXING 推荐参数

使用 MODIFIED_BROYDEN_MIXING 的推荐参数组合为：ALPHA 0.2，BETA 1.5，NBROYDEN 24，GMIX_P T，MAX_GVEC_EXP 3.，N_SIMPLE_MIX 16。

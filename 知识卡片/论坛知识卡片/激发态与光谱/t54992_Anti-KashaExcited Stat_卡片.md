---
key: t54992
title: Anti-Kasha��Excited State Dynamics�������̷���
url: http://bbs.keinsci.com/thread-54992-1-1.html
domain: 激发态与光谱
source: keinsci
year: 2025
cards: 16
---

# Anti-Kasha��Excited State Dynamics�������̷��� — 知识卡片

## 1. Anti-Kasha荧光现象

Anti-Kasha荧光现象是指分子从高激发态（如S₂或S₃）直接发射荧光，而不是经由Kasha规则预测的最低激发态S₁弛豫后发光。这种现象通常在热活化延迟荧光（TADF）或某些特定化学结构的分子中可以观察到，Azulene（薁）是研究此类效应的经典计算对象。

---

## 2. Kasha规则与违反条件

Kasha规则指出光致发光通常发生在能量最低的激发态（S₁），因为高激发态到低激发态的内转换非常快。违反Kasha规则（即发生Anti-Kasha发射）需满足三个条件：S₂-S₁能隙足够大以减缓内转换；S₂-S₁耦合较弱或能隙较大；S₂和S₁具有不同的跃迁性质（如pi-pi*与n-pi*不同）。

---

## 3. Anti-Kasha荧光的动力学模型

Anti-Kasha荧光的观测取决于辐射跃迁速率（$k_{r,S2}$）与S₂态内转换速率（$k_{IC,S2->S1}$）的竞争。当$S_2$态的辐射跃迁速率与内转换速率之和的倒数相当长时，能够观察到明显的Anti-Kasha荧光。

---

## 4. 计算方法软件选择

Anti-Kasha荧光计算涉及激发态优化、频率分析、非绝热耦合（NAC）计算和激发态动力学。优化和频率可使用含时密度泛函理论（TDDFT）及Hessian计算；非绝热耦合计算目前支持Q-Chem和BDF；激发态动力学计算推荐使用MOMAP或开源工具FCclasses3。

---

## 5. Gaussian输入文件与基础优化

Gaussian中的基础优化与频率计算使用 `# opt freq B3LYP/def2svp scrf em=gd3bj`。针对激发态，需添加 `td` 关键字，例如计算第一激发态用 `# opt freq td B3LYP/def2svp scrf em=gd3bj`，计算第二激发态用 `# opt freq td(root=2) B3LYP/def2svp scrf em=gd3bj`。

---

## 6. Gaussian能量与激发态信息提取

从Gaussian输出文件中需提取基态能量（位于 `SCF Done` 行）和各激发态能量（位于 `Excited State N` 部分的 `Total Energy, E(TD-HF/TD-DFT)`）。若S₂/S₁能隙约为0.05534 a.u. (1.5 eV)，根据Energy Gap Law，内转换速率可能不会极快，这有利于Anti-Kasha荧光的产生。

---

## 7. 跃迁偶极矩提取

从Gaussian输出文件 `Ground to excited state transition electric dipole moments (Au)` 部分提取跃迁偶极矩（Dip. S.），计算荧光谱需要S1态结构的偶极矩，计算吸收谱需要S0态结构的偶极矩。使用FCclasses3时可通过fchk文件自动获取这些高精度数据。

---

## 8. BDF基态与激发态NAC计算

在BDF中计算基态与S₁态间非绝热耦合矩阵元（NACME）使用 `resp` 模块，设置 `Single` 参数并指定状态。输入文件示例包含 `$resp`, `Quad`, `FNAC`, `Method 2`, `Nfiles 1`, `Single`, `States`, `1 1 1`, `$end` 等关键字。

---

## 9. BDF激发态间NAC计算

在BDF中计算S₁与S₂态之间的NAC（判断Anti-Kasha荧光竞争的关键）需设置 `Double` 参数。输入文件中通过 `Pairs` 关键字指定计算对，例如 `1 1 1 1 1 2` 表示计算S1-S2耦合。

---

## 10. MOMAP电子-振动耦合设置

MOMAP使用 `evc.inp` 文件进行电子-振动耦合计算，设置 `do_evc = 1`。需在 `&evc` 模块中指定初始和终态的log文件路径（`ffreq(1)` 和 `ffreq(2)`），若计算内转换（IC）还需指定NACME文件路径（`fnacme`）并开启投影重整（`proj_reorg = .t.`）。

---

## 11. MOMAP辐射跃迁速率计算

MOMAP计算辐射跃迁速率（$k_r$）需设置 `do_spec_tvcf_spec = 1` 和 `do_spec_tvcf_ft = 1`。在 `&spec_tvcf` 模块中需设置Duschinsky旋转（`DUSHIN = .t.`）、温度（300 K）、绝热激发能量（`Ead`）、吸收和发射的电偶极矩（`EDMA`, `EDME`）及Duschinsky输入文件（`DSFile = "evc.dint.dat"`）。

---

## 12. MOMAP内转换速率计算

MOMAP计算内转换速率（$k_{ic}$）需设置 `do_ic_tvcf_spec = 1` 和 `do_ic_tvcf_ft = 1`。在 `&ic_tvcf` 模块中需设置绝热激发能量（`Ead`）、温度、时间步长、最大能量及Duschinsky文件（`DSFile = "evc.cart.dat"`）和NAC文件（`CoulFile = "evc.cart.nac"`）。

---

## 13. MOMAP计算结果读取

MOMAP的辐射速率结果输出在 `spec.tvcf.log` 中，包含 `radiative rate` 和寿命（ns）。内转换速率结果输出在 `ic.tvcf.log` 中，包含能量对应的 $k_{ic}$ 值及对数值。每个ESD计算节点会生成一个XD文件。

---

## 14. FCclasses3辐射谱计算设置

FCclasses3计算辐射谱使用 `gen_fcc_state` 和 `gen_fcc_eldip` 获取数据。输入文件中设置 `PROPERTY = EMI`，`MODEL = AH`，`TEMP = 298.0`，并指定 `STATE1_FILE`（激发态fcc文件）和 `STATE2_FILE`（基态fcc文件）及电偶极矩文件（`ELDIP_FILE`）。

---

## 15. FCclasses3内转换计算设置

FCclasses3计算内转换需要BDF输出的NACME数据，需通过脚本 `bdf2fcc` 将BDF的NAC输出转换为FCclasses识别的格式。输入文件中设置 `PROPERTY = IC`，并指定 `NAC_FILE` 为转换后的NAC数据文件（如 `nac_td_Azulene_bdf`）。

---

## 16. 计算结果对比

FCclasses3计算得到的辐射速率和内转换速率（分别为 $8.82\times 10^5\ s^{-1}$ 和 $2.51\times 10^9\ s^{-1}$）与MOMAP的计算结果（分别为 $1.16\times 10^6\ s^{-1}$ 和 $2.09\times 10^9\ s^{-1}$）比较接近。

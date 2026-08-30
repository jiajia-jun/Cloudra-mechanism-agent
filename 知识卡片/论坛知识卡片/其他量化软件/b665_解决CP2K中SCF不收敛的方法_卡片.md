---
key: b665
title: 解决CP2K中SCF不收敛的方法
url: http://sobereva.com/665
domain: 其他量化软件
source: blog
year: 2023
cards: 41
---

# 解决CP2K中SCF不收敛的方法 — 知识卡片

## 1. CP2K SCF收敛判断标准

CP2K通过输出信息判断自洽场(SCF)是否收敛。了解SCF收敛的标准与基本背景知识（如k点、CUTOFF、OT、smearing等）对于解决收敛问题至关重要。

---

## 2. 结构合理性检查对SCF收敛的影响

SCF收敛性与结构合理性关系极大，化学意义越强的结构通常越容易收敛。计算前需检查模型是否有意义、是否漏原子、化学环境是否合理，并确保不存在严重结构扭曲或周期镜像原子过近接触。

---

## 3. 晶胞尺寸设置对SCF收敛的影响

晶胞尺寸设置错误会导致SCF难以收敛。例如，将二维周期性体系（如氧化石墨烯）在平行层方向设置过大造成真空区，会导致边缘出现悬键，从而引发收敛问题。

---

## 4. 关键词与设置检查

计算自旋极化体系时必须在&DFT里设置UKS或LSD，否则即使自旋多重度大于1也会被当作闭壳层计算。使用wavelet Poisson solver计算孤立体系时，若电子密度分布跨越盒子，结果将无意义。

---

## 5. Multiwfn生成CP2K输入文件的优势

使用Multiwfn生成CP2K输入文件可简化使用过程，减少关键词设置错误的可能性。例如，设置自旋多重度大于1时自动添加UKS，进行非周期性计算时自动设置合适的盒子尺寸。

---

## 6. 净电荷与自旋多重度设置合理性

体系的净电荷和自旋多重度设置不合理会导致计算无意义或处于激发态，从而引发SCF极难收敛。特别是对于磁性体系，自旋多重度的设置对SCF收敛影响极大。

---

## 7. SCF迭代次数上限调整

若SCF有收敛趋势，可增大&SCF里的MAX_SCF数值（默认50，Multiwfn默认128）。若SCF过程发生显著震荡且无收敛苗头，单纯增加迭代次数通常无效。

---

## 8. 利用收敛波函数作为初猜

可读取其它泛函或基组下计算收敛的波函数作为初猜，通过&SCF设置SCF_GUESS RESTART，并在&DFT中用WFN_RESTART_FILE_NAME指定文件。两次计算的基组特征（如赝势类型）需定性一致。

---

## 9. 基组大小对SCF收敛的影响

较小基组下的计算通常比大基组更容易收敛。若TZV2P基组不收敛，可尝试DZVP基组计算，读取其收敛波函数作为初猜。

---

## 10. 泛函HF成分对SCF收敛的影响

HF成分越大的泛函通常越容易收敛，因其HOMO-LUMO gap更大。遇到SCF难收敛可尝试HF成分更大的泛函，读取其收敛波函数作为初猜。

---

## 11. DFT+U用于辅助SCF收敛

纯泛函想尝试杂化泛函失败时，可用DFT+U尝试，耗时与纯泛函基本一致。若实际不打算+U，可设置3或4 eV的U值尝试收敛，成功后读取波函数作为初猜。

---

## 12. 杂化泛函计算中的积分屏蔽问题

做杂化泛函计算时（尤其是周期性体系）若开启了SCREEN_ON_INITIAL_P且未读取之前的波函数作为初猜，CP2K将基于自动初猜做积分屏蔽，导致结果无意义且SCF难以收敛。

---

## 13. k点设置对SCF收敛的影响

晶胞边长不够大时必须考虑k点。k点数量不足会导致SCF难收敛或结果无意义，原则上k点应设到能量随k点数增加基本收敛的程度。

---

## 14. 格点精度CUTOFF与REL_CUTOFF

尝试增大&DFT / &MGRID里的CUTOFF和REL_CUTOFF。这两个截断能控制格点精度，不够大不仅结果不准，还可能造成SCF难收敛。

---

## 15. 原子磁化与组态设置对初猜的影响

通过&KIND里的MAGNETIZATION或&BS设置孤立原子的电子组态，使其接近体系收敛后的实际状态。初猜波函数中的原子组态越接近实际，SCF越容易收敛。

---

## 16. 磁性体系的初猜波函数设置

对于磁性体系，若SCF不收敛，必须尝试通过MAGNETIZATION或&BS设置接近实际情况的原子组态。否则可能收敛到错误的波函数导致结果无意义。

---

## 17. 离子性体系的原子带电状态设置

对于高度离子性体系（如NaCl），若SCF不收敛，可尝试在初猜中令原子组态对应离子状态（如Na+和Cl-）而非中性原子状态，这有助于收敛。

---

## 18. EPS_DEFAULT参数调整

尝试将&QS / EPS_DEFAULT减小几个数量级（默认1E-10）。该参数控制数值计算精度，设置过大可能造成SCF难收敛；若数值已很小（如1E-12）则无需继续减小。

---

## 19. 切换泛函、基组与方法

改用其它泛函、基组，或在GPW与GAPW之间切换（结合不同基组/赝势），是解决SCF难收敛的可行方案。

---

## 20. 修改默认波函数产生方式

除了默认的ATOMIC（孤立原子密度叠加）和RESTART（读取波函数），手册中&SCF / SCF_GUESS提供的其它方法效果通常不佳。

---

## 21. 孤立原子SCF迭代次数上限问题

CP2K产生初猜时计算孤立原子的SCF迭代上限固定为50。若迭代50轮后精度仍很差，可通过修改源码atom_kind_orbitals.F中的atom%optimization%max_iter（如改为300）并重新编译来解决。

---

## 22. 外电场对SCF收敛的影响

加外电场时SCF难收敛可能是电场过大所致。可尝试减小数值，或读取较小电场/无电场时收敛的波函数作为初猜。强外电场下体系若无法稳定存在，SCF不收敛属正常物理现象。

---

## 23. 放宽SCF收敛限

在解决无果的情况下，可尝试放宽SCF收敛限，即增大&SCF / EPS_SCF（默认1E-5）。此为最后手段。

---

## 24. 无gap或小gap体系的Smearing方法

对金属、石墨烯等无gap体系或窄带半导体，应使用smearing。即设置&SCF / &SMEAR / METHOD为FERMI_DIRAC，并在&SCF中用ADDED_MOS增加空轨道数量。

---

## 25. Smearing的电子温度设置

使用较小电子温度（如200K、300K）若不收敛，可尝试提升&SMEAR / ELECTRONIC_TEMPERATURE数值。温度升高时通常需要相应增加ADDED_MOS数目。

---

## 26. Smearing的适用性与能量外推

对于gap较大的绝缘体体系，无需尝试smearing。使用smearing得到的能量相当于温度T下的电子自由能，若需基态（0K）能量原则上应做T→0外推，对比能量时至少应保持相同smearing设置。

---

## 27. 能级移动(Level Shift)方法

对于gap较小的体系，可尝试使用能级移动，即设置&SCF / LEVEL_SHIFT（如0.3或0.4 Hartree）。这能人为加大空轨道与占据轨道的能级差，减轻混合程度以帮助收敛。

---

## 28. SCF密度矩阵混合方法

修改&SCF / &MIXING / METHOD可改善收敛。默认DIRECT_P_MIXING表现通常较差，推荐使用BROYDEN_MIXING（Multiwfn默认），也可尝试KERKER_MIXING或PULAY_MIXING。

---

## 29. BROYDEN_MIXING参数调整

使用BROYDEN_MIXING时，可调整ALPHA（默认0.4，难收敛时可尝试0.1-0.3）和NBROYDEN（默认4，改大到8通常有帮助，Multiwfn默认）。对于磁性体系，将ALPHA_MAG设得比ALPHA更大可能帮助收敛。

---

## 30. PULAY_MIXING参数调整

使用PULAY_MIXING时，可尝试修改&MIXING中的NPULAY。默认值4偏小，改大通常有助于收敛。NPULAY、NBROYDEN、NBUFFER三个关键词实际上等价。

---

## 31. DIRECT_P_MIXING与DIIS设置

使用DIRECT_P_MIXING时，收敛到&SCF / EPS_DIIS值后会切换到DIIS。可尝试增大EPS_DIIS（默认0.1）以早点启用DIIS，或将&SCF / MAX_DIIS（默认4）改大（如7）。

---

## 32. 对角化转OT的策略

在对角化框架下无效时，可尝试改用OT（轨道变换）方法。OT不支持k点，也不支持ADDED_MOS，故需用超胞模型且不适合必须用smearing的导体体系。

---

## 33. OT方法中的Outer SCF

在OT计算中开启outer SCF（&SCF / &OUTER_SCF）对解决不收敛非常有效。它在inner SCF达到上限后更新preconditioner，常能加速后续收敛。Multiwfn产生的OT输入文件默认开启此功能。

---

## 34. Outer SCF的迭代次数设置

开启outer SCF时，inner SCF的迭代次数上限（&SCF / MAX_SCF）应设得比平时小（15-35较合适）。总SCF次数上限约为inner次数与(outer次数+1)的乘积。Outer SCF收敛限（&OUTER_SCF / EPS_SCF）应小于等于inner收敛限。

---

## 35. OT Preconditioner选择

OT算法中可尝试不同的preconditioner。FULL_ALL通常最好但最贵，大体系可尝试FULL_SINGLE_INVERSE或FULL_KINETIC。个别情况FULL_KINETIC比FULL_ALL更容易收敛，GAPW计算总应用FULL_ALL。

---

## 36. OT算法IRAC模式

将&OT里的ALGORITHM从默认STRICT改为IRAC，常使SCF收敛更稳健。特别是使用pob系列全电子基组或进行约束性DFT（CDFT）计算时，IRAC往往更容易收敛。

---

## 37. OT极小化方法与线搜索

若&OT / MINIMIZER默认的DIIS不收敛，可改为更稳健但耗时的CG（共轭梯度法）或BROYDEN。使用CG时，可通过&OT / LINESEARCH将线搜索设为比默认2PNT更稳的3PNT。

---

## 38. 几何优化中途SCF不收敛的处理

在几何优化过程中，若偶尔出现几步SCF不收敛，程序通常会继续计算，只要最终优化收敛时SCF也是收敛状态即可（CP2K 2024.1起需设IGNORE_CONVERGENCE_FAILURE）。

---

## 39. 几何优化初期SCF不收敛的特点

几何优化初期由于初始结构相对于极小点存在不合理性，SCF可能一直不收敛。此时不要急于停止，跑一定步数后结构趋于合理，SCF通常会变得容易收敛。

---

## 40. 几何优化与分子动力学中的波函数外推

在几何优化和分子动力学中，程序会自动利用之前结构的波函数外推出当前步的初猜波函数（默认ASPC方式），质量通常优于直接生成的初猜，有助于降低SCF迭代次数和不收敛概率。

---

## 41. 步长与SCF收敛的关系

减小MD步长（&MD / TIMESTEP）或几何优化的置信半径（&MOTION / &GEO_OPT / &BFGS / TRUST_RADIUS），可减小相邻结构差异，使外推的初猜波函数更理想，从而降低SCF不收敛的可能性。

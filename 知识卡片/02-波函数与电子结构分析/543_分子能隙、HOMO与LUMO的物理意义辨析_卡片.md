---
id: 543
title: 正确地认识分子的能隙(gap)、HOMO和LUMO
url: http://sobereva.com/543
domain: 波函数与电子结构分析
topic: 分子能隙、HOMO与LUMO的物理意义辨析
cards: 19
---

# 分子能隙、HOMO与LUMO的物理意义辨析 — 知识卡片

## 1. 分子体系gap的三种类型

孤立体系如分子、团簇有三种gap：HOMO-LUMO gap定义为E(LUMO)-E(HOMO)；Fundamental gap定义为VIP-VEA，即E(N-1)+E(N+1)-2*E(N)；Optical gap是基态到最低激发态的垂直跃迁激发能。HOMO-LUMO gap无法通过实验测定，因为轨道并非真实存在；fundamental gap可通过VIP和VEA实验测定；optical gap通过UV-Vis光谱测定。周期性体系不存在HOMO-LUMO gap，应使用带隙概念。相关文献可见Mater. Horiz., 1, 17 (2014)。
- 涵盖三种gap的定义、可测性及周期性体系的区别。

---

## 2. Optical gap与Fundamental gap的关系

Optical gap在数值上肯定低于fundamental gap，两者的差值称为electron-hole pair binding energy。Fundamental gap是电子转移过程所需的能量，而optical gap涉及光吸收产生电子空穴对，后者存在结合能。在有机染料分子中，optical gap对应S0到S1态的垂直跃迁激发能。即便S0到T1态能量更低，由于对称禁阻，也不算作optical gap。
- 阐述optical gap与fundamental gap的数值差异及物理原因。

---

## 3. HOMO-LUMO gap与Fundamental gap的近似关系

根据Koopmans定理，VIP≈-E(HOMO)且VEA≈-E(LUMO)，因此VIP-VEA≈E(LUMO)-E(HOMO)，即fundamental gap≈HOMO-LUMO gap。虽然二者存在正相关性，但绝对不能期望定量上能有多好的对应关系，因为常用泛函下VEA≈-E(LUMO)的误差极大。将HOMO-LUMO gap直接当做fundamental gap使用是绝对不能接受的。
- 解释利用Koopmans定理建立的近似关系及其局限性。

---

## 4. HOMO-LUMO gap与Optical gap的混淆误区

实验化学常误认为HOMO-LUMO gap等于最低电子激发能，这是错误的。电子激发是电子态间的跃迁，而非轨道间跃迁；轨道是虚构的，电子态是真实的。TDDFT将激发描述为轨道跃迁的线性组合，即使某激发主要由HOMO->LUMO贡献，二者能量差也相差激子结合能。最低激发态未必由HOMO和LUMO跃迁主导（如反式偶氮苯S0→S1为HOMO-1→LUMO），且最低激发态可能是暗态。
- 指出将轨道能量差等同于激发能的错误及激子结合能的影响。

---

## 5. HOMO-LUMO gap与Optical gap的统计相关性

J. Chem. Inf. Model., 57, 1300 (2017)计算了2248895个小分子的最低激发能与HOMO-LUMO gap，发现二者虽呈正相关性但数据分布相当分散。在实际研究中，可以用HOMO-LUMO gap解释fundamental gap或optical gap的趋势，但若解释不通不可强求。HOMO-LUMO gap受泛函影响极大（HF成分越高gap越大），且其数值不可实验测定，不能以此判断泛函好坏。
- 说明二者统计关系的强弱及使用注意事项。

---

## 6. HOMO-LUMO gap在导电性及带隙估算中的应用

寡聚物的HOMO-LUMO gap常用于衡量导电性，gap越小导电性越好。RSC Adv., 3, 25881 (2013)通过组合苯和萘验证了序列对导电性的控制。HOMO-LUMO gap与聚合物带隙密切相关，可通过不同单元数寡聚物的gap外推带隙，如Acc. Chem. Res., 44, 14 (2011)中用B3LYP/6-31G*外推聚噻吩带隙为2.03 eV（周期性计算2.06 eV，实验2.0 eV）。
- 介绍gap在导电性研究和带隙外推中的具体应用案例。

---

## 7. 适合计算HOMO-LUMO gap的泛函选择

B3LYP/6-31G*很适合计算聚合物的导电性。J. Phys. Chem. Lett., 7, 1198 (2016)测试发现B3PW91算带隙平均误差仅0.28 eV，因B3LYP与其特征相近（HF成份20%），结论同样适用。虽然分子体系HOMO-LUMO gap不可观测，但若非要计算，B3LYP或B3PW91是优先考虑的，二者结果几乎一样。
- 推荐适合计算gap的泛函及依据。

---

## 8. HOMO-LUMO gap在化学活性分析中的应用

在概念密度泛函框架中，软度S=1/(VIP-VEA)，即fundamental gap的倒数；Koopmans近似下S=1/HOMO-LUMO gap。软度反映电子活泼性，常用于判断类似分子的反应活性，gap越小活性越高。这种分析仅限类似物，对比差异巨大的分子属于伪科学。若明确反应物且计算表明gap与反应势垒有正相关性，则可在文章中讨论。
- 阐述gap（软度）与反应活性的关系及适用范围。

---

## 9. HOMO-LUMO gap在稳定性和极化率分析中的局限

用HOMO-LUMO gap衡量分子稳定性是粗俗的，稳定性（化学、光、热）不能仅靠gap说明。若讨论化学稳定性且分子相似，或gap与反应势垒有正相关性，用gap说事才可行。HOMO-LUMO gap越小通常极化率越大，因为极化率分母含激发能，而激发能与轨道能量差相关。
- 警告用gap衡量稳定性的误区及与极化率的关系。

---

## 10. 分子轨道的不可实验测定性

分子轨道是单电子近似下人为虚构的本征函数，现实中不存在，无法实验测定。光电子实验观测到的物理意义严格的是Dyson轨道。对于静态相关弱的体系，Dyson轨道与分子轨道定性一致；对于强相关体系（如双自由基），Dyson轨道需写为多个分子轨道的线性组合。只有在完全忽略电子相关和轨道弛豫（Koopmans定理）时，Dyson轨道才等于HF分子轨道。
- 论证分子轨道的非真实性及与实验观测Dyson轨道的区别。

---

## 11. 循环伏安法与HOMO/LUMO能量的关系

循环伏安法测定的是溶液中的氧化势和还原势，对应电极反应的自由能变。将其直接当作HOMO和LUMO能量的负值是荒唐的，二者隔着多层近似，仅存在正相关性且相关性不佳。溶液中的氧化还原势可通过含溶剂模型的量子化学计算得到，这才是与CV实验真正可比的数据，但误差仍可能较大。
- 揭示CV实验数据与轨道能量的本质区别及正确计算方法。

---

## 12. 光电子谱与分子轨道能量的关系

光电子谱测定的是各层电子电离对应的电离能，并非分子轨道能量。将电离能直接当做轨道能量的负值是错误的，因为电离涉及电子相关和轨道弛豫。HF轨道能量负值与实验VIP的平均绝对误差为1.86 eV（价层）或0.74 eV（最外层），Koopmans定理表现尚可是因为忽略了相关和弛豫误差的抵消。
- 澄清光电子谱测定的是电离能而非轨道能量。

---

## 13. 高级别电子相关方法中的轨道概念

CCSD(T)、NEVPT2等高精度方法不属于单电子近似框架，没有定义有效单电子哈密顿算符，因此无法产生分子轨道。Gaussian中CCSD(T)给出的轨道是前一步HF产生的分子轨道。MP2、CCSD等配合pop=NO给出的是自然轨道，MCSCF给出的是赝正则轨道，这些都不是分子轨道。双杂化泛函因含MP2项，给出的轨道也是其中杂化泛函部分的轨道。
- 解释高级别计算方法中轨道的来源及本质。

---

## 14. Koopmans定理的原始定义与HF表现

Koopmans定理最初指分子第一电离能等于HF方法的HOMO能量（忽略电子相关和轨道弛豫）。J. Chem. Phys., 150, 074108 (2019)测试显示，HF轨道能量负值与实验VIP的平均绝对误差为1.86 eV（价层）或0.74 eV（最外层）。HF精度虽烂，但忽略相关和弛豫的误差抵消使得Koopmans定理对最外层电离给出定性正确结果。
- 介绍Koopmans定理原始定义及在HF方法中的表现。

---

## 15. Koopmans定理在LUMO上的不适用性

将Koopmans定理扩展到LUMO，认为第一垂直电子亲和能等于LUMO轨道能量，是非常糟糕且无实用性的近似。非占据分子轨道的物理意义比占据轨道更差，且能量和形状对基组非常敏感。千万不要用-E(LUMO)近似VEA。
- 指出Koopmans定理用于LUMO的严重误差。

---

## 16. DFT-Koopmans定理

DFT-Koopmans定理指出：完全精确的交换-相关泛函做KS-DFT计算得到的HOMO能量等于第一VIP。这是严格证明的，第一VIP既可是E(N-1)-E(N)计算值也可是实验值。该定理不适用于LUMO，但在精确泛函下，VEA精确等于N+1电子态的HOMO能量的负值，即VEA(N) = -HOMO(N+1)。
- 阐述DFT框架下Koopmans定理的严格表述。

---

## 17. 满足Koopmans定理的泛函选择

现有泛函对Koopmans定理满足程度不同，HF成分高或长程校正泛函表现更好。QTP系列泛函（如QTP17、CAM-QTP(00)）表现最佳，QTP17对价层VIP的平均绝对误差仅0.5 eV，优于HF的0.74 eV和M06-2X的1 eV左右。纯泛函误差高达4~5 eV。QTP系列计算内核电子电离能甚至比IP-EOM-CCSD更准。
- 介绍满足Koopmans定理较好的泛函及其精度。

---

## 18. 利用Koopmans定理优化泛函参数

由于精确泛函形式未知，无法直接通过Koopmans定理得到精确VIP。实用中可通过让占据轨道能量负值与电离能尽可能吻合来优化泛函参数，如QTP系列。J. Comput. Chem., 21, 227 (2000)发现将B3LYP杂化成分从20%提至60%可显著改善吻合度。调节长程校正泛函的ω参数也能满足Koopmans定理，优化后的泛函在激发能、极化率、gap等方面表现更好。
- 说明基于Koopmans定理优化泛函参数的方法及效果。

---

## 19. VEA的近似计算方法

J. Phys. Chem. A, 109, 8923 (2005)指出VEA可近似为-E(LUMO)-E(HOMO)-VIP。Mol. Phys., 116, 927 (2018)中杨伟涛等人提出对纯泛函的非经验global scaling correction (GSC)方法，将LUMO代入文中14式得校正量Δε(LUMO)，VEA计算为-[E(LUMO)+Δε(LUMO)]，这比标准E(N)-E(N+1)方式更准确，但校正程序未公开。
- 提供计算VEA的近似公式及校正方法。

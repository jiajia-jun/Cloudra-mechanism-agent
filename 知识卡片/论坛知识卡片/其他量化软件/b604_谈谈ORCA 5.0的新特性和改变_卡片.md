---
key: b604
title: 谈谈ORCA 5.0的新特性和改变
url: http://sobereva.com/604
domain: 其他量化软件
source: blog
year: 2021
cards: 23
---

# 谈谈ORCA 5.0的新特性和改变 — 知识卡片

## 1. ORCA 5.0 发布与手册规模

ORCA 5.0 于2021年7月1日发布，在计算化学社区中具有较高流行度。该版本手册相对于4.2.1版扩增了近300页，达到1300多页的规模。按照当前发展势头，预计后续发布的ORCA 6手册厚度可能超过Q-Chem程序手册。更全面的更新说明可查阅ORCA 5.0版手册中的Foreword和Changes部分。

---

## 2. SHARK 积分代码特性

ORCA 5.0 加入了全新开发的积分代码SHARK，用于替代或补充Libint电子积分库。SHARK 对低角动量和高角动量基函数进行了速度优化，并且对片段收缩基组和广义收缩基组（如ANO系列）均做了专门适配。程序会自动在SHARK和Libint之间选择以达到最佳计算效率。

---

## 3. SHARK 对计算速度的提升

使用SHARK积分代码后，解析Hessian、TDDFT、磁相关属性的计算速度有较大提升。实际测试表明，对于高角动量基组（如cc-pVQZ）计算小体系HF，5.0版本比4.2.1版本耗时降低了百分之十几。完全广义收缩的ANO基组在ORCA 5.0中计算变得可行，而在4.2.1版本中即使计算极小分子也极其缓慢。

---

## 4. DFT 积分格点改进

ORCA 5.0 利用机器学习技术重新设计了DFT积分格点和COSX积分格点。新版本引入了defgrid1、defgrid2和defgrid3三种格点关键词，用于统一控制COSX、CPSCF、TDDFT等步骤涉及的积分格点。新的格点分布经过GMTKN55数据集训练和测试，在相同数量的格点下具有更高的精度。

---

## 5. 积分格点关键词的选择与默认设置

defgrid2是ORCA 5.0的默认积分格点设置，其质量足以满足大多数情况的需求。defgrid1近似相当于旧版本中默认的较粗糙格点。defgrid3适用于对积分格点要求极高的情况（如VPT2非谐振计算）或使用明尼苏达系列泛函时，此时程序会提示建议使用该档位格点。

---

## 6. 积分格点关键词的破坏性变更

旧版本中分别控制DFT和COSX格点的grid和gridx关键词在ORCA 5.0中已失效且不能出现在输入文件中，导致大量旧版输入文件无法直接运行。新的defgrid系列格点具有自适应能力，能针对带弥散基组、带紧s基函数或带核极化函数的基组进行特殊剪裁以保证数值精度。

---

## 7. COSX 算法与默认加速机制

新版本优化了COSX计算解析积分的代码效率，并结合新的COSX格点提升了数值稳健性，可能减少SCF和几何优化的收敛步数。从ORCA 5.0开始，RIJCOSX成为杂化和双杂化泛函计算时的默认加速方法（此前纯泛函默认使用RIJ）。

---

## 8. RIJK 方法与 SCF 收敛增强

由于RIJCOSX已更为成熟，RIJK方法在实际应用中已无显著优势且功能限制较多。当默认的SCF solver收敛失败或表现不佳时，程序会默认切换至新加入的augmented Hessian trust radius SCF converger (TRAH)，该方法虽然较慢，但对含过渡金属等难收敛体系具有较强收敛能力。

---

## 9. CPSCF 与隐式溶剂模型改进

ORCA 5.0 提升了CPSCF的效率，降低了频率计算等任务的耗时。隐式溶剂模型得到了提升，CPCM默认设置更改为范德华型溶质孔洞结合Gaussian分布的表面显著电荷，这比旧版本的gepol_ses孔洞结合离散点电荷具有更好的数值稳定性，解决了势能面不连续问题，使从头算动力学结合溶剂模型更为可靠。

---

## 10. 溶剂模型下的解析 Hessian 与 TDDFT

新版本的CPCM溶剂模型支持计算解析Hessian，并可结合(DLPNO-)CCSD(T)使用，但尚不支持SMD下的解析Hessian。ORCA 5.0 正式支持了CPCM（线性响应形式）下的TDDFT计算，修正了旧版本中因未考虑隐式溶剂对电子激发响应而导致的激发能偏差，结果与Gaussian的线性响应溶剂模型基本一致。

---

## 11. 内存消耗与解析梯度支持

ORCA 5.0 在SCF和CPSCF过程中部分使用了共享内存方式以节约内存消耗量。该版本支持了VV10色散校正的解析梯度，使得wB97M-V、wB97X-V等泛函可以用于几何优化。此外，meta-GGA和meta-杂化泛函（如M06-2X）已支持解析Hessian，可用于优化后的振动分析。

---

## 12. 新增泛函与双杂化泛函

ORCA 5.0 加入了B97M-D4、wB97X-D4、wB97M-D4等新泛函。双杂化泛函新增了wB88PP86、wPBEPP86、RSX-QIDH、RSX-0DH、PBE-QIDH、PBE0-DH及其SCS、SOS变体，以及2009年提出的wB97X-2（需自行定义DFT-D3(BJ)参数或借助工具生成输入文件）。双杂化泛函仍不支持解析Hessian。

---

## 13. r2SCAN-3c 方法支持

ORCA 5.0 支持了r2SCAN-3c复合方法，其构建思想类似B97-3c，但纯泛函部分采用了精度更高的r2SCAN。虽然r2SCAN-3c计算耗时比B97-3c高百分之几十，但精度全面提升，建议在单点能计算任务中只要算得动就使用它代替B97-3c。

---

## 14. NEB 与 Spin-Flip TDDFT

NEB（弹性带）功能在ORCA 5.0中得到了改进，并支持结合TDDFT对激发态势能面寻找过渡态和反应路径。该版本支持了共线形式的spin-flip TDDFT及其解析梯度，可用于搜索圆锥交叉点。

---

## 15. 多参考方法与动力学模块增强

ORCA 5.0 改良了NEVPT2和CASPT2的计算形式，提升了对大活性空间的计算速度。动力学模块支持了一维和二维metadynamics以获取自由能面，集合变量包括距离、角度、二面角、配位数等，并支持Nose-Hoover chain压浴和velocity-rescale热浴。

---

## 16. ONIOM 与 QMMM 功能

ORCA 5.0 支持了两层和三层ONIOM计算，支持电子嵌入，并可结合几何优化、势能面扫描、NEB、IRC、振动分析等任务。程序还改进了QM/MM功能。DLPNO-MP2和DLPNO-双杂化泛函现在可以计算NMR和极化率，适用于较大体系的高精度NMR计算。

---

## 17. 晶体模型与 Workflow 控制

ORCA 5.0 支持了Ionic-Crystal-QMMM和Mol-Crystal-QMMM，利用簇模型计算晶体中的局部区域，背景电荷可自洽确定，适用于计算晶体电子光谱、NMR、带隙及表面吸附问题，并提供了orca_crystalprep工具辅助建模。在Workflow控制方面，输入文件现在支持脚本语言级别的控制，包括循环、条件判断、数据提取和数学运算。

---

## 18. 组合方法与辅助功能

ORCA 5.0 支持通过简单的关键词实现多种组合方法，例如使用compound[W2-2]进行W2.2高精度热力学组合方法计算。DLPNO支持了multi-level模式，允许对不同片段内部和片段间的电子相关使用不同的PNO阈值以节约时间。SARC ZORA/DKH基组支持范围扩展至Rb-Xe。

---

## 19. CASPT2-K 与 ICE 方法

ORCA 5.0 加入了CASPT2-K方法，该方法解决了CASPT2的入侵态问题，且不需要IPEA shift这种经验参数，但在计算激发能方面不如CASPT2-IPEA和NEVPT2。Iterative configuration expansion (ICE)功能得到强化，这是一种selected CI方法，可在精度损失很小的前提下大幅减少Full CI的组态数。

---

## 20. 其它新增计算功能

ORCA 5.0 支持了SCS-CIS(D)和SOS-CIS(D)用于激发态计算，以及DLPNO-NEVPT2-F12和完全内收缩多参考耦合簇（FIC-MRCC）。DLPNO系列方法支持PNO外推，通过compound[EXTRAPOLATE-PNO]关键词可在DLPNO-CCSD(T1)/cc-pVTZ下自动外推至TCutPNO=0的极限。VPT2非谐振模型现在支持计算振动平均的NMR化学位移和EPR超精细耦合常数。

---

## 21. 分析与工具程序更新

ORCA 5.0 加入了ANISO程序用于计算自旋哈密顿参数和属性，并对ab initio ligand field analysis (AILFT)进行了改进。该版本支持了化学位移的定域轨道分解分析，并为NBO的NCS（自然化学屏蔽）分析预留了接口。新版本改进了SARC/ZORA-DKH基组，且可以直接使用月份基组。

---

## 22. 局限性待解决的功能

ORCA 5.0 中PWPB95、PW6B95、DSD-PBEB95仍不支持解析梯度。该版本未直接支持精度更高的revDSD-PBEP86-D3(BJ)双杂化泛函。双杂化泛函依然不支持解析Hessian，meta-泛函做TDDFT时没有解析梯度。拉曼活性计算仍需依赖数值Hessian，耗时较长。

---

## 23. 兼容性与系统资源问题

ORCA 5.0 Windows版仅提供静态库版本，解压后体积高达24.8GB（4.2.1版为9.2GB）。新版本更改了振动分析的输出格式，且禁用了旧版的grid和gridx关键词，导致旧版输入文件和辅助工具需要更新以适配新版本。TDDFT的解析Hessian支持尚未实现。

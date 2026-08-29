---
key: t45086
title: ����MOKIT��ORCA�������������򴫹��
url: http://bbs.keinsci.com/thread-45086-1-1.html
domain: 其他量化软件
source: keinsci
year: 2024
cards: 29
---

# ����MOKIT��ORCA�������������򴫹�� — 知识卡片

## 1. MOKIT 程序的功能概述

MOKIT 可用于在不同量化程序之间传递轨道，实现波函数文件格式的转换。该工具支持从 ORCA 向其他多种量化软件（如 Gaussian、BDF、Molpro 等）传递轨道，为跨软件计算提供了可行的途径。

---

## 2. ORCA 中 RIJK 和 RIJCOSX 积分算法的轨道传递

在 ORCA 中使用 RIJK 或 RIJCOSX 加速的 HF/DFT 计算结果可用于轨道传递。转换过程需要生成 .mkl 文件，并将其转换为其他程序支持的格式以供后续使用。

---

## 3. ORCA 中 post-HF 计算的轨道传递

ORCA 中进行的 CCSD 等 post-HF 计算结果可用于轨道传递。虽然轨道文件生成可能需要额外步骤，但最终可以输出包含必要信息的 .fch 文件以供可视化或进一步计算。

---

## 4. ORCA 中 CASSCF 计算的轨道传递

ORCA 中进行的 CASSCF 计算结果可用于轨道传递。转换过程涉及生成特定文件，该轨道信息可用于后续的相关计算（如 MC-PDFT）。

---

## 5. 轨道传递对 ORCA 计算设置的要求

在 ORCA 中进行轨道传递相关计算时，必须正确收敛 SCF 以获得可靠的波函数源。建议在输入文件中设置高精度 SCF 收敛标准，如使用 `VeryTightSCF` 和 `defgrid3`，以确保轨道数据质量。

---

## 6. 使用 ORCA 生成 .mkl 文件的命令

完成 ORCA 计算后，可使用 `orca_2mkl` 命令将输出文件转换为 .mkl 格式文件。该文件包含了轨道和结构信息，是后续使用 MOKIT 工具进行格式转换的基础。

---

## 7. ORCA 轨道传递至 AMESP

使用 `mkl2amo` 命令可将 .mkl 文件转换为 `h2o.amo` 和 `h2o.aip` 文件，分别包含轨道和几何数据。随后可使用 `a2m` 命令将文本轨道文件转换为二进制文件 `h2o.mo`，以便在 AMESP 中使用。

---

## 8. ORCA 轨道传递至 BDF

使用 `mkl2bdf` 命令可将 .mkl 文件转换为 BDF 程序所需的输入文件。转换生成的 `H2O.BAS`、`h2o.inp` 和 `h2o.scforb` 文件分别包含基组、坐标及轨道信息。

---

## 9. ORCA 轨道传递至 CFOUR

使用 `mkl2cfour` 命令可生成 CFOUR 所需的 `ZMAT`、`GENBAS` 和 `OLDMOS` 文件。若 ORCA 输入文件中使用了笛卡尔坐标，转换过程通常较为顺利；若使用内坐标，可能需要手动调整坐标格式以确保兼容性。

---

## 10. ORCA 轨道传递至 Dalton

使用 `mkl2dal` 命令可将 .mkl 文件转换为 Dalton 程序所需的输入文件。该命令会生成 `h2o.dal` 和 `h2o.mol` 文件，分别包含计算参数和分子结构信息。

---

## 11. ORCA 轨道传递至 GAMESS

使用 `mkl2inp` 命令可生成 GAMESS 的输入文件 `h2o.inp`。该文件包含分子坐标、轨道数据以及一些基本的计算控制关键词。

---

## 12. ORCA 轨道传递至 Molpro

使用 `mkl2com` 命令可生成 Molpro 所需的文件，包括 `h2o.a` 和 `h2o.com`。前者包含 Alpha 轨道，后者包含坐标和关键词。对于 UHF 计算，还会生成包含 Beta 轨道的 `h2o.b` 文件。

---

## 13. ORCA 轨道传递至 OpenMolcas

使用 `mkl2inporb` 命令可生成 OpenMolcas 所需的 `h2o.INPORB`（轨道文件）和 `h2o.input`（输入文件）。

---

## 14. ORCA 轨道传递至 PSI4

使用 `mkl2psi` 命令可生成 PSI4 所需的 `h2o.A`（Alpha 轨道）和 `h2o.inp`（坐标及关键词）。对于 UHF 计算，会额外生成包含 Beta 轨道的 `h2o.B` 文件。

---

## 15. ORCA 轨道传递至 PySCF

使用 `mkl2py` 命令可生成 `h2o.fch` 和 `h2o.py` 文件。在运行 .py 脚本时，程序会从生成的 .fch 文件中读取轨道信息。

---

## 16. ORCA 轨道传递至 Q-Chem

使用 `mkl2qchem` 命令可生成 Q-Chem 的输入文件 `h2o.in`。若未设置 `$QCSCRATCH` 环境变量，临时文件将生成在当前目录下的 h2o 文件夹中；否则将生成在指定目录下。计算完成后可从相应目录获取结果文件。

---

## 17. ORCA 轨道传递至 Gaussian (mkl2gjf)

使用 `mkl2gjf` 命令可生成 Gaussian 的输入文件 `h2o.gjf`，其中包含坐标、基组信息和轨道信息。在 Gaussian 中读取资料件进行计算时，需要配合使用 `guess=cards` 关键词。

---

## 18. ORCA 轨道传递至 Gaussian (常规 HF/DFT/CASSCF)

使用 `mkl2fch` 命令可以将 .mkl 文件转换为 Gaussian 的 .fch 文件。若目录下已存在同名的 .fch 文件，该命令会用新的轨道信息覆盖原文件。

---

## 19. ORCA MP2 自然轨道的计算设置

为了生成 MP2 自然轨道，ORCA 输入文件中需包含 `%mp2` 模块，并设置 `density unrelaxed` 和 `natorbs true`。推荐使用未弛豫密度进行计算，以生成用于轨道转换的 `h2o.mp2nat` 文件。

---

## 20. MP2 自然轨道转换为 Gaussian 格式

首先使用 `orca_2mkl` 命令处理 MP2 自然轨道文件生成 .mkl 文件，随后使用 `mkl2fch` 命令并添加 `-no` 参数将其转换为 .fch 文件。生成的文件包含 MP2 自然轨道信息，可用于可视化或后续计算。

---

## 21. UCCSD 自然轨道的转换步骤

对于 UCCSD 等后自洽场方法的自然轨道，需先使用 `orca_2mkl` 和 `-anyorbs` 参数生成 .mkl 文件，再使用 `mkl2fch` 命令并添加 `-nso` 参数进行转换。这将生成包含 Alpha 和 Beta 自然轨道的 .fch 文件。

---

## 22. UCCSD 自然轨道的数据处理

UCCSD 自然轨道转换后的 .fch 文件中，Alpha 和 Beta 轨道占据数可能不同。若需将其合并为一套轨道，可使用 Python 脚本中的 `gen_no_from_nso` 函数进行处理，最终生成只包含一套轨道的文件。

---

## 23. 点群对称性对轨道传递的影响

若 ORCA 计算开启了点群对称性，MOKIT 在转换时可能仅识别到特定的不可约表示，导致转换后的轨道文件不完整。建议在进行轨道传递计算时关闭对称性使用，或者确保生成的文件包含所有必要的轨道信息。

---

## 24. 基组信息的处理

转换生成的输入文件通常会包含完整的基组信息。推荐用户直接使用生成的文件进行计算，避免手动重写基组信息，这可以减少错误并确保基组数据与原始计算一致。

---

## 25. 伪势的支持情况

MOKIT 支持处理含有赝势的体系，生成的文件会包含相应的赝势数据。目标程序也必须支持对应的赝势才能正确读取和计算。

---

## 26. ORCA SCF 收敛精度的调整

在 ORCA 计算中，若出现 SCF 难以收敛（如震荡不收敛）的情况，可以添加 `%scf` 模块并设置 `sthresh 1e-6` 来收紧密度收敛阈值。这一阈值比 Gaussian 或 GAMESS 的默认值通常更严格，有助于解决收敛问题。

---

## 27. .mkl 文件轨道排序缺失的解决方案

ORCA 官方生成的 .mkl 文件可能缺少轨道排序信息，导致全电子可视化时出现问题。一种解决方案是先使用 Gaussian 生成一个包含排序信息的 .fch 文件，再通过 `fch2mkl` 转换为包含排序信息的 .mkl 文件供 ORCA 使用。

---

## 28. 利用 Gaussian 辅助生成含排序信息的 .mkl 文件 (Step 1)

在 Gaussian 输入文件中使用 `guess(only,save)` 关键词，可以只读取基组和几何信息并生成 .chk 文件，而不进行 SCF 计算。该方法适用于生成含有完整轨道排序信息的初始文件。

---

## 29. 利用 Gaussian 辅助生成含排序信息的 .mkl 文件 (Step 2)

使用 `fch2mkl` 命令将 Gaussian 生成的 .chk 文件转换为 .fch 和 .mkl 文件。生成的 .mkl 文件包含了来自 Gaussian 的轨道排序信息，随后可使用 `orca_2mkl` 将其转换为 ORCA 可用的 .gbw 文件，从而解决轨道排序缺失问题。

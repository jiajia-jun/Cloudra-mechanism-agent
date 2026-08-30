---
key: t57996
title: ʹ��MolAICal����NAMDģ��������С���Ӻ͵���MM/PBSA�Ľ̳�
url: http://bbs.keinsci.com/thread-57996-1-1.html
domain: 其他量化软件
source: keinsci
year: 2026
cards: 30
---

# ʹ��MolAICal����NAMDģ��������С���Ӻ͵���MM/PBSA�Ľ̳� — 知识卡片

## 1. MolAICal 与 MM/PBSA 计算概述

MolAICal 可用于基于 NAMD 分子动力学轨迹进行 MM/PBSA 或 MM/GBSA 计算。该方法适用于蛋白质-配体、蛋白质-蛋白质、DNA-配体、DNA-蛋白质等复合物体系。用户只需在教程示例中替换相应的受体或配体文件即可应用于不同体系。

---

## 2. 计算前的轨迹预处理要求

在开始计算前，需确保分子动力学轨迹中的分子位于同一个周期性盒子内。若轨迹中分子跨越了周期边界，必须先使用 VMD 的 `pbc wrap` 或 `pbc unwrap` 命令对轨迹进行处理，以确保计算结果的准确性。

---

## 3. 使用 VMD 处理周期性边界条件

VMD Tk Console 提供命令用于修复周期性边界问题，使分子保持完整或位于同一盒子内。常用命令包括 `pbc wrap -centersel protein -center com -compound chain -all` 用于将分子折叠回盒子中心，以及 `pbc unwrap -sel "not (water or ions)" -all` 用于去除断键现象。

---

## 4. VMD 轨迹处理与保存

使用 VMD 处理完周期性边界后，可使用 `animate write dcd` 命令将处理后的原子选择保存为新的 DCD 轨迹文件。命令格式为 `animate write dcd pro.dcd sel $all beg 0 end 24 waitfor all`，其中 `beg` 和 `end` 参数指定帧范围。

---

## 5. MolAICal 外部程序环境配置

MolAICal 支持在 Linux 沙盒环境中安装和配置外部程序（如 VMD 和 NAMD）。用户需先将程序文件复制到 MolAICal 目录，使用 `molaical.exe -eset shell in` 进入沙盒，再通过 `cp` 命令移动文件，最后使用 `molaical.exe -call set -n <程序名> -p <路径>` 设置路径。

---

## 6. MolAICal 中 NAMD 的安装与路径设置

安装 NAMD 时，需解压文件并使用 `molaical.exe -call set -n NAMD -p "/root/soft/namdcpu/namd3"` 命令告知 MolAICal 可执行文件的位置。参数 `-n` 后的名称 "NAMD" 是固定标识符，不区分大小写。

---

## 7. MolAICal 中 VMD 的安装与路径设置

安装 VMD 需修改 `configure` 文件中的安装路径（如 `$install_bin_dir`），执行 `./configure LINUXAMD64` 和 `make install` 进行编译安装，最后使用 `molaical.exe -call set -n VMD -p "/root/soft/vmd193/bin/vmd"` 设置路径。

---

## 8. Windows 下 MolAICal 外部程序路径设置

在 Windows 环境下，可直接通过命令行设置外部程序路径，无需进入沙盒。设置命令示例包括 `molaical.exe -call set -n VMD -p "C:\Program Files (x86)\University of Illinois\VMD\vmd.exe"` 和 `molaical.exe -call set -n namd -p "d:\namd2\namd2.exe"`。

---

## 9. MM/PBSA 计算命令与文件准备

MolAICal 提供 `-mmpbgbsa` 功能模块用于执行 MM/PBSA 计算。基本命令为 `molaical.exe -mmpbgbsa -fmmpbsa_apbs.vmd`，其中配置文件 `mmpbsa_apbs.vmd` 包含了输入文件路径和计算参数，用户可根据需要修改。

---

## 10. 去除溶剂以节省内存的轨迹处理

为减少大体系计算时的内存占用，可使用 `stripDCD` 命令去除轨迹中的水分子和离子。命令格式为 `molaical.exe -call run -n vmd -c stripDCD -i -dispdev text -psf "mpro.psf" -args protein,or,resname,LIG "mpro.dcd" "complex" mpro.psf mpro.pdb`，生成只包含特定组分的轨迹。

---

## 11. MM/PBSA 计算结果输出示例

MM/PBSA 计算完成后，终端会输出极性溶剂化能、非极性溶剂化能及结合自由能的统计结果。输出示例中包含帧数、平均值、标准差和误差，单位通常为 kcal/mol，不同体系或 NAMD 版本的具体数值可能存在差异。

---

## 12. PB 求解器的选择与配置

在配置文件中，参数 `-poisson_boltzmann` 用于控制溶剂化模型计算方式。若设置为 2，则调用 APBS 进行 PB 计算；若设置为 1，则调用 DelPhi 进行 PB 计算；若设置为 0，则执行 MM/GBSA 计算。

---

## 13. APBS 与 DelPhi 的调用逻辑

若未设置 `-pb_executable` 参数，MolAICal 会自动调用内置的 APBS 进行 PB 计算。若需使用 DelPhi，需将 `-poisson_boltzmann` 设为 1 并通过 `-pb_executable` 指定 DelPhi 的路径。

---

## 14. 生成外部程序输入文件

MolAICal 可根据配置文件自动生成 NAMD、APBS 或 DelPhi 的输入文件（如 `input.namd`、`input.apbs`）。使用带有 `create_file` 后缀的配置文件（如 `mmpbsa_apbs_create_file.vmd`）执行命令即可生成这些文件，且参数会保持与 MolAICal 设置一致。

---

## 15. MM/PBSA 能量分解计算设置

进行能量分解分析时，需在配置文件中通过 `-complex_selection`、`-receptor_selection` 和 `-ligand_selection` 参数指定复合物、受体和配体的原子选择。这些参数使用 VMD 的 `atomselect` 语法，例如 `protein and resid 165 or resname LIG`。

---

## 16. 执行能量分解计算

配置好选择参数后，使用命令 `molaical.exe -mmpbgbsa -f dec_mmpbsa_apbs.vmd` 即可执行基于残基的能量分解计算。计算结果将输出特定残基（如 M165）与配体之间的相互作用能分量。

---

## 17. 使用 Carma 计算熵的准备工作

在计算熵之前，需使用 VMD 的 `stripDCD` 功能分别提取复合物、受体和配体的轨迹文件。这通常涉及运行三次命令，分别生成以 `complex`、`protein` 和 `ligand` 为前缀的 PSF、PDB 和 DCD 文件。

---

## 18. 复合物轨迹的拟合与预处理

使用 Carma 计算熵时，首先需对复合物轨迹进行去平动和转动处理。命令为 `molaical.exe -call run -centropy -i -v -fit -force -atmid ALLID -segid A -segid C complex.dcd complex.psf`，生成 `carma.fitted.dcd` 文件。

---

## 19. 拟合后轨迹的熵计算

对拟合后的轨迹执行熵计算命令，需指定温度、质量和协方差矩阵等参数。示例命令为 `molaical.exe -call run -centropy -i -v -cov -eigen -mass -force -temp 310 -atmid ALLID -segid A -segid C -last 25 carma.fitted.dcd complex.psf >& com.log &`。

---

## 20. 受体轨迹的拟合预处理

计算受体熵时，需对受体轨迹单独进行去平动和转动拟合。命令示例为 `molaical.exe -call run -c entropy -i -v -fit -atmid ALLID -segid A protein.dcd protein.psf`。

---

## 21. 蛋白质受体熵值计算命令

使用 molaical.exe 计算蛋白质受体熵值时，需执行指定命令进行协方差矩阵和特征值分析。命令参数包括温度设定为 310、片段 ID 设为 A、最后 25 帧数据，并指定了输入和输出文件。具体命令为：
- `molaical.exe -call run -c entropy -i -v -cov -eigen-mass -force -temp 310 -atmid ALLID -segid A -last 25 carma.fitted.dcd protein.psf >& rec.log &`

---

## 22. 配体构象预处理

在计算配体熵值之前，需要对配体轨迹文件进行旋转和平移的拟合处理。拟合命令通过指定片段 ID 为 C，作用于配体 DCD 和 PSF 文件。预处理命令如下：
- `molaical.exe -call run -c entropy -i -v -fit -force -atmid ALLID -segid C ligand.dcd ligand.psf`

---

## 23. 配体熵值计算命令

执行 molaical.exe 计算配体熵值的操作，通过协方差矩阵和特征质量加权等参数完成分析。命令设置温度为 310、片段 ID 为 C、选取最后 25 帧，并将结果输出至日志文件。具体命令为：
- `molaical.exe -call run -c entropy -i -v -cov -eigen-mass -force -temp 310 -atmid ALLID -segid C -last 25 carma.fitted.dcd ligand.psf >& lig.log &`

---

## 24. 熵值提取与最终计算

分别从 com.log、rec.log 和 lig.log 日志文件中查找 Andricioaei 和 Schlitter 熵值。切换至包含日志文件的目录，使用 molaical.exe 读取这些文件并计算最终熵值。执行命令如下：
- `molaical.exe -entropy -if -c com/com.log -r rec/rec.log -l lig/lig.log -t 310.0`

---

## 25. 熵值计算输出示例

程序运行后会输出 Andricioaei 和 Schlitter 两种类型的熵值结果，以 T * delta S 的形式表示，单位为 kcal/mol。示例输出中 Andricioaei 熵值为 -25.3034，Schlitter 熵值为 -32.3195。输出内容如下：
- Entropy Type:Andricioaei
  The entropy (T *delta S) = -25.3034 (kcal/mol)
- Entropy Type:Schlitter
  The entropy (T *delta S) = -32.3195 (kcal/mol)

---

## 26. 熵值计算参数说明

molaical.exe 熵值计算模块包含多个参数选项，用于指定输入文件类型、各组分日志文件及温度。具体参数含义如下：
- `-entropy`: 表示开启熵计算功能。
- `-c`: 指定复合物熵值数据输入的日志文件路径。
- `-r`: 指定受体（第一个结合单元）熵值数据输入的日志文件路径。
- `-l`: 指定配体（第二个结合单元）熵值数据输入的日志文件路径。
- `-t`: 设定用于生物分子模拟的目标计算温度。
- `-if`: 表示开启从输入文件中读取熵值的模式。

---

## 27. 熵值计算系统环境建议

Windows 系统在记录和读取熵值时的速度与稳定性仅限于 Schlitter 方法，因此推荐使用 Linux 系统进行相关文件计算。为确保计算过程顺利，建议在 Linux 系统下记录熵值数据。

---

## 28. MM/PBSA 结合自由能计算公式

MM/PBSA 方法通过热力学循环计算结合自由能，涉及分子力学能量、溶剂化自由能和熵项。总结合自由能及分项计算公式如下：
- `ΔG(bind) = ΔH - TΔS = ΔE(MM)+ ΔG(sol) - TΔS`
- `ΔE(MM)=ΔE(internal) + ΔE(ele) +ΔE(vdw)`
- `ΔG(sol)=ΔG(PB) + ΔG(SA)`
- `ΔG(SA)= γ * SASA + β`

---

## 29. 引入熵校正后的结合自由能计算

将计算得到的熵项 TΔS 引入到未包含熵校正的结合自由能数据中，可得到最终的结合自由能。以原始结合自由能 -66.5006 kcal/mol 为例，分别使用 Andricioaei 和 Schlitter 熵值进行修正：
- 使用 Andricioaei 熵值：`ΔG(bind) = -66.5006 - (-25.3034) = -41.1972 (kcal/mol)`
- 使用 Schlitter 熵值：`ΔG(bind) = -66.5006 - (-32.3195) = -34.1811 (kcal/mol)`

---

## 30. 熵校正计算的结构采样注意事项

对于结合过程中未发生显著结构变化的体系或结构变化幅度较小的系统，计算结果通常具有较高可靠性。若结构变化剧烈，直接使用经验参数值计算 ΔG 可能导致数值误差较大。

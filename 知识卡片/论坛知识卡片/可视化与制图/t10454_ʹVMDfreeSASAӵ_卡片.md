---
key: t10454
title: ʹ��VMD���freeSASA������ӵ��ܼ��ɼ���������(SASA)
url: http://bbs.keinsci.com/thread-10454-1-1.html
domain: 可视化与制图
source: keinsci
year: 2018
cards: 10
---

# ʹ��VMD���freeSASA������ӵ��ܼ��ɼ���������(SASA) — 知识卡片

## 1. VMD计算溶剂可及表面积(SASA)的方法

VMD 内置 `measure sasa` 命令可直接计算指定原子或残基的溶剂可及表面积。通过编写简单的 Tcl 脚本循环处理轨迹中的每一帧，可以将每一帧指定结构的 SASA 值输出到文件中。该方法适用于需要分别计算不同原子或基团 SASA 的场景。

---

## 2. freeSASA 工具简介与安装

freeSASA 是一个可独立运行的命令行工具，能够基于 PDB 文件计算 SASA，支持 Linux 等系统。安装过程通常较为简单，通过一般的编译安装步骤即可完成，支持生成 JSON 或 XML 等格式的输出结果。该工具常作为 Gromacs 等 MD 软件的补充，用于处理更为复杂的 SASA 计算需求。

---

## 3. freeSASA 与 VMD 算法支持

freeSASA 和 VMD 均支持多种 SASA 计算算法，包括 Shrake & Rupley 算法和 Lee & Richards 算法。其中 freeSASA 默认使用 Lee & Richards 算法。不同算法的详细原理和参数设置可参考相关软件的官方文档。

---

## 4. freeSASA 的原子选择语法

freeSASA 支持使用类似 PyMOL 的选择语法来指定计算 SASA 的原子范围，这为用户提供了灵活的结构筛选方式。如果用户熟悉 PyMOL 的选择代数（Selection Algebra），可以较容易地掌握 freeSASA 的原子选择操作。

---

## 5. VMD 与 freeSASA 在计算环境上的差异

VMD 在计算 SASA 时会考虑当前加载的所有结构（包括周围的溶剂、离子等），而 freeSASA 默认仅计算选定结构及其周围紧邻结构的 SASA。若使用 VMD 计算，需在脚本或命令中明确指定要计算的目标原子，以排除环境分子的干扰，从而获得仅针对目标分子的绝对 SASA。

---

## 6. 基于 freeSASA 的 VMD 脚本使用流程

使用集成了 freeSASA 的 VMD 脚本 `freeSASA.tcl` 需在 Linux 环境下预装 freeSASA 程序。使用时需将脚本置于当前目录，在 VMD 文本界面通过 `source freeSASA.tcl` 加载，并根据提示输入结构文件名、原子选择关键字以及计算步长（频率）等参数。计算完成后会在当前目录生成包含各帧 SASA 数据的 `.dat` 文件。

---

## 7. SASA 计算值的显著差异及原因

对同一结构使用 freeSASA 和 VMD 计算得到的 SASA 数值可能存在显著差异，例如在测试案例中相差达 36%。这种差异通常并非由算法不同导致，而是因为两者在处理“计算环境”时的默认逻辑不同：VMD 往往将所有加载分子纳入屏蔽计算，而 freeSASA 仅计算选定部分。

---

## 8. 消除 SASA 计算差异的方法

为消除 VMD 和 freeSASA 计算结果的差异，应确保两者在完全相同的“计算环境”下运行，即排除不参与计算的溶剂分子。具体操作是将每一帧的蛋白质结构单独提取写入临时 PDB 文件，再使用 freeSASA 进行计算。经此处理，两者的计算结果差异可缩小至 2% 以内，仅由算法细微差别造成。

---

## 9. 轨迹帧处理中的水分子处理注意事项

在使用脚本提取轨迹帧进行 SASA 计算时，若将每一帧的所有内容（包括水分子、脂质等）都写入临时 PDB 文件，可能会影响计算结果的准确性。若关注的是蛋白质本身的 SASA，写入临时文件的选择表达式应为 `protein`；若包含膜环境，则应写为 `protein or lipid`，以避免无关分子干扰表面积计算。

---

## 10. VMD 与 freeSASA 的性能对比

VMD 原生的 `measure sasa` 命令在计算不同原子集合的 SASA 时速度较快，具有显著的性能优势。而 freeSASA 虽然在处理特定选择和批处理上具有灵活性，但在计算大量原子的细分 SASA 时可能耗时较长。实际应用中应根据研究重点（如速度 vs. 灵活性）选择合适的工具。

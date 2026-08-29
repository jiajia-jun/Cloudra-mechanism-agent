---
key: t28708
title: ����Gaussian FCHT����ֽ������ܺͼ���Huang-Rhys���ӵ�PythonС�ű�
url: http://bbs.keinsci.com/thread-28708-1-1.html
domain: 激发态与光谱
source: keinsci
year: 2022
cards: 12
---

# ����Gaussian FCHT����ֽ������ܺͼ���Huang-Rhys���ӵ�PythonС�ű� — 知识卡片

## 1. gau_reorg.py 脚本功能

gau_reorg.py 是用于处理 Gaussian 输出文件的 Python 脚本，支持输出重组能分解、Huang-Rhys 因子图以及 Duschinsky 矩阵。该脚本能够将 Gaussian 输出的 Duschinsky 矩阵格式修改为 n×n 的矩阵格式，便于直接导入 Origin 作图。使用该脚本的命令为 `python gau_reorg.py output.log`。

---

## 2. gau_reorg.py 脚本参数配置

运行 gau_reorg.py 脚本时，用户需根据需求设置三个参数，分别控制是否输出重组能分解、Huang-Rhys 因子图和 Duschinsky 矩阵。若选择输出 Huang-Rhys 因子图，数据将保存在当前目录的 `output.log.hr.txt` 文件中；若选择输出 Duschinsky 矩阵，数据将保存在当前目录的 `output.log.mat.txt` 文件中。这些选项均通过输入 1（开启）或 0（关闭）进行设定。

---

## 3. Gaussian 16 C.01 原生输出 Huang-Rhys 因子

Gaussian 16 C.01 版本支持在 FCHT 计算中原生输出 Huang-Rhys 因子、Duschinsky 矩阵（J）以及位移向量（K）。若需在计算结果中包含这些信息，必须在输入文件中添加 `print=(huangrhys,matrix=JK)` 关键词。默认的 `spectroscopy` 选项为 `onephotonabsorption`，若计算发射光谱需将其指定为 `onephotonemission`。

---

## 4. Gaussian FCHT 计算输入文件示例

在 Gaussian 中进行 FCHT 计算并输出 Huang-Rhys 因子时，输入文件需包含 `freq(readfc,fcht,readfcht)` 关键字。计算需要使用初态和末态的检查文件（如 `initial.chk` 和 `final.chk`），并通过 `initial=source=chk` 和 `final=source=chk` 分别指定。若计算的是重组能分解，需将末态 chk 文件通过 `%oldchk` 指定。

---

## 5. FCHT 计算中的错误与警告

Gaussian FCHT 计算过程中可能会报错并提示 "Low progression after class n"，这通常是由于 Franck-Condon 权重图收敛性较差导致的。出现此类报错时，程序会停止计算并提示光谱结果可能不可靠。如果这些低权重模式对分析不重要，可以通过修改输入参数忽略这些报错。

---

## 6. RedDim 参数与低频模式处理

使用 `RedDim=ClearLowFreq=n` 参数可以忽略频率小于 n cm⁻¹ 的模式对 Huang-Rhys 因子和 Duschinsky 矩阵的贡献。该参数适用于只对高频模式感兴趣的情况，因为低频模式通常涉及小幅度的分子变化，却可能具有较大的重组能。需要注意，使用 `RedDim` 可能会导致输出数据的模态顺序与原始顺序不匹配，需确保初态和末态的排序一致。

---

## 7. 错误处理：Low progression 与 Advanced

针对 "Low progression" 错误，可以在 Freq 关键词中添加 `Advanced=(ForceFCCalc)` 来强制进行 Franck-Condon 积分计算。即便 progression 较小，此选项也会尝试完成计算，但结果强度可能极小且不一定可靠。使用 `Advanced=(ForceFCCalc)` 后，若能找到非零 progression，则计算可继续进行。

---

## 8. 预筛选参数 PreScreening 设置

为了解决计算报错或收敛问题，可以使用 `PreScreening=(MaxC1=XX,MaxC2=YY,MaxInt=ZZZ)` 参数来调整筛选阈值。建议将 `MaxInt` 设置为较大的值（例如 >=1000），以包含更多的积分项。如果使用了 `Advanced=(ForceFCCalc)` 强制计算但 progression 仍然很小，Franck-Condon 权重图可能依然不佳，导致结果不可靠。

---

## 9. SaveNormalMode 参数说明

Gaussian 09 和部分 Gaussian 16 版本默认使用 `NoSaveNM`，即不将简正模式信息保存到 .chk 文件中。为了进行后续的振转光谱分析，必须显式添加 `SaveNormalMode` (或 `SaveNM`) 关键词将简正模式信息写入检查文件。Gaussian 16 C.01 版本默认已开启 `SaveNM`，但在旧版本或特定配置下需手动确认。

---

## 10. 常见报错：Checkpoint 文件问题

计算振转光谱时常见的报错包括 "Data taken from checkpoint file" 和 "FileIO operation on non-existent file"，这通常意味着检查文件损坏或不存在。解决方法是确保检查文件路径正确且文件未损坏，或者重新生成检查文件。

---

## 11. GaussView 6 振转光谱分析

GaussView 6 支持可视化振转光谱分析，可通过 Results -> Vibronic 菜单进入。在弹出的窗口中选择 Plot -> Transition Table 可以查看详细的跃迁信息。该功能依赖于检查文件中的数据，能够辅助分析光谱特征。

---

## 12. 相关资源与文献参考

关于振转光谱模式和 Duschinsky 旋转的原理，可参考相关技术博客和论坛帖。Gaussian 官方文档 Freq 部分及 ReadFCHT Input 选项提供了官方参数说明。应用 Huang-Rhys 因子方法的研究案例包括 Lu Wang 等人在 J. Phys. Chem. A 2021 发表的文章以及 Teng-Fei He 等人在 Inorg. Chem. 2020 发表的文章。

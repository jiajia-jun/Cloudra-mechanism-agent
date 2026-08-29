---
key: b595
title: 对Gaussian计算的IRC轨迹上每个点用PSI4做SAPT分析的辅助工具
url: http://sobereva.com/595
domain: 化学信息学与脚本
source: blog
year: 2021
cards: 10
---

# 对Gaussian计算的IRC轨迹上每个点用PSI4做SAPT分析的辅助工具 — 知识卡片

## 1. IRC_SAPT 工具简介与用途

IRC_SAPT 是一个辅助工具，能够将 Gaussian 计算的内禀反应坐标 (IRC) 输出文件转换为每一个 IRC 点对应的 PSI4 SAPT 输入文件。该工具用于研究 IRC 轨迹上相互作用能物理分量的变化，从而揭示反应过程的本质。IRC_SAPT 的可执行程序分别提供了 Windows 和 Linux 版本。

---

## 2. IRC_SAPT 的使用准备与模板设置

在使用 IRC_SAPT 之前，需在当前文件夹下准备一个名为 "SAPT_template.inp" 的模板文件。该模板是标准的 PSI4 SAPT 输入文件，其中两个单体的净电荷、自旋多重度以及坐标部分需分别用 [monomer1] 和 [monomer2] 占位符表示。IRC_SAPT 运行时会利用这些占位符生成具体的输入文件。

---

## 3. IRC_SAPT 的运行流程与输入参数

启动 IRC_SAPT 后，用户需依次输入 Gaussian IRC 输出文件的路径、正向和反向 IRC 点的数量、以及两个片段的电荷、自旋多重度及原子索引。程序随后会在当前文件夹下批量生成对应于每个 IRC 点的 SAPT 输入文件，且生成的几何构型分别对应 IRC 轨迹上的各点。

---

## 4. SAPT 方法的适用范围

SAPT 能量分解分析原则上不适合用于存在化学键作用的两个片段之间的相互作用分解。SAPT 最适合用于弱相互作用的分解分析。

---

## 5. 水二聚体构型转换示例 (IRC 计算)

在水二聚体构型转换的 IRC 计算示例中，首先使用 Gaussian 16 A.03 通过关键字 "# B3LYP/6-311+G** em=GD3BJ opt(calcfc,TS,noeigen) freq" 优化过渡态并进行频率分析。随后基于优化后的结构，使用关键字 "# B3LYP/6-311+G** em=GD3BJ IRC(calcfc,recalc=3,LQA,maxpoints=50)" 生成包含 30 个正向和 30 个反向点的 IRC 轨迹。

---

## 6. PSI4 SAPT 输入文件模板示例

示例中的 SAPT_template.inp 模板将计算级别设定为 SAPT2+(3)δMP2/aug-cc-pVTZ，并设置了 20000 MB 内存。模板中的 [RxCoord] 行会被 IRC_SAPT 自动替换为具体的反应坐标值，且脚本配置了将总能量及各分量（静电、交换、色散、诱导）转换为 kcal/mol 并打印输出。

---

## 7. 生成 PSI4 输入文件的命令操作

在 IRC_SAPT 交互界面中，输入 IRC.out 文件路径、点数 "30,30"、片段 1 的电荷与多重度 "0 1" 和原子索引 "1-3"、片段 2 的电荷与多重度 "0 1" 和原子索引 "4-6"。程序将生成 61 个 PSI4 输入文件，命名为 0001.inp 至 0061.inp，其中 0031.inp 对应过渡态构型。

---

## 8. 批量运行与数据提取脚本

将生成的 SAPT 输入文件及 IRC_SAPT 文件夹中的 psi4all.sh 脚本移至新文件夹并运行，可调用 PSI4 批量计算所有输入文件。计算完成后，运行 extract.sh 脚本可从所有 .out 输出文件中提取数据，并汇总生成包含反应坐标及各能量项的 energy.txt 文件。

---

## 9. energy.txt 数据列含义

生成的 energy.txt 文件包含六列数据：第一列为反应坐标 (单位: sqrt(amu)*Bohr)，第二列至第六列分别为总相互作用能 (E_tot)、静电能 (E_elst)、交换能 (E_exch)、色散能 (E_disp) 和诱导能 (E_ind)。所有能量数据的单位均为 kcal/mol。

---

## 10. 水二聚体 IRC 轨迹 SAPT 分析结论

基于对水二聚体 IRC 轨迹的 SAPT 分析结果绘图可知，静电吸引作用在稳定最小构型（相对于过渡态构型）方面起主导作用，诱导效应也有一定贡献。色散相互作用对二聚体构型的敏感度不如静电和诱导效应，而交换排斥效应在很大程度上抵消了静电和诱导效应的稳定作用。

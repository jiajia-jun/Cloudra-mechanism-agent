---
key: t33837
title: Gaussian-MOKIT-Molpro ���÷��� gmm.py
url: http://bbs.keinsci.com/thread-33837-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2022
cards: 7
---

# Gaussian-MOKIT-Molpro ���÷��� gmm.py — 知识卡片

## 1. Gaussian与Molpro联用的需求

Gaussian 拥有强大的几何优化与搜索算法，Molpro 则擅长高精度的 Post-HF 计算。将两者结合可以利用 Molpro 的高精度计算层级在 Gaussian 的优化框架下进行工作，解决 Molpro 在优化开壳层体系或复杂势能面时容易失败的问题。这种联用方式通常需要 MOKIT 程序中的 `fch2com` 工具来辅助转换文件格式。

---

## 2. 工作流原理与步骤

该联用流程通过 Gaussian 的 `external` 关键字调用外部 Python 脚本实现。步骤包括：Gaussian 读取初始结构并调用脚本进行 ROHF 计算；脚本利用 MOKIT 的 `fch2com` 将结果转换为 Molpro 输入文件；脚本自动补充用户定义的计算命令并调用 Molpro 进行计算；Molpro 输出的能量和梯度被解析并返回给 Gaussian。此过程允许在 Gaussian 的优化任务中使用 Molpro 计算的能量和梯度。

---

## 3. 梯度计算方式

Molpro 对解析梯度的支持仅限于 HF 和 MCSCF 方法，对于 CCSD(T) 等 Post-HF 方法不支持解析梯度。因此，在需要梯度的计算中，Molpro 通过数值梯度接口进行计算，而 Gaussian 对应地需要使用 `freq=(num)` 关键字来配合数值梯度的获取。

---

## 4. 配置文件 gmm.json 的参数设定

计算参数通过 JSON 格式的配置文件 `gmm.json` 进行管理，文件需包含 Gaussian 和 Molpro 两个部分的设置。Gaussian 部分需指定核数、内存和计算层级（必须包含 `nosymm` 和 `int=(nobasistransform)`）；Molpro 部分指定核数、内存以及需要追加的命令列表（如基组和计算方法）。该配置文件需与 Gaussian 输入文件位于同一目录。

---

## 5. Gaussian 输入文件的必要关键字

在 Gaussian 输入文件中，必须设置 `%nproc=1` 并使用 `# external="python3 -u /path/to/gmm.py"` 来调用联用脚本。对于几何优化任务，建议使用 `opt=(nomicro)`；对于涉及数值梯度的频率计算或优化，必须使用 `freq=(num)`。使用 `geom=(allcheck)` 可以方便地承接 checkpoint 文件中的结构。

---

## 6. 过渡态与频率计算任务

进行过渡态搜索和频率验证时，需采用特定的 Gaussian 输入组合。通常先进行一次频率计算获取初始 Hessian，随后使用 `opt=(nomicro,rcfc,ts,noeigen)` 读取 Hessian 进行过渡态优化，最后再次进行频率计算以确认虚频。IRC 计算可以在过渡态优化完成后使用 `irc=(rcfc,gradientonly)` 进行。

---

## 7. HCN 异构化计算测试案例

针对 HCN 与 CNH 异构化反应的测试表明，该联用脚本在 CCSD(T)-F12a/AVTZ 层级下表现良好。相比于 Molpro 内置的优化算法，使用 Gaussian 的优化算法配合 Molpro 的单点能计算，能够更稳定地找到过渡态并完成 IRC 路径计算。测试中脚本在约 3 分钟内完成了包含数值频率和 IRC 的计算任务，结果与文献数据吻合。

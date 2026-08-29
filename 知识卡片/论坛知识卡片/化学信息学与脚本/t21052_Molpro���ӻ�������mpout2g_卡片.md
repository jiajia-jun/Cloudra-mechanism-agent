---
key: t21052
title: Molpro���ӻ�������mpout2gauout.sh�ű�
url: http://bbs.keinsci.com/thread-21052-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 10
---

# Molpro���ӻ�������mpout2gauout.sh�ű� — 知识卡片

## 1. GMolpro 图形界面发布

GMolpro 是 Molpro 程序的前端图形界面工具，目前仅支持 Linux 和 Mac 系统。Windows 用户若需可视化辅助，可考虑使用 mpout2gauout.sh 脚本进行文件格式转换以实现可视化。

---

## 2. mpout2gauout.sh 脚本用途

mpout2gauout.sh 脚本用于将 Molpro 优化和振动分析的输出文件转换为 Gaussian 格式输出文件。通过该转换，生成的文件可在 GaussView 中打开，从而实现对 Molpro 计算结果的可视化查看。

---

## 3. 脚本使用方法

脚本执行命令为 `bash mpout2gauout.sh molpro.out molpro.log`。执行后，当前目录下会生成名为 molpro.gau.log 的 Gaussian 格式文件。

---

## 4. 输入文件内容要求

Molpro 的 out 文件包含频率数值信息，log 文件包含优化过程中每一帧的结构信息。若要查看完整的优化轨迹和振动模式，必须同时提供 out 和 log 文件。

---

## 5. 命令行注意事项

脚本首行需指定系统 bash 的位置，必须使用 bash 命令执行脚本，不可使用 sh 命令。out 和 log 文件的输入顺序不限。

---

## 6. 临时文件说明

脚本运行时会在当前目录下生成 geom001、geom002、GEOM、freq1、FREQ 等临时文件。处理完成后应手动删除这些临时文件，以免造成文件混淆。

---

## 7. 非对称性优化的显示限制

脚本目前无法正确识别非对称性优化的结果。对于非对称体系的几何优化，标准输入可能导致键长键角变化，脚本只能保证第一帧结构的对应关系。

---

## 8. 振动模式显示数量限制

GaussView 通常只能读取 6 个振动模式，若体系振动模式超过 6 个，需自行修改脚本内部限制。Molpro 输出文件中的频率数值已正确打印至 Gaussian 格式文件中，不受此显示限制影响。

---

## 9. 振动位移矢量显示偏差

通过脚本生成的 Gaussian 格式文件在 GaussView 中显示的振动位移矢量（原子运动幅度）可能比原生 Gaussian 文件偏小。这种偏差与不同软件的默认缩放比例有关，但不影响对振动模式的基本分析。

---

## 10. 相关脚本资源

除 Molpro 相关脚本外，作者还提供了 Quantum-Espresso-PWscf 的可视化脚本。用户可根据计算体系需求选择相应的工具进行结果分析。

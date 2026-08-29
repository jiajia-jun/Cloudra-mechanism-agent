---
key: t53565
title: ������GROMACS��AMBER19SB��������
url: http://bbs.keinsci.com/thread-53565-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2025
cards: 9
---

# ������GROMACS��AMBER19SB�������� — 知识卡片

## 1. GROMACS 对 AMBER19SB 力场的版本支持

GROMACS 2026.0 版本已原生包含 AMBER19SB 力场，无需额外下载力场文件。用户可直接使用该版本自带的力场参数进行模拟。在此之前，需手动下载并配置相关力场文件。

---

## 2. GROMACS 2025 版本对 AMBER19SB 的支持特性

GROMACS 2025 版本通过引入支持 CMAP（修正图谱） corrections-amap-pair-matching 功能，从而兼容 AMBER19SB 力场。该功能是支持 AMBER19SB 的必要条件。

---

## 3. AMBER19SB 力场适用的核酸模型推荐

使用 AMBER19SB 力场进行 DNA 模拟时，推荐配合 AMBER25 推荐的 OL24 参数；进行 RNA 模拟时，推荐使用 OL3 参数。适用的水模型包括 OPC、OPC3 及 TIP4P-ice。

---

## 4. OPC 和 OPC3 水模型的来源与特性

OPC 和 OPC3 水模型由 Merz 等人开发，属于一系列极化的水模型。这些模型在计算性质、实验性质和相图方面表现出色，具有较好的模拟效果。

---

## 5. AMBER19SB 与水模型搭配的推荐原则

强烈推荐将 AMBER19SB 力场与 OPC 水模型搭配使用。建议不要将 AMBER19SB 与 TIP3P 水模型联合使用。

---

## 6. AMBER19SB 力场文件缺失的氨基酸

AMBER19SB 的力场文件中缺失鸟氨酸（Ornithine）等非标准氨基酸，这一点与 AMBER14SB 一致。相关残基参数目前未包含在力场文件中。

---

## 7. AMBER19SB 中不同水模型的离子参数文件选择

使用 OPC 水模型时，需选用 ions.itp 离子参数文件；使用 OPC3 水模型时，需选用 ions_opc3.itp 参数文件。若参数文件未列出所有离子，可查看 ffnonbonded.itp 以获取可用的离子信息。

---

## 8. AMBER19SB 对其他力场的兼容性测试

曾尝试将 AMBER19SB 与 GLYCAM_06j（糖类力场）以及 lipid21（脂质力场）进行混合使用，但未获成功。这表明这些力场之间可能存在兼容性问题。

---

## 9. 力场文件使用的注意事项

在使用下载的力场文件时，务必注意阅读随附的说明文档。使用前应仔细核对文件内容与要求，以确保正确应用。

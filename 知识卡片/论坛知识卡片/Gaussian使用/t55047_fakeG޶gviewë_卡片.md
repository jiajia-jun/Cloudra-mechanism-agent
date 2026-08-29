---
key: t55047
title: ����fakeG޶gview��ë
url: http://bbs.keinsci.com/thread-55047-1-1.html
domain: Gaussian使用
source: keinsci
year: 2025
cards: 12
---

# ����fakeG޶gview��ë — 知识卡片

## 1. fakeG 程序简介

fakeG 是一个辅助工具，旨在生成兼容 Gaussian 使用的 .g98.out 格式输出文件。该程序解决了用户不习惯使用 gview 进行可视化的问题，通过为其他计算软件提供数据接口，使得在不同软件间共享计算结果（如分子轨道、梯度、振动频率）更加便捷。

---

## 2. fakeG 的软件接口扩展性

fakeG 具有可扩展的接口设计，用户可以在 `/src/parser/parser_interface.h` 文件中定义新的接口。通过编写相应的解析器，可以支持更多量子化学程序（如 PySCF、Molpro 等）的数据转换为 fakeG 格式，从而实现通用可视化或后续处理。

---

## 3. AfakeG 功能定义

AfakeG 是 fakeG 的一个组件，专门用于将 Amesp（Atomic and molecular electronic structure program）的计算输出文件转换为 fakeG（fake Gaussian）格式。Amesp 官方网站为 https://www.amesp.xyz/。

---

## 4. AfakeG 更新支持动态信息

AfakeG 的最新版本已支持转换包含动态信息的 Amesp 输出文件。该更新发布于 2025-08-22，用于处理更复杂的计算结果数据。

---

## 5. BfakeG 功能定义

BfakeG 是 fakeG 的一个组件，专门用于将 BDF（Beijing Density Functional）的计算输出文件转换为 fakeG 格式。BDF 官方手册位于 https://bdf-manual.readthedocs.io/zh-cn/latest/Introduction.html。

---

## 6. XfakeG 功能定义

XfakeG 是 fakeG 的一个组件，用于将单帧或多帧 xyz 文件转换为 fakeG 格式。该工具特别适用于处理由 xtb、molclus 或 isostat 等程序产生的连续多帧 xyz 文件，便于后续分析。

---

## 7. xtbfakeG 工具发布

xtbfakeG 是专门针对 xtb 程序输出文件转换的工具。附件 `xtbfakeg`（大小 2.85 MB）于 2025-8-19 20:38 上传，用于将 xtb 生成的 g98.out 文件进行处理。

---

## 8. xtbfakeG 版本修复

xtbfakeG 在 2025-8-19 修复了一个程序 bug，以确保转换过程的稳定性。

---

## 9. ORCA 转换工具说明

ORCA 输出文件的转换已有专门的 OfakeG 工具支持（相关介绍链接：http://原作者.com/498），因此 fakeG 系列中未重复开发针对 ORCA 的转换功能。

---

## 10. 交叉编译版本 availability

fakeG 的 Windows 交叉编译版本已经发布，用户无需在 Linux 环境下编译即可直接使用。

---

## 11. ORCA IRC 计算转换支持

论坛用户 @Tanghaoru 提供了支持 ORCA IRC（内禀反应坐标）计算结果转换的 OfakeG 版本。该版本的压缩包文件名为 `build.7z`，大小为 1.34 MB，于 2025-9-14 14:07 上传。

---

## 12. 软件获取渠道

fakeG 的源代码及发布版本可在 GitHub 上获取（链接：https://github.com/bane-dysta/fakeG）。用户也可以关注 GitHub 上的 Release 1.2 及以后版本，或者从论坛附件中下载更新。

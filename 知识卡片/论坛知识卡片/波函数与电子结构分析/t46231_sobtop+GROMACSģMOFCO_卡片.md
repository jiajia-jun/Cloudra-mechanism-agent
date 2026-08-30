---
key: t46231
title: sobtop+GROMACSģ��MOF��COF��ϵʱ�����õĿ��ټ���ԭ�ӵ�ɵķ�����PACMAN
url: http://bbs.keinsci.com/thread-46231-1-1.html
domain: 波函数与电子结构分析
source: keinsci
year: 2024
cards: 8
---

# sobtop+GROMACSģ��MOF��COF��ϵʱ�����õĿ��ټ���ԭ�ӵ�ɵķ�����PACMAN — 知识卡片

## 1. Sobtop与GROMACS结合模拟MOF/COF原子电荷

Sobtop 可与 GROMACS 结合用于 MOF 和 COF 体系的原子电荷模拟。该方法建议配合 CP2K 使用 REPEAT 方法生成电荷。进行此类研究需要研究者具备使用 CP2K 的能力。

---

## 2. CP2K安装与配置指南

CP2K 的安装可参考 J. Chem. Theory Comput. 期刊上的一篇文献进行配置（DOI: 10.1021/acs.jctc.4c00434）。该文献详细介绍了 CP2K 的安装过程及注意事项。

---

## 3. PACMAN预测原子电荷方法

PACMAN 是一种基于机器学习的方法，用于预测 MOF 和 COF 体系原子电荷。使用该方法仅需提供 CIF 文件即可预测 REPEAT、AIM 及 CM5 电荷。该预测方法的结果对于不同类型电荷的数值均存在一定程度的误差。

---

## 4. PACMAN在线工具使用

PACMAN 提供了在线网站（https://pacman-charge-mtap.streamlit.app/）供用户使用。用户上传 CIF 文件后，可在线获得包含预测原子电荷的 CIF 文件。该工具可直接下载处理后的文件。

---

## 5. 预测后CIF文件的数据格式

PACMAN 预测生成的 CIF 文件中包含原子电荷信息。文件中 `_atom_site_charge` 字段记录了具体的原子电荷数值，如 Zn 原子的电荷值约为 1.2。

---

## 6. 手动提取电荷数据生成chg文件

研究者在获得预测后的 CIF 文件后，可手动提取电荷数据生成 `.chg` 格式文件。该过程涉及将 CIF 中的电荷信息整理为 Sobtop 可识别的格式。

---

## 7. Sobtop读取chg文件配置

Sobtop 处理 MOF/COF 文件时需要通过 `.chg` 文件读取原子电荷。若 CIF 文件坐标不正确或需避免 `.chg` 文件覆盖原有坐标，需修改 `sobtop.ini` 配置文件。将 `ichggeom` 参数设置为 0，可指示 Sobtop 读取电荷时不更新坐标。

---

## 8. 预测方法的局限性

机器学习预测方法生成的原子电荷可能存在一定误差。在某些特定情况下，预测结果可能违反物理化学直观规律。

---
key: t58097
title: ʹ��MolAICal���ֵ�������Ǳ�ڵĻ��Կڴ���λ��
url: http://bbs.keinsci.com/thread-58097-1-1.html
domain: 其他量化软件
source: keinsci
year: 2026
cards: 7
---

# ʹ��MolAICal���ֵ�������Ǳ�ڵĻ��Կڴ���λ�� — 知识卡片

## 1. P2Rank与fpocket的特点对比

P2Rank和fpocket是常用的开源结合位点识别工具。fpocket适用于任何原子类型，侧重于几何特征。P2Rank基于机器学习模型，考虑了局部化学环境和空间特征，能更准确地识别潜在结合位点。

---

## 2. MolAICal与PyMOL的安装

MolAICal可从官网或GitLab页面获取。PyMOL可通过pip安装wheel包，推荐先安装Miniconda环境。需分别安装pymol和pymol_launcher对应的whl文件。

---

## 3. 示例文件下载

MolAICal关于识别结合位点的完整示例文件可从Gitee仓库下载。仓库路径为molaical/tutorials下的019-detect_pocket文件夹。

---

## 4. MolAICal调用P2Rank识别结合位点

在019-detect_pocket文件夹目录下执行命令 `molaical.exe -call run -c pocket -i predict -f 1UYD.pdb -o results`。计算结果将保存在results文件夹中。

---

## 5. P2Rank结果可视化

进入results\visualizations目录，在PyMOL中运行该目录下的1UYD.pdb脚资料件。该操作会在PyMOL中显示识别出的潜在结合位点。

---

## 6. MolAICal调用fpocket识别结合位点

在019-detect_pocket文件夹目录下执行命令 `molaical.exe -call run -c fpocket -i -f 1UYD.pdb`。fpocket目前支持在Linux系统下运行，结果输出至1UYD_out文件夹。

---

## 7. fpocket结果可视化

进入1UYD_out目录，在PyMOL中运行该目录下的1UYD.pml脚资料件。同时载入1UYD.pdb文件，可以观察到被准确识别出的肮蛋白结合位点。

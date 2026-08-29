---
key: t50199
title: ѧϰ�ʼǣ������ж�PDB��X-ray�ṹģ�����ض��л�/����ṹ���Ŷȵķ���
url: http://bbs.keinsci.com/thread-50199-1-1.html
domain: 波函数与电子结构分析
source: keinsci
year: 2024
cards: 11
---

# ѧϰ�ʼǣ������ж�PDB��X-ray�ṹģ�����ض��л�/����ṹ���Ŷȵķ��� — 知识卡片

## 1. PDB结构模型质量评估的重要性

使用PDB数据库中的结构模型作为分子模拟或对接的起始结构时，必须预先判断结构的可靠性，特别是小分子配体部分的结构准确度。若直接使用存在误差的结构，可能导致后续建模或机理分析出现严重偏差。

---

## 2. 电子密度图验证原理

通过分析PDB提供的structure factor mtz文件和原始电子密度图，可以验证PDB模型中的原子位置是否真实存在衍射实验支持。PDB官网的Mol* viewer工具支持查看electron density map，但需注意直接查看model map可能存在模型偏差，建议使用omit map进行客观验证。

---

## 3. Phenix软件安装环境

Phenix官方目前推荐在Windows 10及以上系统通过WSL2安装Linux版使用，原Windows版本已停止维护；Linux版本（如Centos 7、Linux Mint 19）安装最为直接；Mac版本可能需要XQuartz，且需注意解决潜在的python bug或参考官方mailing list的修复指引。

---

## 4. Coot与WinCoot下载地址

Mac和Linux用户可通过官方链接下载Coot，Windows用户需下载WinCoot；Mac版本也可通过MacPort或Home Brew安装，或随CCP4软件包一起安装。

---

## 5. 在线查看电子密度图的操作

在PDB网站查看结构时，若不安装软件，可直接使用网页工具显示电子密度图。点击右上角显示density，有色density对应未删除原子，灰色density对应被删除/omit的模型，对比二者可判断模型是否被人为修正或删除。

---

## 6. Phenix与Coot联用准备文件

从PDB下载结构的pdb文件和mtz文件（若PDB未直接提供mtz，需下载structure factor cif并转换为mtz）。复制一个新的pdb文件用于后续操作，在新文件中删去待检测的目标分子/配体，保留其余部分。

---

## 7. Phenix生成Omit Map的步骤

在Phenix中设置working directory，选择Phenix.refine工具，输入已删除目标分子的pdb文件和原始mtz文件。运行一次refinement，系统会自动生成计算所需的相关文件和地图。

---

## 8. Coot加载文件与显示设置

在Coot中通过File - Open coordinates加载删除了目标分子的pdb文件，通过File - Auto open MTZ加载Phenix生成的mtz文件。在Display区域可查看2D切片图，Display Options中设置Map contour level数值，通常绿色2fo-fc map设为1 rmsd，红色/蓝色fo-fc map设为3 rmsd。

---

## 9. 依据电子密度图判断结构可靠性

若目标分子位置存在明显的绿色(2fo-fc)密度，且无明显的红色/蓝色(fo-fc)差异密度（或差异密度较小），则说明该分子在电子密度图中拟合良好，结构可信。若需更严谨的验证，可降低fo-fc map的等高面数值（如2 rmsd）进行观察。

---

## 10. Omit Map方法的局限性

简单的删除-重算方法属于快速验证形式，并非最严谨的正式Omit Map。最严谨的Omit Map需使用专门工具（如Phenix中的相关功能）进行计算，以完全消除模型偏差。

---

## 11. PDB结构质量的其他评估指标

除电子密度图外，判断PDB结构质量还应查看Validation Report，关注分辨率高低、R-free值是否在同等分辨率结构的正常范围内、B-factor是否在平均B-factor的合理区间等指标。

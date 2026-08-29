---
key: t18916
title: ʹ��MolAICal���������������������vinardo��ֺ���
url: http://bbs.keinsci.com/thread-18916-1-1.html
domain: 其他量化软件
source: keinsci
year: 2020
cards: 7
---

# ʹ��MolAICal���������������������vinardo��ֺ��� — 知识卡片

## 1. MolAICal 资源与相关文献

MolAICal 提供了官方主页、中文教程、博客spot以及介绍其新功能的文献链接。Vinardo 评分函数是基于 Autodock Vina 修改并重新训练得到的一种打分方式。关于 Vinardo 评分函数的详细介绍，可以阅读指定的文献。相关资源网址包括 https://molaical.github.io、https://molaical.github.io/cntutorial.html、https://qblab.blogspot.com 和 https://doi.org/10.1093/bib/bbaa161。

---

## 2. MolAICal 教程示例文件下载

MolAICal 的教程示例文件托管在 GitHub 上。本次关于 Vinardo 评分函数的教程文件路径为 https://github.com/MolAICal/tutorials/tree/master/008-vinardoScore。

---

## 3. 准备对接盒子参数文件

在计算 Vinardo 评分之前，需要准备一个名为 boxPar.dat 的文资料件。该文件第一行包含盒子中心的三个坐标，第二行包含盒子在三个维度上的长度。示例内容中中心坐标为 -10.733 12.416 68.829，盒子边长均为 30.0。

---

## 4. 生成 Vinardo 评分网格文件

执行命令 `molaical.exe -tool grid -i boxPar.dat -p mproNolig.pdb -n vinardoScore` 可以生成计算所需的网格文件。输入参数中，boxPar.dat 定义了盒子参数，mproNolig.pdb 是受体 Mpro 的结构文件。该命令将生成的网格文件命名为 vinardoScore.dat。

---

## 5. 计算单个配体的 Vinardo 评分

执行命令 `molaical.exe -tool vinardo -i ligands/lig_1.mol2 -g vinardoScore.dat -t vinardoscore` 可计算单个配体的 Vinardo 评分。该命令读取 ligands/lig_1.mol2 文件和 vinardoScore.dat 网格文件。计算结果将输出该配体的打分值，例如 -6.21 kcal/mol。

---

## 6. 生成配体文件列表

在 Linux 终端下执行 `ls > ligandList.dat` 或在 Windows DOS 下执行 `dir /b > ligandList.dat` 可以生成包含配体文件名的列表文件。生成的 ligandList.dat 文件需要清理，删除除文件名以外的多余字符，确保文件中仅包含配体文件名称。

---

## 7. 批量计算配体的 Vinardo 评分

执行命令 `molaical.exe -score vinardo -i ligands/ligandList.dat -o output.dat -g vinardoScore.dat` 可以对多个配体进行批量评分。该命令读取 ligandList.dat 中的配体列表和 vinardoScore.dat 网格文件。计算结果将汇总输出到名为 output.dat 的文件中，文件包含所有配体的打分数值。

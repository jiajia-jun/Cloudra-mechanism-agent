---
key: t26132
title: ʹ��MolAICal��Pafnucyģ�Ͷ�ҩ���׺�������Ԥ��
url: http://bbs.keinsci.com/thread-26132-1-1.html
domain: 其他量化软件
source: keinsci
year: 2021
cards: 14
---

# ʹ��MolAICal��Pafnucyģ�Ͷ�ҩ���׺�������Ԥ�� — 知识卡片

## 1. MolAICal 简介

MolAICal 是一款药物设计软件，集成了 Pafnucy 模型用于预测蛋白质-配体结合亲和力。该软件内置的深度学习模型能够对药物结合亲和力进行预测，方法相对稳定。相关详细信息可参考发表在 *Bioinformatics* (2020) 的文献 (doi: 10.1093/bib/bbaa161)。

---

## 2. Pafnucy 模型安装环境要求

Pafnucy 模型的安装目前仅支持 Linux 系统。用户需在该环境下下载模型压缩包并进行解压和配置。

---

## 3. Pafnucy 模型下载与放置

Pafnucy 模型文件需从指定链接下载 `pafnucy.tar.gz`，并将其移动至 MolAICal 安装目录下的 `mtools` 文件夹中。解压该压缩包后，会得到一个名为 `pafnucy` 的目录。

---

## 4. Pafnucy 模型安装命令

进入解压后的 `pafnucy` 目录，需要依次执行赋予安装脚本执行权限和运行脚本的命令来完成安装。命令如下：
```bash
chmod +x install.sh
./install.sh
```

---

## 5. 结合位点盒子坐标与尺寸生成

MolAICal 可利用中心点坐标和盒子边长生成结合位点盒子文件。生成命令需要使用双引号包裹参数，且数值间需用空格分隔：
```bash
molaical.exe -tool box -i "5.081 12.632 43.498" -l "20.0 20.0 20.0" -o box.bild
```
生成的 `box.bild` 文件包含盒子的空间范围信息，如最小和最大坐标值。

---

## 6. 使用 VMD 提取口袋区域蛋白

利用 VMD 的 Tk 控制台，可以根据生成的盒子坐标范围提取蛋白质口袋区域。使用 `atomselect` 命令定义选择范围，并将选中的原子写入新的 PDB 文件：
```tcl
set box [atomselect top "protein and (not ((x < -4.919 or x > 15.081) or (y < 2.6319999999999997 or y > 22.631999999999998) or (z < 33.498 or z > 53.498)))"]
$box writepdb box.pdb
```

---

## 7. 口腔蛋白文件格式转换

提取出的 `box.pdb` 文件通常需要使用 UCSF Chimera 转换为 Mol2 格式（例如 `3ui7_pocket.mol2`），以便后续用于结合亲和力预测。

---

## 8. 单个配体结合亲和力预测命令

在终端中使用指定命令可预测单个配体与口袋蛋白的结合亲和力。输出结果文件 `results.csv` 中包含预测的 pKx 值：
```bash
molaical.exe -model pafnucy -l 3ui7_ligand.mol2 -p 3ui7_pocket.mol2 -o results.csv
```

---

## 9. 输入文件格式转换

若输入文件为 PDB 格式，需使用 MolAICal 的格式转换工具将其转换为 Mol2 格式后方可进行计算。格式转换命令如下：
```bash
molaical.exe -tool format -i ligand.pdb -o ligand.mol2
```
转换时应注意正确指定配体的结合位点坐标，否则软件可能无法自动识别。

---

## 10. 批量配体预测列表生成

进行批量配体预测时，可使用 `ls` 命令将当前目录下所有 Mol2 格式的配体文件名输出到 `list.txt` 文件中：
```bash
ls lig*.mol2 > list.txt
```

---

## 11. 批量配体预测脚本执行

通过编写并运行 Shell 脚本（如 `run.sh`），可以遍历列表文件中的配体进行批量预测。脚本执行完成后，可使用 `cat` 命令将所有生成的 CSV 结果合并：
```bash
bash run.sh
cat *.csv > results.csv
```

---

## 12. 多配体并行预测

对于少量配体，可以在命令行中使用双引号将多个配体文件名作为参数一次性输入，实现基于同一受体的结合亲和力批量预测：
```bash
molaical.exe -model pafnucy -l "lig_1.mol2 lig_2.mol2" -p receptor.mol2 -o twoTest.csv
```
注意文件名之间应以空格分隔。

---

## 13. pKx 值与结合自由能转换

MolAICal 预测输出的结果为 pKx 值。若研究者需要结合自由能数据，可参考 MolAICal 官方教程页面提供的转换模块进行数值转换。

---

## 14. Pafnucy 模型参考文献

Pafnucy 模型的开发与验证相关文献为：Stepniewska-Dziubinska MM, Zielenkiewicz P, Siedlecki P. Development and evaluation of a deep learning model for protein-ligand binding affinity prediction. *Bioinformatics*. 2018;34(21):3666-74.

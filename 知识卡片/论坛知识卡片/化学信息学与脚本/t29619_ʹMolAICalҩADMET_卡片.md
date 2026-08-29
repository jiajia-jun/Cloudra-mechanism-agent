---
key: t29619
title: ʹ��MolAICal����ҩ��ADMET��Ԥ��ͷ������Եļ���
url: http://bbs.keinsci.com/thread-29619-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2022
cards: 12
---

# ʹ��MolAICal����ҩ��ADMET��Ԥ��ͷ������Եļ��� — 知识卡片

## 1. MolAICal 软件简介与资源

MolAICal 是一款用于药物研发的集成软件，支持基于结构的药物设计以及 ADMET 性质预测。该软件提供了 Linux 和 Windows 版本，官方主页与中文镜像页分别托管于 GitHub 和 Gitee。相关教程、演示视频以及学术文献资料可在其官方社区或 arXiv、Bioinformatics 等平台获取。
- 官方主页: https://molaical.github.io
- 中文镜像: https://molaical.gitee.io
- 论文链接: https://doi.org/10.1093/bib/bbaa161

---

## 2. 药物 ADMET 预测的重要性

在临床前阶段，约 40% 的候选药物因 ADMET（吸收、分布、代谢、排泄和毒性）问题而研发失败。由于体内实验成本高昂且涉及伦理问题，利用计算机辅助方法在早期阶段预测 ADMET 性质对药物筛选至关重要。
- MolAICal 集成了 FP-ADMET 模型用于此类预测。

---

## 3. FP-ADMET 模型安装准备

Part I 教程中的 FP-ADMET 功能目前仅支持 Linux 版本的 MolAICal。安装前需从指定链接下载模型压缩包，并将其放置于 MolAICal 安装目录下的 `mtools` 文件夹中。
- 模型下载路径: DownloadModel -> AImodels -> ADMET -> FPADMET -> linux64 -> fpadmet.tar.gz

---

## 4. FP-ADMET 模型安装步骤

下载并移动 `fpadmet.tar.gz` 到指定目录后，需在终端执行解压与安装脚本。进入目录后，首先赋予安装脚本执行权限，随后运行安装脚本即可完成部署。
- 解压命令: `tar -xzvf fpadmet.tar.gz`
- 进入目录: `cd fpadmet`
- 赋予权限: `chmod +x install.sh`
- 运行安装: `./install.sh`

---

## 5. MolAICal 输入文件格式要求

使用 MolAICal 进行 ADMET 预测时，输入文件需为文本格式（如 `.smi`），每行包含一个分子的 SMILES 字符串和分子名称。SMILES 字符串与分子名称之间必须由一个或多个空格分隔。
- 示例格式: `[SMILES字符串] [分子名称]`

---

## 6. 批量预测分子 ADMET 属性的命令

使用 FP-ADMET 模型对输入文件中的所有分子进行全属性预测，需使用 `molaical.exe` 命令并指定 `fpadmet` 模型。参数 `-s all` 表示预测所有指标，`-i` 指定输入文件，`-o` 指定输出结果文件。
- 命令示例: `molaical.exe -model fpadmet -s all -i mols.smi -o results.dat`

---

## 7. ADMET 预测结果解读（分类任务）

对于分类预测任务（如血脑屏障渗透性），结果文件会输出预测标签、置信度和可信度。置信度接近 1 表示预测非常确定，而较低的可信度（如 0.32）提示模型在训练集中缺乏足够的类似数据支持，用户应谨慎对待该预测结果。
- 输出列名: Predicted, Confidence, Credibility

---

## 8. ADMET 预测结果解读（回归任务）

对于回归预测任务（如 pKa 解离常数），结果文件会输出预测值以及 95% 的预测区间（quantile_0.025 和 quantile_0.975）。FP-ADMET 的原始文献指出其预测区间通常较窄，反映了预测的不确定性相对较低。
- 输出列名: Predicted, quantile_0.025, quantile_0.975

---

## 9. 预测指定 ADMET 指标的命令

若仅需预测输入文件中特定序号对应的 ADMET 指标，可使用 `-s single` 参数配合 `-n` 参数。`-n` 后接数字代表 ADMET 指标在列表中的序号，结果将生成以该序号命名的独立文件（如 `1.dat`）。
- 命令示例: `molaical.exe -model fpadmet -s single -i mols.smi -n 1`
- 输出文件示例: `1.dat`

---

## 10. MolAICal ADMEPro 模型预测药物分子基本信息

使用 `admepro` 模型配合参数 `-s 0`，可以直接输入 SMILES 字符串来预测药物分子的基本信息。此功能适用于快速获取单个分子的基本属性。
- 命令示例: `molaical.exe -model admepro -s 0 -i "O=C(C)Oc1ccccc1C(=O)O"`

---

## 11. MolAICal ADMEPro 模型预测药代动力学信息

设置参数 `-s 1` 可使用 `admepro` 模型预测药物分子的药代动力学（PK）信息及相关规则。输出内容通常包含胃肠道吸收、血脑屏障渗透性以及 Lipinski 五规则违规情况等。
- 命令示例: `molaical.exe -model admepro -s 1 -i "O=C(C)Oc1ccccc1C(=O)O"`
- 输出示例: GI absorption, BBB permeant, Lipinski Rule of 5 Violations

---

## 12. MolAICal ADMEPro 模型预测药物化学信息

设置参数 `-s 2` 可使用 `admepro` 模型预测与药物化学性质相关的信息，如 PAINS 过滤器和 Brenk 过滤器结果。这些信息有助于评估分子的潜在干扰或结构性问题。
- 命令示例: `molaical.exe -model admepro -s 2 -i "O=C(C)Oc1ccccc1C(=O)O"`
- 输出示例: PAINS filter, Brenk filter

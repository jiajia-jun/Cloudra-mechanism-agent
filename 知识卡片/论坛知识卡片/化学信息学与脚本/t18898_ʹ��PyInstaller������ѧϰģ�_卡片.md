---
key: t18898
title: ʹ��PyInstaller������ѧϰģ�͡�AIGenMols��������
url: http://bbs.keinsci.com/thread-18898-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 12
---

# ʹ��PyInstaller������ѧϰģ�͡�AIGenMols�������� — 知识卡片

## 1. MolAICal 官方资源链接

MolAICal 的官方主页、论文介绍、中文教程以及博客资源可通过特定网址访问。官方主页为 https://molaical.github.io。相关论文发表于 DOI: 10.1093/bib/bbaa161。中文教程位于 https://molaical.github.io/cntutorial.html，博客位于 https://qblab.blogspot.com。

---

## 2. 使用 ORGAN 生成可执行文件

药物化学学习模型在使用时需要以开源形式运行，需要将其封装成独立可执行文件。本教程选用 ORGAN 作为源码来生成名为 AIGenMols 的独立可执行程序。使用者可根据本教程处理自己训练的化学学习模型以进行替换。

---

## 3. 环境准备与工具下载

进行操作前需要下载 MolAICal 和 Anaconda。MolAICal 可在 https://molaical.github.io 下载。Anaconda 可在 https://www.anaconda.com/open-source 下载，且应选择 Python 3.x 版本。示例教程文件可从 https://github.com/MolAICal/specialtopic/tree/master/012-AIGenMols 获取。

---

## 4. Anaconda 安装注意事项

安装 Anaconda 时应确保进行完全安装并勾选添加到环境变量。安装路径中不应包含空格，例如路径 /home/test install/anaconda 中的空格可能导致 AIGenMols 生成失败。

---

## 5. 创建 Conda 虚拟环境

使用 spec-list.txt 文件可以创建名为 AIGen 的 Conda 虚拟环境。创建命令为 `conda create --name AIGen --file spec-list.txt`。创建完成后需使用命令 `conda activate AIGen` 激活环境。

---

## 6. 处理 Conda 安装依赖包错误

若执行安装时出现 CondaHTTPError: HTTP 404 NOT FOUND 错误，需在 spec-list.txt 中删除对应出错的包名。随后重复创建环境步骤，或单独使用 `conda install -c conda-forge xxxx` 安装缺失或指定版本的包。

---

## 7. 安装额外依赖项

环境激活后需安装特定依赖库 openblas 和 openssl，命令分别为 `conda install -c conda-forge openblas` 和 `conda install -c conda-forge openssl`。此外还需通过 pip 安装特定版本的 editdistance：`pip install editdistance==0.3.1`。

---

## 8. 使用 PyInstaller 生成可执行文件

解压 organ.zip 并进入目录后，需使用 PyInstaller 命令打包 main.py。命令包含多个 --add-data 参数以指定数据文件和检查点文件的路径，例如 `--add-data="organ/NP_score.pkl.gz:organ"`。完整命令需包含所有相关的数据文件和模型检查点文件（如 FDA-H, FDA1884, ZINC 相关文件）。

---

## 9. 可执行文件重命名与权限设置

生成的文件位于 organ/dist 目录下。需将生成的 main 文件重命名为 AIGenMols，并使用命令 `chmod +x AIGenMols` 赋予其可执行权限。

---

## 10. 可执行文件的部署

生成的 AIGenMols 即为封装好的独立药物化学学习模型。该文件可直接复制或移动到 MolAICal 的程序目录中即可使用。若使用自定义训练的模型，需替换 PyInstaller 命令中对应的关键部分。

---

## 11. AIGenMols 运行参数示例

AIGenMols 的使用需通过命令行参数指定，参数包括 -f, -s, -n。生成 100 个分子的命令示例为 `AIGenMols -f test.txt -s FDAFrag -n 100` 或 `AIGenMols -f test.txt -s ZINCMol -n 100`。

---

## 12. AIGenMols 命令行参数含义

参数 -f 指定包含待生成分子 SMILES 格式种子的文件。参数 -s 指定所使用的药物化学学习模型名称，例如 ZINCMol 表示使用 ZINC 数据库训练的生成模型。参数 -n 指定需要生成的分子数量。

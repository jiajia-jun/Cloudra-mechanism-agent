---
key: t53463
title: SmilesFakeG�����������chemdraw����Gaussian�����ļ�
url: http://bbs.keinsci.com/thread-53463-1-1.html
domain: Gaussian使用
source: keinsci
year: 2025
cards: 7
---

# SmilesFakeG�����������chemdraw����Gaussian�����ļ� — 知识卡片

## 1. SmilesFakeG 运行模式与输出文件

SmilesFakeG 运行时会自动检测当前目录下是否存在输入文件或 .smi 文件，若未找到则自动切换至终端输入模式。优化模式默认设定为固定步数（Fixed steps）4000步。所有优化过程产生的数据帧将写入日志文件 SmilesFakeG.log 中，该日志文件可被 GaussView 直接读取。

---

## 2. SMILES 字符串的输入方式

用户可在终端中直接输入或粘贴 SMILES 字符串，多个结构之间可以用句点或换行符进行分隔。输入完成后需通过两次回车键（提交一个空行）来结束输入并开始执行程序。这种方式允许批量处理多个分子结构。

---

## 3. ChemDraw 与 SMILES 字符串的批量获取

通过在 ChemDraw 中选中多个结构式并使用快捷键 Ctrl+Alt+C，可以复制出由句点分隔的 SMILES 字符串。该内容可以直接粘贴至 SmilesFakeG 程序的终端界面中，从而实现一键全选并批量获取目标分子的 SMILES。

---

## 4. SmilesFakeG.log 的后处理功能

生成的 SmilesFakeG.log 文件记录了优化的全过程帧，可直接用 GaussView 打开查看每一帧。在 GaussView 中不仅可以对结构进行修改和构建实际工作，还可以直接将保存后的文件另存为 Gaussian 的输入文件。

---

## 5. -conv 参数的功能

使用 -conv 参数可以切换程序的计算模式，使其直接进行格式转换而不执行优化任务。此模式下程序能够处理自定义的目标，专注于格式的转换输出。

---

## 6. 依赖环境与算法更新

运行相关脚本需要预先安装 OpenBabel 和 RDKit 库。2025年7月17日的更新版本增加了逻辑，当 MMFF94 力场优化计算失败时，程序会自动回退（fallback）使用 UFF 力场进行计算。

---

## 7. 脚件信息

相关功能的实现包含在名为 smiles_to_gaussian.py 的 Python 脚本中，该脚本提供了批量处理 SMILES 并生成 Gaussian 输入文件或执行优化的功能。

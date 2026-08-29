---
key: t18917
title: ʹ��MolAICal�������������ԱȽϻ������Ĳ����̳�
url: http://bbs.keinsci.com/thread-18917-1-1.html
domain: 其他量化软件
source: keinsci
year: 2020
cards: 10
---

# ʹ��MolAICal�������������ԱȽϻ������Ĳ����̳� — 知识卡片

## 1. MolAICal 官方资源

MolAICal 提供了官方网站、中文教程、Blogspot 及文献介绍等资源。官方主页地址为 https://molaical.github.io。中文教程可通过 https://molaical.github.io/cntutorial.html 访问。相关文献发表在 https://doi.org/10.1093/bib/bbaa161。

---

## 2. MolAICal 相似性搜索应用场景

某些特定骨架片段的衍生物通常具有较好的生物活性，方便化学家寻找潜在的活性化合物。该教程介绍了基于分子指纹和 3D 结构相似性的比较方法。该教程适用于基于分子指纹的相似性比较，或基于骨架结构相似性的文件筛选。

---

## 3. MolAICal 教程示例文件下载

相似性搜索教程所需的示例文件可从指定网址下载。下载地址为 https://github.com/MolAICal/tutorials/tree/master/011-similaritySearch。该文件包含了用于后续操作步骤的输入文件。

---

## 4. 生成分子指纹比较的输入文件列表

在 Linux 终端使用 `ls > listfiles.dat` 命令，或在 Windows 系统 DOS 终端使用 `dir /b > listfiles.dat` 命令。需检查生成的 `listfiles.dat` 文件并删除其中的非文件名内容。确保 `listfiles.dat` 文件中仅包含需要处理的文件名称。

---

## 5. 运行分子指纹比较命令

进入 `011-similaritySearch/fingerprint` 文件目录后，执行命令 `molaical.exe -tool finger -i listfiles.dat -o result.dat`。计算结果将保存在 `result.dat` 文件中。输出文件中的结构预测数据按照 `listfiles.dat` 中的文件顺序对应排列。注意 `result.dat` 文件中以 `#` 开头的行是注释行，第一行是被比较的模板。

---

## 6. 生成 3D 结构相似性比较的输入文件列表

在 `011-similaritySearch/3Dsimilarity` 目录下，使用 `ls > listfiles.dat` (Linux) 或 `dir /b > listfiles.dat` (Windows) 生成文件列表。需清理生成的 `listfiles.dat` 文件，确保其中仅保留待处理的文件名称。该步骤用于准备 3D 结构相似性计算的输入。

---

## 7. 运行 3D 结构相似性批量比较命令

在 `011-similaritySearch/3Dsimilarity` 目录下执行命令 `molaical.exe -tool 3Dcompare -i listfiles.dat -s result.dat -f mol2list`。结果将保存在 `result.dat` 文件中。输出文件中的结构预测数据对应于 `listfiles.dat` 中除去第一行之后的文件顺序。注意 `result.dat` 的第一行是被比较的模板，后续行分别对应 `listfiles.dat` 中的文件。

---

## 8. 单对 3D 结构相似性比较

MolAICal 支持直接比较两个分子的 3D 结构相似性。用于比较单个配体与输出文件中特定分子结构的命令示例为 `molaical.exe -tool 3Dcompare -i ligand.mol2 -s 1_10023_out.mol2`。

---

## 9. Linux 系统下合并并排序结果

在 Linux 系统下，需删除 `listfiles.dat` 中的第一行，然后执行命令 `molaical.exe -tool col -f listfiles.dat -l result.dat -s " " -o merge.dat` 合并文件。随后执行 `sort -n -t ' ' -k 2r merge.dat > rank.dat` 对结果进行排序。最终生成的 `rank.dat` 文件包含排序后的结果。

---

## 10. Windows 系统下合并并排序结果

在 Windows 系统下，需删除 `listfiles.dat` 中的第一行。将 `result.dat` 中的数据复制到 Excel 第一列，将 `listfiles.dat` 中的数据复制到第二列。选中两列数据后，使用 Excel 的 "Sort Largest to Smallest" 功能进行排序。

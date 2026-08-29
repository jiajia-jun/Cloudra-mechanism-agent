---
id: 472
title: 将多帧xyz文件转化成量子化学输入文件的工具：xyz2QC
url: http://sobereva.com/472
domain: 化学信息学与脚本
topic: xyz2QC多帧转Gaussian与ORCA输入
cards: 8
---
## 1. xyz2QC程序的功能与定位

xyz2QC是作为Molclus程序（1.7版及之后）的一个子程序发布的免费工具，旨在解决在超算上不便自动调用程序的问题。该程序能够基于Gaussian和ORCA的模板文件，将含有多帧的.xyz文件中指定的一批帧转化成Gaussian和ORCA输入文件。转化出的输入文件既可以是所有被选择的结构作为多步任务出现在同一个输入文件里，也可以拆分成一个个独立的文件。
- 官网介绍：http://www.keinsci.com/research/molclus.html

---

## 2. xyz2QC模板文件的命名要求

xyz2QC要求模板文件的格式必须与molclus的完全一致，Gaussian的模板文件必须命名为template.gjf，ORCA的模板文件必须命名为template.inp。在运行xyz2QC之前，必须将相应的模板文件放置在当前目录下。

---

## 3. xyz2QC支持的输入文件来源

xyz2QC读取的多帧.xyz文件来源广泛，可以是genmer、gentor直接产生的文件，也可以是molclus运行完毕后产生的isomers.xyz，或者是isostat筛选、排序、归簇后产生的cluster.xyz。这保证了程序能够适配构象搜索和团簇构型搜索工作流中的不同环节。

---

## 4. 生成多步Gaussian输入文件的操作示例

将cluster.xyz、template.gjf放入xyz2QC目录后，启动程序并依次输入：1（选择产生含多步的单一Gaussian输入文件）、cluster.xyz（输入文件路径）、1-3（选择第1~3帧）。程序将生成Gaussian.gjf文件，其中包含通过--link1--分隔的三个计算任务，执行该文件即可挨个算出所有结构的能量。
- 模板示例内容：
%nproc=4
 # M062X/TZVP

Template file

0 1
 [GEOMETRY]
 <---此处有空行
 <---此处有空行

---

## 5. Gaussian多步任务中link1的空行规则

在生成的Gaussian.gjf文件中，--link1--用于分隔多步任务，其前头的空行数目必须正确，否则多步任务将运行不成功。xyz2QC生成的文件中--link1--前面的空行数目取决于template.gjf模板文件末尾的空行数，因此用户需确保模板文件末尾的空行数符合要求。

---

## 6. 拆分独立Gaussian输入文件的应用场景

虽然将多个结构合并在一个.gjf文件里运行最方便，但缺点是如果其中一个任务（如SCF不收敛、几何优化不收敛）失败，整个任务就会停止。将结构拆分成单独的.gjf文件（如000001.gjf、000002.gjf...）可以避免这个问题，各个任务独立运行，互不干扰。

---

## 7. Gaussian模板文件中的[FILENAME]占位符

Gaussian模板文件中可以使用[FILENAME]占位符，xyz2QC在产生输入文件时会将其替换为“前缀 帧号”。这允许用户在模板中写入如%chk=/sob/[FILENAME].chk，使得计算完毕后chk文件能以恰当的名字保存在指定目录（如/sob），便于通过Multiwfn程序批量做波函数分析。
- 批量操作参考：《使用Gaussian时的几个实用脚本和命令》http://原作者.com/258

## 8. ORCA多步任务模板的注意事项

使用xyz2QC产生ORCA的多步任务输入文件时，强烈建议在模板文件template.inp里加入noautostart关键词。如果不加入此关键词，下一个任务的初猜会自动用前一个任务收敛的波函数，由于选定的结构几何差异可能不小，这样得到的初猜可能会很糟糕。加入noautostart可以确保不自动读取初猜波函数。

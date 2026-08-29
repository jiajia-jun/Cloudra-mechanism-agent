---
id: 345
title: 各种Sadlej基组的Gaussian格式的定义
url: http://sobereva.com/345
domain: Gaussian使用
topic: Sadlej极化基组定义及使用
cards: 13
---
## 1. Sadlej基组的适用性

Sadlej基组是专用于计算电场响应性质的基组，包括偶极矩、极化率、超极化率。这类基组在计算此类问题上比普适的Dunning系列基组更具成本效益。

---

## 2. Gaussian格式Sadlej基组文件获取

Gaussian格式的各种Sadlej基组定义文件已通过程序转换提供，下载压缩包内包含.gbs文件。该文件可用文本编辑器打开，且已排除专用于相对论计算的版本，仅适用于非相对论计算。

---

## 3. Gaussian中引用自定义基组文件

在Gaussian输入文件中，使用gen关键词配合@符号可引用外部.gbs基组文件，程序会自动从中提取当前计算所需元素信息。例如输入 #p B3LYP/gen 后，在分子结构下方写入 @C:\POL.gbs 即可调用。

---

## 4. 基组转换的准确性与重复定义说明

转换过程虽经程序处理，但因涉及众多基组和元素，无法保证100%无错误。此外，针对原子不同组态，部分元素在.gbs文件中被定义了两遍，用户需参考基组源文件中的注释加以区分。

---

## 5. Sadlej基组的定义来源

提供的基组定义源自两个网页：http://www.qch.fns.uniba.sk/Baslib/ 提供 POL、HYPOL、POL_F 完整定义及 Z2POL、Z3POL 部分定义；http://www.chem.uni.torun.pl/zchk/basis-sets.html 提供 ZPOL 过渡金属定义及完整 LPOL 定义。

---

## 6. Sadlej POL基组特征与性能

Sadlej POL基组（也称Sadlej pVTZ）大小与cc-pVTZ相近，但第二、三周期原子不含f函数却增加了弥散函数。该基组参数基于静态极化率优化，适用于TDDFT及外场性质计算，性能与昂贵的aug-cc-pVTZ相仿。

---

## 7. Sadlej POL基组在Gaussian中的计算效率

EMSL提供的Sadlej pVTZ基组与该资料提供的POL基组不完全相同，前者为片段收缩，后者为广义收缩。在Gaussian等基于片段收缩的程序中，使用广义收缩基组（该资料提供版本）计算速度会显著变慢。

## 8. Sadlej POL_F基组定义

Sadlej POL_F基组是在POL基组的基础上，对部分元素增加了f极化函数，而POL原先的参数保持不变。

---

## 9. Sadlej HYPOL基组定义

Sadlej HYPOL基组提出于1998年，是专门用于计算超极化率的基组。该基组基于Sadlej POL基组，通过去收缩并增加轨道指数相同、角量子数更高一阶的基函数构建而成。

---

## 10. Sadlej ZPOL与Z2POL基组定义

Sadlej ZPOL基组（Z3POL）提出于2004年，是对POL基组的简化，适合大体系偶极矩和极化率计算。Z2POL则是Z3POL的变体，减少了收缩极化函数中的primitive shell数。

---

## 11. Sadlej LPOL基组定义与适用范围

Sadlej LPOL基组提出于2009年，具有很高的广义收缩程度，若在Gaussian中使用会很慢。该基组规模大于POL，适合中、小体系的极化率和第一、第二超极化率计算，目前仅对C、H、O、N、F元素有定义。

---

## 12. Sadlej LPOL基组的大小分类

Sadlej LPOL基组具体分为fl、fs、dl、ds四种类型。l代表large，s代表small（减少极化函数并调整收缩方式以降低耗时）；f、d代表重原子的最高角动量极化函数。四种类型的大小关系为：ds < dl < fs < fl。

---

## 13. Sadlej+基组的定义与改进

Sadlej+基组并非Sadlej课题组提出，而是Casida等人在JCP,108,4439中为计算里德堡激发态，在Sadlej POL基础上增加弥散函数的结果。该基组仅定义了C、H、O、N，对s增加两层弥散函数，对p、d增加一层弥散函数（H除外），计算超极化率应比POL有显著改进。

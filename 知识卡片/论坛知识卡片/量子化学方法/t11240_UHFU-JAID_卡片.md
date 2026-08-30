---
key: t11240
title: ��UHF�������U-J������AIDFT+U
url: http://bbs.keinsci.com/thread-11240-1-1.html
domain: 量子化学方法
source: keinsci
year: 2018
cards: 11
---

# ��UHF�������U-J������AIDFT+U — 知识卡片

## 1. LDA+U 与 GGA+U 的 U 和 J 参数确定方法

LDA+U 和 GGA+U 计算依赖于强关联体系中 U 和 J 参数的有效确定。Mosey 和 Carter 于 2007 年提出基于 UHF 方程自动求解 U 和 J 参数的自洽方法。该方法通过顺次求解 U 和 J 来实现参数确定。

---

## 2. AIDFT-U 项目与代码资源

AIDFT-U 项目及相关代码（也称为 GAMESS-UJ）用于自动确定 DFT-U 计算中的 U 和 J 参数。相关代码和说明文档可在 https://github.com/EACcodes/AIDFT-U/ 获取。

---

## 3. AIDFT-U 兼容的 GAMESS 版本

AIDFT-U 最早基于 GAMESS 2006-Feb(R5) 版本开发，推荐使用补丁版本的 GAMESS 2009-May(R3)。2010 年及以后的 GAMESS 版本对 scflib.src 文件中的 UHF 结构进行了全面修改，导致应用补丁较为困难。

---

## 4. 针对 2010 年后 GAMESS 版本的修改方案

对于 2010 年之后的 GAMESS 版本，需将修改前的 AIDFT-U 对象代码文件 OrbsAA 中的参数直接写入 GAMESS 输入文件。需复制的修改部分包括以 `C<<<CMOSEY` 开始、以 `C>>>` 结束的代码块，且应位于输入文件的结构数据之后。

---

## 5. 获取与安装补丁的步骤

首先从相关论坛链接下载 GAMESS 2009-May(R3) 源代码及对应版本的 AIDFT-U 源代码（或修改后的 GAMESS 源代码）。随后将解压并修改后的 GAMESS 源代码文件覆盖至 gamess/source/ 目录下，最后重新编译 GAMESS。

---

## 6. 输入文件中 $OrbsAA 的关键参数设置

AIDFT-U 的关键参数通过 GAMESS 输入文件中的 namelist $OrbsAA 指定。主要包括 IDFrst、IDLast 和 PopThr，这些参数对应原 OrbsAA 文件中的同名变量，分别指定特定原子的 d 轨道起始序号、终止序号以及轨道布居阈值。

---

## 7. 参数 IDFrst 与 IDLast 的定义

IDFrst 和 IDLast 用于指定需要进行 U 和 J 拟合的原子及其 d 轨道范围。这两个参数分别代表起始和终止的轨道编号，对应于目标原子集合。

---

## 8. 参数 PopThr 的作用与推荐值

PopThr 是轨道布居阈值，用于筛选参与计算的轨道；若不设置则默认为 0。对于较大的模型体系，建议将 PopThr 设置为 5.0e-3，以节省计算时间。

---

## 9. 结果提取与计算执行

运行计算后，在输出文件末尾可以找到 U 和 J 的拟合结果，这些结果可用于随后的 LDA+U 计算。

---

## 10. AIDFT-U 的元素支持范围

AIDFT-U 目前仅支持包含 d 轨道的元素。尚不支持 p 区元素和 f 区元素。

---

## 11. ENERGY COMPONENTS 输出信息的限制

输出结果中的 ENERGY COMPONENTS 部分显示的能量数值可能不准确，不应直接使用。这是该程序的一个已知输出显示问题。

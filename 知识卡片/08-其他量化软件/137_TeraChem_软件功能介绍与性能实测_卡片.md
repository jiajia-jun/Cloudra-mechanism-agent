---
id: 137
title: 首个完全基于GPU的量化软件-TeraChem杂谈及真实性能测试
url: http://sobereva.com/137
domain: 其他量化软件
topic: TeraChem_软件功能介绍与性能实测
cards: 16
---

# TeraChem_软件功能介绍与性能实测 — 知识卡片

## 1. TeraChem软件简介

TeraChem是第一个完全基于GPU运算的从头算量化程序，于2010年5月发布第一版，由Todd Martinez和Ufimtsev基于CUDA开发。其算法基础是发表在JCTC上的三篇文章（JCTC,4,222、JCTC,5,1004、JCTC,5,2619），分别阐述了利用GPU进行双电子积分、直接SCF、解析梯度的实现方法。与其他在CPU代码基础上改造的GPU加速程序不同，TeraChem是第一个完全从头编写以充分发挥GPU运算能力的量化程序。

---

## 2. TeraChem软件功能与局限性

TeraChem支持单点能、几何优化、找过渡态、BOMD、偶极矩和极化率计算，支持HF、GGA/杂化DFT及R/U/RO形式，但尚不支持激发态、频率、后HF方法、对称性及隐式溶剂模型等。程序支持Grimme的DFT-D2/D3色散校正并附带NBO6.0，但NBO分析时容易崩溃且部分功能如NBO deletion不可用。其QM/MM功能仅支持TIP3P水作为MM区域，且使用的基函数为高斯型基函数。

---

## 3. TeraChem硬件与系统环境要求

TeraChem要求至少有一个支持CUDA的nVidia GPU方可运行，目前版本（1.5）只有Linux版，建议使用RHEL5.5及以上版本。系统需安装CUDA驱动和CUDA 4.0 Toolkit，程序运行受主机内存大小限制。手册中不推荐使用GTX580和Tesla C2075，且基于新架构Kepler的GTX680等运行可能存在问题。

---

## 4. TeraChem数值精度模式

TeraChem内部默认采用单双精度混合模式，对于数值大小高于阈值的双电子积分以及涉及到数值累加的变量一律用双精度以保证精确度，而数值较小的双电子积分采用单精度。这种混合模式旨在兼顾nVidia Geforce系列GPU双精度性能较弱的特点，在保证精度的同时利用单精度的高速度。

---

## 5. TeraChem安装运行与输入文件

TeraChem只需将环境变量指向license文件即可运行，如export TeraChem=/sob/TeraChem/license.dat，运行命令为./TeraChem [输入文件名]。输入文件编写容易，关键词顺序随意，注释写在#号后，支持xyz和pdb格式。如需NBO分析，需设定环境变量export NBOEXE=/sob/TeraChem/nbo6.exe。

---

## 6. TeraChem输入文件示例

TeraChem的一般计算任务输入文件示例如下，包含基组、电荷、多重度、方法、运行类型和坐标文件：
basis 6-31gss
charge 0
spinmult 1
method wb97x
run minimize
coordinates MN-NN.xyz
end
若需加入DFT-D3色散校正，只需加入dftd d3关键词。

---

## 7. TeraChem图形界面与交互功能

于建国教授等人开发了收费的前端图形界面SimuTera，可构建分子、创建输入文件及提交任务。TeraChem官方推荐使用VMD观看结果，支持Interactive molecular dynamics(IMD)，通过在输入文件中设置imd [端口号]与VMD连接，可实时观察结构变化及动力学过程，未来计划支持交互式施加外力。

---

## 8. TeraChem几何优化与过渡态搜索

TeraChem的几何优化支持L-BFGS、共轭梯度、最陡下降法，但搜索过渡态仅支持NEB方法。NEB方法需要提供过渡态前后两个位置的初猜坐标，虽然能顺便得到能量极小路径，但比常用的基于GDIIS和准牛顿法只需单个初猜坐标的方法更麻烦。

---

## 9. 聚苯分子单点能速度测试结果

测试使用链状聚苯分子（总原子数2+10*N）在B3LYP/6-31G*级别下的计算时间，结果显示TeraChem和G03在N=2至N=14范围内均显示出线性标度特征。两块GTX480相比单卡性能提升显著，且优于两块Tesla C2050，主要得益于TeraChem的混合精度模式利用了GTX480更强的单精度性能。

---

## 10. 显存与GPU流处理器对性能的影响

TeraChem计算大体系时耗显存严重，1.5GB显存的GTX480在计算N=14聚苯时会报错，Tesla产品的优势主要在于更大显存。GPU性能对运算速度影响明显，GTX460M（192个流处理器）的运算速度只有GTX480（480个流处理器）的不到1/3。

---

## 11. TeraChem与Gaussian03速度对比

测试表明，i7-2630QM CPU在Gaussian03下的运算耗时基本上与两块Tesla C2050在TeraChem下的运算速度持平。在咪唑配位镁卟啉的测试中，单块GTX480+TeraChem的耗时仅比i7-2630QM+G03降低三分之一，且GTX460M+TeraChem效率明显不如i7-2630QM+G03。

---

## 12. 不同精度模式的计算速度差异

在8个苯环B3LYP/6-31G*测试中，两块GTX480下纯双精度（205.9s）比纯单精度（54.3s）慢得多，而动态混合单双精度（67.5s）并不比单精度多耗时多少。两块C2050也表现出类似规律，说明默认的动态混合模式在精度和速度上取得了较好的平衡。

---

## 13. TeraChem与Gaussian计算精度对比

对于咪唑配位镁卟啉，TeraChem默认模式结果与Gaussian03 SCF=Tight结果符合很好，且比G03默认标准精度稍高。在DFT计算中，TeraChem默认结果也与G03 Tight收敛标准结果相符。TeraChem默认的动态单双精度混合结果与纯双精度结果差异极小，建议一般计算使用默认精度。

---

## 14. TeraChem官方测试数据辨析

TeraChem官方图表显示GTX480相比GAMESS-US有巨大加速比，但分析发现官方数据仅使用了X5680的一个核心进行对比，且GAMESS-US耗时异常偏长。实测表明，i7-2630QM在Gaussian03中每轮迭代仅花18秒，甚至略快于单GTX480+TeraChem，官方数据缺乏公平性和现实意义。

---

## 15. 2019年补充测试与性价比分析

2019年的补充测试显示，TeraChem v1.93P结合GTX1080Ti计算110原子体系耗时48s，而双路E5 2696v3服务器结合ORCA 4.1.1耗时61s，两者无明显区别。考虑到TeraChem约10000元的授权费和GTX1080Ti约12000元的价格，总计两万多的成本相比性能持平且ORCA免费的CPU服务器方案，性价比没有任何优势。

---

## 16. TeraChem后续功能缺陷

截至2019年3月，TeraChem虽然有所改进，但功能局限性依然极大，不支持d以上角动量基函数，没有解析Hessian，且不支持明尼苏达系列泛函（如M06-2X）。从功能角度看，TeraChem几乎毫无使用价值。

---
id: 137
title: 首个完全基于GPU的量化软件-TeraChem杂谈及真实性能测试
url: http://sobereva.com/137
domain: 其他量化软件
topic: TeraChem_软件功能介绍与性能实测
cards: 1
---

# TeraChem_软件功能介绍与性能实测 — 知识卡片

## 1. TeraChem软件概况与开发背景

TeraChem是2010年5月发布的第一个完全基于GPU运算的从头算量化程序，由Todd Martinez和Ufimtsev基于CUDA开发，算法基础发表于JCTC (JCTC,4,222、JCTC,5,1004、JCTC,5,2619)。该程序要求至少有一个支持CUDA的nVidia显卡，目前属于PetaChem公司产品，购买量价格从315到900刀不等，在中国由坤成基业公司代理。
- 与其他程序不同，TeraChem是完全从头编写以发挥GPU运算能力，而非在原有CPU代码上改造。

## TeraChem支持的理论方法与功能局限性
TeraChem主要支持HF、GGA/杂化DFT（R/U/RO形式），可直接进行单点能、几何优化、找过渡态、BOMD、偶极矩和极化率计算，并直接支持Grimme的DFT-D2/D3和附带NBO6.0。该程序尚不支持激发态计算、频率分析、任何后HF方法、对称性、隐式溶剂模型、NMR、BSSE、赝势及外加电场，且不支持f及以上角动量基函数。
- 虽支持QM/MM，但MM区域只能是TIP3P水，实用意义有限。

## TeraChem的安装环境与运行要求
TeraChem 1.5仅有Linux版，建议使用RHEL5.5及以上版本，需安装CUDA驱动和CUDA 4.0 Toolkit。运行时需通过环境变量指定license文件，例如export TeraChem=/sob/TeraChem/license.dat，执行命令为./TeraChem [输入文件名]，结果输出在scr目录下。
- 若涉及NBO分析，需设置环境变量指向NBO可执行文件，如export NBOEXE=/sob/TeraChem/nbo6.exe。

## TeraChem输入文件格式与关键参数
TeraChem输入文件编写简单，关键词顺序随意，注释写在#号后。例如结构优化任务可写为：basis 6-31gss，charge 0，spinmult 1，method wb97x，run minimize，coordinates MN-NN.xyz，end。
- 如需加DFT-D3色散校正，仅需添加dftd d3一句，支持xyz和pdb格式结构文件。

## TeraChem的交互式分子动力学(IMD)功能
TeraChem支持与VMD结合实现交互式分子动力学(IMD)，在输入文件中设定如imd 54332，TeraChem将等待VMD连接，动力学过程的结构变化会实时传至VMD图形界面。结构优化和过渡态搜索过程也支持此方式观看，未来计划支持在VMD中通过拖动鼠标交互式施加外力。
- TeraChem官方主要推荐用VMD观看生成的结构、动力学轨迹和分子轨道。

## TeraChem的过渡态搜索与几何优化算法
TeraChem的几何优化使用L-BFGS、共轭梯度、最陡下降法等常见算法，但过渡态搜索仅支持NEB方法。NEB方法必须提供过渡态前后两个位置的初猜坐标，类似于QST2，这比只需要提供一个初猜坐标的GDIIS和准牛顿法更为麻烦。
- 使用NEB方法的好处是能顺便得到两点间的能量极小路径（若坐标为两个极小点，即得到IRC）。

## TeraChem的动力学模拟功能与限制
TeraChem的从头算动力学是其卖点之一，支持每隔几帧输出一次分子轨道信息以便在VMD中观察动态变化。该程序支持控温，但无法指定温度变化过程，无法方便地由用户设定初始速度，无法加限制势或拉伸力，且只支持球形周期边界条件而不支持一般的矩形盒子边界条件。
- 球形周期边界条件的描述在手册中较为抽象含糊。

## TeraChem的数值精度模式
TeraChem内部默认采用单双精度混合模式，数值大小高于阈值的双电子积分及涉及累加的变量用双精度，数值较小的双电子积分采用单精度。这种混合模式是为了适配nVidia家用Geforce系列GPU双精度性能较弱的情况（Tesla和Quadro系列双精度性能为单精度一半）。
- 程序也支持设定完全单精度或完全双精度运算。

## TeraChem测试环境与对比对象
测试旨在比较TeraChem与Gaussian 03 E.01版的速度与精度，考察体系尺寸增加时的耗时变化。测试对象包括链状聚苯分子和咪唑配位的镁卟啉，计算级别为B3LYP/6-31G*，G03使用默认收敛判据，TeraChem使用默认收敛限并设定dftgrid 2以匹配G03积分精度。
- TeraChem数据为程序自身统计耗时，G03为Linux time命令给出的wall clock time。

## 聚苯分子链上的速度测试结论
测试显示两块GTX480性能提升接近翻倍，且优于两块C2050，这是由于TeraChem混合精度下GTX480的高核心频率和流处理器数量占优。GTX460M因流处理器少、频率低，速度仅为GTX480的不到1/3，且TeraChem算大体系时显存消耗大（GTX480在N=14时显存溢出）。
- 两块C2050性能不如两块GTX480，从性价比看使用高端Geforce卡比Tesla卡更划算。

## TeraChem与Gaussian在聚苯分子链上的速度对比
在聚苯分子测试中，i7-2630QM CPU运行Gaussian 03的耗时与2*C2050运行TeraChem基本持平。主流双路服务器下的G03耗时可与2*GTX480+2*C2050持平，若使用主流家用级GPU（如GTX460M），其速度远不如普通四核CPU运行G03。
- TeraChem与G03均显示出线性标度特征，但这主要是因为测试对象为线性分子。

## 咪唑配位镁卟啉分子的速度测试
对于咪唑配位的镁卟啉分子，TeraChem比G03快，但单块GTX480仅比i7-2630QM快三分之一左右。多种GPU配置的相对速度表现与聚苯分子测试一致，GTX460M+TeraChem依然慢于i7-2630QM+G03。
- 对于高对称性体系，TeraChem的优势预计会进一步丧失。

## TeraChem不同精度模式的耗时对比
对于8个苯环的B3LYP/6-31G*计算，纯双精度模式比纯单精度模式慢很多。动态混合单双精度模式的耗时仅比纯单精度略多，远低于纯双精度。
- 2*GTX480下默认模式耗时67.5s，纯双精度205.9s，纯单精度54.3s。

## TeraChem的计算精度测试结果
对比咪唑配位镁卟啉的HF计算结果，TeraChem默认混合精度与纯双精度结果仅在小数点后第六位有差异，单精度结果在小数点后第四位有差异。TeraChem默认结果与Gaussian SCF=Tight结果符合很好，可信度有保证，且默认精度下结果比G03默认标准略高。
- G03默认与Tight标准结果相差约0.42KJ/mol，一般可接受。

## TeraChem的DFT计算精度对比
在B3LYP/6-31G*下计算N=14聚苯分子，TeraChem默认精度结果与Gaussian SCF=Tight结果符合很好。尽管不同程序DFT数值积分格点设定差异较大，TeraChem依然表现出与高精度G03结果的一致性。
- TeraChem默认结果为-3235.9678361702，G03 SCF=Tight为-3235.9678984。

## 对TeraChem官方性能测试数据的质疑
官方图表显示GTX480比单个Intel X5680核心快43倍，但实测i7-2630QM运行G03每轮迭代仅18秒，甚至略快于GTX480的19.7秒。官方使用X5680单核与GTX480的480个流处理器对比缺乏公平性，且GAMESS-US的数据异常偏高。
- TeraChem实际效率与当前主流量子化学程序处于同一数量级，不能带来质的耗时降低。

## TeraChem的综合评价与购买建议
实际测试表明TeraChem的效率远被夸大，在日常研究工作中难以带来显著收益，且程序功能稚嫩、不完善。购买TeraChem需谨慎，不应盲目信从官方宣传，建议先在目标问题上进行实际测试并理性分析硬件性价比。
- TeraChem目前的意义主要在于证明了基于GPU的量子化学程序能完成传统CPU程序的工作且结果可信。

## 2019年TeraChem与ORCA的补充性能对比
在2019年3月的补充测试中，TeraChem v1.93P结合GTX1080Ti计算110原子有机分子能量+受力耗时48s。对比使用2*E5 2696v3 CPU的ORCA 4.1.1 (RI-BLYP/def2-SV(P))耗时61s，两者可视为无差别。
- 考虑到硬件成本和软件授权费，TeraChem在性价比上依然没有任何优势。

## TeraChem的功能成熟度现状
截至2019年3月，TeraChem仍不支持d以上角动量基函数，没有解析Hessian，不支持明尼苏达系列泛函（如M06-2X）。从功能角度看，TeraChem被认为几乎毫无使用价值，尽管其计算速度有所改进。
- 功能上的巨大局限性限制了其在实际研究中的应用。

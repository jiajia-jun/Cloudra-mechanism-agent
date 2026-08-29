---
id: 281
title: 简谈CPU峰值性能怎么计算
url: http://sobereva.com/281
domain: 软件安装与环境
topic: CPU与GPU峰值浮点性能计算及硬件选购
cards: 9
---
## 1. CPU峰值浮点性能计算公式

CPU峰值性能是CPU运算能力在理想情况下的理论性能，实际性能应以软件实测为准。计算峰值浮点性能的公式为：峰值浮点性能=CPU核数*CPU频率*每周期执行的浮点操作数。目前世界顶尖的高性能计算机(HPC)的浮点性能常以PFLOPs来计，1P=1000T=1000000G。
- FLOPs (FLoating-point Operations Per Second)是衡量浮点性能的常用单位，即每秒做的浮点运算次数，1GFLOPs代表每秒十亿次浮点运算。

---

## 2. 常见CPU内核每周期浮点操作数

目前常见的几类CPU内核的每周期浮点操作数如下（引自网络，见[http://stackoverflow.com/questions/15655835/flops-per-cycle-for-sandy-bridge-and-haswell-sse2-avx-avx2](http://stackoverflow.com/questions/15655835/flops-per-cycle-for-sandy-bridge-and-haswell-sse2-avx-avx2)）：Intel Core 2 and Nehalem为4 DP FLOPs/cycle (2-wide SSE2 addition + 2-wide SSE2 multiplication) 和 8 SP FLOPs/cycle (4-wide SSE addition + 4-wide SSE multiplication)。Intel Sandy Bridge/Ivy Bridge为8 DP FLOPs/cycle (4-wide AVX addition + 4-wide AVX multiplication) 和 16 SP FLOPs/cycle (8-wide AVX addition + 8-wide AVX multiplication)。Intel Haswell为16 DP FLOPs/cycle (two 4-wide FMA instructions) 和 32 SP FLOPs/cycle (two 8-wide FMA instructions)。AMD K10为4 DP FLOPs/cycle (2-wide SSE2 addition + 2-wide SSE2 multiplication) 和 8 SP FLOPs/cycle (4-wide SSE addition + 4-wide SSE multiplication)。AMD Bulldozer/Piledriver/Steamroller (per module, two cores)为8 DP FLOPs/cycle (4-wide FMA) 和 16 SP FLOPs/cycle (8-wide FMA)。
- 普通CPU的单精度(SP)浮点性能通常是双精度(DP)浮点性能的两倍。

---

## 3. XEON处理器代数与架构对应关系

计算化学常用的XEON E3/E5系列中，v3对应Haswell架构，v2对应Ivy Bridge架构，不带后缀的对应Sandy Bridge架构。更老的如XEON 5500系列对应Nehalem架构。如果不清楚具体对应关系，建议查阅《硬件资料库》（[http://原作者.com/datasheet.rar](http://原作者.com/datasheet.rar)）。

## 4. XEON E5-2690 v2 峰值性能计算示例

以E5-2690 v2为例，其基本频率为3.0GHz（不考虑Turbo boost动态升频），有10个核，每个核每周期可以做8次双精度浮点运算或16次单精度浮点运算。计算得出：单精度峰值浮点性能=3.0*10*16=480 GFLOPs；双精度峰值浮点性能=3.0*10*8=240 GFLOPs。

---

## 5. AVX指令集对Sandy Bridge/Ivy Bridge性能的影响

Sandy Bridge/Ivy Bridge支持AVX指令集，可以一次处理256bit浮点指令，双精度浮点数长度为64bit，即一次可以做四个双精度浮点运算。理论上一个周期可以执行一次AVX浮点乘和一次AVX浮点加，共8个双精度浮点运算，但这只是理论最大值。实际上程序中不能完全利用AVX指令集，且指令类型（如仅有加法或仅有乘法）不匹配会导致运算单元空闲，因此实际性能提升远低于理论值，一般应用中同频同核下性能比Nehalem高近一半。

---

## 6. FMA指令对Haswell (XEON v3) 性能的影响

Haswell支持AVX 2.0和FMA3指令，FMA（Fused Multiply-Add）指令可以在一个周期内完成result=a+(b*c)运算，相当于两次常规浮点运算。Haswell每个内核一个周期可处理两条FMA指令，包含4个双精度浮点数，故每核每周期满打满算可做2*4*2=16次双精度浮点操作。表面上看XEON v3比v2浮点性能高一倍，但这水分巨大，因为并非总是乘加运算（如仅有乘法时v3与v2性能相等）。实际测试显示Haswell比Ivy Bridge性能高不到10%。

---

## 7. AMD推土机架构浮点性能弱点

从推土机架构（Bulldozer/Piledriver/Steamroller）开始，AMD采用两个核心作为一个模块共用一个浮点单元的设计，一个周期只能处理一次256bit FMA指令。相比Haswell每个核能同时处理两条256bit FMA指令，AMD的四个核才顶Haswell一个核的峰值浮点性能。实际使用中，要达到XEON v2或v3 N个核的实际性能，同频下现在的Opteron需要用>2N个核，且并行效率低时效能极差，不适合计算化学。

---

## 8. GPU峰值浮点性能计算示例

以nVidia高端GTX Titan black为例，基础频率0.889GHz，有2880个单精度浮点单元和960个双精度浮点单元，每个浮点单元每周期能做一次FMA指令。计算得出：单精度峰值浮点性能=0.889*2880*2=5120GFLOPs；双精度峰值浮点性能=0.889*960*2=1707GFLOPs。GTX Titan black双精度峰值性能约是E5-2690 v2的4、5倍，但GPU峰值性能水分较大，不能仅凭FMA推断实际双倍处理能力。

---

## 9. 消费级GPU单双精度性能差异

GPU单精度浮点性能性价比远胜于CPU，但大多数消费级GPU的双精度性能较差。GTX Titan black价格比GTX 780Ti贵一倍，主要原因是其双精度性能能达到单精度的1/3，而GTX 780Ti该比例仅为1/24。GTX 780Ti基准频率0.876GHz，单精度性能与GTX Titan black基本无异，但双精度峰值性能仅210GFLOPs，若不计入FMA甚至不如E5-2690 v2。

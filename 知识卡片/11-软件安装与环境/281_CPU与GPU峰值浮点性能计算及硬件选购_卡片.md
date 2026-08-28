---
id: 281
title: 简谈CPU峰值性能怎么计算
url: http://sobereva.com/281
domain: 软件安装与环境
topic: CPU与GPU峰值浮点性能计算及硬件选购
cards: 1
---

# CPU与GPU峰值浮点性能计算及硬件选购 — 知识卡片

## 1. CPU峰值浮点性能计算公式

CPU峰值浮点性能为CPU运算能力满打满算最理想情况下的性能，仅有理论意义，实际性能需以软件实测为准。计算公式为：峰值浮点性能=CPU核数*CPU频率*每周期执行的浮点操作数。搞计算化学一般只关注浮点性能，时下普通CPU的单精度(SP)浮点性能是双精度(DP)浮点性能的两倍。

## 常见CPU内核每周期浮点操作数
Intel Core 2和Nehalem架构为4 DP FLOPs/cycle (2-wide SSE2 addition + 2-wide SSE2 multiplication) 和 8 SP FLOPs/cycle；Intel Sandy Bridge/Ivy Bridge架构为8 DP FLOPs/cycle (4-wide AVX addition + 4-wide AVX multiplication) 和 16 SP FLOPs/cycle；Intel Haswell架构为16 DP FLOPs/cycle (two 4-wide FMA) 和 32 SP FLOPs/cycle。AMD K10架构为4 DP FLOPs/cycle和8 SP FLOPs/cycle；AMD Bulldozer/Piledriver/Steamroller架构每个模块(两个核)为8 DP FLOPs/cycle (4-wide FMA) 和 16 SP FLOPs/cycle。数据引自http://stackoverflow.com/questions/15655835/flops-per-cycle-for-sandy-bridge-and-haswell-sse2-avx-avx2。

## XEON处理器版本与架构对应关系
时下计算化学常用的XEON E3/E5中，v3版本对应Haswell架构，v2版本对应Ivy Bridge架构，不带后缀的对应Sandy Bridge架构。更老的如XEON 5500系列对应Nehalem架构，不清楚版本可查阅《硬件资料库》(http://sobereva.com/datasheet.rar)。

## CPU峰值浮点性能计算示例
以E5-2690 v2为例，基本频率为3.0GHz，有10个核，每个核每周期可做8次双精度浮点运算或16次单精度浮点运算。其单精度峰值浮点性能为3.0*10*16=480 GFLOPs，双精度峰值浮点性能为3.0*10*8=240 GFLOPs。

## 浮点性能常用单位定义
FLOPs (FLoating-point Operations Per Second) 是衡量浮点性能的常用单位，即每秒做的浮点运算次数。1GFLOPs代表每秒十亿次浮点运算，目前世界顶尖的高性能计算机(HPC)浮点性能以PFLOPs计，1P=1000T=1000000G。

## SIMD指令集与理论性能的水分
SIMD指令集(如MMX、SSE、AVX)允许一个指令同时对多个数据处理，Sandy Bridge/Ivy Bridge支持AVX可一次处理256bit浮点指令，理论上每周期能做8个双精度浮点运算。实际水分很大，前提必须是完全处理AVX 256bit指令且编译器和操作系统支持，且若只有加法或乘法指令，另一运算单元会空闲导致性能浪费。一般应用中Sandy Bridge/Ivy Bridge比Nehalem在同频同核下性能高近一半，主要源于架构改进而非单纯理论峰值。

## Haswell架构FMA指令的实际性能影响
Haswell支持AVX 2.0及FMA3指令，FMA (Fused Multiply-Add) 可在一个周期内完成result=a+(b*c)运算，相当于两次常规浮点运算。Haswell每个核每周期理论可做16次双精度浮点操作，表面比v2高一倍，但实际水分巨大，因为并非总是乘加运算。实际测试Haswell比Ivy Bridge性能高不到10%，买服务器时若v3比v2贵太多则不划算。

## AMD推土机架构浮点性能缺陷
AMD推土机架构(Bulldozer/Piledriver/Steamroller)设计糟糕，两个核心作为一个模块共用一个浮点单元，一个周期只能处理一次256bit FMA指令。论峰值浮点性能，现今AMD四个核才顶Haswell一个核，实际要达到XEON v2/v3的N个核性能，同频下Opteron需用>2N个核。

## GPU峰值浮点性能计算示例
以nVidia GTX Titan black为例，基础频率0.889GHz，有2880个单精度浮点单元和960个双精度浮点单元，每个单元每周期能做一次FMA指令。其单精度峰值浮点性能为0.889*2880*2=5120GFLOPs，双精度峰值浮点性能为0.889*960*2=1707GFLOPs。

## 消费级GPU单双精度性能差异
GPU单精度浮点性能性价比远胜CPU，但消费级GPU双精度性能一般较差。GTX Titan black双精度性能能达到单精度的1/3，而GTX 780Ti该比例仅为1/24。GTX 780Ti基准频率0.876GHz，单精度性能与Titan black基本无异，但双精度峰值性能仅为210GFLOPs。

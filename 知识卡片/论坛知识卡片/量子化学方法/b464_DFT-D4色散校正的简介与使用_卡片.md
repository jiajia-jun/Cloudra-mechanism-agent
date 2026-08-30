---
key: b464
title: DFT-D4色散校正的简介与使用
url: http://sobereva.com/464
domain: 量子化学方法
source: blog
year: 2019
cards: 9
---

# DFT-D4色散校正的简介与使用 — 知识卡片

## 1. DFT-D4方法的改进原理

DFT-D4是DFT-D3的后继版本，其关键改进在于让原子色散系数与原子电荷挂钩，从而能够反映体系的实际电子结构。DFT-D3主要依赖于体系几何结构，未考虑原子电荷变化对色散系数的影响，因此对于过渡金属配合物、离子化合物等存在显著带电原子的体系，DFT-D3在原理上不够理想。DFT-D4通过结合电负性均衡(EEQ)方法计算的原子电荷，解决了DFT-D3无法体现体系实际电子结构的问题。

---

## 2. DFT-D4方法的主要特征

DFT-D4使用与DFT-D3(BJ)相同的BJ阻尼函数，并带有Axilrod–Teller–Muto (ATM)形式的三体校正项。该方法基于EEQ模型计算原子电荷，具有解析梯度（Hessian目前只有半数值的），最高支持到86号元素(Rn)，计算速度极快。根据测试，DFT-D4的精度能达到VV10等更复杂色散校正方法的水平，甚至在某些情况下更好。

---

## 3. DFT-D4与其他色散校正方法的比较

对于不存在显著带电原子的体系，D4与D3精度相当；对于存在显著带电原子的体系，D4比D3有更明显的改进。DFT-D4也可以结合其它原子电荷（如GFN-xTB方法计算的Mulliken电荷），但这种DFT-D4(TB)形式计算更麻烦且结果不如结合EEQ电荷的标准DFT-D4。相比XDM、dDSC、TS、VV10等依赖电子结构的色散校正方法，DFT-D4计算成本更低且易于实现解析梯度。

---

## 4. Grimme的dftd4程序简介

dftd4是Grimme发布的独立计算DFT-D4色散校正的程序，支持基于EEQ电荷的DFT-D4(EEQ)-ATM和DFT-D4(EEQ)-MBD形式。该程序不包含xtb程序，因此不支持基于Mulliken电荷的DFT-D4(TB)。dftd4的用法和DFT-D3程序相似，需要先编译才能运行，已提供Linux版和Windows版的预编译可执行文件。

---

## 5. Linux下dftd4的简单编译方法

在Linux环境下，若已安装Intel Fortran编译器和MKL库，可将dftd4压缩包中include目录下的.f文件拷入source目录，进入source目录后运行以下命令编译：`ifort *.f90 -qopenmp -qopenmp-link=static -mkl -static-intel -stand f08 -check bounds -o dftd4`。带static的选项确保生成的可执行文件不依赖于动态库。

---

## 6. Windows下dftd4的简单编译方法

在Windows环境下使用Visual Studio 2017和Intel Fortran编译器进行编译时，需新建项目并将include目录下的.f文件和source目录下的.f90文件加入项目。编译配置应设为Release，Runtime Library设为Multithreaded，Use Intel Math Kernel Library设Sequential，Process OpenMP Directives设Generate Parallel Code。编译后在Release目录下生成dftd4.exe可执行文件。

---

## 7. dftd4程序的基本用法

dftd4程序通过命令行运行，使用`./dftd4`可查看选项。例如，基于BLYP泛函计算H2O.xyz的色散校正能，命令为：`./dftd4 H2O.xyz --func blyp`。程序会输出计算设置、阻尼参数和色散校正能（Edisp），结果也会写入隐藏文件.EDISP中。常用的选项还包括`--chrg`设定体系净电荷，`--grad`计算梯度，`--hess`计算半数值Hessian。

---

## 8. dftd4程序支持的泛函

dftd4程序支持的泛函列表位于源代码包的dfuncpar.f90文件中，可以通过搜索get_d4eeqbjatm来查看支持的名称。在特定时间点（如2019-May-8），参数库中可能尚未包含某些常用泛函（如M06-2X）的参数，导致无法结合使用。程序计算输出的色散校正能单位包括kcal/mol和Hartree。

---

## 9. 量子化学程序对DFT-D4的支持情况

Gaussian从25版开始支持DFT-D4。ORCA从4.2版本开始支持DFT-D4(EEQ)-ATM形式，使用时直接添加D4关键词。CP2K从2024.2版本开始支持，Molpro从2018.1版本开始支持，Turbomole从7.3版本开始支持。对于不支持DFT-D4的旧版本Gaussian（如G16），可以通过external关键词编写接口调用dftd4程序来实现能量、受力和Hessian的计算。

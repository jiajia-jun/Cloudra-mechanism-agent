---
id: 464
title: DFT-D4色散校正的简介与使用
domain: 量子化学方法
topic: DFT-D4色散校正原理与dftd4程序使用
cards: 12
---

## 1. DFT-D4方法相对于DFT-D3的改进
DFT-D3色散校正无法考虑体系的实际电子结构，对于存在显著带电原子（如过渡金属配合物、离子化合物）的情况在原理上不够理想。DFT-D4方法的关键改进在于让原子色散系数与原子电荷挂钩，从而能更好地反应实际情况。DFT-D4的最终形式发表于J. Chem. Phys. 150, 154122 (2019)。

---

## 2. DFT-D4最终形式的主要特征
DFT-D4最终形式使用和DFT-D3(BJ)一样的BJ阻尼函数，并带有ATM形式的三体校正项。其色散系数依赖于electronegativity equilibration (EEQ)方法计算的原子电荷，具有解析梯度（Hessian目前只有半数值的）。DFT-D4最高支持到86号元素（Rn），计算基本零耗时，精度能达到VV10等更复杂方法的水平。

---

## 3. DFT-D4方法的精度适用性
对于不存在显著带电原子的情况，D4和D3精度相当；而对于有显著带电原子的情况，D4比D3的改进明显。相关测试可参考Grimme的J. Chem. Phys. 150, 154122 (2019)以及Acc. Chem. Res., 52, 258 (2019)。

---

## 4. DFT-D4与原子电荷的结合方式
DFT-D4原理上可以结合其它原子电荷，初代DFT-D4结合的是GFN-xTB方法产生的Mulliken电荷（DFT-D4(TB)），但测试发现这种形式计算麻烦且结果不如结合EEQ电荷的最终版DFT-D4好。标准的DFT-D4是基于EEQ电荷的。

---

## 5. dftd4程序简介
Grimme发布的独立dftd4程序用于计算DFT-D4。该程序不含xtb程序，因此只能做基于EEQ电荷的DFT-D4计算。程序支持ATM和MBD形式的三体校正项，具体形式包括DFT-D4(EEQ)-ATM和DFT-D4(EEQ)-MBD。

---

## 6. dftd4程序在Windows下的编译
编译Windows 32bit版需要Visual Studio及Intel Parallel Studio XE（含Intel Fortran compiler和Intel MKL）。将include目录下的.f文件和source目录下的.f90文件加入项目，配置改为Release。在Fortran标签页将Runtime Library设为Multithreaded，Use Intel Math Kernel Library设Sequential；Language标签页将Process OpenMP Directives设Generate Parallel Code。编译后在Release目录生成dftd4.exe。

---

## 7. dftd4程序在Linux下的简单编译
Linux下编译需Intel Fortran compiler和MKL库。将include目录下的.f文件拷入source目录，进入source目录运行命令。
ifort *.f90 -qopenmp -qopenmp-link=static -mkl -static-intel -stand f08 -check bounds -o dftd4
其中带static的选项是为了让可执行文件不依赖于动态库。

---

## 8. dftd4程序的标准编译方法
标准编译使用meson+ninja系统，需先安装meson、lapack-devel和ninja-build，并建立符号链接ln -s /usr/bin/ninja-build /usr/bin/ninja。解压dftd4源码后，运行FC=ifort meson setup build && ninja -C build进行编译。编译完成后在build目录生成dftd4可执行文件。

---

## 9. dftd4程序的基本用法与示例
运行./dftd4可查看程序选项。计算BLYP泛函下的DFT-D4(EEQ)-ATM色散校正能的命令。
./dftd4 H2O.xyz --func blyp
结果输出中包含色散校正能Edisp（单位kcal/mol和Hartree），并生成隐藏文件.EDISP存储高精度数据。

---

## 10. dftd4程序的常用选项
dftd4程序的常用选项包括：--chrg用于设定体系净电荷；--grad用于计算色散校正能的梯度；--hess用于计算色散校正能的半数值Hessian。程序支持的泛函列表可在源代码包的dfuncpar.f90文件中通过搜索get_d4eeqbjatm找到。

---

## 11. 支持DFT-D4的量子化学程序
Gaussian从25版开始支持DFT-D4。ORCA从4.2开始支持且只支持DFT-D4(EEQ)-ATM形式，直接使用D4关键词。CP2K从2024.2开始支持，Molpro从2018.1开始支持，Turbomole从7.3开始支持。

---

## 12. 在不支持DFT-D4的程序中使用DFT-D4
对于不支持DFT-D4的Gaussian 16版本，可以利用external关键词写接口，让Gaussian在计算能量、受力、Hessian时调用dftd4程序。具体实现可参考Gaussian与ORCA联用及与xtb程序联用的相关文章。

---
key: t36834
title: VASP��EPYC 7543��Platinum 8358�ϵĲ��ԶԱȺͱ����Ż�
url: http://bbs.keinsci.com/thread-36834-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 13
---

# VASP��EPYC 7543��Platinum 8358�ϵĲ��ԶԱȺͱ����Ż� — 知识卡片

## 1. 测试平台硬件配置

测试平台为 Dell R750，配置两颗 AMD EPYC 7543 或 Intel Platinum 8358 处理器，系统内存为 32x8GB 共 256GB。硬盘方面使用了 480GB SATA 固态硬盘组建 RAID 0 以及 1.2T SAS 硬盘组建 RAID 5。VASP 版本为 5.4.4。

---

## 2. AMD 平台编译方式1

在 AMD EPYC 7543 平台上，第一种编译方式参考了特定链接中的 Intel 平台编译方法。其关键编译参数设置为 OFLAG = -O2 -xHOST。该方式在测试中使用了包含 50 个 Hg 原子的模型体系。

---

## 3. AMD 平台编译方式2

在 AMD EPYC 7543 平台上，第二种编译方式的关键参数设置为 OFLAG = -O2 -xcore-avx2。此方式需要配合特定的环境变量设置以优化性能，特别是针对 MKL 和 MPI 的绑定设置。

---

## 4. AMD 平台性能优化环境变量

在 AMD EPYC 平台上运行 VASP 时，推荐设置以下环境变量以获得更好性能：`export MKL_DEBUG_CPU_TYPE=5` 用于强制加速；`export MKL_CBWR=AVX2` 指定 CPU 默认支持 AVX2 指令集；`export I_MPI_PIN_DOMAIN=numa` 用于将内存位置与 CPU 位置绑定，减少跨内存访问延迟。

---

## 5. 编译方式1在 EPYC 7543 上的基准测试结果

在 AMD EPYC 7543 处理器上使用 50 个 Hg 原子的标准测试模型，编译方式1在不同核心数下的平均计算耗时如下：4核 2.7730s，8核 1.4358s，16核 0.7971s，32核 0.4947s，48核 0.4816s，64核 0.4820s。

---

## 6. 编译方式2在 EPYC 7543 上的基准测试结果

在 AMD EPYC 7543 处理器上使用相同的 50 个 Hg 原子模型，编译方式2（默认环境变量）的平均计算耗时明显高于方式1。数据显示方式2在 4核至 64核下的平均耗时均约为方式1的 1.3 至 1.9 倍。

---

## 7. EPYC 7543 编译方式对比结论

对于 AMD EPYC 7543 处理器，使用方式1（-xHOST）编译 VASP 的计算速度要显著优于方式2。测试还表明，配合使用第一个和第二个 export 环境变量可以进一步提升速度。

---

## 8. EPYC 7543 与 Platinum 8358 性能对比

基于 NiO 吸附 50 个 Hg 原子的模型进行测试，AMD EPYC 7543 在该体系上的计算速度比 Intel Platinum 8358 更快。在 16 核测试中，EPYC 7543 的平均耗时约为 5.8137s，而 Platinum 8358 的平均耗时约为 7.4519s。

---

## 9. Platinum 8358 适用的编译方式

Intel Platinum 8358 处理器在使用方式1编译后，在 50 个 Hg 原子体系的第一行和第二行计算中表现良好，且计算速度随着核心数增加而提升。

---

## 10. Intel 编译器在 AMD 平台的兼容性

在 AMD 平台上编译 VASP 时，可以使用 Intel 2019 或 Intel oneAPI 编译器。只需在 `.bashrc` 中设置特定的 export 环境变量（MKL_DEBUG_CPU_TYPE=5 和 MKL_CBWR=AVX2），即可获得与 Intel 平台相当的编译效果。

---

## 11. SPECint 2017 性能基准参考

根据微图图吧 2021 年的数据，在 32 颗产品的对比中，AMD EPYC 7543 的 SPECint 2017 Base Rate 性能比 Intel Platinum 8358 强约 15%。同等核心数下，EPYC 7543 的每千片价格也优于 Platinum 8358。

---

## 12. EPYC 9554 与 EPYC 7763 性能对比

根据微图图吧 2022 年的数据，在双路系统对比中，采用 DDR5 内存且频率更高的 EPYC 9554（Zen4）性能表现优异。在 256 线程测试中，EPYC 9554 的单核性能较 Zen3 架构提升了 90.2%，多核性能提升了 62.2%。

---

## 13. EPYC 9374F 与 EPYC 7763 性能对比

在双路系统对比中，核心线程数较少的 EPYC 9374F（64核/128线程）依然战胜了高核心线程数的 AMD EPYC 7763 双路系统。这表明 Zen4 架构在高性能计算场景下具有较高的效能。

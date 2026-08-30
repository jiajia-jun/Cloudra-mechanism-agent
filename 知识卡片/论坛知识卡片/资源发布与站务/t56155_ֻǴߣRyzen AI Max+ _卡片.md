---
key: t56155
title: ��ֻ�Ǵ���ߣ�Ryzen AI Max+ 395 CPU��������
url: http://bbs.keinsci.com/thread-56155-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2025
cards: 18
---

# ��ֻ�Ǵ���ߣ�Ryzen AI Max+ 395 CPU�������� — 知识卡片

## 1. AMD Ryzen AI Max+ 395 与 Ryzen 9 9950X 的架构差异

Ryzen AI Max+ 395 是移动端 SoC 芯片（Strix Halo），与 Ryzen 9 9950X 同样具备 16 个 Zen5 核心，但集成了约 40 CU 的核显。为了满足高带宽需求，该处理器采用 256-bit 位宽的 LPDDR5X 8000 统一内存，理论带宽达到 256 GB/s，相比桌面平台的 DDR5 内存具有更高的带宽上限。

---

## 2. 测试平台硬件配置：395 平台

测试使用的 395 平台基于 Framework Desktop 机箱，配备 128 GB LPDDR5X 8000 内存（每通道 512 MB 最小粒度）。系统盘为 Optane P5801X 400G E1.s 并配置 16 GB swap，临时文件盘使用 Optane P5800X 800G U.2 PCIe 4.0。

---

## 3. 测试平台硬件配置：9950X 平台

测试使用的 9950X 平台基于 MSI B850 Tomahawk Wifi 主板，配备 2 根共 64 GB 6000MT/s CL36 内存（F5-6000J3644D64GX4-FX5）。系统盘为 Optane P4801X 100G M.2 并配置 16 GB swap，临时文件盘使用 Solidigm D7-PS1030 3.2T E3.s PCIe 5.0。

---

## 4. 9950X 内存超频与 BIOS 设置

测试中 9950X 开启了 SMT（多线程）和 IOMMU，内存设置保持 MEMCLK=UCLK。FCLK 设定为 2000 MHz 以降低延迟，时序预设为 balanced 并开启 gear down mode。温度墙设定为 95 度，同时应用了 Boost Clock Override +200 MHz 以及各 CCD 与 CS 的负压优化（CO）设置。

---

## 5. 大容量内存配置对 9950X 的频率影响

9950X 在单根 256 GB 内存配置下频率较低，任何降频都会导致计算性能下降。在测试 256 GB 内存之前，原本使用的是 2 * 48 GB 6400c32 内存，由于大容量内存的时序较高且执行命令前需要刷新，性能表现不及使用 96 GB 6400c32 内存的 9950X 平台。

---

## 6. 软件环境与编译配置

测试在 Fedora Server 42 系统上进行，内核版本 6.16.9-200。ORCA 使用 6.0.1 AVX2 版本配合 OpenMPI，Gaussian 使用 16 C.02 AVX2 版本。由于 Framework 机箱 BIOS 无法关闭 SMT 和 IOMMU，395 平台通过内核参数关闭了相关功能。

---

## 7. 内存带宽与延迟测试数据

使用 Intel® Memory Latency Checker v3.11 测得的读写带宽与延迟如下：395 读/写/延迟分别为 122111.0 MB/s、194948.8 MB/s、150.2 ns；9950X (256G) 为 67863.6 MB/s、66963.0 MB/s、76.2 ns；9950X (128G) 为 75153.0 MB/s、71704.9 MB/s、73.5 ns；9950X (96G) 为 83242.8 MB/s、78230.5 MB/s、66.5 ns。

---

## 8. 测试算例：Gaussian DFT SCF+Gradient

测试项目包含 Gaussian DFT SCF+Gradient（G16-force），选用测试用例 test 0397。计算关键词设置为：b3lyp/def2TZVP G09default force scf=novaracc。

---

## 9. 测试算例：Gaussian DFT 频率计算

测试项目包含 Gaussian DFT 频率计算（G16-freq），选用测试用例 test 0397。计算关键词设置为：b3lyp/6-31G** freq scf=novaracc。

---

## 10. 测试算例：ORCA wB97MV QZ 计算

测试项目包含 ORCA wB97MV QZ 计算（ORCA-DFT），选用测试用例 test 0397。计算关键词设置为：! wB97M-V def2-QZVPP def2/J TightSCF。

---

## 11. 测试算例：ORCA TDDFT

测试项目包含 ORCA TDDFT（ORCA-TDDFT），选用测试用例 test 0397。计算关键词设置为：! B3LYP def2-TZVP D4 def2/J TightSCF；%TDDFT Nroots 3 END。

---

## 12. 测试算例：ORCA 大体系 DLPNO-CCSD(T)

测试项目包含 ORCA 大体系单点 DLPNO-CCSD(T)（ORCA-DLPNOlargeM），选用测试用例 test 0397。计算关键词设置为：! DLPNO-CCSD(T) NormalPNO cc-pVDZ cc-pVDZ/C TightSCF。

---

## 13. 测试算例：ORCA 小体系 DLPNO-CCSD(T1)

测试项目包含 ORCA 小体系中等精度 DLPNO-CCSD(T1)（ORCA-DLPNOsmallM），测试对象为 RhC10H14O2Cl。计算关键词设置为：! DLPNO-CCSD(T1) cc-PVTZ cc-PVTZ/C VeryTightSCF TightPNO，并通过 %BASIS 块指定了 Rh 元素的基组和赝势。

---

## 14. 测试算例：ORCA QD-NEVPT2

测试项目包含 ORCA QD-NEVPT2（ORCA-NEVPT2），测试对象为 {Fe[C(SiMe3)3]2}-。计算关键词设置为：! def2-TZVPP TightSCF RIJCOSX def2-TZVPP/C MOread NoIter，并配合 %CASSCF 块设定了电子数、轨道数、自旋多重度及 NEVPT2 方法参数。

---

## 15. 395 与 9950X 的计算性能对比

测试结果显示 395 在大部分项目中与配备 128 GB 内存的 9950X 互有胜负。在 DFT 相关项目中，395 落后约 5-10%；在大体系 DLPNO 项目中，395 领先约 10-20%，且受限于 PCIe 4.0；在 NEVPT2 项目中，395 的内存带宽优势使其表现优于 9950X。395 的全核运行频率维持在 4.5-4.7 GHz，功耗约为 120 W。

---

## 16. Zen5 架构 CPU 内存带宽瓶颈分析

对于 Zen5 架构 CPU，内存带宽是计算化学性能的重要瓶颈。在常规 DFT 计算中，395 相比 9950X 的劣势在 10% 以内；在内存敏感型项目中，395 可领先 10-20%。这种优势不仅来源于高带宽内存，也得益于 CCD 与 IOD 之间采用更短的片内互连，而非桌面平台的 PCB 走线。

---

## 17. Ryzen AI Max+ 395 的适用场景建议

Ryzen AI Max+ 395 适合需要高性能内存带宽且不计划安装独立显卡的计算场景。其仅提供 16 条 PCIe 4.0 通道限制了扩展能力，适合作为小型化、高内存带宽的桌面计算节点或办公主机。购买时需注意机箱散热能否保证 140W Boost 持续运行，并确认 PCIe 通道分配是否满足需求。

---

## 18. 9950X 内存升级建议

对于 9950X 用户，如果需要大于 96 GB 的内存，目前 2DPC 256 GB 内存配置并非优选，因为高负载下会降频。较好的选择是 96 GB (2 * 48 GB) 6400c32 内存套装，或者等待未来厂商推出兼容性更好的 2 * 64 GB 高频内存条。

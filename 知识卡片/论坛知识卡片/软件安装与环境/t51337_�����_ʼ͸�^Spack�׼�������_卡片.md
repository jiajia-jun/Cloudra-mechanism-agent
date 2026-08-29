---
key: t51337
title: �����_ʼ͸�^Spack�׼�����������VASPȫ��Ͱ@7K62*2 (AOCC, AOCL and HDF5)
url: http://bbs.keinsci.com/thread-51337-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2025
cards: 14
---

# �����_ʼ͸�^Spack�׼�����������VASPȫ��Ͱ@7K62*2 (AOCC, AOCL and HDF5) — 知识卡片

## 1. AMD EPYC 7K62 硬件配置

AMD EPYC 7K62 处理器搭配 Supermicro H11DSI 主板、8 条 32G DDR4 RIDMM 内存以及 SN580 1T 固态硬盘可用于计算化学测试。该平台具备 48 核心(96 线程)和 24 个 L3 Cache 实例，适合进行 VASP 密度泛函计算及性能优化研究。

---

## 2. Ubuntu Server 与 Windows Server 双系统安装

Ventory 可用于在 Windows Server 2022 基础上引导安装 Ubuntu Server 24.04.1 LTS，操作过程与普通双系统差异不大。安装时需注意，Ubuntu Server 安装程序无法自动挂载现有的 NTFS 数据盘，需要用户在安装过程中手动进行配置。

---

## 3. Spack 环境变量设置与初始化

安装 Spack 需先设置 SPACK_ROOT 环境变量并创建目录，随后通过 Git 克隆源码并运行初始化脚本。为了使环境永久生效，需将环境变量设置和初始化命令添加到 /etc/profile 文件末尾。

---

## 4. 使用 Spack 安装 AOCC 编译器

在 Ubuntu 系统中，使用命令 `spack install aocc +license-agreed` 可安装 AOCC 编译器。安装完成后运行 `spack compiler find` 即可将检测到的 AOCC 5.0.0 添加到 Spack 的编译器列表中供后续使用。

---

## 5. Spack 中 VASP 版本信息查询

通过 `spack info vasp` 命令可以查看 VASP 软件包的描述、版本信息及构建变体。输出信息显示 Spack 已识别本地的 VASP 6.4.3、6.3.2 等版本源码包，并支持 openmp、fftlib、hdf5 和 cuda 等构建选项。

---

## 6. 使用 Spack 安装 VASP 依赖与核心

执行 `spack install vasp +openmp +fftlib +hdf5 %aocc ^amdfftw ^amdblis threads=openmp ^amdlibflame ^amdscalapack ^openmpi fabrics=cma,ucx` 命令可利用 AOCC 编译器安装 VASP。该命令指定了启用 OpenMP、FFTLIB、HDF5 支持，并链接 AMD 的数学库和 OpenMPI。

---

## 7. Spack 安装多个 VASP 实例

Spack 允许同时安装不同配置的 VASP 实例，例如一个开启 HDF5，一个关闭 HDF5。使用 `spack find -lv vasp` 可以列出所有已安装的实例及其哈希值，通过 `spack load /哈希值` 命令可以加载特定配置的 VASP 版本进行计算。

---

## 8. VASP 基准测试运行命令

在准备好 INCAR、POSCAR、POTCAR 和 KPOINTS 文件后，加载 VASP 环境并使用 `mpirun -np 96 vasp_std` 可启动计算。计算过程中可通过 `grep "LOOP: cpu time" OUTCAR` 命令实时监控每次离子步的 CPU 时间和实际耗时。

---

## 9. 未优化的 VASP 性能对比

在 8 通道内存环境下使用全核心(96 核)运行 VASP，前 10 步的平均耗时约为 18.236 秒；相比之下，仅使用单路 CPU 运行相同体系的平均耗时约为 37.251 秒。测试表明，内存通道数和带宽对 VASP 计算速度有显著影响。

---

## 10. AMD EPYC L3 Cache 资源查看

使用 `lscpu | grep "L3 cache"` 命令可以查看系统的 L3 Cache 实例数量及大小。在 AMD EPYC 7K62 平台上，输出显示拥有 24 个 L3 Cache 实例，这对于后续进行 MPI 进程与硬件资源的映射至关重要。

---

## 11. AMD EPYC 7002 系列 L3 Cache 架构

AMD EPYC 7002 (Rome) 系列处理器的每个 L3 Cache 大小为 16MB，且每个 L3 Cache 连接 4 个核心。这种架构意味着一个包含 8 个核心的 CCD 芯粒中，实际上分布着 2 个各包含 4 个核心的 CCX，每个 CCX 独享 16MB 的 L3 Cache。

---

## 12. 基于 L3 Cache 的 VASP 运行优化

针对 AMD EPYC 处理器，推荐的优化策略是每个 L3 Cache 运行一个 MPI 进程，并将 OMP_NUM_THREADS 设置为每个 L3 Cache 中的核心数。对于 7K62 处理器，设置 `OMP_NUM_THREADS=4` 并使用 `mpirun -np 24 --map-by ppr:1:l3cache:pe=4 vasp_std` 运行计算，能显著减少跨 CCX 的数据传输开销。

---

## 13. 优化后的 VASP 性能提升

实施基于 L3 Cache 的资源映射优化后，VASP 计算前 10 步的平均耗时降至 10.332 秒左右。与未优化前相比，计算速度提升了接近 3 倍，验证了合理的进程与硬件绑定对提高计算效率的重要性。

---

## 14. 高性能计算系统内核参数优化

在进行 VASP 计算前，建议关闭 Swap、NUMA Balancing、ASLR 和 Transparent Hugepage (THR)，并将 CPU 频率模式设置为 performance。同时，禁用 CPU 的 C2 状态(`sudo cpupower -c 0-95 idle-set -d 2`)有助于获得更稳定的计算性能。

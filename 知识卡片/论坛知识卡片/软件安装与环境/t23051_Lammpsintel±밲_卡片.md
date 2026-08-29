---
key: t23051
title: Lammps��intel�������±��밲װ
url: http://bbs.keinsci.com/thread-23051-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 6
---

# Lammps��intel�������±��밲װ — 知识卡片

## 1. Lammps 编译适用版本

Lammps 编译操作已验证适用于 lammps-29Oct20 版本，同时也适用于 lammps-17Feb2022 版本。

---

## 2. Intel 并程套件版本要求

编译过程需要使用 Intel 并行 studio 套件的 MPI 版本，具体使用的版本为 parallel_studio_xe_2020_update4_cluster_edition。

---

## 3. FFTW 库生成方法

进入目录 ~/intel/compilers_and_libraries_2020.4.304/linux/mkl/interfaces/fftw3xf 执行命令进行编译：make libintel64。执行完成后会生成 libfftw3xf_intel.a 文件。

---

## 4. 源码解压与基础编译配置

使用命令 tar -xvf lammps-***** 解压 Lammps 源码包。进入 lammps-29Oct20/src 目录，依次执行 make yes-all 和 make no-lib 进行基础包编译配置。

---

## 5. Intel CPU IntelMPI 编译命令

在 src 目录下执行编译命令 make -j n intel_cpu_intelmpi，其中 n 为 CPU 核心数。编译完成后生成的可执行文件名为 lmp_intel_cpu_intelmpi。

---

## 6. 剪切测试案例运行方法

创建测试目录 mkdir lammps_test 并复制案例文件 cp -r ~/lammps-29Oct20/examples/shear .。使用 16 核心运行测试的命令为 mpirun -np 16 ~/lammps-29Oct20/src/lmp_intel_cpu_intelmpi < in.shear。

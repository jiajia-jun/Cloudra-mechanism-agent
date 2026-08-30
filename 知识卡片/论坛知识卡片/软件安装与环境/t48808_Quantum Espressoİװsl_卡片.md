---
key: t48808
title: Quantum Espresso�İ�װ��slurm��ҵϵͳ�ļ򵥲���
url: http://bbs.keinsci.com/thread-48808-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 17
---

# Quantum Espresso�İ�װ��slurm��ҵϵͳ�ļ򵥲��� — 知识卡片

## 1. Rocky Linux 9 下 Slurm 的软件包安装

Rocky Linux 9 默认提供 Slurm 22.05.9 的 RPM 安装包，可通过 `dnf` 命令直接安装。用户需确保已启用 EPEL 仓库（通过 `dnf config-manager --set-enabled crb` 和 `dnf install epel-release epel-next-release` 命令）。安装指令包括主程序、控制节点守护进程、计算节点守护进程及 Perl API 接口。
- `dnf install slurm slurm-slurmctld slurm-slurmd slurm-perlapi`

---

## 2. Slurm 认证服务 Munge 的配置

Slurm 需要配置 Munge 认证服务，可通过 `dnf install munge` 安装。在 `/etc/munge` 目录下需生成 Munge 密钥，默认使用 `/usr/sbin/create-munge-key` 或 `dd if=/dev/random of=/etc/munge/munge.key bs=1024 count=1`。必须正确设置 munge 目录及密钥文件的权限（目录权限 700，文件权限 400），随后启动并启用 Munge 服务。
- `systemctl start munge.service`
- `systemctl enable munge.service`

---

## 3. Slurm 配置文件 slurm.conf 的关键参数

Slurm 的配置文件 `slurm.conf` 可通过在线生成器创建或手动修改。关键参数包括设置调度类型、资源选择类型及节点定义。建议设置 `SelectTypeParameters=CR_Core` 以仅对 CPU 资源进行关联，并将节点定义中的 `NodeAddr`、`CPUs`、`RealMemory` 等参数修改为实际硬件配置（如 IP 地址、核心数、可用内存）。
- `SelectTypeParameters=CR_Core`
- `NodeName=master NodeAddr=10.7.159.134 CPUs=32 RealMemory=60000 Sockets=2 CoresPerSocket=16 ThreadsPerCore=2 State=UNKNOWN`

---

## 4. Slurm 的 Cgroup 配置

Slurm 支持 Cgroup 资源限制，需在 `/etc/slurm` 目录下创建 `cgroup.conf` 文件。配置文件通常包含自动挂载、核心限制及内存空间限制的选项，确保任务在分配的资源范围内运行。
- `CgroupAutomount=yes`
- `ConstrainCores=yes`
- `ConstrainRAMSpace=yes`

---

## 5. Slurm 服务的启动与验证

将生成的 `slurm.conf` 和 `cgroup.conf` 文件放入 `/etc/slurm` 目录后，需启动控制节点和计算节点的服务。使用 `systemctl` 命令启动并设置开机自启 `slurmctld` 和 `slurmd` 服务。通过执行 `sinfo` 命令检查节点状态，若显示为 `idle` 则表示安装配置成功。
- `systemctl start slurmctld.service`
- `systemctl enable slurmd.service`

---

## 6. Slurm 对 GPU 资源的支持配置

若计算节点包含 GPU（如 RTX 4080），需在 `slurm.conf` 中启用 GPU 资源类型并修改节点定义添加 `Gres` 参数。同时需新建 `gres.conf` 文件，指定节点名称、GPU 类型及设备文件路径。
- `GresTypes=gpu`
- `NodeName=master ... Gres=gpu:RTX_4080:1 ...`
- `NodeName=master Name=gpu Type=RTX_4080 File=/dev/nvidia0`

---

## 7. Quantum Espresso 基于 Intel 编译器的配置方法

编译 Quantum Espresso (QE) 推荐使用 Intel 编译器及 oneAPI 环境（如 2023.1 版本）。配置时指定 Intel MKL 提供的 ScaLAPACK 和 BLAS 支持，设置 MPI Fortran 编译器为 `mpiifort`，Fortran 编译器为 `ifort`（新版 oneAPI 为 `ifx`），C 编译器为 `icc`（新版为 `icx`）。
- `./configure --prefix=/opt/qe7.3.1 --with-scalapack=intel --with-scalapack-qrcp=yes MPIF90=mpiifort FC=ifort FCFLAGS=-O3 CC=icc CFLAGS=-O3 LIBDIRS="${MKLROOT}/lib/intel64/ /opt/intel/oneapi/mpi/latest/lib"`

---

## 8. Quantum Espresso 基于 GNU 编译器和 OpenMPI 的配置方法

使用 GNU 编译器链（`gcc`, `gfortran`）和 OpenMPI 编译 QE 时，建议链接 Intel MKL 数学库以获得较高计算效率。配置需指定 Fortran 编译器为 `gfortran`，C 编译器为 `gcc`，MPI 包装器为 `mpifort`。
- `./configure --prefix=/opt/qe7.3.1_gnu --with-scalapack-qrcp=yes MPIF90=mpifort FC=gfortran FCFLAGS=-O3 CC=gcc CFLAGS=-O3 LIBDIRS="${MKLROOT}/lib"`

---

## 9. Quantum Espresso 集成 Environ 模块

Environ 是 QE 的求解隐式溶剂化模型的模块，编译时需指定已安装的 QE 源码目录路径。配置命令使用 Intel 编译器，并开启优化选项。
- `./configure --with-qe=/opt/qe-7.3.1 MPIF90=mpiifx FC=ifx FCFLAGS="-O3 -xHost" CC=mpiicx CFLAGS="-O3 -xHost"`
- `make -j32 compile`

---

## 10. Quantum Espresso 集成 Libxc 交换关联泛函库

Libxc 提供丰富的交换关联泛函供 QE 使用。下载源码后需先执行 `autoreconf -i` 生成 configure 文件，然后配置安装路径并使用 Intel 编译器编译。
- `autoreconf -i`
- `./configure --prefix=/opt/libxc6.2.2 FC=ifx FCFLAGS="-O3 -xHost" CC=mpiicx CFLAGS="-O3 -xHost"`

---

## 11. Quantum Espresso 集成 ELPA 对角化库

ELPA 库可加速 QE 的对角化过程，安装时需根据 CPU 支持的指令集（如 AVX512）配置编译选项。创建独立 build 目录进行配置，链接 MKL 中的 ScaLAPACK 库，并开启 AVX2 和 AVX512 支持。
- `../configure --prefix=/opt/elpa2023 FC=mpiifx CC=mpiicx ... FCFLAGS="-O3 -xCORE-AVX512" ... SCALAPACK_LDFLAGS="-L$MKLROOT/lib/intel64 -lmkl_scalapack_lp64 ..." --enable-avx2 --enable-avx512`

---

## 12. Quantum Espresso 集成 HDF5 库

编译 HDF5 时需启用 Fortran 和并行支持，以便 QE 能够处理并行 I/O 和特定数据格式。配置使用 Intel MPI 编译器包装器。
- `./configure --prefix=/opt/hdf5 CC=mpiicx FC=mpiifx CXX=mpiicpx --enable-fortran --enable-fortran2003 --enable-parallel`

---

## 13. Quantum Espresso 的全功能编译命令

当需要同时编译支持 Environ、Libxc、ELPA 和 HDF5 的 QE 时，configure 命令需包含所有对应的库路径和头文件路径。需指定 ELPA 的静态库文件、Libxc 和 HDF5 的安装前缀及 include 路径。
- `./configure --prefix=/opt/qe7.3.1 --with-environ=/opt/Environ-3.1 --with-libxc=yes --with-libxc-prefix=/opt/libxc6.2.2 ... --with-elpa-lib=/opt/elpa2023/lib/libelpa.a ... --with-hdf5=/opt/hdf5/ ...`

---

## 14. Slurm 作业脚本中 Intel MPI 环境设置

使用 Slurm 提交基于 Intel MPI 编译的 QE 作业时，需在脚本中设置 `I_MPI_PMI_LIBRARY` 环境变量指向 PMI2 库。作业执行命令使用 `srun --mpi=pmi2` 调用 `pw.x` 程序。
- `export I_MPI_PMI_LIBRARY=/usr/lib64/libpmi2.so.0`
- `srun --mpi=pmi2 pw.x -i ${inf} > ${inf//in/out}`

---

## 15. Slurm 作业脚本中 OpenMPI 环境设置

使用 Slurm 提交基于 OpenMPI 编译的 QE 作业时，`srun` 命令需指定 `--mpi=pmix` 参数。此类脚本模板同样适用于提交 CP2K 等 OpenMPI 程序。
- `srun --mpi=pmix pw.x -i ${inf} > ${inf//in/out}`

---

## 16. Slurm 作业脚本中的关键资源参数

Slurm 脚本通过 `#SBATCH` 指令声明作业资源需求，包括作业名称、分区、节点数、每节点任务数及每个任务的 CPU 核心数。通常设置 `--cpus-per-task=1` 以匹配 MPI 进程数与物理核心数。
- `#SBATCH --nodes=1`
- `#SBATCH --ntasks-per-node=32`
- `#SBATCH --cpus-per-task=1`

---

## 17. Slurm 调用 GPU 资源的作业脚本

在 Slurm 脚本中使用 GPU 需通过 `#SBATCH --gres` 参数指定 GPU 类型与数量（如 `gpu:RTX_4080:1`）。执行程序（如 GROMACS 的 `gmx mdrun`）时需在命令行中指定 GPU ID 及相关线程绑定参数。
- `#SBATCH --gres=gpu:RTX_4080:1`
- `gmx mdrun ... -gpu_id 0`

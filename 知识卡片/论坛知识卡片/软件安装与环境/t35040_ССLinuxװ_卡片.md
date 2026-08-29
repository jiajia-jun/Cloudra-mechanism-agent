---
key: t35040
title: СС������Linux����װ��������������
url: http://bbs.keinsci.com/thread-35040-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 14
---

# СС������Linux����װ�������������� — 知识卡片

## 1. Windows 下计算软件超线程占用问题

Windows 系统下运行计算软件（如 Gaussian 16、ORCA）时，若开启超线程（HT）且设置 `%nproc` 等于物理核心数，计算任务往往会集中于 CPU0，导致该核心占用 100% 而其余核心仅占 1%~3%。为避免此类负载不均，在双路 E5-2699v3 等支持超线程的 CPU 上，建议在 BIOS 中关闭超线程功能。
- 关闭超线程后，使用 def2TZVPP 基组进行单点计算，耗时可从原本的 3~4 天显著缩短至 11 小时。

---

## 2. CentOS 7.6 安装启动盘制作与引导修复

使用 UltraISO 或 Rufus 制作 CentOS 7.6 安装 U 盘时，若在安装界面遇到显示错误（如 dracut-initqueue timeout），需在选择安装项时按 Tab 键编辑引导参数。将 `inst.stage2=hd:LABEL=CentOS\x207\x20x86_64` 修改为 `inst.stage2=hd:/dev/sdb4`（其中 `/dev/sdb4` 需根据实际 U 盘设备名调整），即可成功引导安装。
- 此方法解决了因 U 盘盘符标签识别问题导致的安装启动中断。

---

## 3. CentOS 8 Stream 环境选择

安装 CentOS 8 Stream 时，在 Base Environment（基础环境）界面应选择 Workstation（工作站）。在 Additional Software for Selected Environment（附加软件）界面，建议勾选 GNOME Applications、Legacy UNIX Compatibility、Development Tools 和 Scientific Support。
- 完成安装后需参照相关教程编辑 `~/.bashrc` 文件以配置环境变量。

---

## 4. ORCA 5.0.3 依赖的编译器安装

在 CentOS 系统中编译安装 ORCA 5.0.3 之前，需先行安装 gcc 和 gfortran 编译器。使用 root 权限或 sudo 命令执行 `yum install gcc` 和 `yum install gfortran`（CentOS 8 为 dnf）即可完成安装。
- 系统默认可能未包含这些编译工具，需手动安装。

---

## 5. OpenMPI 4.1.1 编译安装配置

ORCA 5.0.3 推荐使用 OpenMPI 4.1.1。下载解压源码后，在目录内执行配置命令：`./configure --prefix=/home/user/openmpi411 --disable-builtin-atomics`，随后运行 `make all install`。
- 编译过程中不建议使用 `-j` 参数进行多线程并行，以避免莫名错误。
- 安装路径 `/home/user/openmpi411` 可根据实际情况修改。

---

## 6. OpenMPI 环境变量配置

OpenMPI 编译安装完成后，需在用户目录下的 `.bashrc` 文件末尾添加以下环境变量：
`export PATH=$PATH:'/home/user/openmpi411/bin'`
`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:'/home/user/openmpi411/lib'`
- 保存并重启终端后，执行 `mpiexec -V` 显示版本信息即代表配置成功。

---

## 7. ORCA 5.0.3 静态版安装与配置

下载 ORCA 5.0.3 静态版压缩包并解压至 `/home/user/orca503` 目录。在 `.bashrc` 文件末尾添加路径变量和别名：
`export PATH=$PATH:'/home/user/orca503'`
`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:'/home/user/orca503'`
`alias orca='/home/user/orca503/orca'`
- CentOS 8 Stream 自带的旧版 ORCA 可通过 `sudo rpm -e orca` 卸载。

---

## 8. ORCA 运行命令

配置好环境变量后，在终端中使用以下命令运行 ORCA 输入文件（推荐使用 Multiwfn 生成输入文件）：
`orca test.inp |tee test.out`
- 该命令会将屏幕输出实时显示并保存到 `test.out` 文件中。

---

## 9. Intel MKL 数学库安装

编译 CP2K 前建议安装 Intel MKL 数学库以提升性能。在 CentOS 8 Stream 中，依次执行以下命令添加源并安装：
`sudo dnf config-manager --add-repo https://yum.repos.intel.com/mkl/setup/intel-mkl.repo`
`sudo rpm --import https://yum.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS-2019.PUB`
`sudo dnf install intel-mkl`
- 安装路径默认为 `/opt/intel/`。

---

## 10. Intel MKL 环境变量加载

Intel MKL 安装完成后，需在 `.bashrc` 文件末尾添加以下命令以加载环境变量：
`source /opt/intel/parallel_studio_xe_2018.0.033/bin/psxevars.sh`
- 若安装过程中遇到失败，建议尝试重新下载或清理缓存后再次安装。

---

## 11. CP2K Toolchain 编译安装

进入 CP2K 源码目录下的 `tools/toolchain`，执行以下命令开始编译 toolchain：
`./install_cp2k_toolchain.sh --with-sirius=no --with-openmpi=system --with-plumed=install`
- 该过程耗时较长（在双路 2699v3 上约需 5 小时），期间请勿中断。

---

## 12. CP2K 编译配置与执行

将 toolchain 安装目录 `install/arch` 下的所有文件复制至 CP2K 源码目录的 `arch` 文件夹中。随后在 CP2K 根目录下执行以下命令进行编译：
`source /home/user/cp2k20231/tools/toolchain/install/setup`
`make -j 36 ARCH=local VERSION="ssmp psmp"`
- 编译参数 `-j 36` 可根据实际 CPU 核心数调整，编译完成后将可执行文件路径加入环境变量。

---

## 13. CP2K 运行命令

在 `.bashrc` 中配置 CP2K 路径和别名（例如使用 36 核并行）：
`export PATH=$PATH:'/home/user/cp2k20231/exe/local'`
`alias cp2k='mpirun -np 36 cp2k.popt'`
- 运行输入文件时使用命令：`cp2k test.inp |tee test.out`。

---

## 14. 超线程对 Linux 计算任务的影响

对比测试表明，在 Linux 系统下运行计算任务时，超线程（HT）对性能的提升微乎其微。为了获得最佳计算效率，建议在 BIOS 中关闭超线程。
- 这与 Windows 系统下必须关闭 HT 以避免任务堆积的情况不同，Linux 下关闭主要是为了消除无效的调度开销。

---
key: t56735
title: ����Arch��Linux���а���CP2K����
url: http://bbs.keinsci.com/thread-56735-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2025
cards: 9
---

# ����Arch��Linux���а���CP2K���� — 知识卡片

## 1. 计算化学系统环境选择

高性能计算主要使用 Linux 系统。若追求系统更新及时，可选择 Arch 或 Arch-based 发行版。Arch 及其衍生版适合需要紧跟最新软件版本的用户。

---

## 2. 编译环境系统信息参考

参考系统为 CachyOS。内核版本为 Linux 6.17.7-3-cachyos。gcc 版本为 15.2.1 20250813，gfortran 版本为 15.2.1 20250813。Shell 环境为 Fish shell 4.1.2。

---

## 3. 编译前配置依赖注意事项

CP2K 编译前需确保联网。Arch 系统下的 cmake 版本较新（如 4.1.2），可能导致编译报错（提示版本需小于 3.5）。需手动运行 `install_cp2k_toolchain.sh` 脚本安装适配的旧版本 cmake。安装后的工具链文件应放置于 `/usr` 下的 `lib`、`lib32`、`share` 等目录，以避免与系统自带包冲突。

---

## 4. gcc15 编译 COSTA 源码修复

gcc15 编译 COSTA 时，其头文件 `mpi_type_wrapper.hpp` 因未包含 `<cstdint>` 而报错（缺失 `uint32_t` 定义）。需修改源码文件 `tools/toolchain/build/COSTA-2.2.2/src/costa/grid2grid/mpi_type_wrapper.hpp`。在该文件头部添加一行 `#include <cstdint>` 即可解决。

---

## 5. install_cp2k_toolchain 脚本执行与重复解压问题修复

执行 `install_cp2k_toolchain.sh` 过程中，脚本会下载并解压源码，但解压逻辑可能会覆盖前述修改过的源码文件。需修改脚资料件 `tools/toolchain/scripts/stage4/install_cosma.sh`。将文件中删除旧目录并重新解压的命令注释掉，涉及命令为 `[ -d COSTA-${costa_ver} ] && rm -rf COSTA-${costa_ver}` 和 `tar -xzf COSTA-v${costa_ver}.tar.gz`。

---

## 6. install_cp2k_toolchain 脚本路径问题

执行 `install_cp2k_toolchain.sh` 可能出现路径相关错误。脚本执行过程中生成的文件或配置可能未正确处理。解决方法为检查并确保脚本运行时的当前工作目录正确，或参考相关指南修正路径配置。

---

## 7. CP2K 编译命令与 Fortran 模块路径问题

使用命令 `make -j 4 ARCH=local VERSION="ssmp psmp"` 进行编译时可能遇到报错。报错原因可能是编译器在 Fortran 源码编译阶段找不到 DFTD4 相关的模块文件 `dftd4.mod`。需先使用命令 `echo $(dirname "$(find tools/toolchain/install -name dftd4.mod | head -n1)")` 查找模块所在路径。随后需在 `arch` 目录下的 `local.ssmp` 和 `local.psmp` 文件中的 `FCFLAGS` 参数里添加包含路径，格式为 `-I'xxx'`（其中 `xxx` 为查找到的路径）。

---

## 8. ssmp 版本编译报错处理

在编译 ssmp 版本时可能出现报错。psmp 版本对应 CP2K 的并行可执行文件，若 ssmp 版本报错且非必需，可直接跳过。可仅使用命令 `make -j 4 ARCH=local VERSION="psmp"` 单独编译 psmp 版本。

---

## 9. 编译成果验证

编译完成后，可使用命令 `cp2k.psmp --version` 验证编译结果是否正常。

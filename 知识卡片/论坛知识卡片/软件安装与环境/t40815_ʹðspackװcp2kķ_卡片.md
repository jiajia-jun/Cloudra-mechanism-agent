---
key: t40815
title: ʹ�ð�������spack��װcp2k�ķ�������
url: http://bbs.keinsci.com/thread-40815-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 7
---

# ʹ�ð�������spack��װcp2k�ķ������� — 知识卡片

## 1. 使用 Spack 安装 GCC-13 编译器

在用户目录下创建 soft 文件夹并克隆 Spack 仓库后，需配置环境变量并通过 Spack 安装 binutils 和 GCC-13。安装完成后需加载新版本 GCC 并将其添加为编译器，随后即可使用该编译器安装其他软件。
- `git clone -c feature.manyFiles=true https://github.com/spack/spack.git`
- `spack install binutils`
- `spack install gcc@13+binutils`
- `spack load gcc@13`
- `spack compiler find`

---

## 2. Spack 环境变量配置

使用 Spack 前必须设置 SPACK_ROOT 环境变量并执行其初始化脚本，建议将这两条命令写入 ~/.bashrc 配置文件中以便自动加载。
- `export SPACK_ROOT=${HOME}/soft/spack`
- `source ${SPACK_ROOT}/share/spack/setup-env.sh`

---

## 3. 使用 Spack 安装 CP2K

通过 Spack 安装 CP2K 时可指定使用 GCC-13 编译器并开启 ELPA 功能，安装过程中 Spack 会自动处理依赖关系。
- `spack install cp2k%gcc@13 +elpa`

---

## 4. CP2K 运行环境加载

Spack 安装的 CP2K 通过 `-Wl,-rpath` 设置了运行库路径，加载模块后通常无需手动设置 LD_LIBRARY_PATH，可直接使用 mpirun 运行 cp2k.psmp。
- `spack load cp2k`
- `mpirun [OPTIONS] cp2k.psmp`

---

## 5. CentOS 7 环境下 Spack 启动报错处理

在 CentOS 7 系统中 source Spack 初始化脚本若报错提示找不到 `_ctypes` 模块，是因为系统缺少 libffi 开发包，需安装该依赖并重新登录或重新设置环境。
- `sudo yum install libffi-devel`
- `sudo apt-get install libffi-dev`

---

## 6. Sirius 模块在 GCC-13 下的安装修复

使用 GCC-13 编译 Sirius-7.5.0 时会因缺少头文件报错，需要在 Spack 包目录下创建补丁文件修改源码，并在 packages.py 中应用该补丁。
- 文件路径: `${SPACK_ROOT}/var/spack/repo/builtin/packages/sirius/gcc-13.patch`
- 修改内容: 在 `src/SDDK/memory.hpp` 和 `src/typedefs.hpp` 中添加 `#include <cstdint>`
- 配置指令: `patch("gcc-13.patch", when="@7.4.3%gcc@13.1.0:")`

---

## 7. CP2K 链接错误 File format not recognized

编译时出现 "File format not recognized" 错误通常是因为 binutils 版本过旧不支持解压算法，通过 Spack 加载 binutils 模块通常可解决此问题。
- `spack load binutils`

---
key: t46059
title: �� Apple Silicon оƬ��ԭ������ Multiwfn 3.8(dev) �ķ������ȿӼ�¼
url: http://bbs.keinsci.com/thread-46059-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 11
---

# �� Apple Silicon оƬ��ԭ������ Multiwfn 3.8(dev) �ķ������ȿӼ�¼ — 知识卡片

## 1. Apple Silicon 芯片上编译 Multiwfn 3.8(dev) 的环境兼容性

在 macOS Sonoma 14.5 系统上已验证支持源码编译安装 Multiwfn 3.8(dev)。该方案适用于 Apple Silicon 系列芯片及较新版本的 macOS，但尚未完全确认是否支持 Multiwfn 的全部功能。若用户需要使用计算化学软件，且硬件为 Mac，macOS 可作为除 Windows 和 Linux 之外的第三种操作系统选择。

---

## 2. 编译 Multiwfn 所需的依赖工具

编译前需确保 macOS 已安装包管理器 Homebrew 以及 git，并使用 Homebrew 安装 GCC、OpenBLAS、CMake、arb 和 flint 等必要工具。由于 arb 库已合并进 flint-3.0.0 中，直接安装 arb 可能会报错，建议仅安装 flint 或手动处理缺失的头文件问题。

---

## 3. OpenBLAS 环境变量配置

Apple Silicon 原生编译默认使用 Apple 的 BLAS/LAPACK，为了使用 OpenBLAS，需要在 ~/.zshrc 配置文件中添加特定的环境变量。需设置 `LDFLAGS` 和 `PKG_CONFIG_PATH` 指向 OpenBLAS 的库路径，实际路径可通过 `brew list openblas` 命令获取。
```bash
export LDFLAGS="-L/opt/homebrew/opt/openblas/lib"
export PKG_CONFIG_PATH="/opt/homebrew/opt/openblas/lib/pkgconfig"
```

---

## 4. Multiwfn 源码的基础编译命令

将下载的 Multiwfn 3.8(dev) 源码包解压并进入目录，配合下载的 CMakeLists.txt 文件使用 CMake 进行构建。基础编译流程包括创建 build 目录、配置以及编译生成的命令，生成的可执行文件为调试版本。
```bash
cd Documents/Multiwfn-3.8_dev_src_Linux
cmake -B build
cmake --build build
```

---

## 5. Multiwfn 的 Release 优化编译

为了获得更快的运行速度，适合日常使用，应删除旧的 build 文件夹并使用 Release 模式重新编译。Release 编译会启用优化选项，显著提升 Multiwfn 的运行效率。
```bash
rm -rf build
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

---

## 6. CMake 编译参数说明

使用 cmake -B 命令时可携带特定参数，其中 `-DCMAKE_BUILD_TYPE=Release` 用于指定编译类型为 Release 版本。若使用 `-DWITH_OpenMP=ON` 参数尝试启用 OpenMP，在使用 Apple Clang 编译器时可能会报错。
```text
-DCMAKE_BUILD_TYPE=Release
-DWITH_OpenMP=ON
```

---

## 7. Apple Silicon 上 Multiwfn 的 GUI 支持限制

由于 Apple Silicon 缺乏 DISLIN 库的支持，目前不支持编译带 GUI 的版本。虽然 DISLIN 官网提供了 ARM 版本，但编译后运行 GUI 会显示空白窗口并出现 segmentation fault 错误，目前尚无解决方案。

---

## 8. PATH 环境变量配置

编译完成后，将生成的 multiwfn 可执行文件移至指定目录（如 Documents/Multiwfn），并在 ~/.zshrc 中添加 PATH 和 Multiwfnpath 环境变量。配置完成后需重启终端，输入 `multiwfn` 命令若显示 ASCII 字符画，即表示安装成功。
```bash
export PATH=$PATH:"$HOME/Documents/Multiwfn"
export Multiwfnpath="$HOME/Documents/Multiwfn"
```

---

## 9. 缺失 arb 头文件问题的解决

Homebrew 显示 arb 已合并进 flint，但直接安装 flint 后仍可能提示缺少 arb 相关的 .h 头文件。解决方法包括从 arb 官方 GitHub 仓库下载源码并复制头文件到 Multiwfn 源码的 etc 目录，或通过 git clone 将文件放置于 Homebrew 的 Cellar 目录并手动链接。

---

## 10. 解决 OpenMP 编译错误的方法

若在编译过程中遇到与 OpenMP 相关的目录错误，需修改 CMakeLists.txt 文件头部，强制指定使用 GCC 编译器而非系统默认的 Clang。GCC 的具体路径可通过 `brew list gcc` 命令查询并填入配置文件。
```cmake
set(CMAKE_C_COMPILER "/usr/bin/gcc")
set(CMAKE_CXX_COMPILER "/usr/bin/g++")
```

---

## 11. Apple Silicon 上的 Fortran 编译器支持

Apple Silicon 芯片的 Mac 不支持使用 ifort 或 ifx 等 Intel Fortran 编译器，只能使用 gfortran。部分 Multiwfn 源代码可能对 gfortran 版本有严格要求，不同版本可能导致编译结果存在差异。

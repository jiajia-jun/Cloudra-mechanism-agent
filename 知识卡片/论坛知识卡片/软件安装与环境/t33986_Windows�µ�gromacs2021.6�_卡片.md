---
key: t33986
title: Windows�µ�gromacs2021.6��GPU�汾��gromacs2022��CPU�汾
url: http://bbs.keinsci.com/thread-33986-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 8
---

# Windows�µ�gromacs2021.6��GPU�汾��gromacs2022��CPU�汾 — 知识卡片

## 1. Windows 平台下 GROMACS 编译环境准备

Windows 平下编译 GROMACS 2021 及 2022 版本需要准备 Visual Studio 2022、Intel oneAPI basetoolkit（包含 FFTW-3.3.10）、CUDA Toolkit 11.6 以及对应的 GROMACS 源码安装包。确保这些基础软件和库已正确安装是进行后续编译步骤的前提。

---

## 2. GROMACS 2021.6 GPU 版本编译前配置

使用 Visual Studio 2022 编译 GROMACS 2021 GPU 版本时，需修改 CMake 文件 `gmxManageNvccConfig.cmake`。具体修改内容为将 `CXX` 相关设置调整为 CUDA 编译参数，以解决编译失败问题，确保能够正确识别和处理 CUDA 代码。

---

## 3. GROMACS 2021.6 GPU 版本 CMake 命令

GROMACS 2021.6 GPU 版本推荐使用 MKL 库而非 FFTW3.3.10，两者速度差异不大。配置 CMake 的命令如下：
```bash
cmake -GNinja -S. -B./build -DGMX_GPU=CUDA -DGMX_FFT_LIBRARY=mkl -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=off -DMKL_INCLUDE_DIR="C:/Program Files (x86)/Intel/oneAPI/mkl/latest/include" -DMKL_LIBRARIES="C:/Program Files (x86)/Intel/oneAPI/mkl/latest/lib/intel64/mkl_intel_lp64.lib;C:/Program Files (x86)/Intel/oneAPI/mkl/latest/lib/intel64/mkl_sequential.lib;C:/Program Files (x86)/Intel/oneAPI/mkl/latest/lib/intel64/mkl_core.lib" -DCMAKE_INSTALL_PREFIX=C:/gromacs2021.6
```
该命令指定了 GPU 支持、MKL 库路径及安装前缀。

---

## 4. GROMACS 2022.1 CPU 版本 CMake 命令

编译 GROMACS 2022.1 CPU 版本无需修改源码，可直接使用 CMake 进行构建。配置命令如下：
```bash
cmake -GNinja -S. -B./build -DGMX_FFT_LIBRARY=mkl -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=off -DMKL_INCLUDE_DIR="C:/Program Files (x86)/Intel/oneAPI/mkl/latest/include" -DMKL_LIBRARIES="C:/Program Files (x86)/Intel/oneAPI/mkl/latest/lib/intel64/mkl_intel_lp64.lib;C:/Program Files (x86)/Intel/oneAPI/mkl/latest/lib/intel64/mkl_sequential.lib;C:/Program Files (x86)/Intel/oneAPI/mkl/latest/lib/intel64/mkl_core.lib" -DCMAKE_INSTALL_PREFIX=C:/gromacs2022.1
```
此过程仅依赖 MKL 进行 FFT 计算。

---

## 5. GROMACS 2022.3 GPU 版本编译遇到的源码问题

尝试编译 GROMACS 2022.3 GPU 版本时，即使修改了 `src/gromacs/nbxmn` 和 `src/gromacs/ewald` 等源文件，仍会面临数值变化导致的错误。将 `nbxnm_cuda_kernal_utils.cuh` 中的 `static_assert` 改为 `assert` 可以让编译过程继续进行，但最终结果仍可能存在较大偏差，相关 Issue 编号为 4582。

---

## 6. GROMACS Windows 编译 /MD 与 /MT 运行库不匹配问题

在编译 GROMACS Windows 版本时，常遇到 /MD 和 /MT 运行库不匹配的问题，仅通过 Visual Studio 修改 Release 选项通常无法成功解决。通过在根目录的 `CMakeList.txt` 文件中 `project()` 命令之后添加代码，可以强制统一运行库设置，解决编译障碍。

---

## 7. 强制使用 /MT 运行库的 CMake 设置

为了避免编译 GPU 版本 GROMACS 时出现 /MD 与 /MT 不匹配的问题，建议强制使用 /MT flag。需在 `CMakeList.txt` 中 `project()` 后添加以下代码：
```cmake
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
```
该方法比修改 .cmake 文件更为有效，能覆盖默认的 /MD 设置，确保编译一致性。

---

## 8. GROMACS Windows 版源码修改方案参考

针对 GROMACS 在 Windows 下的编译问题，修改 `gmxManageNvccConfig.cmake` 文件是常见的解决方案。主要修改点是将 nvcc 的编译 flag 从 Windows 风格的 `-std:c++17` 改为 Linux 风格的 `-std=c++17`，该方案适用于 2021-2023 年的 GROMACS Windows 版本，相关修改方法和已编译好的 Release 版本可在 GitHub 项目 `CondaPereira/Gromacs_windows_Release` 中获取。

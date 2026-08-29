---
key: t37179
title: GROMACS2023 Windowsԭ��ϵͳ�±��볬��ϸ����
url: http://bbs.keinsci.com/thread-37179-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 10
---

# GROMACS2023 Windowsԭ��ϵͳ�±��볬��ϸ���� — 知识卡片

## 1. GMX2023_Win 编译背景

在 Windows 上编译 GROMACS 2023 面临 CMake 复杂和 MSVC 混乱的挑战，导致部分用户无法完成编译。Linux 环境已提供新版本，但 Windows 用户往往停留在 2020 版本，因此基于原版方法进行了调整以支持 GMX2023_Win 的编译工作。
- **来源**: [Github](https://github.com/Hsuchein/Gromacs_For_Windows/releases/tag/publish)

---

## 2. NVCC C++ 标准选项错误

编译过程中出现 `nvcc fatal : Unknown option '-std:c++17'` 错误，这是因为 NVCC 传递了错误的 C++ 标准参数。解决方法是将 `gmxManageNvccConfig.cmake` 文件中的 `CXX17` 修改为 `CUDA17`，即把 `CMAKE_CXX17_STANDARD_COMPILE_OPTION` 替换为 `CMAKE_CUDA17_STANDARD_COMPILE_OPTION`。
- **相关链接**: [Sobereva 教程](http://bbs.keinsci.com/thread-11848-1-1.html)、[Chris 和 szk 帖子](http://bbs.keinsci.com/thread-33986-1-1.html)

---

## 3. NVCC GPU 架构支持错误

出现 `nvcc fatal : Unsupported gpu architecture 'compute_89'` 错误通常是因为 GPU 架构设置不匹配，例如 GTX 1050 应使用 compute_86 而非 compute_89。在 `gmxManageNvccConfig.cmake` 中需手动指定或修改 GPU 架构参数，如 `--generate-code=arch=compute_86,code=sm_86`，以适应具体显卡型号。
- **注意**: 修改 build 文件后需检查内容以确保架构参数正确应用。

---

## 4. C++17 标准与 filesystem 库冲突

在 C++17 标准下，`<experimental/filesystem>` 应替换为 `<filesystem>`，但直接修改 CMake 标准可能引发 `static_assert` 等编译错误。一个可行的修改方案是将源码中的 `std::filesystem` 替换为 `std::experimental::filesystem`，或者根据具体文件报错情况调整命名空间，以兼容 C++14 和 C++17。
- **提示**: 某些报错可能源于模板或命名空间不匹配，需仔细检查修改。

---

## 5. MSVC 编译 MD/MT 运行时库问题

MSVC 编译 GROMACS 时可能涉及 MD/MT 多线程运行时库的链接错误。通过修改 `CMakeLists.txt`，在 `project()` 命令之前添加 `cmake_policy(SET CMP0091 NEW)` 并设置 `CMAKE_MSVC_RUNTIME_LIBRARY` 为 "MultiThreaded$<$<CONFIG:Debug>:Debug>"，可以强制使用静态运行时库。
- **参考**: [CMake Policy CMP0091](https://cmake.org/cmake/help/latest/policy/CMP0091.html#policy:CMP0091)

---

## 6. Ninja 构建系统与 Clang 编译器

使用 Ninja 作为生成器可以避免 MSVC 的某些内部混乱，且 Ninja 对 MD/MT 线程的处理更为明确。若追求更好的优化效果，可以使用 Clang 编译器替代 MSVC，只需在 `CMakeLists.txt` 中指定 Clang 路径并设置 C 和 CXX 编译器即可。
- **相关链接**: [Ninja 编译示例](https://github.com/CondaPereira/Gromacs_windows_Release)

---

## 7. GMX2023 性能测试对比

在 GTX 1050 / 7th i5 平台上对 3.3w 原子的体系进行 MD 模拟，对比不同编译版本的每日 ns 数：GMX2023_CLANG_86_Win 为 57ns，GMX2020_MSVC_80_Win 为 51ns，GMX2023_GCC_86_Linux 为 63ns。GMX2023 在 Windows 上的 GPU 利用率可达 80-95%，显示出较优的优化效果。
- **注意**: 2023 版本对 AVX2 指令集有更好支持，但受限于硬件无法发挥前沿性能。

---

## 8. 修改 gmxManageNvccConfig.cmake

在 `gmxManageNvccConfig.cmake` 文件中，需将 `list(APPEND GMX_CUDA_NVCC_FLAGS "${CMAKE_CXX17_STANDARD_COMPILE_OPTION}")` 修改为 `list(APPEND GMX_CUDA_NVCC_FLAGS "${CMAKE_CUDA17_STANDARD_COMPILE_OPTION}")`。此外，可在 `gmx_add_nvcc_flag_if_supported` 函数调用附近添加 `-std=c++17` 以确保 NVCC 使用正确的 C++ 标准。
- **文件**: `gmxManageNvccConfig.cmake`

---

## 9. CMakeLists.txt 配置策略

在 `CMakeLists.txt` 文件开头（`project(Gromacs VERSION 2023.0)` 之前）需添加 CMake 策略设置以解决 MSVC 运行时库问题：
```cmake
set(CMAKE_POLICY_DEFAULT_CMP0091 NEW)
set(CMAKE_POLICY_DEFAULT_CMP NEW)
cmake_policy(SET CMP0091 NEW)
```
并在 `if(MSVC)` 块中添加替换编译标志的代码，将 `/MD` 替换为 `/MT`。

---

## 10. CMake 配置与安装命令

配置 CMake 时需指定安装路径、FFT 库路径、CUDA 路径及生成器。执行以下命令进行配置：
```bash
cmake .. -DCMAKE_INSTALL_PREFIX=D:/gmxtest/gromacs-2023 -DGMX_FFT_LIBRARY=fftw3 -DCMAKE_PREFIX_PATH=D:/gmxtest/fftw-3.3.10 -G "Visual Studio 17 2022" -DGMX_GPU=CUDA -DCUDA_TOOLKIT_ROOT_DIR=E:/GPU2/bin
```
安装命令为：
```bash
cmake --build . --target INSTALL --config Release
```
- **依赖**: MSVC 2022, FFTW, CUDA Toolkit

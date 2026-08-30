---
key: t48313
title: ���������Windows Server 2016��Gromacs 2024.3 GPU�汾���뾭��
url: http://bbs.keinsci.com/thread-48313-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 7
---

# ���������Windows Server 2016��Gromacs 2024.3 GPU�汾���뾭�� — 知识卡片

## 1. Windows Server 2016 下 A100 显卡 GROMACS 编译环境

在配备一片 A100 显卡的 Windows Server 2016 系统服务器上编译 GPU 版本 GROMACS 时，若切换至 Linux 系统会影响同组其它工作。推荐使用的编译环境包括 Visual Studio 2019 Community、CUDA Toolkit v11.8 以及 CMake 3.27（手动安装的 CMake 版本）。

---

## 2. gmxManageNvccConfig 文件修改 (C++17 支持)

在 gromacs-2024.3/cmake/gmxManageNvccConfig 文件中，需将 C++17 标准编译选项添加至 NVCC 标志列表。具体操作是在第 241 行添加代码：`list(APPEND GMX_CUDA_NVCC_FLAGS "${CMAKE_CXXCUDA17_STANDARD_COMPILE_OPTION}")`。

---

## 3. CMakeLists 策略设置 (CMP0091)

在 gromacs-2024.3/CMakeLists 文件中，需设置 CMake 策略以解决编译兼容性问题。具体是在文件开头添加以下三行代码：`set(CMAKE_POLICY_DEFAULT_CMP0091 NEW)`、`set(CMAKE_POLICY_DEFAULT_CMP NEW)`、`cmake_policy(SET CMP0091 NEW)`。

---

## 4. CMakeLists 运行时库设置

在 gromacs-2024.3/CMakeLists 文件第 92 行，需将 MSVC 运行时库设置为多线程静态链接。修改内容为：`set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")`。

---

## 5. AVX-512 编译内部错误处理

在 Windows 上编译时，若遇到 impl_x86_avx_512_simd_float.h 文件报出“内部编译器错误”，应避免使用 AVX-512 指令集。解决措施是在 CMake 配置时添加 `-DGMX_SIMD=AVX2_256` 参数。

---

## 6. 值不匹配错误

若编译过程中出现“值 MT_StaticRelease 不匹配值 MD_DynamicRelease”的错误，需检查运行时库设置。实施第 1.3 条关于 CMakeLists 的修改后，该错误通常会得到解决。

---

## 7. GROMACS 运行所需的 DLL 文件

成功编译获得 GROMACS 可执行文件后，程序运行可能缺少必要的动态链接库。需要将 NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin 路径下的 cufft64_10.dll 文件复制到 GROMACS2024_3/bin 目录下。

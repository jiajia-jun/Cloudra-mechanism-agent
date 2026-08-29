---
key: t54954
title: ��AMBER��ʹ�û���ѧϰ�ƣ�MLIP����ML/MMģ��ķ���
url: http://bbs.keinsci.com/thread-54954-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2025
cards: 10
---

# ��AMBER��ʹ�û���ѧϰ�ƣ�MLIP����ML/MMģ��ķ��� — 知识卡片

## 1. AMBER 中机器学习势 ML/MM 模拟的开发现状

随着机器学习势（MLIP）的发展，传统分子动力学（MD）模拟软件开始集成机器学习势功能。AMBER 开发了基于机器学习势的 ML/MM 模拟功能，目前集成了 ANI 系列势能面。该功能由佛罗里达大学 Adrian Roitberg 团队和科罗拉多州立大学 Junmei Wang 团队共同开发。相关工作可参考 *J. Chem. Theory Comput.* 期刊的文献。
- 该项目实现了对 MLIP 的嵌入和通用的 ML/MM 接口，扩展了 QM/MM 的工作流模块。

---

## 2. AmberTools 的安装准备与源码编译

AmberTools 的安装需要使用 CMake 进行配置，建议在干净环境中安装以避免冲突。在 AmberTools 源码包的 build 目录下，找到 `run_cmake` 脚本并进行修改以配置编译选项。推荐使用 `-DMPI=TRUE`、`-DBUILD_SANDER_LES=FALSE` 和 `-DBUILD_SANDER_API=FALSE` 等参数进行配置。根据系统环境，可额外指定编译器（如 `-DCOMPILER=GNU`）及禁用某些依赖（如 `-Dlapack_ENABLED=FALSE`）。
- 配置完成后，在 build 目录执行 `./run_cmake` 和 `make install -j` 完成编译。

---

## 3. 依赖库：Intel MKL 的配置

系统需要预先安装 Intel MKL（Math Kernel Library）以支持后续计算。确认安装后，需设置 `MKLROOT` 环境变量，以便 CMake 能够识别库文件。如果系统未安装，需从 Intel 官网下载对应平台的 MKL 安装包。
- 正确配置 MKL 是确保 ML/MM 模块编译和运行效率的前提。

---

## 4. 依赖库：Libtorch 的选择与安装

Libtorch 是 PyTorch 的 C++ 前端，是 AMBER 实现 ML/MM 功能的核心依赖。选择 Libtorch 版本时需注意与系统 CUDA 版本的匹配，推荐使用 CUDA 11.8 对应的版本以获得较好的稳定性。用户应前往 PyTorch 官网下载与本地系统 CUDA 版本和编译器兼容的 Libtorch 预编译包。
- 避免使用过高的 CUDA 版本（如 12.6/12.8），除非确认有对应的稳定 Libtorch 支持。

---

## 5. MKL 路径在 CMake 中的指定

为了让 CMake 正确链接 MKL，需修改 Libtorch 目录下的 `libtorch/share/cmake/Caffe2/public/mkl.cmake` 文件。在该文件中添加 `MKL_INCLUDE_DIR` 和 `MKL_LIBRARIES` 变量，分别指向 MKL 的安装路径。具体操作是将 MKL 的 `include` 路径和 `lib` 路径填入对应的 `set` 命令中。
- 此步骤是手动链接数学库的关键，确保编译器能找到头文件和库文件。

---

## 6. 替换 SANDER 源码以集成 ML/MM 功能

需将原版 AmberTools 中的 `src/sander` 目录删除，并替换为包含 ML/MM 功能的 SANDER 源码。可通过 Git 命令 `git clone https://github.com/ClickFF/MLMM4AMBER.git` 获取修改版源码。替换后，需修改 `src/sander/CMakeLists.txt` 文件，在文件开头添加 Libtorch 的路径到 `CMAKE_PREFIX_PATH`。
- 此操作替换了核心计算模块的源代码，使其支持机器学习势。

---

## 7. 重新编译与 MLIP 模型环境配置

在替换源码并配置好 Libtorch 路径后，需回到 build 目录执行 `./run_cmake` 和 `make install -j` 重新编译 AMBER。编译成功后，需设置环境变量 `MODEL_PATH` 指向存放 MLIP 模型文件的目录。通过 `source` 命令加载 AMBER 环境变量，并将 Libtorch 和 SANDER 的库路径添加到 `LD_LIBRARY_PATH` 中。
- 确保动态链接库路径正确是程序能够正常加载模型和运行的必要条件。

---

## 8. ML/MM 模拟的输入文件关键参数

在 AMBER 输入文件的 `&cntrl` namelist 中设置 `ifmlp = 1` 以启用 MLIP 支持。随后需添加 `&mlp` namelist 来配置具体参数，包括 `mlp_model`（指定模型）、`mlp_shake`（约束设置）和 `ani_mask`（选择原子）。`mlp_model` 支持内置的多种模型代码（如 0 代表 ANI-2x，1 代表 MACE-OFF23(S) 等）。
- 这些参数直接控制 ML/MM 模拟的势函数调用方式和计算区域。

---

## 9. ML/MM 模拟中的原子选择与约束设置

`ani_mask` 参数使用 AMBER 标准的原子/残基选择语法（如 `@1-10` 或 `:20-25`）来指定由 MLIP 计算的原子。`mlp_shake` 参数用于控制 ML 区域原子的约束，推荐在长模拟中对非 H 原子施加强约束（如设为 2）。目前 MLIP 在处理未约束原子时可能出现结构崩塌问题，尤其是涉及氢原子时。
- 合理设置约束对于保持模拟体系的稳定性至关重要，因为 MLIP 势能面在未约束区域可能存在不稳定性。

---

## 10. AMBER ML/MM 功能的扩展性应用

目前的 ML/MM 接口支持与 PLUMED 结合，从而实现基于 MLIP 的增强采样（如 MetaDynamics）。相关研究表明，该方法可用于化学反应的高精度探索，并能描述诸如冲击效应等极端条件下的动力学行为。尽管目前仍处于开发阶段，且部分功能可能未完善，但已具备处理复杂计算化学任务的能力。
- 这种扩展性使得 AMBER 能够利用机器学习势研究更为复杂的化学反应和动态过程。

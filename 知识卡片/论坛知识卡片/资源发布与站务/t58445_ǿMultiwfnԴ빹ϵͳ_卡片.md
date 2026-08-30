---
key: t58445
title: ��ǿ��MultiwfnԴ���빹��ϵͳ
url: http://bbs.keinsci.com/thread-58445-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2026
cards: 14
---

# ��ǿ��MultiwfnԴ���빹��ϵͳ — 知识卡片

## 1. Multiwfn 源码 gfortran 编译改进方案

Multiwfn 源码自带的 Makefile 主要针对 ifort 编译器配置，缺乏对 gfortran 的支持及灵活的编译选项管理。改进后的构建系统支持 gfortran 和 ifort/ifx，允许配置数学库路径、Debug/Release 模式及硬件优化选项，并将中间文件与输出文件分离存放。使用该方案在启用 gfortran 时，通常仅需执行 `make -j` 即可完成编译，无需手动修改参数。

---

## 2. 编译器检测与配置文件规则

构建系统通过后缀名自动识别编译器配置文件，以 `*.gnu` 结尾的文件用于 gfortran，以 `*.intel` 结尾的文件用于 ifort/ifx。Makefile 会自动检测当前环境变量中可用的编译器并调用对应的配置文件，无需用户手动指定编译器类型。

---

## 3. 输出文件目录结构

编译过程生成的目标文件存放于 `obj` 目录下，最终生成的可执行文件存放于 `exe` 目录下。配置文件 `settings.ini` 也会被自动复制到 `exe` 目录中，以便程序调用和查找。

---

## 4. 硬件指令集优化选项

用户可以通过设置 `ARCH` 选项来指定编译针对的硬件指令集，例如 `ARCH=native` 可针对当前 CPU 支持的指令集进行优化。默认设置为 `ARCH=generic`，这与原版 Makefile 仅支持到 SSE3 指令集的通用性相比，提供了更灵活的优化选择。

---

## 5. 编译类型与调试版本控制

编译时可以通过指定 `TYPE=Release` 或 `TYPE=Debug` 来选择构建版本，默认为 `Release` 模式并启用默认的优化选项。若需构建 Debug 版本进行调试，必须手动指定类型，仅修改文件去除注释无法生成 debug 版本。

---

## 6. 编译输出与日志控制

该构建系统兼容 CMake 风格的彩色终端输出，并支持将详细日志输出到文件。如果需要查看详细的编译过程或进行调试，可以在执行 make 命令时手动指定 `V=1` 或 `VERBOSE=1` 参数。

---

## 7. 增量编译与错误检测

系统支持依赖项跟踪和增量编译，仅重新编译修改过的源文件。如果用户修改了编译选项但未清理旧文件，系统会检测到差异并报错，强制用户清理后重新编译。

---

## 8. 清理命令的区别

执行 `make clean` 仅会删除生成的可执行文件，保留编译产生的中间目标文件。若需彻底清理包括目标文件在内的所有生成内容，必须执行 `make distclean`。

---

## 9. gfortran 编译与线性代数库建议

在使用 gfortran 编译 Multiwfn 时，建议链接 OpenBLAS 或 MKL 等优化库，未进行局部优化可能存在计算速度慢的风险。如果用户环境中已安装 MKL，可以在配置文件中选择启用 MKL 选项。

---

## 10. 简单使用方法

将改进的 `Makefile` 文件和 `config` 目录复制到 Multiwfn 源码目录下，替换原有 Makefile，然后运行 `make -jN` 即可开始编译。其他可用的 flag 选项可以通过 `make help` 查看，详细信息也可参考项目中的 README.md 文件。

---

## 11. Rocky Linux 系统的静态库依赖

在 Rocky Linux 系统上使用 gfortran 编译时，通常需要通过 `dnf` 额外安装 `libgfortran-static` 和 `glibc-static` 静态库，以确保编译顺利进行。

---

## 12. gfortran + MKL 编译已知异常与解决

使用 gfortran 结合 MKL 编译的 Multiwfn 在读取包含晶系结构的文件（如 `.gjf` 或 `.orcainp`）并执行涉及晶胞的操作时，可能会提示 "IEEE_INVALID_FLAG" 浮点异常。这是因为源代码中对晶体结构的边界判断和 `getcellabc` 等函数在特定情况下未做严谨处理，该警告通常不影响结果，可通过编译参数 `-ffpe-summary=none` 屏蔽。

---

## 13. 多种编译配置性能测试数据

基于 GitHub 仓库提供的 Workflow 测试数据，不同编译器和数学库组合构建 Multiwfn 的时间存在显著差异。gfortran + MKL 耗时 2 分 54 秒，gfortran + OpenBLAS 耗时 2 分 51 秒，ifort 耗时 8 分 46 秒，ifx 耗时 4 分 31 秒。

---

## 14. 旧版 ifort 支持移除

2026年5月3日的更新中，构建系统已删除对旧版 ifort 编译器的支持。

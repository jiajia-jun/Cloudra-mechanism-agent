---
key: t24545
title: �����dftd4��vasp.6.2.1
url: http://bbs.keinsci.com/thread-24545-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 13
---

# �����dftd4��vasp.6.2.1 — 知识卡片

## 1. VASP 对 DFT-D4 的支持

VASP 从 6.2.0 版本开始支持 DFT-D4 色散校正方法。
- 官方 Wiki 提供了相关安装说明与文档链接。
- 使用 DFT-D4 需要配合外部的 dftd4 程序库。
- 用户需正确配置环境并编译源代码以实现 VASP 与 dftd4 的链接。

---

## 2. dftd4 版本兼容性

VASP 源码接口主要兼容 dftd4 的 2.x 版本 API。
- dftd4 3.3.0 之前的 3.x 版本不包含 VASP 需要的旧版 API，可能导致链接失败。
- 自 3.3.0 版本起，dftd4 恢复了对旧版 API 的支持。
- 官方 GitHub Issue 和相关技术文档确认了此版本兼容性细节。

---

## 3. dftd4 编译环境示例

编译 dftd4 需要特定的编译器与构建工具环境。
- 测试环境包括 GCCcore-10.3.0、CentOS Linux 8.4.2105、meson-0.58.0、ninja-1.10.2 和 python-3.9.5。
- Intel 编译器环境测试过 Intel® Parallel Studio XE 2020 Update 1 (19.1.1.217) 和 2019 Update 1 (19.0.1.144)。
- 不同版本的 Intel 编译器可能需要设置不同的环境变量。

---

## 4. dftd4 标准编译流程

dftd4 使用 meson 和 ninja 进行构建的标准步骤如下。
- 首先执行 `meson setup _build` 配置构建目录。
- 运行 `meson test -C _build --print-errorlogs` 进行测试。
- 设置安装路径：`meson configure _build --prefix=/path/to/install`。
- 执行 `meson install -C _build` 完成安装。

---

## 5. dftd4 编译环境变量配置

针对不同 Intel 编译器版本，需在 meson setup 命令前指定相应的环境变量。
- 使用 Intel® Parallel Studio XE 2020 update 1 (19.1.1.217) 时，执行：`FC=ifort CC=icc CXX=icpc meson setup _build`。
- 使用 Intel® Parallel Studio XE 2019 update 1 (19.0.1.144) 时，执行：`FC=ifort meson setup _build`。
- 缺少正确的环境变量设置可能导致编译报错。

---

## 6. dftd4 旧版 API 激活参数

若编译报错或提示缺少 API，需在配置阶段显式开启旧版 API 支持。
- 使用命令 `meson configure _build --prefix=/path/to/install -Dapi_v2=True`。
- 该参数确保 dftd4 提供兼容 VASP 接口的定义。

---

## 7. dftd4 环境变量设置

安装完成后需在系统环境变量中添加 dftd4 库文件路径。
- 在 `.bashrc` 中添加：`export LD_LIBRARY_PATH=$HOME/bin/dftd4/lib64:$LD_LIBRARY_PATH`。
- 假设 dftd4 安装时的 `--prefix` 设置为 `$HOME/bin/dftd4`。
- 添加后需执行 `source ~/.bashrc` 使环境变量生效。

---

## 8. VASP makefile.include 配置 (DFT-D4)

编译支持 DFT-D4 的 VASP 需在 makefile.include 文件中添加特定编译选项和链接路径。
- 添加预编译选项：`CPP_OPTIONS += -DDFTD4`。
- 设置链接库：`LLIBS += -L$HOME/bin/dftd4/lib64 -ldftd4`。
- 设置头文件路径：`INCS += -I$HOME/bin/dftd4/include/dftd4/intel-xx.x.x.xxx`。
- 头文件路径末尾的 `intel-xx.x.x.xxx` 需替换为实际使用的 Intel 编译器版本号。

---

## 9. VASP 6.1.0 及更早版本支持 DFT-D4 的原理

VASP 6.1.0 源码中已包含部分 dftd4 相关代码，与 6.2.0 版本相近。
- 对比 `vdwforcefield.F` 和 `subdftd4.F` 文件发现两者差异不大。
- 早期版本可通过引入 GitHub 项目 `dftd4/dftd4_vasp` 中的子项目来支持 DFT-D4。
- 这种方式通过修改代码并添加 dftd4 库文件来实现功能。

---

## 10. 修改 vdwforcefield.F 启用 DFT-D4

在旧版本 VASP 源码的 `vdwforcefield.F` 文件中需添加 D4 相关调用。
- 在 `vdw_forces_main` 子程序中添加声明：`USE vdwD4`。
- 在 D3 相关代码后添加 D4 的 CASE 分支：
  ```
  ! D4-ATM(EEQ) implemented by Eike Caldeweyher
  CASE(13)
  CALL vdw_forces_D4(IO,LATT_CUR,DYN,T_INFO,TSIF,TIFOR,TOTEN,ELEM,IVDW)
  ```

---

## 11. 修改 vdwforcefield.F 中的 IVDW 判断逻辑

为识别新的 D4 方法，需扩展 `vdw_read` 子程序中对 IVDW 标志的判断条件。
- 将原判断条件中的 `(IVDW>=10 .AND. IVDW<=12)` 修改为 `(IVDW>=10 .AND. IVDW<=13)`。
- 此修改允许 INCAR 中使用 IVDW=13 来调用 DFT-D4 方法。

---

## 12. 旧版本 VASP 添加 subdftd4 文件

将 `subdftd4.F` 文件放入 VASP 源码的 `src` 目录下。
- 对于 VASP 5，需注释掉 `subdftd4.F` 中与 `vtutor` 相关的代码。
- VASP 6 无需修改 `vtutor` 相关部分。
- 该文件包含了连接外部 dftd4 库所需的接口代码。

---

## 13. 旧版本 VASP 编译配置调整

在添加 `subdftd4.F` 后需修改 VASP 的编译配置文件。
- 在 `/src/.objects` 文件中，找到 `subdftd3.o` 所在行，并在其后添加 `subdftd4.o`。
- 修改 `makefile.include` 文件，添加 `CPP_OPTIONS += -DWITH_DFTD4` 或 `-DDFTD4`。
- 完成上述步骤后即可进行编译。

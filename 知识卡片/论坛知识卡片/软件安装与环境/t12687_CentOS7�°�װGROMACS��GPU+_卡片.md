---
key: t12687
title: CentOS7�°�װGROMACS��GPU+AVX512���ľ�������
url: http://bbs.keinsci.com/thread-12687-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2019
cards: 9
---

# CentOS7�°�װGROMACS��GPU+AVX512���ľ������� — 知识卡片

## 1. GROMACS 硬件配置参考

Intel Xeon Gold 6148 双路处理器搭配 NVIDIA RTX2080 显卡，配合 4TB SATA 机械硬盘、500G SSD 以及 128GB (8*16GB) DDR4-2666 ECC 内存，可作为 GROMACS 计算的高性能工作站配置。
- 微星 X11DAI-N 主板支持上述硬件。
- CentOS 7.3 操作系统适用于该环境。

---

## 2. GROMACS 版本与编译参数

GROMACS 2019.1 和 2018.6 版本编译时需要指定特定的 cmake 参数以支持高级指令集和 GPU 加速。
- 使用 AVX512 指令集需添加参数 `-DGMX_SIMD=AVX_512`。
- 启用 GPU 支持需添加参数 `-DGMX_GPU=ON -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda`。

---

## 3. GCC 版本与 AVX512 指令集支持

GCC 4.8.5 版本不支持 AVX512 指令集，而从 GCC 5.x 版本开始支持该指令集。
- CentOS 7.3 默认源自带的 GCC 版本为 4.8.5。
- 执行 `gcc -v` 可查看当前 GCC 版本信息。

---

## 4. CUDA 对 GCC 版本的兼容性

CUDA 9.0 起支持 GCC 6.0，CUDA 10.0 支持 GCC 6.4，且 CUDA 无法支持过新的 GCC 版本。
- 选用 GCC 5.5.0 可兼容 CUDA 环境并支持 AVX512 指令集。

---

## 5. GCC 5.5.0 源码编译步骤

通过源码编译安装 GCC 5.5.0 需经历下载、解压、配置依赖、创建构建目录及配置编译选项等步骤。
- 下载命令：`wget https://mirrors.ustc.edu.cn/gnu/gcc/gcc-5.5.0/gcc-5.5.0.tar.gz`。
- 解压命令：`tar -xf gcc-5.5.0.tar.gz`。
- 进入目录：`cd gcc-5.5.0`。
- 下载依赖：`./contrib/download_prerequisites`。
- 创建构建目录：`mkdir gcc-build-5.5.0`。
- 进入构建目录：`cd gcc-build-5.5.0`。

---

## 6. GCC 编译配置命令

GCC 5.5.0 的编译配置需开启检查、支持 C 和 C++ 语言并禁用 multilib。
- 配置命令：`../configure --enable-checking=release --enable-languages=c,c++ --disable-multilib`。
- 编译命令：`make -j`。
- 安装命令：`make install`。

---

## 7. GLIBCXX 动态库版本检查

可通过 `strings` 命令配合 `grep` 查看特定路径下 `libstdc++.so.6` 库文件包含的 GLIBCXX 版本。
- 查看旧版本库：`strings /usr/lib64/libstdc++.so.6|grep GLIBCXX`。
- 查看新版本库：`strings /usr/local/lib64/libstdc++.so.6|grep GLIBCXX`。

---

## 8. 系统动态库更新替换方法

将编译产生的新版本 `libstdc++.so.6.0.21` 复制至系统库目录并替换软链接，可完成系统动态库的更新。
- 复制文件：`cp /usr/local/lib64/libstdc++.so.6.0.21 /usr/lib64/`。
- 进入目录：`cd /usr/lib64/`。
- 删除旧链接：`rm -f libstdc++.so.6`。
- 创建新链接：`ln -s libstdc++.so.6.0.21 libstdc++.so.6`。
- 验证链接：`ll libstdc*`。

---

## 9. CMake 编译器环境变量设置

在运行 cmake3 进行编译前，需通过 export 命令指定 CC 和 CXX 环境变量为新安装的 GCC 路径。
- 设置 C 编译器：`export CC=/usr/local/bin/gcc`。
- 设置 C++ 编译器：`export CXX=/usr/local/bin/g++`。

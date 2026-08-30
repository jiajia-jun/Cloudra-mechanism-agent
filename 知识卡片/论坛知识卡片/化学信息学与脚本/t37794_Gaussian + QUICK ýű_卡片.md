---
key: t37794
title: Gaussian + QUICK ���ýű�
url: http://bbs.keinsci.com/thread-37794-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2023
cards: 12
---

# Gaussian + QUICK ���ýű� — 知识卡片

## 1. QUICK 源码下载与版本选择

QUICK 是一款基于 GPU 加速的量子化学程序，源代码托管于 GitHub。用户可下载 Release 版本（如 QUICK-22.03）至指定目录（如 /opt）并解压，后续需进入该目录进行编译配置。
- 官方开源地址：https://github.com/merzlab/QUICK

---

## 2. QUICK 编译环境与 cmake 配置

编译 QUICK 需指定编译器（如 gcc 9.4.0）和 CUDA 版本（如 11.3）。在源码目录创建 build 子目录后，使用 cmake 进行配置时需开启 MPI、CUDA 选项，并设置安装前缀及显卡架构参数。
- 配置命令示例：`cmake .. -DCOMPILER=GNU -DMPI=TRUE -DCUDA=TRUE -DQUICK_USER_ARCH=turing -DCMAKE_INSTALL_PREFIX=/opt/QUICK-QUICK-22.03`

---

## 3. QUICK 显卡架构参数设置

cmake 配置中的 `QUICK_USER_ARCH` 参数需根据实际显卡型号调整。例如，GTX 1660 显卡对应 Turing 架构，参数应设置为 `turing`，其他显卡应查阅相应架构名称。
- 注意：架构参数设置错误可能导致编译或运行问题。

---

## 4. QUICK 编译与安装步骤

完成 cmake 配置并确认 Build Report 信息无误后，执行 make 命令进行多线程编译，随后执行安装命令。安装完成后，需 source 环境配置文件以加载 QUICK 运行所需环境变量。
- 编译命令：`make -j20`
- 安装命令：`make install`
- 环境配置：`source /opt/QUICK-QUICK-22.03/quick.rc`

---

## 5. QUICK 用户手册与教程

QUICK 提供详细的 User Manual 和 Hands-on Tutorials 文档，涵盖程序使用方法及案例。教程中包含自旋多重度 `MULT=` 的写法说明，其中该值等于 $2S+1$（$S$ 为总自旋）。
- 文档参考：User Manual 与 Hands-on Tutorials

---

## 6. QUICK 支持的计算方法与功能

QUICK 支持 HF 和 DFT 计算层级，擅长处理单点能量计算、梯度和几何优化。程序支持色散校正，但在计算频率（Hessian）方面存在限制，仅能解析计算一阶导数。
- 注意：频率计算功能受限。

---

## 7. QUICK 可执行文件类型与调用方式

根据编译配置，QUICK 会生成不同的可执行文件，分别对应单核、MPI 并行、单 GPU 及多 GPU 并行模式。调用时需根据计算需求选择对应的执行命令。
- CPU 单核：`quick water.in &`
- CPU 并行：`mpirun -np 10 quick.MPI water.in &`
- 单 GPU：`quick.cuda water.in &`
- 多 GPU 并行：`mpirun -np 2 quick.cuda.MPI water.in &`

---

## 8. Gauick 脚本功能与来源

Gauick 是一个 Python 脚本，旨在将 QUICK 作为外部程序与 Gaussian 结合使用，利用 Gaussian 处理几何优化和频率，利用 QUICK 加速单点计算。该脚本已在 GitHub 开源，名称为 Gauick。
- 项目地址：https://github.com/mizu-bai/Gauick

---

## 9. Gauick 配置文件设置

Gauick 通过读取名为 `gauick.json` 的配置文件来获取 QUICK 执行路径和计算层级设置。配置文件包含 `exec`（执行命令）和 `job`（计算方法）字段，DFT 或 HF 前需加 `U` 表示开壳层。
- 配置示例：
  ```json
  {
   "exec": "mpirun -np 1 quick.cuda.MPI",
   "job": "DFT B3LYP GD3BJ BASIS=6-31G*"
  }
  ```

---

## 10. Gaussian 调用 QUICK 进行几何优化

在 Gaussian 输入文件中，通过 `external` 关键字指定调用 `gauick.py`，并使用 `opt=nomicro` 进行几何优化。此时 QUICK 负责计算能量和梯度，Gaussian 负责优化步骤。
- 输入文件示例：
  ```
  %nproc=1
  %chk=water.chk
  #p external="python3 -u gauick.py" opt=nomicro
  water
  0 1
   O -0.06756756 -0.31531531 0.00000000
   H 0.89243244 -0.31531531 0.00000000
   H -0.38802215 0.58962052 0.00000000
  ```

---

## 11. Gaussian 调用 QUICK 进行频率计算

由于 QUICK 本身不支持频率计算，Gauick 脚本允许在优化完成后，利用 Gaussian 的数值频率功能结合 QUICK 的能量计算。使用 `--link1--` 连接任务，读取 chk 文件进行频率计算。
- 频率计算输入段：
  ```
  --link1--
  %nproc=1
  %chk=water.chk
  #p external="python3 -u gauick.py" freq=num geom=allcheck
  ```

---

## 12. QUICK 计算性能与混合方案优势

实测表明，对于中大型体系，QUICK 的 GPU 加速版本性能显著优于 CPU MPI 版本。采用 Gaussian + QUICK 的混合方案，可以利用 QUICK 快速计算梯度和单点能量，同时利用 Gaussian 的优化算法和频率计算功能，弥补 QUICK 在频率分析上的短板。
- 适用场景：包含优化和频率计算的全流程作业。

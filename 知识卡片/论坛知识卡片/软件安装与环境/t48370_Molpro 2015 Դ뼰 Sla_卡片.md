---
key: t48370
title: Molpro 2015 Դ����뼰�� Slater �������¼���ĳ���
url: http://bbs.keinsci.com/thread-48370-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 11
---

# Molpro 2015 Դ����뼰�� Slater �������¼���ĳ��� — 知识卡片

## 1. Molpro 2015 版本授权与编译背景

Molpro 自 2015 版本后改为订阅制授权模式，旧的永久授权（有效期至 2115 年）对应的 2015 版预编译安装包在 CentOS 7 以上的新系统上无法使用。为确保 Molpro 2015 能够在新系统上运行，需要通过源码编译安装，并在编译时加入 --enable-slater 选项以启用 Slater 函数积分模块（SMILES）。

---

## 2. Slater 模块对编译工具链的要求

Molpro 2015 的 Slater 模块源码包含 QFloat 扩展精度（4 倍精度），该特性仅支持 Intel 编译器（ifort），GNU 编译器（gfortran）未实现 QFloat Intrinsic。若需编译支持 Slater 模块的 Molpro 2015，必须使用 Intel 编译器，推荐版本为 Intel Parallel Studio XE 2018。

---

## 3. Molpro 2015 源码编译配置命令

在切换至 2015.1.39 版本标签并配置好 MKL 环境后，使用 Intel 编译器进行配置的命令为：`$ CC=icc CXX=icpc FC=ifort ./configure --prefix=/opt/molpro --enable-mpp=auto-ga-mpich --enable-scalapack --enable-integer8 --enable-slater`。若不使用 Intel 编译器而使用 GNU 8.5.0 + MKL 2022.0.1，则不能添加 --enable-slater 选项。

---

## 4. Molpro 2015 编译安装与依赖处理

执行 `make install` 进行安装，若遇到 boost、mpich、scalapack 等依赖缺失问题，需将 boost_1_59_0.tar.gz、mpich-3.2.tar.gz、scalapack-2.0.2.tgz 放入 ~/.molpro/cache/ 目录下，配置脚本会自动解压编译。编译完成后，需将 .token 文件复制到 /opt//molpro/molprop_2015_1_linux_x86_64_i8/lib/ 目录下。

---

## 5. SMILES 模块调用与积分计算原理

SMILES 模块通过输入卡 `intyp='SLATER'` 调用，生成的辅助文件名由 `SLFILES=filename` 指定，默认为 "slscratch"。该模块通过高斯基组展开（STO-nG）计算 (AB|AC) 和 (AB|CD) 类型的三中心双电子积分，默认展开长度为 9（STO-9G）。

---

## 6. SMILES 模块的精度限制与调整

由于 STO-9G 展开的积分精度可能无法满足后 HF 方法（特别是高质量基组）的要求，可通过设置变量 `NGSSTO=number of gaussians` 修改展开长度。虽然最大允许值为 30，但实际可用的展开长度取决于量子数，若请求的展开长度不可用，程序会自动选用当前可用的最大值。

---

## 7. SMILES 模块的使用限制

当前版本的 SMILES 模块最多允许 511 个基函数，且不支持收缩基函数。

---

## 8. SMILES 模块输入文件示例

在输入文件中设置 `intyp='SLATER'` 和 `basis=VB1` 即可调用 Slater 基组进行计算，示例几何结构为水分子（O-H 键长 0.96 Å，键角 102 度），计算流程包含 HF、CCSD(T)、MULTI 和 MRCI。

---

## 9. 默认 STO-9G 展开在大基组下的收敛问题

在使用 VB3 等大基组进行 CCSD(T) 计算时，若保持默认的 STO-9G 展开，耦合簇迭代过程可能会出现不收敛（报错 UNREASONABLE NORM 或 NO CONVERGENCE）。这是因为默认展开长度不足以提供精确的积分数据，导致计算异常中断。

---

## 10. 通过增加 NGSSTO 解决收敛问题

通过增大 `NGSSTO` 值可以提高积分精度从而解决收敛问题。实验表明，将 `NGSSTO` 设为 17 时，使用 VB3 基组的 CCSD(T) 计算能够正常收敛，得到能量为 -76.36349351 Hartree。

---

## 11. Slater 函数计算特点与性能

Slater 型轨道（STO）计算能够解决 GTO 中的核-电子 cusp 问题，计算结果较为可靠。在并行计算方面，SMILES 模块似乎仅支持 MPI，不支持 OpenMP。高精度 STO 计算耗时显著，当计算扩展至 STO-20G 且进行 CCSD(T) 计算时，单点计算耗时可能超过 10 小时。

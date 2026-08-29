---
key: t12111
title: Periodic NBO�������
url: http://bbs.keinsci.com/thread-12111-1-1.html
domain: 波函数与电子结构分析
source: keinsci
year: 2019
cards: 11
---

# Periodic NBO������� — 知识卡片

## 1. Periodic NBO 接口程序 pnbo 介绍

pnbo 是用于对周期性体系进行 NBO (自然键轨道) 分析的程序。目前该程序支持 VASP 和 Crystal 等软件的接口。若针对 VASP 编译遇到问题，可以尝试使用 Crystal 接口。

---

## 2. pnbo 源码下载与编译依赖

pnbo 及其接口程序源码可通过 NBO 官方网站获取。该程序接口依赖 Intel MKL 库，通常只能使用 Intel Fortran 编译器配合 MKL 进行编译。如果编译环境的 MKL 版本较新，可能需要对源码进行特定修改才能编译通过。

---

## 3. 修改源码以适配新版 MKL (Fortran 代码)

针对 process_crystal 目录下的 shared.f90 和 periodic_nbo 目录下的 matutil.f90、nbo.f90、nbo_shared.f90、periodic_matutil.f90、pre_nao.f90 等文件，需进行以下替换：将 `USE mkl95_BLAS` 改为 `USE BLAS95`；将 `USE mkl95_LAPACK` 改为 `USE LAPACK95`；将 `CALL ZHEEV_MKL95` 改为 `CALL HEEV`；将所有带 `_MKL95` 后缀的调用（如 `CALL *ABCD_MKL95`，其中 * 为 G 或 Z 等）改为去掉后缀的形式（如 `CALL ABCD`）。

---

## 4. 修改 Makefile 路径配置

需修改 process_crystal 目录下的 makefile 以及 periodic_nbo 目录下的 Makefile.template。修改内容包括更新 MKL 的路径和相关变量，确保拼写正确。完成源码修改后，用修改后的代码直接替换同名原文件，并同步更新 makefile 和 Makefile.template 中的 MKL 目录设置。VASP 接口程序的编译也可参考此方式进行修改。

---

## 5. 编译生成可执行文件

执行 make 命令进行编译，成功后将生成 process_crystal.exe 和 nbo.exe 可执行文件。该编译过程已在 Intel 2017 版本编译器环境下测试通过。

---

## 6. Crystal 计算运行命令

使用 Crystal 软件进行周期性计算时，需准备输入文件（如 mgo.d12 和 mgo.d3），分别运行 crystal 和 properties 模块。运行命令示例为：`./crystal < mgo.d12 > mgo.out` 和 `./properties < mgo.d3 > mgo.pout`。

---

## 7. Crystal 输入文件 SHRINK 与 NEWK 参数设置

pnbo 程序对 k 点网格有特定要求。输入文件 mgo.d12 中的 SHRINK 参数以及 mgo.d3 中的 NEWK 参数必须设置为一致的数值，且该数值不能过小，以确保满足精度要求。

---

## 8. 运行 Crystal 计算的输出流处理技巧

pnbo 接口脚本需要读取 mgo.out 文件开头的特定信息。如果 mgo.out 文件开头不包含这些信息（例如文件为空或格式不对），会导致后续报错。建议使用重定向追加的方式运行 crystal，例如：`cp mgo.d12 mgo.out` 后执行 `./crystal < mgo.d12 >> mgo.out`。

---

## 9. Crystal 输出文件转换与处理

Crystal 计算完成后，需运行转换脚本和接口程序生成 NBO 输入文件。命令依次为：`./read_crystal.py mgo.out > cry2nbo.out` 和 `./process_crystal.exe cry2nbo.out KRED.DAT`。运行成功后将生成 NBO.out 和 NBO_mat.out 等必要文件。

---

## 10. 运行 pnbo 分析

使用生成的 NBO.out 文件运行 nbo.exe 以执行 NBO 分析。命令示例为：`./nbo.exe NBO.out > mgo_nbo.out`。分析结果将输出到 mgo_nbo.out 文件中。

---

## 11. pnbo 结果文件与进阶配置

pnbo 运行结束后会生成一个名为 nbo.config 的配置文件。用户可以通过修改该文件中的参数来控制后续功能，例如生成 cube 文件等可视化数据。具体的参数配置方法和说明可参考程序包自带的 READ_ME.txt 文件。该方法已在 Crystal 09 和 14 版本上验证通过。

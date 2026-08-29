---
key: t15304
title: ����xtb��amberQM/MMģ��
url: http://bbs.keinsci.com/thread-15304-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2019
cards: 11
---

# ����xtb��amberQM/MMģ�� — 知识卡片

## 1. AMBER QM/MM 计算效率

AMBER 软件包中的 QM/MM 计算效率并不算高。许多研究者在模拟中并不采用全 QM 计算，而是使用一些半经验方法来替代全 QM 计算，以提升计算速度。

---

## 2. AMBER 内置半经验方法

AMBER 源代码内置的半经验方法主要包括 PM6 和 DFTB3。AMBER 中的 PM6 实现仅包含 DFT-D 色散校正，DFTB3 实现则不包含 DFT-D 色散校正。

---

## 3. AMBER 与 xtb 接口的现状

xtb 程序可作为 QM 区域的计算引擎以替代 AMBER 原有的 QM/MM 计算模块。虽然存在名为 Holger Kruse 开发的 AMBER/xtb 接口，但其主要基于 AMBER14 模型，且可能涉及商业授权问题。

---

## 4. ORCA 对 xtb 的支持

ORCA 软件从 4.2 版本开始支持调用 xtb 进行计算。由于 AMBER 原生支持 ORCA，因此可以通过搭建 AMBER/ORCA/xtb 的组合来实现 xtb 参与的 QM/MM 计算。

---

## 5. ORCA/xtb 接口的兼容性缺陷

ORCA/xtb 接口生成的点电荷梯度文件 `pcgrad` 其格式与 AMBER 的 AMBER/ORCA 接口不兼容。文件格式差异主要体现在点电荷的排列顺序和符号定义上。

---

## 6. 修改版 xtb 程序

针对 `pcgrad` 格式不兼容的问题，存在一个修改版的 xtb 源代码（托管于 GitHub 仓库 xiki-tempula/xtb）。该版本生成的 `pcgrad` 文件能够被 AMBER 的 AMBER/ORCA 接口正确读取。

---

## 7. xtb 程序的编译环境

编译修改版的 xtb 程序需要使用 Intel 编译器套件。编译工具链要求 Meson 版本大于 0.49 并结合 Ninja 进行构建，Meson 需单独通过 git 源码进行安装。

---

## 8. xtb 编译命令示例

在配置编译环境时，需设置 Intel 编译器相关的环境变量。示例命令为 `export FC=ifort CC=icc CXX=icpc`。

---

## 9. xtb 的静态编译与多线程问题

xtb 程序采用强制静态编译方式，这可能导致与静态 pthread 库出现兼容性问题。解决该问题可以使用一个名为 dendrite 的修改版 xtb 代码分支，该分支采用了一种“粗糙”的方式解决了此类问题。

---

## 10. AMBER 调用 ORCA/xtb 的配置

将编译生成的 xtb 可执行文件放置在 ORCA 的目录下并重命名为 `otool_xtb`。通过 AMBER 调用 ORCA 时，需使用名为 `orc_job.tpl` 的模板文件，并需根据实际情况修改内存、线程数以及 QM 原子切割（qmcut）等参数。

---

## 11. AMBER 输入文件与模板文件

AMBER 的计算输入文件示例为 `ua_equil.in`，ORCA 的作业模板文件示例为 `orc_job.tpl`。这些文件用于配置和执行 AMBER/ORCA/xtb 联合计算。

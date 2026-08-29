---
key: t23319
title: ʹ��ElaStic��Quantum Espresso���㵯�Գ�����ģ��
url: http://bbs.keinsci.com/thread-23319-1-1.html
domain: 其他量化软件
source: keinsci
year: 2021
cards: 10
---

# ʹ��ElaStic��Quantum Espresso���㵯�Գ�����ģ�� — 知识卡片

## 1. ElaStic 版本与 Python 环境依赖

ElaStic 软件存在基于 Python 2.* 的旧版本（ElaStic 1.1）和基于 Python 3.* 的新版本（ElaStic 2020）。新版本修正了 Python 3.* 的兼容性问题并提高了精度，使用新版本需要安装 numpy，若同时安装两个版本 Python 需在使用时进行切换。

---

## 2. ElaStic 环境变量配置

解压 ElaStic 1.1 安装包后，需设置环境变量 `ElaSticROOT` 和 `PATH` 指向安装目录，如 `export ElaSticROOT=/home/$USER/software/ElaStic_1.1` 和 `export PATH=/home/$USER /software/ElaStic_1.1:$PATH`。

---

## 3. 绘图工具 xmgrace 安装

ElaStic 1.1 依赖的绘图工具 xmgrace 在非开源系统中可能无法从官网下载，可通过系统包管理器安装（如 Ubuntu 使用 `sudo apt-get install grace`，CentOS 使用 `sudo yum install grace`，SLES 使用 `sudo zypper install xmgrace`）。

---

## 4. Sgroup 工具安装

Sgroup 用于判断空间群，需解压 ElaStic 附带的 `adon_v1_0.tar.gz`，进入 `SpaceGroups` 目录执行 `make` 编译，并将生成的 `sgroup` 可执行文件复制到上级目录。

---

## 5. Quantum Espresso 弹性常数计算输入文件设置

使用 Quantum Espresso 配合 ElaStic 进行计算时，输入文件（如 pw.x）需设置 `calculation = 'relax'`、`tprnfor = .true.`、`forc_conv_thr = 1d-4`、`tstress = .true.` 等参数，并注意 `ibrav = 0` 且晶胞参数使用 `alat`（单位为 a.u.）。

---

## 6. ElaStic_Setup 生成计算文件流程

在包含输入文件的目录下运行 `ElaStic_Setup`，依次选择 Quantum ESPRESSO（选项 3）、Energy 方法（选项 1）、二阶弹性常数（选项 2），并输入输入文件名、最大拉格朗日应变值（建议 0.030-0.150）及畸变结构数量（奇数且大于 4），脚本将自动生成畸变结构目录。

---

## 7. 批量运行 Quantum Espresso 计算

为批量运行生成的畸变结构计算，可编写 Shell 脚本 `elastic_pwx_run.sh`，通过循环遍历 `Dst??` 及其子目录，对每个 `.in` 文件执行 `pw.x < ${inf} > ${inf//in/out}` 命令，脚本需赋予执行权限。

---

## 8. 弹性常数数据分析与绘图

计算完成后，在 `***_2nd` 目录执行 `ElaStic_Analyze` 命令，程序将自动调用 xmgrace 绘制 Energy-vs-Strain 关系图（需 GUI 环境支持 X11 转发）。手动绘图或分析时，可读取 `Energy-vs-Strain` 目录下 `Dst**_d2e.dat` 文件中的原始数据。

---

## 9. 应变范围与拟合阶数调整

为获得准确的弹性常数，需观察拟合曲线的线性区间，编辑 `ElaStic_2nd.in` 文件调整 `eta_max`（应变范围）和 `Fit_order`（拟合阶数）。例如，排除四阶项波动较大的区域后，可将参数设置更新为 `Dst01 0.05 4` 等具体数值。

---

## 10. 弹性常数计算结果提取

修正 `ElaStic_2nd.in` 参数后，执行 `ElaStic_Result` 命令，程序将在 `ElaStic_2nd.out` 文件中输出弹性常数刚度矩阵、柔度矩阵以及体积模量、剪切模量、杨氏模量、泊松比和弹性各向异性等计算结果。

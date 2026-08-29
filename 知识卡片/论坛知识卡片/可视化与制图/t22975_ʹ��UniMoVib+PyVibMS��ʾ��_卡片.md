---
key: t22975
title: ʹ��UniMoVib+PyVibMS��ʾ�������������񶯷������
url: http://bbs.keinsci.com/thread-22975-1-1.html
domain: 可视化与制图
source: keinsci
year: 2021
cards: 11
---

# ʹ��UniMoVib+PyVibMS��ʾ�������������񶯷������ — 知识卡片

## 1. PyVibMS 与 UniMoVib 的协同工作原理

PyVibMS 支持通过标准格式的 XYZ 坐标文件和包含振动模式的文资料件对分子振动进行可视化。UniMoVib 能够从近 30 种主流量子化学程序中读取 Hessian 矩阵等数据，计算出频率、红外强度和拉曼强度，并统一输出为 PyVibMS 可识别的 XYZ 文件和 mode 文件。通过 UniMoVib 作为中间桥梁，PyVibMS 可以对原本不直接支持的量化软件计算得到的振动分析结果进行可视化。

---

## 2. UniMoVib 的基本功能与获取方式

UniMoVib 是一个用 Fortran 编写的开源工具，能够从多种量化程序的输出文件中提取 Hessian 矩阵数据，计算频率、红外强度和拉曼强度，并生成可视化所需的文件。该工具的源代码、二进制文件及部署文件均托管在 GitHub 平台供用户获取。

---

## 3. UniMoVib 在 Windows 系统下的安装

在 Windows 系统下安装 UniMoVib，需从 GitHub 页面下载 ZIP 压缩包并解压。解压后得到的文件夹中的 win32 目录包含可直接使用的可执行文件。

---

## 4. UniMoVib 在 Linux 和 Mac 系统下的编译安装

在 Linux 或 Mac 系统下，需打开终端窗口进入 UniMoVib-master 源码目录，依次执行 `cd src`、`mkdir object`、`make` 命令进行编译。编译完成后，会在 UniMoVib-master 目录下生成名为 unimovib.exe 的可执行文件。此过程要求系统环境已安装 gfortran 编译器。

---

## 5. 使用 UniMoVib 处理 CFOUR 计算结果的输入文件设置

利用 UniMoVib 处理 CFOUR 的振动分析结果时，需编写名为 job.inp 的输入文件。该文件需指定 qcprog="cfour" 以表明程序来源，并将 ifpyvibms 参数设置为 .true. 以生成 PyVibMS 兼容的输出格式。$qcdata 模块中需指定 fchk 参数为 CFOUR 的输出文件名（如 h2o.out），若涉及几何结构还需指定 geom 参数（如 GRD）。

---

## 6. UniMoVib 对 CFOUR 输出文件的数据要求

CFOUR 的输出文件需包含 Hessian 矩阵信息，其生成的 GRD 文件包含分子结构信息及各原子的梯度数据（优化完成时梯度应接近 0）。UniMoVib 依赖这些文件来提取必要的振动分析数据。

---

## 7. 使用 UniMoVib 处理 CFOUR 数据的执行与输出

完成 job.inp 设置后，在终端执行 `./unimovib.exe` 即可运行 UniMoVib。程序运行后会生成 job.out 输出文件，其中包含简正振动的频率、对称性、模式矢量、红外强度及拉曼强度等数据。此外，UniMoVib 还会生成 system.xyz 和 pyvibms_mode_full.txt 两个供 PyVibMS 读取的文件。

---

## 8. CFOUR 振动分析结果在 PyVibMS 中的可视化

在 PyMOL 中启动 PyVibMS 插件后，分别将 UniMoVib 生成的 system.xyz 作为 Input File，pyvibms_mode_full.txt 作为 Mode File 载入，即可对 CFOUR 计算得到的分子振动结果进行可视化查看。

---

## 9. 使用 UniMoVib 处理 Molpro 计算结果

对于 Molpro 程序，UniMoVib 的输入文件需设置 qcprog="molpro" 并将 ifpyvibms 设为 .true.。$qcdata 模块中的 fchk 参数需指向 Molpro 的输出文件（如 ch4.out），该文件需包含结构和振动分析信息。运行 UniMoVib 后生成的 XYZ 和 mode 文件可直接用于 PyVibMS 可视化。

---

## 10. UniMoVib 对 BDF 程序的支持与文件格式

BDF 程序输出的特定格式文件（如 .umv 文件）包含了直角坐标和 Hessian 矩阵信息，UniMoVib 可以直接读取该类文件而无需额外转换。对应的 UniMoVib 输入文件（如 .unimovib.input）和输出文件（如 .unimovib.out）处理逻辑与其他量化软件类似，最终生成用于 PyVibMS 可视化的标准文件。

---

## 11. UniMoVib 的通用扩展性

UniMoVib 能够支持的量化软件范围不仅限于 CFOUR、Molpro 和 BDF，还涵盖其它多种程序。只要在相应的输入文件中将 ifpyvibms 参数设置为 .true.，UniMoVib 即可生成 PyVibMS 能够自动读取的必要文件。

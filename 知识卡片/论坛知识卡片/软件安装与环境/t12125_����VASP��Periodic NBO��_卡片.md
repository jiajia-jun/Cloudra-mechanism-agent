---
key: t12125
title: ����VASP��Periodic NBO����ͼ򵥲���
url: http://bbs.keinsci.com/thread-12125-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2019
cards: 16
---

# ����VASP��Periodic NBO����ͼ򵥲��� — 知识卡片

## 1. VASP 与 Periodic NBO 资源链接

Periodic NBO 相关的简易操作介绍链接如下：VASP 与 SSAdNDP 的结合参考链接为 http://bbs.keinsci.com/thread-12385-1-1.html，Crystal 与 Periodic NBO 的结合参考链接为 http://bbs.keinsci.com/thread-12111-1-1.html。官方软件主页为 https://schmidt.chem.wisc.edu/nbosoftware，参考论文为 Dunnington, B. D.; Schmidt, J. R. J. Chem. Theory Comput., 2012, 8, 1902–1911。

---

## 2. Periodic NBO 软件下载文件

VASP 用户需要下载 projection_v.1.1.2.tgz，所有用户都需要下载 periodic_nbo_v.1.1.tgz。Crystal 用户还需要额外下载 CRYSTAL_interface.tgz，且 Crystal 用户可参考 http://bbs.keinsci.com/thread-12111-1-1.html 获取具体的编译方法。

---

## 3. VASP 版本兼容性与补丁要求

目前 ssNBO 和 ssAdNDP 仅支持 vasp.5.4.1.24Jun15 之前的版本，使用 vasp.5.4.1.05Feb16 和 5.4.4 版本通常无法直接使用。若尝试在这些不兼容版本上报错，尝试修改源文件不一定能成功，5.4 和 5.3 版本的编译方法存在很大差异。

---

## 4. 编译环境与 MKL 库兼容性

Intel 2013 之前版本的 Intel MKL 库可能导致编译问题，推荐使用 2015 年之后的版本。若使用较新的 MKL 版本，可能需要对相关代码进行修改以适配。

---

## 5. 参考编译环境示例

参考的编译环境为 composer_xe_2013_sp1.2.144 和 vasp.5.4.1.24Jun15。VASP 的自行编译可参考 http://bbs.keinsci.com/thread-11812-1-1.html，服务器上编译可参考 http://bbs.keinsci.com/thread-11111-1-1.html。

---

## 6. VASP 源码补丁步骤

将 projection_v.1.1.2.tgz 解压得到的 proj_VASP_5.4.patch 和 projection_output.F 文件复制到 VASP 的 src/ 目录下。在 src/ 目录下执行命令 `patch < proj_VASP_5.4.patch` 应用补丁。对于 VASP5.3，需在 ~/src/.objects 文件的 SOURCE 里添加 projection_output.o；对于 VASP5.4，则不需要添加。

---

## 7. 编译 projection.exe

使用 Intel 2013 编译器可以成功编译 projection.exe，使用 Intel 2015 及之后的版本可能无法成功编译。Makefile 文件通常无需修改，直接执行 `make` 命令即可生成 projection.exe。

---

## 8. 编译 nbo.exe 的路径修改

编译 nbo.exe 之前需修改 Makefile.template 文件，需将默认的 `MODULE_PATH=/opt/intel/mkl/10.0.3.020/lib/em64t` 替换为实际路径 `MODULE_PATH=/opt/intel/composer_xe_2013_sp1.2.144/mkl/include/intel64/lp64/`。`LDFLAGS=` 参数也需要进行相应的修改。

---

## 9. 编译 nbo.exe 的 Makefile 示例

成功的 Makefile.template 配置示例如下：
- `MODULE_PATH=/opt/intel/composer_xe_2013_sp1.2.144/mkl/include/intel64/lp64/`
- `MKL_LIB=/opt/intel/composer_xe_2013_sp1.2.144/mkl/lib/intel64`
- `FC=ifort`
- `LD=ifort`
- `FFLAGS= -vec-report0 -openmp -I $(MODULE_PATH)`
- `LDFLAGS=-L${MKL_LIB} -lmkl_core -lmkl_intel_lp64 -lmkl_sequential ${MKL_LIB}/libmkl_blas95_lp64.a ${MKL_LIB}/libmkl_lapack95_lp64.a -openmp`

---

## 10. VASP 投影计算与 INCAR 设置

在 INCAR 文件中设置 `LNBO = True`，即可让 VASP 输出投影所需文件。运行成功后会生成一个 wavefunction.dat 文件。

---

## 11. 基组文件准备

需要准备高斯基组文件 basis.inp（Gaussian94 format），该文件可从 EMSL 基组库网站 https://bse.pnl.gov/bse/portal 生成。示例中使用的基组为 3-21G(d) basis set。

---

## 12. 运行投影程序

执行命令 `./projection.exe basis.inp wavefunction.dat NBO.out` 进行平面波基组到高斯基组的投影。计算过程会生成 NBO.out、NBO_mat.out、band_spillover.out 和 spillover.out 文件。

---

## 13. 运行 NBO 分析程序

执行命令 `./nbo.exe NBO.out` 运行 NBO 程序，结果将输出到屏幕上。nbo.config 文件用于判断孤对电子和键的阈值。

---

## 14. nbo.config 参数配置示例

nbo.config 文件中，孤对电子 (LP) 的占据数截断值默认为 1.60，双中心键 (BD) 的占据数截断值默认为 1.85。
- `1.60` 表示 Occupancy cutoff for one-center NBOs
- `1.85` 表示 Occupancy cutoff for two-center NBOs
可视化输出控制参数中，`F` 表示不输出 .cube 文件，`vis_start vis_end` 设为 `0 -1`。

---

## 15. NBO 输出结果解读示例

对于硅体系，NBO6.0 输出结果中包含 BD（成键）、BD*（反键）和 RYD（里德堡）轨道信息。输出内容包括轨道占据数 (Occ)、极化度 (Polarization) 和杂化成分 (Hybrid s%/p%/d%/f%)，以及轨道系数。

---

## 16. ssAdNDP 使用方法参考

ssAdNDP 的使用方法与 ssNBO 非常相似，具体方法可参考官方网站 http://ion.chem.usu.edu/~boldyrev/ssadndp.php。

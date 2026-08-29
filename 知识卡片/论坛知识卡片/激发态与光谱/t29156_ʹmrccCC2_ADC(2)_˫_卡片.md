---
key: t29156
title: ʹ��mrcc����CC2/ADC(2)/˫�ӻ�TD-DFT����ļ���̬����
url: http://bbs.keinsci.com/thread-29156-1-1.html
domain: 激发态与光谱
source: keinsci
year: 2022
cards: 16
---

# ʹ��mrcc����CC2/ADC(2)/˫�ӻ�TD-DFT����ļ���̬���� — 知识卡片

## 1. MRCC 程序官网地址

MRCC 程序的官方网站为 https://www.mrcc.hu/。
该网站提供程序下载、文档及相关资源。
用户可通过此网站获取最新版本的二进制包或源码。

---

## 2. MRCC 激发态计算方法支持列表

MRCC 支持多种激发态计算方法，包括 CIS, TDA, TDDFT, CIS(D), ADC(2) 及双杂化 TDDFT。
程序支持 ADC(2), CC2, CIS(D), DIS(D) 及其自旋分量缩放 (SCS) 和相同轨道缩放 (SOS) 版本。
计算可同时处理单重态和三重态。
所有计算均支持分辨率恒等 (RI) 近似以加速。
程序不支持 Meta-GGA 泛函的 TDDFT，仅支持直角坐标系，不支持亚原子分辨率，且不支持自旋轨道耦合 (SOC) 和激发态密度输出。
CC2 方法无法计算偶极允许的跃迁。
CIS 和 TD-HF 支持计算跃迁偶极矩。
程序仅支持 OpenMP 并行，不支持 MPI 并行。

---

## 3. MRCC 下载与安装步骤

注册账号并下载二进制压缩包，如 `mrcc.2022-03-18.binary.tar`。
创建目录 `mrcc-2022`，将压缩包移入并解压。
将解压后的当前目录路径添加到环境变量 PATH 中，并重新加载配置文件。
安装完成后，进入 `MTEST` 目录运行 `./mest` 进行测试，屏幕显示约 1000 行输出文件内容并提示结束即为成功。
相关命令示例：
```bash
mkdir mrcc-2022
mv mrcc.2022-03-18.binary.tar mrcc-2022
cd mrcc-2022
tar -xvf mrcc.2022-03-18.binary.tar
echo 'PATH='$(pwd)':$PATH' >> ~/.bashrc
source ~/.bashrc
```

---

## 4. MRCC 输入文件 MINP 格式

MRCC 输入文件通常命名为 `MINP`，参数通过 `key=value` 的形式设置。
常用设置包括内存 (`mem`)、计算类型 (`calc`)、基组 (`basis`)、泛函 (`dft`)、单重态数 (`nsing`)、三重态数 (`ntrip`)、电荷 (`charge`)、多重度 (`mult`) 和几何格式 (`geom`)。
几何信息紧随参数之后输入。
示例（对应 Gaussian 的 B3LYP/def2-SVP TDDFT 计算）：
```text
mem=10GB
calc=TDDFT
basis=def2-SVP
dft=B3LYP3
nsing=4
ntrip=3
charge=0
mult=1
geom=xyz
4
Formaldehyde
C -3.14381262 -0.27313266 0.00000000
O -1.91649562 -0.27313266 0.00000000
H -3.73595762 0.66627134 0.00000000
H -3.73595762 -1.21253666 0.00003900
```

---

## 5. MRCC 命令行运行方式

设置 OpenMP 线程数和环境变量绑核策略后，使用 `dmrcc` 命令运行。
标准命令会将输出重定向到屏幕并保存到文件。
运行命令示例：
```bash
export OMP_NUM_THREADS=16
export MKL_NUM_THREADS=16
export OMP_PLACES=cores
export OMP_PROC_BIND=spread,close
dmrcc | tee mrcc.out
```

---

## 6. genmrcc.sh 脚本功能概述

`genmrcc.sh` 是用于自动生成 MRCC 计算任务目录和输入文件的 Shell 脚本。
脚本支持从 XYZ 文件自动生成 `MINP` 文件和运行脚本 `runmrcc.sh`。
运行后会生成以计算方法命名的文件夹，包含所有必要文件。
脚本安装后需赋予执行权限：`chmod +x genmrcc.sh`。

---

## 7. genmrcc.sh 脚本参数说明

`-m` 指定内存大小（如 10GB）。
`-n` 指定 OpenMP 线程数，影响并行效率。
`-p` 指定计算方法类型，如 `tddft`, `tda`, `scs-cc2`, `scs-adc(2)`。
`-b` 指定基组，如 `def2-SVP`。
`-d` 指定 DFT 泛函，如 `b2plyp`。
`-D` 指定使用双杂化或高级方法选项，适用于 `cis(d)`, `adc(2)` 及其 SCS/SOS 版本。
`-S` 设置单重态数量。
`-T` 设置三重态数量。
`-R` 设置加速算法参数（如 local fitting domains 参数）。
`-C` 设置 CC 计算收敛阈值（如 `cctol`）。
`-s` 指定输出文件名后缀。

---

## 8. 使用脚本运行 SCS-CC2 计算示例

使用 `genmrcc.sh` 生成 SCS-CC2 计算任务，指定基组为 cc-pvdz，加速参数为 3，收敛阈值为 5，单重态 4 个，三重态 3 个。
生成任务目录后，进入目录执行 `runmrcc.sh` 开始计算。
计算过程中屏幕会有进度显示，约 2 分钟后开始计算，完成后目录下包含结果文件 `runmrcc.out` 和耗时文件 `runtime`。
命令示例：
```bash
genmrcc.sh -n 8 -m 10GB -p scs-cc2 -b cc-pvdz -S 4 -T 3 -R 3 -C 5 BN.xyz
sh BN_SCS-CC2/runmrcc.sh
```

---

## 9. mrccST.py 脚本结果提取功能

`mrccST.py` 是用于提取 MRCC 计算结果中激发态信息的 Python 脚本。
运行脚本可读取任务目录下的输出文件并提取激发态数据。
支持指定目录名提取，也可使用通配符 `*` 同时提取当前目录下所有任务的结果。
脚本会自动按能量从低到高排序激发态。
命令示例：
```bash
mrccST.py BN_SCS-CC2
mrccST.py *
```

---

## 10. MRCC 并行效率与核心数关系

MRCC 的计算速度与 CPU 核心数在低核数下呈近似线性增长关系。
在使用 SCS-CC2 方法时，从 1 核到 8 核加速比接近线性。
8 核到 32 核之间加速效果开始下降，超过 32 核后并行效率进一步衰减。

---

## 11. MRCC 加速与精度策略

MRCC 提供多种加速策略，包括 CIS 模块的强制 RI 加速、减少计算成本的 `redcost_exc` (local fitting domains/state-averaged NOs)、局部相关方法 `localcc` 以及快速多极子方法 `fmm`。
`genmrcc.sh` 脚本中的 `-R` 对应 `redcost_exc`，`-L` 对应 `localcc`。
针对不同激发态性质（LE, MR, ICT, TICT, CT-like），推荐不同的加速参数组合。

---

## 12. 加速参数对精度的影响

对于包含 MR（多参考）特征的体系，必须开启 `localcc`，仅调整 `redcost_exc` 往往效果不佳。
对于大多数体系，`localcc` 是加速的关键，而 `redcost_exc` 设为 3 或 8 对结果影响较小（误差 < 0.01 eV）。
若仅计算 SCS-CC2 的单重态，关闭 `localcc` 仅使用 `redcost_exc` 也能获得较好的加速效果且结果可接受。

---

## 13. 修改收敛阈值的加速效果

将 CC 计算的收敛阈值从默认的 6 放宽到 5，精度损失可忽略，速度可提升约 1.5 倍。
使用 `redcost_exc=3` 代替 `redcost_exc=8`，误差小于 0.01 eV，速度可提升约 1.5 倍。
同时使用 R3 和 C5 参数（对应脚本 `-R 3 -C 5`），总体速度可提升约 2.25 倍。
`cctol=4` 通常可接受，但复杂体系可能产生较大误差。

---

## 14. 基组选择与计算耗时关系

`def2-TZVP` 和 `cc-pVTZ` 精度相当，但 TZVP 基组耗时更长。
从 `cc-pVDZ` 到 `cc-pVTZ`，耗时增加约 8.5 倍；若同时使用 C5 和 R3 双重加速，耗时可降至 20 倍左右。
对于大体系，强烈推荐使用双重加速策略。
`def2-SVP` 系列基组与 `cc-pVDZ` 无显著差别，推荐使用。
使用 RI 加速的 MRCC 在 R3/C5 设置下，计算单个激发态的耗时约为同类程序（如 adcc）的 1/10。

---

## 15. 激发态数量对计算速度的影响

计算耗时与请求的激发态数量（单重态和三重态总和）大致呈线性关系。
计算更多激发态会显著增加总计算时间。
对于 HOMO 和 LUMO 发生反转的复杂体系，需额外计算一些高能态以确保低能态的正确性。

---

## 16. MRCC 方法性能 Benchmark 总结

对于 MR-TADF 体系，双杂化方法（ADC2, CC2, DIS(D)）的 SCS/SOS 版本通常表现更好，误差较低。
TDDFT 倾向于高估或低估能隙，具体取决于 HF 交换成分的比例；TDA 相比 TDDFT 误差通常更小。
TD-DH-DFT（双杂化）结合 CIS(D) 表现稳定。
对于 LE（局域激发）、ICT（分子内电荷转移）、CT-like（类电荷转移）及 TICT（扭曲分子内电荷转移）体系，TD-DH-DFT + CIS(D) 通常是最优选择之一。
纯 TDDFT 方法在处理 CT 态和 TICT 态时，若 HF% 较低容易导致低估能隙。
XYG3 的 TDDFT 版本表现较好，但需使用特定的补丁版本。

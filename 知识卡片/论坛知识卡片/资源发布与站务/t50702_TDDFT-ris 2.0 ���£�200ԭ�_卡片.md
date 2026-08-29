---
key: t50702
title: TDDFT-ris 2.0 ���£�200ԭ����ϵ��ѹ��, ֧��Multiwfn
url: http://bbs.keinsci.com/thread-50702-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2024
cards: 12
---

# TDDFT-ris 2.0 ���£�200ԭ����ϵ��ѹ��, ֧��Multiwfn — 知识卡片

## 1. TDDFT-ris 方法简介与原理

TDDFT-ris (Resolution-of-the-identity with minimal auxiliary basis sets) 是一种基于最小辅助基组的含时密度泛函理论计算方法。该方法通过使用极简的辅助基组（如 J 使用 sp，K 使用 s 基组）来大幅降低计算成本，适用于大体系的激发态计算。
- Zehao Zhou 等人在 *The Journal of Physical Chemistry Letters* (2023) 提出了该方法，旨在解决有机分子电子激发光谱计算中的效率问题。
- 该方法的核心思想是牺牲少量精度换取计算速度的大幅提升，使得数百原子的体系 TDDFT 计算成为可能。
- TDDFT-ris 的计算复杂度约为 N^4，但由于辅助基集极小，实际计算速度优于传统的 TDDFT-as 方法，接近 N^3 量级。
- 计算效率提升主要得益于 AO 到 MO 变换时间的显著减少，但代价是对内存的需求较高。

---

## 2. 环境安装依赖 (Conda 方式)

安装基于 MOKIT、PySCF 和 pyscf-forge 的 TDDFT-ris 计算环境，推荐使用 mamba 或 conda 进行包管理。
- 创建并激活名为 `mokit-ris` 的 Python 3.11 环境，并安装 MOKIT：`mamba create -n mokit-ris python=3.11 mokit -c mokit -c conda-forge` 和 `mamba activate mokit-ris`。
- 安装 PySCF：`mamba install pyscf -c conda-forge`。
- 安装 pyscf-forge：`pip install pyscf-forge`。

---

## 3. 获取并配置代码库

使用 `pyscf_TDDFT_ris` 代码库进行计算前，需要将代码路径添加到 Python 环境变量中。
- 通过 git 命令克隆代码库到本地：`git clone git@github.com:John-zzh/pyscf_TDDFT_ris.git`。
- 设置 `PYTHONPATH` 环境变量，将代码库的绝对路径（`absolue_path_to_ris_repo`）加入其中：`export PYTHONPATH=absolue_path_to_ris_repo:$PYTHONPATH`。

---

## 4. Python 脚本调用示例 (API 模式)

利用 PySCF 和 MOKIT 的接口，可以在 Python 脚本中直接调用 TDDFT-ris 进行计算。
- 导入必要的模块：`import pyscf.tdscf.ris as ris` 和 `from mokit.lib.fch2pyscf import get_mf_from_fch`。
- 从 Gaussian 的 fch 文件读取分子信息并生成均值场对象：`mf = get_mf_from_fch('Vitamin_C.fch', functional='pbe0')`。
- 初始化 TDDFT-ris 计算对象并运行核函数：`td = ris.TDDFT(mf=mf, nstates=5, spectra=True, print_threshold=1e-1, verbose=4)` 和 `td.kernel()`。
- 该过程无需输入复杂的参数，即可完成计算并输出结果。

---

## 5. 命令行运行 TDDFT-ris 计算

通过主程序 `main.py` 可以在命令行中执行 TDDFT-ris 计算，需指定 fch 文件、泛函、态数等参数。
- 激活 conda 环境并设置环境变量（如线程数）：`export MKL_NUM_THREADS=4` 和 `export OMP_NUM_THREADS=4`。
- 执行计算命令：`python absolute_path_to_ris_repo/main.py -f gau.fch -func pbe0 -n 5 -M 4000 -pt 0.0001`。
- 参数说明：`-f` 指定 fch 文件；`-func` 指定泛函（如 pbe0，也可通过 `-ax` 指定 HF 交换系数）；`-n` 指定计算激发态数量；`-M` 指定内存（GB）；`-pt` 设置打印跃迁系数的阈值（默认 0.05）。

---

## 6. ORCA 输出文件转换方法

若使用 ORCA 进行 DFT 基态计算，需将生成的 gbw 文件转换为 fch 文件以供 MOKIT 读取。
- 首先使用 ORCA 自带工具生成 mkl 文件：`orca_2mkl molecule -mkl`。
- 然后使用 MOKIT 提供的工具将 mkl 转换为 fch：`mkl2fch molecule.mkl molecule.fch`。

---

## 7. 计算性能与基准测试

TDDFT-ris 在大体系计算中表现出显著的效率优势，计算时间随原子数增加而线性或近线性增长。
- 117 原子体系 (wb97x-d/def2-TZVP, 10 states) 在 4 核 16G 内存下耗时约 2 分钟。
- 243 原子体系 (wb97x-d3bj/def2-TZVP, 10 states) 在 4 核 64G 内存下耗时约 12 分钟。
- 362 原子体系 (wb97x-d3bj/def2-TZVP, 10 states) 在 4 核 64G 内存下耗时约 1 小时 10 分钟。

---

## 8. 程序优化与截断策略

代码实现中包含多项针对内存和速度的优化策略，包括轨道截断和精度控制。
- J 和 K 积分使用不同的辅助基组：J 使用 sp 轨道以保证高精度，K 使用 s 轨道以降低成本。
- 对 K 积分实施了轨道截断策略，默认删除 HOMO 以上 >40eV 以及 LUMO 以下 >40eV 的占据/空轨道，以减少计算量且基本不影响精度。
- 计算支持单精度浮点数以降低内存消耗。
- 支持混合泛函和交换积分系数指定。

---

## 9. 输出文件说明

TDDFT-ris 计算完成后，会在当前目录生成三个文资料件，分别用于后续的光谱分析和波函数分析。
- `gau_TDDFT_ris_eV_os_Multiwfn.txt`：包含激发能、波长 和振子强度，可用于绘制 UV-Vis 光谱。
- `gau_TDDFT_ris_eV_rs_Multiwfn.txt`：包含激发能和旋转强度，可用于绘制 ECD 光谱。
- `gau_TDDFT_ris_coeff_Multiwfn.txt`：包含跃迁系数数据，可用于 Multiwfn 进行 NTO 等高级分析。

---

## 10. 使用 Multiwfn 绘制 UV-Vis 光谱

利用 Multiwfn 读取 TDDFT-ris 生成的数据文件，可以绘制并与标准 TDDFT 结果对比 UV-Vis 光谱。
- 在 Multiwfn 中选择 `11 Plot IR/Raman/UV-Vis/ECD/VCD/ROA/NMR spectrum` -> `3:UV-Vis` -> `0 Plot spectrum`。
- 直接载入 `gau_TDDFT_ris_eV_os_Multiwfn.txt` 文件即可绘图。
- 可通过创建 `multiple.txt` 文件同时载入 Gaussian 的 log 文件和 RIS 结果文件，进行光谱的叠加对比。

---

## 11. 使用 Multiwfn 进行 NTO 分析

结合 Multiwfn 和 TDDFT-ris 的输出文件，可以生成自然跃迁轨道 (NTO) 以分析激发态性质。
- 首先在 Multiwfn 中打开基态的 fch 文件（如 `gau.fch`）。
- 选择 `18 Electron excitation analysis` -> `6 Generate natural transition orbitals (NTOs)`。
- 输入跃迁系数文件路径 `gau_TDDFT_ris_coeff_Multiwfn.txt` 并选择感兴趣的激发态（如态 2）。
- 选择输出 NTO 轨道到 `.mwfn` 文件，随后可使用 VMD 或其他软件可视化生成的 NTO 文件。

---

## 12. 文献引用与致谢

使用该 TDDFT-ris 实现及相关工具时，需引用原始方法论文、优化算法论文以及依赖的软件包。
- **方法论文**：Zhou, Zehao, Fabio Della Sala, and Shane M. Parker. *Minimal auxiliary basis set approach for the electronic excitation spectra of organic molecules*. J. Phys. Chem. Lett. 14, no. 7 (2023): 1968-1976.
- **轨道截断技术**：Zhou, Zehao, and Shane M. Parker. *Converging Time-Dependent Density Functional Theory Calculations in Five Iterations with Minimal Auxiliary Preconditioning*. J. Chem. Theory Comput. 20, no. 15 (2024): 6738-6746.
- **思想起源**：Giannone, Giulia, and Fabio Della Sala. *Minimal auxiliary basis set for time-dependent density functional theory...*. J. Chem. Phys. 153, no. 8 (2020).
- **软件包**：pyscf-TDDFT-ris (Zehao Zhou), MOKIT (Jingxiang Zou), PySCF (Q. Sun, et. al.).

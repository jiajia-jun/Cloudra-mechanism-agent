---
key: t54051
title: Using the Universal Model for Atoms for single point calculations
url: http://bbs.keinsci.com/thread-54051-1-1.html
domain: 量子化学方法
source: keinsci
year: 2025
cards: 20
---

# Using the Universal Model for Atoms for single point calculations — 知识卡片

## 1. UMA 模型概述

UMA (Universal Model for Atoms) 是由 Facebook AI 研究团队开发的机器学习原子间势 (MLIP)。该模型基于超过 60 亿 CPU 核小时的 DFT 数据训练，理论水平为 ωB97M-V/def2-TZVPD，涵盖了广泛的研究领域。其计算精度与高水平 DFT 计算相当，但计算成本更低，且时间复杂度优势明显，能够处理包含数千个原子的大体系。相关细节可在对应论文中查阅。

---

## 2. UMA 硬件与软件环境

UMA 模型基于 PyTorch 实现，需要在 GPU 上运行。显存 (VRAM) 需求相对适中，普通硬件（如配备 RTX 4050 的笔记本电脑）即可运行。示例系统配置包括 Ubuntu 24.04.2 LTS、Python 3.12.3、NVIDIA 驱动 570.133.07、CUDA 12.8 (PyTorch 使用 12.4) 以及 PyTorch 2.6.0+cu124。

---

## 3. 虚拟环境设置建议

为使用 UMA 模型，建议创建一个新的 Python 虚拟环境以确保库版本的兼容性。使用 Python venv 模块时，首先创建不含空格的目录（如 `/home/david/PyEnv/UMA`），然后运行 `python3 -m venv "/home/david/PyEnv/UMA"`。激活环境的方法是进入 `/home/david/PyEnv/UMA/bin` 目录并执行 `source activate`。

---

## 4. UMA 模型权重文件获取

UMA 模型权重文件（最新文件名为 `uma-s-1.pt`，旧版为 `uma_sm.pt`）大小约为 1.2 GB。该文件可从 Hugging Face 平台下载，但需要获得 FAIRChem 团队的批准。许可协议中未发现地理限制，但部分地区获取批准可能存在困难。

---

## 5. 依赖包安装流程

安装所需 Python 包的推荐流程包括：安装 JupyterLab (`pip install jupyterlab`)、ASE (`pip install ase`)、FAIRChem core (`pip install fairchem-core`) 以及 Sella (`pip install sella`)。Sella 是一种高效的鞍点优化算法的 Python 实现。安装完成后，通过 `jupyter lab` 启动 Jupyter Notebook。

---

## 6. 常见安装警告修复

为解决运行代码时出现的警告，可以执行以下可选步骤：将 setuptools 降级至 80.7.1 版本 (`pip install setuptools==80.7.1`)，并安装 CUDA 版本的 jax (`pip install -U "jax[cuda12]"`)。此外，将 UMA 检查点文件（如 `uma_sm.pt`）放置在 Python 环境的 bin 目录或指定路径中。

---

## 7. 修改 FAIRChem 代码以支持离线加载

若需从硬盘离线加载模型而非通过 Hugging Face 账户下载，需修改 FAIRChem 包的代码。文件路径位于虚拟环境下的 `lib/python3.12/site-packages/fairchem/core/calculate/pretrained_mlip.py`。将第 76-88 行的代码块（包含 `hf_hub_download` 等内容）替换为单行代码 `checkpoint_path=model_name`。

---

## 8. 环境变量配置建议

为了优化性能，建议限制 ASE 使用的 CPU 核心数为 1，以避免不必要的资源消耗。同时，建议强制 JAX 在 CPU 上运行，因为使用 CUDA 会占用更多显存且性能更差。设置示例包括 `os.environ['OMP_NUM_THREADS']='1'` 以及 `os.environ['JAX_PLATFORMS'] = 'cpu'`。

---

## 9. UMA 模型推理自定义设置

为了最小化显存使用并加快推理速度，可以自定义 `InferenceSettings`。推荐参数设置为：`tf32=True`、`activation_checkpointing=True`、`merge_mole=True`、`compile=False`、`wigner_cuda=False`、`internal_graph_gen_version=2`、`external_graph_gen=False`。若使用同一计算器连续计算出现 "Embeddings seem different" 错误，建议重启内核。

---

## 10. ASE 中设置 UMA 计算器

在 ASE 中设置 UMA 计算器需要使用 `pretrained_mlip.get_predict_unit` 加载模型（指定模型名称和设备为 "cuda"），并结合自定义推理设置。然后通过 `FAIRChemCalculator(predictor, task_name="omol")` 创建计算器实例。对于小分子几何优化，任务名称 (`task_name`) 通常设为 "omol"。

---

## 11. ASE 几何优化函数实现

使用 ASE 进行几何优化的函数定义通常包含以下步骤：读取输入的 XYZ 文件，将计算器赋值给原子对象，设置电荷和自旋信息。接着使用 BFGS 优化器（例如设置 `alpha=50`）进行优化，指定收敛标准 (`fmax`) 和最大步数 (`maxsteps`)，并输出轨迹文件。日志输出可通过 `logfile` 参数控制。

---

## 12. 几何优化执行示例

对包含 58 个原子的有机金属铜络合物进行几何优化时，调用定义好的优化函数，传入输入 XYZ 文件名（如 `input_geometry.xyz`）和输出轨迹文件名（如 `output_trajectory.xyz`）。计算过程中会输出步数、时间、能量和最大原子力 (`fmax`) 等信息。

---

## 13. BFGS 几何优化输出日志解读

BFGS 优化步骤日志包含步数、时间、能量值及收敛标准等关键信息。示例日志显示从初始能量 -94732.800124 逐步优化至 -94733.020140，耗时约 14.3 秒。每步迭代耗时少于 30 毫秒，且在更大体系下速度表现更为显著。
- 步骤示例: BFGS: 1 13:12:55 -94732.800124 0.259838
- 耗时统计: CPU times: user 14.3 s, sys: 45.7 ms, total: 14.3 s, Wall time: 14.2 s

---

## 14. UMA 模型显存占用情况

通过 nvidia-smi 监测，该计算任务在当前体系下的显存（VRAM）占用为 742 MB。此显存需求在现代 GPU 硬件能力范围内，而更大约 500 个原子的体系显存占用可能超过 3 GB。
- 当前体系显存占用: 742 MB
- 大体系参考占用: > 3 GB (500 atoms)

---

## 15. ASE GUI 可视化轨迹文件

优化输出的轨迹文件 `output_trajectory.traj` 可使用 ASE GUI 进行可视化查看。操作步骤需先激活 Python 虚拟环境，随后在终端输入相应命令启动图形界面。
- 启动命令: `ase gui`

---

## 16. 获取优化体系的能量属性

几何优化函数返回包含优化后几何结构的 ASE atoms 对象。通过调用该对象的 `get_potential_energy()` 方法，可以提取体系的势能（单位为 eV）。
- 代码示例: `dE = atoms.get_potential_energy()`

---

## 17. Sella 过渡态优化函数定义

使用 Sella 算法进行一阶鞍点（过渡态）优化的函数需读取输入结构（如 `input_geometry_TS.xyz`）并设置计算器及自旋多重度。函数初始化 Sella 对象时需指定轨迹文件及超参数（如 eta, gamma, delta0），并执行优化运行。
- 关键参数: fmax=0.0025, maxsteps=1000, eta=2e-2, gamma=0.0001, delta0=0.02
- 对象配置: TSatoms.info = {'charge': 0, 'spin': 1}

---

## 18. Sella 算法超参数配置

Sella 算法包含若干超参数，其详细定义可参考原始文献及项目 Wiki。默认超参数值在 UMA 模型中可能不适用，建议使用特定经验值（如 eta=2e-2, gamma=0.0001, delta0=0.02）作为起点，并针对不同体系进行调整。
- 参考文献: https://pubs.acs.org/doi/10.1021/acs.jctc.2c00395
- 参数说明: https://github.com/zadorlab/sella/wiki/Hyperparameters

---

## 19. Sella 过渡态优化输出日志

Sella 优化过程输出包含步数、时间、能量、最大力分量（fmax）、最大约束分量（cmax）、信任半径（rtrust）及预测比（rho）。示例日志显示对含 147 原子的有机金属铜体系进行优化，能量从 -126516.018063 变化至 -126516.311059，耗时约 9 分 30 秒。
- 输出示例: Sella 0 15:58:47 -126516.018063 0.6620 0.0000 0.0200 1.0000
- 性能数据: Wall time: 9min 30s, VRAM usage: 1570 MB

---

## 20. UMA 与传统 DFT 计算效率对比

Sella 优化过程中近似 Hessian 矩阵计算及大量几何迭代步骤耗时较长。相较于 ORCA 软件（16 核）进行同等体系的 ωB97M-V/def2-TZVPD 单点计算需超过 2 小时，UMA 模型完成单次计算耗时少于 1 秒。
- 对比基准: ωB97M-V/def2-TZVPD
- ORCA 耗时: > 2 hours (16 cores)
- UMA 耗时: < 1 second

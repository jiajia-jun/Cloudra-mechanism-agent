---
key: t27360
title: KST48����ǿ���MECP����
url: http://bbs.keinsci.com/thread-27360-1-1.html
domain: 反应机理与过渡态
source: keinsci
year: 2022
cards: 12
---

# KST48����ǿ���MECP���� — 知识卡片

## 1. KST48 程序简介

KST48 是一个用于寻找势能面交叉点（包括 MECP、锥形交叉及不同自旋态交叉点）的 Python 程序。该工具支持 Gaussian、ORCA 和 xtb 等量化软件，支持同自旋态和不同自旋态（如单态和三重态）之间的交叉点搜索，并能进行势能面扫描。程序依据 Harvey 的 MECP 理论编写，旨在解决原有接口程序复杂的问题。
- Github 地址：https://github.com/RimoAccelerator/KST48

---

## 2. KST48 基本目录结构

使用 KST48 需要在当前目录下创建一个名为 JOBS 的目录，用于存储计算产生的中间文件。主程序为一个名为 kst48.py 的 Python 脚本，必须与 JOBS 目录位于同一路径下。所有的计算任务和输入文件交互都基于此目录结构进行。
- 程序会自动读取当前目录下的输入文件并将输出写入 JOBS 目录。

---

## 3. KST48 输入文件：基本参数设置

输入文件中必须包含控制量化任务的基本参数，如计算资源和方法关键字。参数 `nprocs` 设置处理器数，`mem` 设置内存（ORCA 需改为 maxcore 值）。`method` 填写关键字行（无需写 guess=mix 或 stable=opt，程序会自动添加）。`charge` 设置电荷，`mult1` 和 `mult2` 分别设置态 A 和态 B 的多重度。
- 示例：`nprocs = 8`，`method = wb97xd def2sv`，`mult1 = 1`，`mult2 = 3`。

---

## 4. KST48 输入文件：TD-DFT 与 MP2 设置

对于涉及激发态的计算（仅限 Gaussian），需使用 `td1` 和 `td2` 参数分别指定态 A 和态 B 的 TD-DFT 关键字。若在 Gaussian 中进行 MP2 或双杂化泛函计算，需将 `mp2` 参数设置为 true。对于 ORCA，TD-DFT 关键字应写在后续的 `*tail` 部分，而非此处。
- 示例：`td1 = `，`td2 = `，`mp2 = false`。

---

## 5. KST48 输入文件：收敛与 GDIIS 控制

输入文件可选部分包含收敛阈值和 GDIIS 算法的细节控制。参数包括能量变化阈值 `dE_thresh` (默认 0.000050)、均方根梯度阈值 `rms_thresh` (默认 0.0025) 等。算法默认前 3 步使用 BFGS，之后切换至 GDIIS。当 RMS 梯度接近收敛时，步长会乘以 `reduced_factor` (默认 0.5)。`max_steps` 为最大步数(默认 100)，`max_step_size` 为最大步长(默认 0.1)。
- 相关参数均可根据需要修改。

---

## 6. KST48 输入文件：程序调用与坐标

输入文件需指定调用的量化程序路径及初始几何构型。`program` 参数选择 gaussian 或 orca，`gau_comm`、`orca_comm` 和 `xtb_comm` 分别设置对应程序的调用命令（如 g16 或 /opt/orca5/orca）。几何坐标需写在 `*geom` 和 `*` 之间，使用笛卡尔坐标（单位：埃）。
- 示例：`program = gaussian`，`gau_comm = 'g16'`。

---

## 7. KST48 输入文件：尾部设置与约束

`*tail1` 和 `*tail2` 中的内容会被分别追加到态 A 和态 B 的输入文件末尾，这对于 ORCA 添加 `%` 开头的关键字或 Gaussian 的特殊设置尤为重要。`*constr` 部分用于设置几何约束或扫描，支持固定键长、键角以及进行 1D 或 2D 扫描。
- 示例：`R 1 2 1.0` 固定原子 1 和 2 的距离为 1.0 埃。

---

## 8. KST48 运行命令

配置好输入文件（假设文件名为 inp）后，在 kst48.py 和 JOBS 目录所在的同级目录下运行命令即可启动程序。程序信息会输出到屏幕上。计算完成后，最终结构文件会输出到当前目录。
- 命令：`python3 kst48.py inp`

---

## 9. KST48 运行模式：normal 与 stable

KST48 支持 5 种运行模式。`normal` 模式执行标准的 Harvey MECP 寻找流程。`stable` 模式会在初始几何结构上自动添加 `stable=opt` 计算并读取优化后的结构进行后续任务，适用于 ORCA 碎碎念或需要确保波函数稳定性的情况（注意 ORCA 的开壳层需在 method 中写 UKS）。
- 模式设置参数：`mode = stable`。

---

## 10. KST48 运行模式：read 与 inter_read

`read` 模式要求在同目录下提供已有的波函数文件（如 Gaussian 的 .chk 或 ORCA 的 .gbw），程序将自动读取这些文件作为初始猜测。`inter_read` 模式用于 RKS 直接 `stable=opt` 难以收敛或需要混合波函数的情况，它会对态 B 进行稳定化处理后，将其作为态 A 的初始猜测，但用户需自行手动添加 `guess=mix` 和 `scf=vshift=-1000` 等关键词。
- 模式设置参数：`mode = read` 或 `mode = inter_read`。

---

## 11. KST48 运行模式：noread

`noread` 模式表示不读取任何波函数文件，程序将在每一步计算中尝试自动生成初始猜测。这适用于不需要继承前一步波函数信息的场景。
- 模式设置参数：`mode = noread`。

---

## 12. KST48 引用与更新日志

使用 KST48 时应引用相关文献，程序在 2022 年进行了多次更新。2022 年 1 月 24 日更新修复了文件命名问题，增加了在超算集群文件系统中调用 ORCA 的脚本。2022 年 2 月 6 日更新增加了对 BAGEL 的支持，可利用 BAGEL 处理多态性质和计算不同态之间的能量差。
- 引用文献：Y. Ma, A. A. Hussein, *ChemistrySelect* 2022, 7, e202202354.

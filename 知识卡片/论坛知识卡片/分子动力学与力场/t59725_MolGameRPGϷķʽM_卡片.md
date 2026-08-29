---
key: t59725
title: MolGame����RPG��Ϸ�ķ�ʽ��MDģ��
url: http://bbs.keinsci.com/thread-59725-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2026
cards: 21
---

# MolGame����RPG��Ϸ�ķ�ʽ��MDģ�� — 知识卡片

## 1. MolGame 项目简介

MolGame 是一个结合分子动力学模拟与 3D 游戏交互的项目，旨在通过第一人称视角的实时 3D 游戏环境让用户操作分子系统。用户可以使用键盘（如 WASD）或游戏手柄直接在模拟场景中移动、抓取、推动或切换视角，并观察力学系统的实时响应。
- 项目的源代码托管在 GitHub 平台上。
- 该工具将计算化学模拟转化为直观的交互体验。

---

## 2. 模拟引擎与力场参数

MolGame 使用 OpenMM 作为后端模拟引擎。默认设置包括 Amber14SB 蛋白质力场与 TIP3P 显式水模型，并采用 PME 方法处理静电相互作用。配体力场支持通过 OpenFF 或 openmmforcefields 进行 GAFF2 参数化。OpenMM 后端支持 CUDA、OpenCL 和 CPU 计算平台。

---

## 3. 图形界面与渲染技术

项目的渲染与交互界面基于 Pygame 和 OpenGL 开发。界面包含一个平视显示器（HUD）用于显示实时状态，右侧提供 3D 视图投影。
- 该架构实现了模拟数据与可视化图形的实时同步。

---

## 4. 通过 PDB ID 自动下载结构

程序支持直接输入 PDB ID 从 RCSB 数据库自动下载并加载分子结构。运行命令格式为 `python start.py --pdb 1UBQ` 或 `python start.py --pdb 2LYZ`。
- 系统会自动处理网络请求并获取对应的结构文件。

---

## 5. 支持配体与 PDB ID 组合加载

程序支持指定 PDB ID 并同时加载其中的配体分子。例如命令 `python start.py --pdb 4HJO --ligand AQ4` 会下载指定蛋白结构并提取相应配体。
- 配体提取后使用 GAFF2/AM1-BCC 方法进行参数化，随后插入到总计算体系中。

---

## 6. 支持本地 PDB 和配体文件加载

用户可以加载本地的 PDB 蛋白文件以及已处理好电荷、3D 坐标、氢和底物的 SDF 或 MOL2 格式配体文件。相关命令包括 `python start.py --pdb-file ./protein.pdb`、`python start.py --pdb-file ./protein.pdb --ligand-file ./ligand.sdf` 及 `python start.py --pdb-file ./protein.pdb --ligand-file ./lig1.sdf --ligand-file ./lig2.mol2`。
- 如果未指定配体文件，默认仅加载蛋白及溶剂。

---

## 7. 多配体文件加载与分组

当使用重复的 `--ligand-file` 参数加载多个文件时，每个文件被视为一个独立的配体组。默认视角控制第一组配体，用户可在操作模式下按 X 键切换选择目标，从而对不同配体组进行操控。
- 这种设计允许同时对多个分子实体进行区分和交互。

---

## 8. 特定离子的加载与支持

程序允许加载 PDB 中的特定金属离子。命令示例为 `python start.py --pdb 4MS2 --ion CA` 或 `python start.py --pdb 4MS2 --ion MG`。
- 目前支持的离子类型包括 CA、NA、CL、K、MG、ZN。

---

## 9. 键盘与鼠标控制操作说明

MolGame 提供类 RPG 游戏的操作方式。WASD 控制移动当前目标（施力）；方向键旋转当前目标（施扭矩）；Space/Shift 键上下移动目标（施力）；鼠标用于转动视角；滚轮用于缩放；X 键进入选择模式以切换配体或确定选择；左/右方向键或 D-pad 对当前目标施加推力（以目标为中心）；V 键切换视角显示模式；L 键切换表示模式（支持球棍或线条模型）；P 键暂停并打开菜单。
- 这套操作逻辑旨在实现对分子系统的精细化实时干预。

---

## 10. 游戏手柄控制操作说明

手柄操作方案包括左摇杆移动视角，右摇杆移动视角或按下加速移动，D-pad 对目标施加推力，A 键暂停。
- 手柄为用户提供了除键盘鼠标外的另一种交互选择。

---

## 11. 交互范围与选择模式

在暂停菜单的 Select scope 选项中，用户可选择 Residue（准备选择单个残基）或 Chain（选择一个原子后选择所在链的所有原子）。
- 该功能主要用于测试不同范围的选择以及对应操作对分子动力学行为的影响。

---

## 12. 实时 HUD 信息显示

HUD 实时显示系统状态信息，包括 PE total（总势能）、PE clean（扣除外部施加的 steering force / torque force 后的势能）、clean PE 的实时变化曲线、温度、FPS 以及当前选择模式（force mode）。
- Clean PE 的计算通过 OpenMM force group 实现，将 steering force 和 torque force 归入 group 31，计算公式为 clean PE = total PE - group 31 energy。

---

## 13. 模拟计算频率优化

为保证运行流畅，物理引擎内部计算频率约为每 0.5 秒一次，每帧渲染时仅获取原子坐标。
- 这种分离策略平衡了计算精度与实时交互的流畅度。

---

## 14. 暂停菜单与快照保存功能

在暂停菜单中，用户可以保存当前系统状态。默认保存包含蛋白、配体及水分子，用户也可选择不保存水分子。文件命名格式为 `molgame_snapshot_YYYYMMDD_HHMMSS_dry.pdb`（无水）和 `_all.pdb`（全系统）。
- 该功能方便用户记录模拟过程中的特定构象。

---

## 15. 安装与环境配置

推荐使用 mamba 或 conda 进行环境安装。执行命令 `mamba env create -f environment.yml` 创建环境，随后使用 `mamba activate molgame` 激活环境，最后运行启动命令 `python start.py --pdb-file ./protein.pdb --ligand-file ./ligand.sdf`。
- 依赖配置文件已预设好必要的库。

---

## 16. 支持的运行平台

项目支持 macOS、Linux/Ubuntu 发行版、Windows 以及 WSL（Windows Subsystem for Linux）。
- 注意：由于项目需要 Pygame + OpenGL 窗口，不支持 Ubuntu Server 或 SSH 下的 headless 运行；WSL 推荐使用 Windows 11 WSLg，传统 WSL 需要配置 X server 和 OpenGL 转发。

---

## 17. 计算平台选择与优先级

OpenMM 默认按 CUDA -> OpenCL -> CPU -> Reference 的顺序自动选择计算平台。用户也可以通过命令手动指定平台，例如 `python start.py --platform CUDA`、`python start.py --platform OpenCL` 或 `python start.py --platform CPU`。
- 显式指定平台有助于在特定硬件上获得最佳性能。

---

## 18. 显式水模型的性能限制

显式水分子体系下的模拟性能受限于计算与渲染。当体系包含数万原子时，实时 FPS 可能仅能达到十几帧。
- 这一限制是由 OpenMM 物理计算和 GPU/CPU 渲染同步共同导致的。

---

## 19. 项目的定位与当前局限性

该项目定位于实时互动工具/游戏原型，而非标准的科研级 MD 模拟软件。其显式动力学模型未经过标准 OpenMM/Gromacs/AMBER 流程的体系平衡、温控和压控处理。
- 因此，该工具主要适合用于定性观察和交互演示，不适合用于生产严谨的科研数据。

---

## 20. 结构文件的预处理要求

由于缺少复杂的拓扑构建逻辑，加载的文件需满足特定条件：蛋白和配体必须已经具备显式的 3D 坐标，且配体和底物需处于同一坐标系中。
- 如果涉及配体插入，需预先保证插入位置的合理性，以避免物理重叠。

---

## 21. 项目的应用场景与设计初衷

该项目旨在打破传统计算化学“提交任务、等轨迹、后处理”的非交互模式，提供一种所见即所得的直观体验。应用场景包括直观地探索结合口袋、选择残基并施加外力、观察局部接触或能量变化，以及实时调试体系的动力学行为。
- 它适合作为化学教学演示、分子动力学可视化调试或辅助理解分子相互动的工具。

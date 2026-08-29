---
key: t59812
title: ʹ��FDVIB����QE������λ�Ʒ���Ч��������񶯣�����Shermo����Ȼ�ѧ����
url: http://bbs.keinsci.com/thread-59812-1-1.html
domain: 其他量化软件
source: keinsci
year: 2026
cards: 13
---

# ʹ��FDVIB����QE������λ�Ʒ���Ч��������񶯣�����Shermo����Ȼ�ѧ���� — 知识卡片

## 1. FDVIB 简介

FDVIB 是一种基于有限差分法计算振动频率和热力学性质的工具，与基于密度泛函微扰理论(DFPT)的 `ph.x` 形成互补。该工具通过调用 Quantum ESPRESSO 的 `pw.x` 程序计算单点能，从而构建 Hessian 矩阵，并利用 `dynmat.x` 直接获取频率。FDVIB 支持将 `dynmat.x` 的结果转换为 Molden 格式，以便通过 MfakeG 等程序可视化振动模式，并可通过 Shermo 计算热力学性质。

---

## 2. FDVIB 的适用场景

FDVIB 适用于周期性体系中仅关注特定部分（如吸附分子、活性中心或缺陷结构）振动频率的情况。在需要通过分子振动光谱确认吸附态或只需计算振动频率和热力学性质时，FDVIB 能快速得到频率结果，并可直接生成 .shm 文件用于 Shermo 计算热力学。对于周期性体系，该方法相比全体系 DFPT 计算具有更高的计算效率。

---

## 3. FDVIB 支持的计算模式

FDVIB 支持两种计算模式：`local` 模式适用于周期性体系或团簇模型，仅对 `selected_atoms` 指定的原子进行位移，计算这些原子的局部 Hessian；`gas` 模式适用于孤立分子或团簇，位移所有原子，计算完整 Hessian 并去除平动和转动。

---

## 4. FDVIB 计算示例概述

该示例演示了使用 FDVIB 计算 CO@H-LTA 分子筛中吸附的 CO 分子振动频率的过程。计算对象为 CO@H-LTA 体系，仅选择第 74 和 75 号（O 和 C）原子进行局部振动计算，涉及 6 个自由度的位移，得到 6 个振动模式，而骨架原子保持固定。

---

## 5. FDVIB 的安装与获取

FDVIB 可从 GitHub Releases 页面下载 Linux x86_64 预编译版本，解压后将 `fdvib` 可执行文件加入 PATH 环境变量即可使用。使用前需确保 Quantum ESPRESSO 的 `pw.x` 和 `dynmat.x` 已正确配置并可用。

---

## 6. FDVIB 的基本命令

FDVIB 提供了一系列命令用于初始化、运行和后处理，包括 `fdvib init local`、`fdvib init gas`、`fdvib -inp fdvib.in`、`fdvib modes fdvib/results`、`fdvib shm fdvib/results` 和 `fdvib thermo fdvib/results -inp thermo.in`。若计算中断，用户只需重新运行相同的 FDVIB 命令，程序会自动检测并跳过已完成或失败的作业。

---

## 7. 输入文件准备与目录结构

在运行 FDVIB 前，当前目录下需包含原始未位移结构的 QE 输入文件 `scf.in` 和 FDVIB 配置文件 `fdvib.in`。运行后，FDVIB 会在 `fdvib/calculations/` 目录下生成参考 SCF 计算目录（如 `init_scf_001/scf.in`）以及各原子的正负位移计算目录（如 `disp_0074_x_p_001/pw.in`）。

---

## 8. QE 输入文件 scf.in 的配置要点

`scf.in` 需包含 `calculation = 'scf'`、`tprnfor = .true.` 以输出力，且收敛标准（如 `etot_conv_thr` 和 `forc_conv_thr`）应设置得足够严格以保证频率精度。FDVIB 会自动将 `disk_io` 设置为 `'nowf'` 以节省磁盘空间，且用户不应设置 `startingpot='file'`，因为 FDVIB 内部已通过复制参考 SCF 的电荷密度来处理初始势。

---

## 9. FDVIB 输入文件 fdvib.in 的配置

运行 `fdvib init local` 可生成 `fdvib.in` 模板，关键参数包括 `scf_input`（指定 `scf.in`）、`system_type = local`、`selected_atoms = 74,75`（指定计算原子）、`displacement_angstrom = 0.01`（位移大小）以及 `pw_command` 和 `dynmat_command`。需注意 `prefix` 参数是 FDVIB 生成文件的前缀，与 QE 输入文件中的 `prefix` 不同。

---

## 10. FDVIB 的运行与输出日志

执行 `fdvib -inp fdvib.in > fdvib.out` 即可开始计算，日志会显示参考 SCF 和各个位移任务的运行状态。计算完成后，日志会输出 Hessian 的最大非对称性，并提示已生成 `fdvib/results/system.dynG` 等文件以及 `dynmat.x` 的运行结果。

---

## 11. 结果文件说明

计算完成后，`fdvib/results/` 目录下会包含 `metadata.dat`（记录元数据）、`system.dynG`（`dynmat.x` 输入文件）、`dynmat.out`（`dynmat.x` 输出文件）和 `system.freq.out`（包含频率和振动模式信息）。`metadata.dat` 文件记录了程序类型、电子能量、多重度、模式选择方式及选中的原子序号。

---

## 12. 生成 Molden 模式文件

使用命令 `fdvib modes fdvib/results` 可以将结果转换为 Molden 格式的文件 `system.mol`。该文件中仅包含发生位移的原子（如 74 和 75 号原子）的振动数据，未选中的骨架原子在结构中保持静止。生成的文件包含频率信息，且 FDVIB 默认不包含强度信息（[INT]部分缺失）。

---

## 13. 与 DFPT (ph.x) 方法的对比设置

为了对比 FDVIB 的有限差分法与 QE DFPT 方法，可使用相同的结构和赝势，通过 `ph.x` 设置 `nat_todo=2` 仅计算第 74 和 75 号原子。`ph.in` 输入文件需包含 `prefix`、`outdir`、`fildyn`、`tr2_ph`、`nat_todo=2`、`nogg=.true.` 等参数，并在末尾指定 Gamma 点和原子序号列表。

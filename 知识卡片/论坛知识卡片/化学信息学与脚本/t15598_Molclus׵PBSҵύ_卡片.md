---
key: t15598
title: ����Molclus���׵�PBS��ҵ�ύ�ű�
url: http://bbs.keinsci.com/thread-15598-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2019
cards: 46
---

# ����Molclus���׵�PBS��ҵ�ύ�ű� — 知识卡片

## 1. Molclus 1.12 版本更新

Molclus 于 2022 年 8 月 23 日更新至 1.12 版本。当设置 `ibkout=-1` 时，同时也实现 `ibkout=1` 的效果，即保留特定输出文件。若设置 `ibkout=-1`，即使计算文件被标记为备份，也不会被删除。

---

## 2. Molclus 自动创建单点计算输入文件

从 2022 年 8 月 17 日的更新开始，当 `settings.ini` 中 `ibkout=-1` 时，Molclus 会在当前目录下查找 `template_SP.inp` 和 `template_SP.gjf`。若找到这些文件，程序会自动为 ORCA 或 Gaussian 生成单点计算输入文件，并根据当前数据命名（如 `orcaSP00002.out` 或 `gauSP00005.out`）。

---

## 3. Molclus ibkout 参数保留输出文件

2022 年 7 月 9 日的更新在 `settings.ini` 中增加了 `ibkout` 设为 -1 的选项。在进行 Gaussian 或 ORCA 计算时，若 `ibkout` 为 -1，当前目录下由当前步骤生成的文件（如 `gau00002.out` 或 `orca00005.out`）将被保留，不会被 Molclus 自动删除。

---

## 4. Molclus 结构筛选距离约束控制

2022 年 9 月 9 日的更新支持对 `traj.xyz` 中的结构进行更细致的原子间距离控制。若将 `settings.ini` 中的 `distmax` 设为 0，Molclus 会从当前目录的 `distrange.txt` 读取设置，文件每行格式为“原子组1 原子组2 最近距离 最远距离”，单位为埃。

---

## 5. distrange.txt 格式与约束规则

`distrange.txt` 文件用于定义原子组间的距离约束，例如 `1,3-5 2,8 2.5 10.2` 表示原子 1,3,4,5 与原子 2,8 之间的距离需在 2.5 至 10.2 埃之间。若 `traj.xyz` 中的结构违反此约束，该结构将被视为无效并忽略。

---

## 6. Molclus 重复结构判断与距离阈值

2022 年 5 月 28 日修复了 `isostat` 中使用 `-Edis` 判断重复结构时阈值取位可能出错的问题。2022 年 6 月 8 日修复了 `genmer` 中 `$distcons` 设置存在的 Bug。

---

## 7. Molclus Windows xtb 支持与 Freeze 参数

2022 年 6 月 14 日的版本支持在 Windows 上通过 Molclus 调用 xtb。2022 年 6 月 24 日修复了 Molclus 调用 xtb 时 `settings.ini` 中 `freeze` 参数无效的 Bug。

---

## 8. Molclus 脚件下载与适配

附件提供了适配 Molclus 1.12 及 1.9.9.3 版本的 Linux 脚本包。新版本脚本删除了 `isostat` 相关的 `*.ini` 文件，参数改为直接通过命令行传递给 `isostat`，PBS 脚本中的 `./isostat` 行需相应修改。

---

## 9. Molclus 1.9.9.8 版本 genmer 更新

2022 年 3 月 3 日的 1.9.9.8 版本更新了 `genmer`。在 `genmer.ini` 中增加了 `ishuffle` 选项，用于控制带电体系的原子添加顺序；若设为 -1，原子将按随机顺序添加，避免对特定原子组合的偏好，适用于构建复杂体系。

---

## 10. Molclus 激发态构象搜索支持

2021 年 11 月 23 日的 1.9.9.7 版本支持激发态构象搜索。在 `settings.ini` 中将 `energyterm` 设为 "TD=" 并在 Gaussian 模板文件中设定 TDDFT 计算，配合 Multiwfn 提取激发态能量，Molclus 即可基于激发态能量进行构象筛选。

---

## 11. Molclus 热力学量计算

2021 年 9 月 4 日的 1.9.9.6 版本增加了热力学校正功能。通过在 `settings.ini` 中设置 Shermo 路径，Molclus 可在 Gaussian 或 ORCA 频率计算后自动调用 Shermo 计算热力学数据，并将能量、焓、吉布斯自由能等信息用于后续构象搜索与筛选。

---

## 12. genmer 距离约束与键长控制

`genmer.ini` 支持通过 `$distcons` 关键字设定特定原子对的距离范围（如 `Pt Pt 1.8 3.2`），违反约束的构象将被视为生成失败。此外，支持通过 `$modrad` 修改原子半径（如 `Pt 3.5`），以影响构象生成过程中的空间位阻判断。

---

## 13. Molclus 缺失配置文件提示

`genmer` 运行时若当前目录无 `genmer.ini`，会提示用户手动输入文件路径。`molclus` 运行时若缺失 `traj.xyz` 或 `settings.ini`，也会提示用户输入路径，建议将配置文件置于当前目录。

---

## 14. Molclus 原子类型识别 Bug

2021 年 9 月 29 日修复了一个 Bug：Molclus 调用 OpenBabel 处理 xyz 文件时，若元素符号为大写（如 CL），且未通过双字符明确指定原子类型，可能导致识别错误。

---

## 15. genmer 空间范围限制

2021 年 8 月 28 日的 1.9.9.5 版本允许在 `genmer.ini` 中设置 `xmin`, `xmax`, `ymin`, `ymax` 等参数，用于控制构象生成时原子在三维空间中的分布范围。此前版本仅支持 `zmin` 和 `zmax`。

---

## 16. xyz2QC 文件名占位符

2021 年 8 月 28 日的更新支持在 Gaussian 模板文件中使用 `[FILENAME]` 占位符。生成输入文件时，该占位符会被替换为“前缀.帧数”，例如 `%chk=/sob/[FILENAME].chk`，便于将 checkpoint 文件归档到 `/sob` 目录。

---

## 17. isostat 命令行参数

`isostat` 支持通过命令行参数直接运行分析，例如：`isostat Rize.xyz -Nout 8 -Eout 2.4 -Edis 0.5 -Gdis 0.2 -T 350 -nt 32`。该命令表示从 `Rize.xyz` 导出能量最低的 8 个结构，能量差阈值为 2.4 kcal/mol，结构相似性判断基于 0.5 kcal/mol 和 0.2 埃，温度设为 350K，使用 32 线程。

---

## 18. genmer 旋转限制

2021 年 2 月 11 日的 1.9.9.3 版本在 `genmer.ini` 中增加了 `noxrot`, `noyrot`, `nozrot` 选项，用于禁止分子在 X、Y、Z 轴方向的旋转。可单独或组合使用，例如仅允许 Z 轴旋转。

---

## 19. Molclus 1.9.9.2 与 1.9.9.1 更新

2020 年 12 月 28 日的 1.9.9.2 版本解决了某些情况下 Gaussian 优化未正常结束时 Molclus 卡住的问题。2020 年 12 月 10 日的 1.9.9.1 版本增加了 `igaucontinue` 功能，当 Gaussian 优化失败时，会尝试使用 `template3.gjf` 进行重新优化。

---

## 20. ORCA Hessian 文件处理

在 1.9.9.1 版本中，`settings.ini` 新增 `ibkhess` 选项。当设为 1 时，涉及振动分析的 ORCA 计算生成的 `.hess` 文件将被自动重命名为 `orca[序号].hess` 并保留，供用户后续分析 Hessian 矩阵。

---

## 21. Molclus 1.9.9 版本特色功能

2020 年 11 月 16 日的 1.9.9 版本增加了 `mol2_xyz` 程序，用于将 Frog2 或 Confab 生成的多帧 mol2 文件转换为 `traj.xyz`。支持通过在当前目录创建名为 `STOP` 的文件来强制终止 Molclus 循环。

---

## 22. Molclus 输出文件控制

2020 年 10 月 18 日的 1.9.8 版本优化了 `isostat` 的处理速度。当 `settings.ini` 中 `iappend=1` 时，会自动删除当前目录下的 `.out`、`.chk` 等 ORCA 输出文件以节省空间，除非这些文件已被 `ibkout` 或 `ibkchk` 选项保留。

---

## 23. Molclus iappend 参数

`settings.ini` 中的 `iappend` 选项控制 `isomers.xyz` 的写入模式。若设为 1，新优化的结构将追加到现有的 `isomers.xyz` 文件末尾；若为 0，则覆盖原文件。该参数确保文件序号在续算时不发生冲突。

---

## 24. gentor 失败报告与参数调整

2020 年 10 月 14 日的 1.9.7 版本在 `gentor.ini` 中增加了 `reportfail=1` 选项，可显示构象生成失败的具体原因。默认的 `critskip` 阈值从 0.8 调整为 0.75，以减少含氢体系的构象被误判为无法生成的情况。

---

## 25. Molclus 1.9.6 高精度单点能量 Bug 修复

2020 年 7 月 12 日的 1.9.6 版本修复了一个 Bug：当 `itask=3` 且未切换到高精度单点计算模板时，`isomers.xyz` 记录的能量为 0。修复后确保记录的是 freq 计算得到的能量。

---

## 26. Molclus 1.9.5 与 1.9.4 更新

2020 年 5 月 31 日的 1.9.5 版本使 `isostat` 支持不写参数运行。2020 年 4 月 21 日的 1.9.4 版本修复了 `itask=3` 下未提供高精度单点模板文件时的崩溃 Bug。

---

## 27. Molclus 与 CREST 结合使用

2020 年 2 月 11 日的 1.9.3 版本支持读取 CREST 通过 `-mdopt` 模式输出的 xyz 文件。Molclus 可配合 xtb 对 `traj.xyz` 中的结构进行逐一优化，或利用 CREST 的多线程并行优化功能提高效率。

---

## 28. CREST 命令行调用示例

调用 CREST 进行构象搜索的命令示例如下：`/sob/crest -mdopt traj.xyz -gfn0 -opt normal -niceprint`。其中 `/sob/crest` 为执行文件路径，`-gfn0` 指定计算方法，`-niceprint` 用于减少输出信息，可通过 `-chrg` 和 `-uhf` 指定电荷和自旋多重度。

---

## 29. Molclus 1.9.2 高精度单点计算自动调用

2020 年 2 月 5 日的 1.9.2 版本支持在优化或优化+频率计算完成后，自动调用高精度单点能计算。用户需在当前目录提供 `template_SP.gjf`（Gaussian）或 `template_SP.inp`（ORCA），程序将自动提取优化后的结构信息生成输入文件并提交计算。

---

## 30. Molclus 高精度单点计算逻辑

若同时存在 `template_SP.inp` 和 `template_SP.gjf`，程序优先使用 `template_SP.inp`（ORCA）。即使使用 Gaussian 进行优化（`iprog=1`），也可通过提供 `template_SP.inp` 自动切换至 ORCA 进行高精度单点计算。对于 Gaussian 单点计算，需在 `settings.ini` 中正确设置 `energyterm` 以读取能量。

---

## 31. Molclus 指定文件路径运行

为方便批处理，Molclus 支持直接指定配置文件和初始结构文件的路径，例如 `molclus /RAS/Layer.ini`。使用 `lock.ini` 时也可指定路径，如 `molclus lock.ini /RAS/chu2.xyz`。

---

## 32. PBS 脚本目录结构规范

建议将所有参数文件（`*.ini`）统一放在 `ini` 文件夹下，所有输出文件存放在 `results` 文件夹下，所有模板文件（`template*`）存放在 `templates` 文件夹下。提交脚本 `molclus_g16orca.pbs` 实现了 Gaussian 优化结构与 ORCA 单点计算的组合流程。

---

## 33. 分层构象搜索策略 (PBS 脚本)

示例脚本采用分层计算策略：(1) 使用 `gentor` 生成初始结构；(2) 使用 Molclus 结合 xtb (GFN1-xTB) 进行粗筛；(3) 使用 Molclus 结合 Gaussian (B3LYP-D3(BJ)/6-31G*) 对筛选后的结构进行优化和频率计算；(4) 使用 ORCA (RIJK-DLPNO-CCSD(T)/def2-QZVPP) 进行高精度单点能量计算。

---

## 34. isostat 交互式参数设置

`isostat` 运行时会依次提示用户输入：输入文件路径（默认为当前目录 `isomers.xyz`）、区分不同团簇的能量阈值（默认 0.5 kcal/mol）、几何结构阈值（默认 0.25 Angstrom）。在 PBS 脚本中，通过 `isostat_*.ini` 文件预设这些参数可实现非交互式运行。

---

## 35. molclus_xtb.pbs 脚本内容

`molclus_xtb.pbs` 脚本设置了 xtb 所需的环境变量（`OMP_NUM_THREADS`, `MKL_NUM_THREADS`），调用 `gentor` 生成初始结构，重命名配置文件后运行 Molclus 进行 xtb 优化，最后调用 `isostat` 分析结果并输出 `cluster_xtb.xyz`。

---

## 36. molclus_g16.pbs 脚本内容

`molclus_g16.pbs` 脚本首先将上一步生成的 `cluster_xtb.xyz` 复制为 `traj.xyz`，切换至 `settings2.ini`（包含 `ngeom=10` 等设置），运行 Molclus 进行 Gaussian 优化，最后使用 `isostat` 分析并输出 `cluster_g16.xyz`。

---

## 37. molclus_orca.pbs 脚本用途

该脚本为 PBS 任务提交脚本，适用于基于 ORCA 进行结构搜索与优化的任务。脚本通过调用 molclus 及其相关组件，执行构象搜索、几何优化及结果分析流程。在使用前需要确保 ORCA 计算环境及 molclus 程序已正确配置。

---

## 38. PBS 任务资源与队列设置

脚本通过 `#PBS` 指令申请计算资源，包括指定节点数、CPU 核心数、 walltime 时间限制及队列名称。示例配置为申请 1 个节点、32 个 CPU 核心，最大运行时间设为 1440 小时，队列名为 `gentai`。任务标准输出和错误输出将被重定向到以 `jobID.` 开头的文件中。

---

## 39. 程序执行权限设置

脚本在执行前会将当前目录下的 molclus、isostat 以及 gentor 和 genmer 子目录下的可执行文件赋予执行权限。这是确保后续构象生成和聚类分析步骤能够顺利运行的必要操作。

---

## 40. 初始构象文件输入流程

脚本会将 Gaussian 生成的 `cluster_g16.xyz` 文件复制为 `traj.xyz`，以此作为 molclus 的初始输入构象文件。这一步骤允许用户利用已有计算结果继续进行后续的结构搜索或优化。

---

## 41. 配置文件切换与参数生效

脚本通过重命名配置文件来切换 molclus 的运行模式，将 `settings3.ini` 重命名为 `settings.ini` 以激活特定参数设置。该配置文件中包含了如 `ngeom= 10` 等关键参数，用于控制几何优化或构象生成的数量。

---

## 42. molclus 主程序执行

脚本执行 `./molclus` 命令启动主程序，并利用 `tee` 命令将屏幕输出实时保存到 `info_orca.txt` 文件中。该步骤负责执行核心的结构搜索与优化循环，直到满足设定条件结束。

---

## 43. 异构体聚类分析执行

主程序运行结束后，脚本将配置文件还原，并执行 `./isostat` 命令对优化后的几何结构进行聚类分析。分析过程依据 `isostat_orca.ini` 文件中的设定进行，并将结果输出重定向保存至 `summary_orca.txt`。

---

## 44. 结果文件整理与重命名

分析完成后，脚本会删除中间过程产生的 `traj.xyz` 文件，并将最终生成的聚类结果文件 `cluster.xyz` 重命名为 `cluster_orca.xyz`。此操作旨在区分不同计算软件（如 ORCA）产生的结果文件，防止覆盖。

---

## 45. 使用前注意事项

在使用该脚本之前，必须检查 `settings3.ini` 文件中的 `ngeom=` 参数设置是否正确。此参数决定了 molclus 在调用 ORCA 进行计算时，从输入文件中提取的几何构象数量或生成的结构数量。

---

## 46. 输入文件准备要求

运行脚本要求当前目录下存在名为 `cluster_g16.xyz` 的输入文件。该文件通常由 Gaussian (G16) 计算生成，包含了用于后续 molclus 结构搜索的初始构象数据。缺少资料件将导致后续的复制与计算步骤无法进行。

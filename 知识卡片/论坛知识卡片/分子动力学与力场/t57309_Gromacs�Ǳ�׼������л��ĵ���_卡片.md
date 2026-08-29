---
key: t57309
title: Gromacs�Ǳ�׼������л��ĵ���MD��ģ��sobtop����rtp�ļ�
url: http://bbs.keinsci.com/thread-57309-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2025
cards: 14
---

# Gromacs�Ǳ�׼������л��ĵ���MD��ģ��sobtop����rtp�ļ� — 知识卡片

## 1. PyMOL 原子名称标准化

在为 GROMACS 准备配体文件时，需将非标准原子名称修改为符合 Amber 力场标准的名称，涉及的元素如 C、N、H、O 应分别命名为 C、N、H、O。使用 PyMOL 的 alter 命令可以将选中结构中特定元素的原子名称统一修改为标准名称，例如 `select C_tmp, sele and element C` 后执行 `alter C_tmp, name='C'`。

---

## 2. GROMACS 残基连接顺序

GROMACS 识别文件中的原子顺序对于定义残基连接至关重要，必须确保前一个残基的末端原子（通常是 C）与后一个残基的起始原子（通常是 N）相邻。如果 PDB 文件中残基顺序不符合这一逻辑（如 PDB ID 5exb 中 64 号和 65 号残基之间插入了 5SQ），需要手动调整原子或残基的排列顺序。

---

## 3. PyMOL 添加端基与原子重命名

在 PyMOL 中通过 Builder 功能给非标准残基添加端基后，需要对新增的原子进行重命名以避免 `pdb2gmx -ignh` 时的冲突。可以使用 alter 命令将氢原子名称修改为特定的标准名称，例如 `alter sele, name='H'` 或 `alter sele, name='HA1'`。

---

## 4. 文件格式与工具用途

使用修改后的 mol2 文件通过 sobtop 生成 rtp 文件，使用 xyz 文件进行 xtb 计算（如 Hessian 计算或优化）。在保存 mol2 文件后，建议另存为 pdb 文件（`save 5SQ_capped.pdb, all`）以确认 25 个原子的顺序与原始 PDB 文件中 5SQ 残基原子顺序一致，若 capping 基团的氢原子顺序有误，可在生成 rtp 文件后手动删除。

---

## 5. hdb 文件结构与定义

hdb 文件用于定义氢原子如何加在重原子上，以及这些重原子的名称，参考文件路径为 `gromacs2023/share/gromacs/top/amber14sb_parmbsc1.ff/aminoacids.hdb`。文件格式中，第一列为残基名和原子数，后续每一行描述一个氢原子，格式为 `1 1 H N -C CA`，其中数字代表氢原子数量和二面角类型，原子列表用于定义二面角（i-j-k-l），`-C` 表示前一个残基的 C 原子。

---

## 6. 非标准残基 hdb 文件编写

为非标准残基 5SQ 编写 hdb 文件时，需列出所有需要添加氢原子的坐标定义，总行数对应氢原子总数（如 13 个）。定义中若涉及 capping 基团（如 CO2），需在原子列表中包含相应位置；若某个重原子上连接了多个氢原子（如 HA1, HA2），需分别写出对应行，并使用 1 1 或 1 2 等参数区分类型，例如 `2 6 HA CA3 N3 C`。

---

## 7. RESP 电荷计算流程

使用 xtb 进行 Hessian 计算的命令为 `xtb *xyz --ohess --gbsa h2o -P 6`，计算得到 `xtbopt.xyz` 后，使用 `RESP_ORCA_noopt.sh` 脚本结合 `Multiwfn_noGUI` 进行 RESP 电荷拟合。脚本执行示例为 `bash RESP_ORCA_noopt.sh xtbopt.xyz 0 1 gas`，需确保 SP.molden 文件存在于当前目录。

---

## 8. RESP 电荷约束文件

在 `RESP_ORCA_noopt.sh` 脚本运行中，`chgcons.txt` 文件用于指定某些原子的电荷约束为 0，通常用于 cap 基团或特定片段。文件格式为原子 ID 列表后跟 0，例如 `2,3,25,26,27,28 0`，表示这些原子在拟合过程中总电荷被约束为 0。

---

## 9. PyMOL 获取原子 ID

可以通过编写并在 PyMOL 中运行 Python 脚本（如 `id.py`）来获取选中原子的内部 ID 和名称，脚本包含 `cmd.get_model(selection).atom` 及打印 ID 和名称的逻辑。在 PyMOL 命令行中使用 `run id.py` 加载脚本后，执行 `printid sele` 即可打印当前选中原子的 ID 列表，用于填写 `chgcons.txt`。

---

## 10. sobtop 生成 rtp 文件

在 sobtop 目录下运行 sobtop 程序，输入 mol2 文件路径、选择功能 7、电荷文件路径（SP.chg）、选择功能 3（生成 GROMACS .rtp）、功能 4（分配 AMBER 原子类型）以及 Hessian 数据路径，可生成原始的 origin.rtp 文件。交互式输入示例包括指定分子路径、RESP 电荷文件路径以及 Hessian 文件路径。

---

## 11. rtp 文件修改规范

对 sobtop 生成的 rtp 文件需进行五项修改：注释掉 `[ bondedtypes ]` 及之后内容；将残基名 `[ MOL ]` 改为 `[ 5SQ ]`；在 `[ bonds ]` 中添加 `-C N` 以表示与前一个残基的连接；在 `[ impropers ]` 中添加二面角参数（如 `-C CA1 N H 4 180.0 4.60240 2`）；删除与 capping 基团相关的任何参数。

---

## 12. 自动化修改 rtp 文件

编写 Python 脚本（如 `rtp.py`）可以自动完成对 origin.rtp 文件的上述修改操作，执行 `python rtp.py > 5SQ.rtp` 后生成最终文件。生成的 5SQ.rtp 文件需复制到力场目录 `gromacs2023/share/gromacs/top/amber14sb_parmbsc1.ff/` 下。

---

## 13. 注册非标准残基类型

将非标准残基 5SQ 添加到 GROMACS 残基类型定义文件 `residuetypes.dat` 中，需添加一行 `5SQ Protein`，表明该残基属于蛋白质类残基。该文件通常位于 `/root/jojo/software/gromacs2023/share/gromacs/top/` 目录下。

---

## 14. 生成拓扑文件与参数修正

使用 `gmx pdb2gmx -f 5exb_monomer.pdb -o 5exb_monomer.gro -ignh -water spc -nobackup` 命令生成拓扑文件 `topol.top` 后，需使用 `sed` 命令清理或修正二面角参数中的异常格式。例如，执行 `sed -i 's/ 9 9 / 9 9 /g' topol.top` 等命令来删除多余的参数编号，修正后的拓扑文件可用于后续的 GROMACS 模拟（如加水、NPT 平衡）。

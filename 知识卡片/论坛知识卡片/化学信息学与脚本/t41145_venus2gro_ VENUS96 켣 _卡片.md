---
key: t41145
title: venus2gro: VENUS96 �켣 �� ��֡ gro �ļ�
url: http://bbs.keinsci.com/thread-41145-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2023
cards: 9
---

# venus2gro: VENUS96 �켣 �� ��֡ gro �ļ� — 知识卡片

## 1. venus2gro 脚本简介

venus2gro 是一个开源脚本，用于将 VENUS96 程序输出的轨迹转换为包含坐标和速度的 .gro 文件格式。该工具使用 BSD-2-Clause 协议发布，源代码托管于 GitHub 仓库 https://github.com/CQPES/venus2gro。它能够将 VENUS96 的轨迹数据输出至 GROMACS 兼容格式以便于后续分析或可视化。

---

## 2. 环境依赖与基本命令

使用 venus2gro 需要预先安装 Python 3.7 及以上版本（推荐 3.9）以及 numpy 库。执行 `python3 venus2gro.py -h` 可以查看帮助文档及使用说明。

---

## 3. 参数：输入与输出文件

使用 `-v` 或 `--venus` 指定 VENUS96 的输出文件。使用 `-o` 或 `--output` 指定输出文件名；若不指定，默认输出文件名为 traj.out，对于多条轨迹将自动生成为 traj_0.gro, traj_1.gro 等序列文件。

---

## 4. 参数：GRO 模板文件

使用 `-g` 或 `--gro` 指定一个模板 .gro 文件。该参数是可选的，用于补充 VENUS96 输出中可能缺失的拓扑信息或原子信息。

---

## 5. 参数：原子重排序

使用 `-r` 或 `--reorder` 指定原子重排序映射文件。当 VENUS96 输出中的原子顺序与模板 .gro 文件不一致时（例如 VENUS96 顺序为 H H H H C 而 .gro 为 C H H H H），需要通过该文件进行映射。重排序文件只需写入映射关系（如 `5 1 2 3 4` 表示将 VENUS96 中第 5 个原子映射到模板的第 1 位）。

---

## 6. 参数：轨迹合并

使用 `--no-split` 选项可以将 VENUS96 输出的所有轨迹写入同一个文件中，而不是分拆为多个文件。

---

## 7. 示例文件说明

示例目录中包含 VENUS96 输入文件 `ch4.dt5`（包含 5 条轨迹，每条 50,000 步，时间步长 0.1 fs）和输出文件 `ch4.out`（包含速度和坐标数据）。另外还包含提供拓扑参数的模板文件 `template.gro` 以及重排序文件 `reorder.txt`。

---

## 8. 示例运行命令

使用示例文件进行转换的命令为 `python3 ../src/venus2gro.py -v ch4.out -g template.gro -o ch4_traj.gro -r reorder.txt`。运行后将生成 5 个 `ch4_traj_序号.gro` 文件，这些文件可以直接导入 VMD 或 PyMOL 进行可视化。

---

## 9. 参考文献

VENUS96 程序的参考文献为 Hase, W. L. 等人发表在 Quantum Chemical Program Exchange (QCPE) Bulletin, 1996, 16 (4), 671 上的文章。GROMACS 的参考文献为 Abraham, M. J. 等人发表在 SoftwareX 2015, 1–2, 19–25 上的文章。

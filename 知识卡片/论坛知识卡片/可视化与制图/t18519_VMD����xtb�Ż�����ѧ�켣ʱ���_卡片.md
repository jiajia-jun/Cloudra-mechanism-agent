---
key: t18519
title: VMD����xtb�Ż�����ѧ�켣ʱ����/����pdb��Ϣ�ķ���
url: http://bbs.keinsci.com/thread-18519-1-1.html
domain: 可视化与制图
source: keinsci
year: 2020
cards: 6
---

# VMD����xtb�Ż�����ѧ�켣ʱ����/����pdb��Ϣ�ķ��� — 知识卡片

## 1. xtb 轨迹文件格式与输入输出差异

xtb 优化或分子动力学生成的轨迹文件默认为 xyz 格式，而输入文件通常为 pdb 格式。在后续处理中，若直接进行格式转换，可能会丢失连接性信息，导致 ligand 每个原子之间出现 TER 分隔符。xtb 6.3.3 及更高版本已支持输出带 MODEL 字段的 pdb 格式轨迹文件。

---

## 2. xtb 轨迹在 VMD 中的加载与帧处理

将 xtb 生成的轨迹文件加载至 VMD 时，通常先通过 `mol new` 加载初始 pdb 模板文件，再使用 `mol addfile` 加载 xyz 格式的轨迹文件。若 xtb 计算中使用了 `--cma` 选项，轨迹可能存在跳跃，建议删除初始帧（Frame 0）以避免可视化问题。

---

## 3. VMD 加载 xtb 轨迹的命令示例

在 VMD Tk Console 中执行以下命令可加载模板和轨迹：先使用 `mol new original_input.pdb`，随后使用 `mol addfile xtb.trj type xyz waitfor all`。若需删除特定帧以修正跳跃，可使用 `animate delete beg 0 end 0 skip 0 0`。

---

## 4. VMD 轨迹转换为 PDB 格式脚本

通过 VMD 脚本可将 xyz 轨迹转换为单一个 pdb 文件或分离为多个 pdb 文件。转换过程中使用 `atomselect` 定义原子选择集，利用 `molinfo` 获取帧数，并配合 `animate write pdb` 命令输出，支持指定起始帧、结束帧及跳帧步长。

---

## 5. 轨迹拆分脚本功能

VMD 脚本中的 `seppdb` 函数用于将轨迹的每一帧拆分为独立的 pdb 文件。该过程通过循环遍历帧数，利用 `$sel frame` 和 `$sel writepdb` 命令，按照设定的间隔（示例中为每 50 帧）将结构保存为 `trj_$i.pdb`。

---

## 6. VMD 与 xtb 版本兼容性说明

在使用 VMD 1.9.3 处理 pdb 文件时需注意，其输出可能不含 MODEL 字段。对于 xtb 6.3.3 之前的版本，建议使用上述脚本方法进行转换；新版 xtb 直接输出 pdb 轨迹时已包含 MODEL 字段。为确保连接性正确，脚本处理中常将 ATOM 和 HETATM 记录统一处理。

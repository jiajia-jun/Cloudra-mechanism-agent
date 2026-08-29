---
key: t28120
title: ���gentor����schrodinger python api���п��ٶ�ά�����ɨ��
url: http://bbs.keinsci.com/thread-28120-1-1.html
domain: 半经验与构象搜索
source: keinsci
year: 2022
cards: 9
---

# ���gentor����schrodinger python api���п��ٶ�ά�����ɨ�� — 知识卡片

## 1. 初始结构文件准备

示例体系结构文件名为 ACE-ALA-NME.xyz。为便于后续工具调用，可通过建立软链接将其重命名为 mol.xyz，命令为 `ln -s ACE-ALA-NME.xyz mol.xyz`。

---

## 2. 构象生成工具配置

使用 gentor 工具进行构象生成时需编辑 gentor.ini 配置文件。文件中的参数 `2-1` 设定为 `e5`，参数 `2-3` 设定为 `e5`。

---

## 3. 执行构象生成

运行 `./gentor` 命令可执行构象生成任务。该过程会显示最初生成的构象数量、未通过检查的构象数量以及最终成功导出的构象数量。

---

## 4. 构象生成结果输出

成功生成的构象会被导出至当前文件夹下的 traj.xyz 文件中。示例中显示最初生成了 5184 个构象，其中 89 个未通过检查，最终导出 5095 个有效构象。

---

## 5. 分子格式转换

为了使 Schrödinger 软件能够识别结构文件，需使用 OpenBabel 将 xyz 格式转换为 sdf 格式。转换命令为 `obabel -ixyz traj.xyz -osdf -O traj.sdf`。

---

## 6. OPLS4 力场结构优化

通过 Schrödinger Python API 脚本 opls_energy.py 可对 traj.sdf 中的结构进行分子力学结构优化。优化过程使用 OPLS4 力场，并计算优化后构象的能量。

---

## 7. 能量计算结果输出

执行脚本后会生成 traj_opls_energy.sdf 文件。该文件包含优化后的构象结构、构象编号以及对应的 OPLS4 能量数值。

---

## 8. 能量与二面角数据提取

opls_energy.py 脚本默认可提取并打印能量和二面角数据。若需将数据直接导出到文件，可在运行命令时使用重定向，例如 `run opls_energy.py traj.sdf > data.csv`。如需提取二面角数据绘图，可取消脚本第 10 至 29 行的注释。

---

## 9. 能量面可视化

使用 plotly 库绘制能量面的三维图可执行 `python plotly_surface.py data.csv`。运行后会生成 plotly_surface.html 文件，该文件可通过浏览器打开以动态查看图形。

---
key: t31439
title: ʹ��QEtoolkit�����ش���QE�ĸ��������ļ�
url: http://bbs.keinsci.com/thread-31439-1-1.html
domain: 其他量化软件
source: keinsci
year: 2022
cards: 18
---

# ʹ��QEtoolkit�����ش���QE�ĸ��������ļ� — 知识卡片

## 1. QEtoolkit 简介

QEtoolkit 是一个用于生成 Quantum ESPRESSO (QE) 各模块输入文件的辅助工具，其使用习惯与 Multiwfn 相似。该工具支持 pw.x、neb.x、dos.x、projwfc.x、hp.x、ph.x、pp.x、bands.x 等常用模块的输入文件生成，旨在简化参数设置和文件编写过程。用户通过交互式界面选择所需任务类型和选项，工具即可自动生成相应的输入文件。

---

## 2. Quantum ESPRESSO 主要模块功能

pw.x 模块用于执行自洽场计算、结构优化、分子动力学及NEB计算的初步步骤。neb.x 模块用于执行 CI-NEB (微动弹性带) 计算以寻找过渡态，但其能量和力的计算仍需依赖 pw.x。dos.x 和 projwfc.x 模块用于计算态密度 (DOS) 和投影态密度 (PDOS)。hp.x 模块通过线性响应理论计算 Hubbard U 参数，并支持 DFT+U+V 方法。ph.x 模块用于计算声子频率及声子谱。pp.x 模块用于后处理，可生成电荷密度、波函数实空间文件及静电势等信息。bands.x 模块用于处理 pw.x 产生的能带数据，生成适合 gnuplot 绘图的数据格式。

---

## 3. QEtoolkit 伪势库设置

使用 QEtoolkit 前需在 user defined parameters 中设置默认赝势库路径及 QE 版本。工具预置了 GBRV 高精度赝势、PSlibrary 的 pbe 和 pbesol PAW 赝势、ONCV 模守恒赝势 (NC) 等。GBRV 赝势计算速度快但在某些元素上可能存在精度问题；PSlibrary 的 pbesol 赝势适合构建高通量计算文件且精度较好；ONCV 赝势适合高精度计算。

---

## 4. QE 版本与赝势类型注意事项

不同版本的 Quantum ESPRESSO (如 7.1 版本) 对 DFT+U 的关键字书写可能有差异，使用时需注意版本兼容性。对于 Raman 光谱计算，若遇到精度不足或特定方法不支持的问题，可能需要修改源代码或更换赝势类型（如从 LDA+NC 改为 PBE+NC）。在使用赝势库时，需确保元素对应关系正确，否则可能导致计算错误。

---

## 5. BCC Fe 结构优化输入生成

执行 `./QEtoolkit.sh Fe.cif` 启动工具，依次选择 pw.x 模块 (0)、体相体系 (1)、Fe 为金属 (3)、周期性边界条件 (2)、结构优化 (4)。选择 6 定义磁矩，输入原子类型 1 并设置磁矩值为 0.5，输入 q 退出磁矩设置。最后设置 K 点为 3*3*3 (选项 8)，程序将生成 Fe.vcrelax.in 输入文件。

---

## 6. 磁矩设置规则

在 QEtoolkit 中定义磁矩时，磁矩值范围为 -1 到 1，计算公式为 (nalpha-nbeta)/(nalpha+nbeta)。若需设置反铁磁状态，应将同种类型的两组原子分别设置为相反的磁矩值 -n 和 n。设置完毕后输入 "q" 即可退出磁矩定义界面。

---

## 7. Cu(111) 功函数计算步骤 (SCF)

Cu(111) 的功函数计算推荐使用 Hartree 单位，首先需进行自洽场计算以确定 Fermi 能级。运行 `./QEtoolkit Cu111.cif`，选择 pw.x 模块 (0)、金属体系 (1)、金属 (3)、设置 K 点 (8)。K 点设置根据层状结构输入 3,3,1，最后生成 SCF 输入文件 (0)。

---

## 8. Fermi 能级获取与 Cube 文件生成

完成 SCF 计算后，使用 `grep Fermi Cu111.scf.out` 命令获取 Fermi 能级数值 (示例为 2.0330 eV)。随后使用 QEtoolkit 选择 pp.x 模块 (6) 及生成 Cube 文件选项 (5)，生成 esp.pp.in 文件。用户需手动修改 prefix 以匹配 pw.x 的设置，运行 pp.x 后得到 esp.cube 文件。

---

## 9. Multiwfn 绘制静电势平均值曲线

将生成的 esp.cube 文件载入 Multiwfn，选择主功能 13 (绘制曲线) 和子功能 18 (绘制 Z 方向平面平均值)。输入 Z、a 并选择绘图 (3)，选择绘制当前曲线 (6) 和绘制平面平均值 (9)。在图形窗口中读取 Z 轴方向真空层中间位置对应的 Z 值 (示例约为 0.51 a.u.)。

---

## 10. 功函数数值计算

计算功函数需将 QE 输出的 Hartree 单位 Z 值转换为 eV，并减去 Fermi 能级。计算公式为：功函数 = Z(au) * 13.6 - Fermi(eV)。例如，Z 值为 0.51 a.u.，Fermi 能级为 2.0330 eV，则功函数 = 0.51 * 13.6 - 2.0330 = 4.903 eV。

---

## 11. Si 能带结构计算流程

Si 的能带计算首先进行自洽场计算：运行 `./QEtoolkit Si.cif`，选择 pw.x (0)、晶胞 (1)、半导体 (2)、设置 K 点 (8) 为 4,4,4。随后进行能带计算，利用 QEtoolkit 结合 Seek-Path 获取高对称 K 点路径，修改 Si.bands.in 并运行。最后生成的 bands.dat.gnu 可用于 gnuplot 绘图，也可使用 QEtoolkit 的脚本功能 (选项 19) 辅助绘图。

---

## 12. FeO 的 Hubbard U 值计算准备

FeO 是反铁磁体系，当前版本 QEtoolkit 无法直接处理反铁磁态，需先设为铁磁态再手动修改。运行 `./QEtoolkit FeO`，选择 pw.x (0) 和磁矩定义 (6)，设置 Fe 磁矩为 0.5 (两个 Fe 原子需分为不同类型 Fe1 和 Fe2 以便后续设置不同 U 值)。接着选择 DFT+U (7) 和反铁磁 (2)，设置 K 点 (8) 为 3,3,3。

---

## 13. FeO Hubbard U 响应计算设置

生成的 FeO.scf.in 中 ntyp 会自动变为 3 (Fe1, Fe2, O)，且 Hubbard_U(1) 和 Hubbard_U(2) 初始值设为 1.D-8。使用 QEtoolkit 生成 hp.x 输入文件 (选项 3)，并对每种元素设置线性响应 U 值计算 (选项 1)。需确保 hp.in 中的 prefix 与 scf.in 一致。

---

## 14. 修正 SCF 输入用于 hp.x 计算

为运行 hp.x 计算 Hubbard U，需将 FeO.scf.in 复制并修改为 FeO.scf2.in。修改内容包括设置 occupations='fixed'，添加 tot_magnetization=0 和 nbnd=26，并在 &ELECTRONS 中添加 startingpot='file' 和 startingwfc='file'。运行 pw.x 和 hp.x 后，结果将输出至 FeO.Hubbard_parameters.dat 文件，其中包含 Fe1 和 Fe2 的 U 值 (示例为 5.58 和 5.97)。

---

## 15. TiO2(110)-H2O 体系声子频率计算

针对表面吸附分子 H2O 的 Gamma 点声子频率计算，首先使用 QEtoolkit 生成 SCF 和 ph.x 输入文件。选择分子振动模块 (2)、slab 模型 (1)、Gamma 点振动频率 (1)，输入 H2O 分子对应的原子索引 (如 37-39)。按照提示依次运行 pw.x 和 ph.x，计算结果包含在 TiO2_H2O.ph.out 文件末尾的 3N 个频率中。

---

## 16. 吸附分子热力学性质计算

利用 QEtoolkit 生成 Shermo 程序所需的输入文件以计算吸附分子的热力学性质。运行 `./QEtoolkit TiO2.relax.in`，选择 ph.x 模块 (2)、slab 模型提取频率 (1)、生成 Shermo 输入文件 (2)，并指定频率输出文件 TiO2_H2O.ph.out。在生成的文件中手动输入电子能量 (*E, Hartree 单位) 和波数 (*wavenum)，并在 Shermo 中设置 imode=1 以忽略平动和转动贡献。

---

## 17. 气相 CO2 分子振动频率计算

气相 CO2 分子的 Gamma 点声子频率计算需在 ph.x 后增加 dynmat.x 步骤以施加声子求和规则 (ASR)。使用 QEtoolkit 选择 ph.x 模块 (2) 和气相分子 (2)，工具会提示 ASR 施加步骤 (Step 3)。计算过程包括 pw.x 自洽计算、ph.x 声子计算及 dynmat.x 处理，最终在 dynmat.mold 文件中得到 3N-5 个振动频率 (线性分子)。

---

## 18. 气相分子热力学性质计算

计算气相 CO2 的热力学性质时，使用 QEtoolkit 选择 ph.x (2)、气相分子 (2)、生成 Shermo 文件 (2)，工具将自动读取 dynmat.mold 文件中的频率信息。生成的 CO2.shm 文件需手动补充电子能量 (*E, Hartree)，并使用 Shermo 运行命令计算热力学数据。注意气相分子计算时需保留平动和转动贡献 (imode=0)。

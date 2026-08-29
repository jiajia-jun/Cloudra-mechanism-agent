---
key: t12510
title: ʹ��VMD��޶���SiO2��׽���
url: http://bbs.keinsci.com/thread-12510-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2019
cards: 8
---

# ʹ��VMD��޶���SiO2��׽��� — 知识卡片

## 1. VMD脚本构建Gyroid相结构

Packmol软件不支持直接构建Gyroid（螺旋二十四面体）相结构，但可利用VMD（Visual Molecular Dynamics）的绘图功能结合Tcl脚本实现。用户在VMD中通过编写脚本执行特定的数学函数运算来选取并保留满足Gyroid方程的原子，从而构建出所需的三维周期结构模型。

---

## 2. carve.tcl脚本背景显示设置

脚本的前几行用于配置VMD的显示环境参数，以便更清晰地观察模型。相关命令包括：将背景颜色设为白色（`color Display Background white`），开启GLSL渲染模式（`display rendermode GLSL`），关闭深度暗示（`display depthcue off`），以及将投影方式设置为正交投影（`display projection Orthographic`）。

---

## 3. carve.tcl脚件加载与初始显示

脚本使用 `mol new 1.pdb` 命令加载名为 `1.pdb` 的初始模型文件，并使用 `pbc box` 命令显示周期性边界盒。通过 `mol modstyle 0 top VDW 1.000000 12.000000` 命令，将顶部分子的显示风格设置为范德华球体模式，其半径缩放比例为1.0，分辨率为12。

---

## 4. carve命令的调用格式与参数含义

脚本定义了一个名为 `carve` 的过程，调用格式为 `carve 1.42 90 90 90`。第一个参数 `val`（如1.42）是截断阈值，取值范围在0到1.5之间；后续三个参数 `{a 90} {b 90} {c 90}` 代表模型在X、Y、Z方向上的尺寸，默认值均为90。

---

## 5. Gyroid相的数学判定方程

脚本利用数学表达式来筛选原子，判定方程为：`abs{sin(2*$M_PI*x/$a)*cos(2*$M_PI*y/$b)+sin(2*$M_PI*y/$b)*cos(2*$M_PI*z/$c)+sin(2*$M_PI*z/$c)*cos(2*$M_PI*x/$a)} <= $val`。只有坐标（x, y, z）满足此不等式的原子才会被选中并保留。

---

## 6. 脚本构建Gyroid模型的处理流程

脚本首先将模型中心移动到坐标原点，然后根据Gyroid方程筛选原子，最后将筛选出的原子模型保存为 `2.pdb` 文件。此过程中输入文件 `1.pdb` 通常需由Material Studio（MS）构建，且要求其晶格参数为正交晶系（即角度均为90度），a、b、c边长需根据实际模型尺寸手动设定。

---

## 7. 大原子数模型的文件格式限制与处理

当构建的模型包含超过10万个原子时，生成的 `.pdb` 文件可能会因PDB格式限制（最多支持99999个原子）而报错。针对这种情况，可以使用Material Studio自带的Perl脚本来处理或保存模型，以规避原子数量的限制。

---

## 8. VMD构建模型后的原点归位注意事项

使用VMD构建模型后，生成的文件坐标原点可能发生变动。若后续操作需要删除不可见原子或进行其他基于原点的处理，需要注意此时模型的原点位置已不同于初始状态。

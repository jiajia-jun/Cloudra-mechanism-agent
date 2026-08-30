---
key: t17104
title: ��ASE��ʹ��xtb-6.3.0(pre.2)��py�ű�
url: http://bbs.keinsci.com/thread-17104-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 8
---

# ��ASE��ʹ��xtb-6.3.0(pre.2)��py�ű� — 知识卡片

## 1. ASE与xtb联用优化方法

Atomic Simulation Environment (ASE) 提供接口调用 xtb 进行几何优化，支持多种 xtb 原生不支持的优化算法。ASE 提供的优化算法包括 BFGS、BFGSLineSearch、LBFGS、LBFGSLineSearch、GPMin、MDMin 和 FIRE。该方法支持处理 1D、2D 和 3D 周期性边界条件 (PBC) 体系的结构优化过程。

---

## 2. xtb-python模块环境配置

使用 ASE 接口调用 xtb 需安装 xtb-python 模块并配置环境变量。需编辑 ~/.bashrc 文件添加 xtb 的库路径，如 export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/mnt/d/xtb_Linux/xtb_6.3.pre2/lib64，并执行 source ~/.bashrc。随后切换至 xtb 源码下的 python 目录，执行 python3 setup.py install --prefix=/home/yjy/.local 完成安装。

---

## 3. ASE脚本定义晶胞与周期性边界条件

在 ASE 脚本中可设置正交晶胞参数和周期性边界条件。通过 mol.cell = [a, b, c] 设定晶胞矢量，参数示例为 7.8598, 7.8598, 19.5257。通过 mol.pbc = (True, True, True) 开启 x、y、z 三个方向的周期性边界条件。

---

## 4. ASE脚本固定原子设置

ASE 脚本通过 FixAtoms 约束来固定指定的原子索引。原子索引通过字符串定义，如 "1,3-4,6-17,19-20,22-33,35-36,38-49,51-52,54-64"，其中单个数字表示该原子，连字符表示范围。labels_convertion 函数将此类字符串转换为从 0 开始的索引列表传递给 FixAtoms(indices=...)。

---

## 5. GFN1-xTB计算参数设置

使用 ASE 调用 GFN1-xTB 方法进行计算时，通过 mol.calc = GFN1(...) 设置计算参数。可设置的关键参数包括 accuracy=1、electronic_temperature=300 和 max_iterations=250。体系的总电荷和自旋多重度通过 set_initial_charges 和 set_initial_magnetic_moments 方法平均分配给所有原子。

---

## 6. 几何优化过程与参数控制

使用 BFGS 算法进行几何优化时，需设定轨迹文件和重启文件。优化命令为 opt = BFGS(mol, trajectory=name+".traj", restart=name+".pckl")。调用 opt.run(fmax=0.001, steps=800) 执行优化，最大迭代步数设为 800，收敛标准设为最大受力小于 0.001 eV/Å。

---

## 7. 优化结果输出与文件处理

优化脚本会计算并输出初始几何和优化后几何的单点能，单位同时显示 eV 和 Hartree。脚本使用 write 函数将最终结构和轨迹分别保存为 name+"_opted.xyz" 和 name+"_traj.xyz"。计算结束后会自动删除 xtb 生成的 xtrestart 和 wbo 临时文件。

---

## 8. PBS作业提交脚本配置

PBS 作业提交脚本用于指定 ASE 与 xtb 联用计算的资源环境。脚本设置节点、核心数 (#PBS -l nodes=1:ppn=12) 和最大运行时间 (#PBS -l walltime=1440:00:00)。通过 export OMP_NUM_THREADS=12 和 export MKL_NUM_THREADS=12 配置线程数，并执行 python3 ${FILENAME} ${FILENAME%.py} 运行 Python 脚本。

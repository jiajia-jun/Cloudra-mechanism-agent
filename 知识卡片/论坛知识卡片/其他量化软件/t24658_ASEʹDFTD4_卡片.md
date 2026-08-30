---
key: t24658
title: ASE��ʹ��DFTD4
url: http://bbs.keinsci.com/thread-24658-1-1.html
domain: 其他量化软件
source: keinsci
year: 2021
cards: 5
---

# ASE��ʹ��DFTD4 — 知识卡片

## 1. DFT-D4对PBC系统的支持情况

Grimme发布的DFT-D4程序dftd4自3.2.0版本起直接支持-pbc命令参数，能够处理周期性边界条件（PBC）系统。此前已有关于dftd4与VASP 6.2.1结合使用的方案，而新版本内置了对PBC的支持。该程序通过C语言API提供接口，并计划支持直接访问QCArchive项目。

---

## 2. DFT-D4的Python接口与集成途径

DFT-D4提供了Python目录和API，XTB也采用了相同路径。ASE（Atomic Simulation Environment）官方尚未包含D4的库，但D4支持直接调用ASE。用户可以通过C API方式调用D4，相关说明包含在生成的dftd4.txt文件中。

---

## 3. DFT-D4的安装命令

使用Conda安装DFT-D4 Python接口的命令如下。需先添加conda-forge频道，随后安装dftd4-python包，安装完成后即可在3.2.0版本中使用。
```bash
conda config --add channels conda-forge
conda install dftd4-python
```

---

## 4. DFT-D4在ASE中的调用方法

在ASE中调用DFT-D4的代码为`from dftd4.ase import DFTD4`。使用方法与D3类似，通过`add_calculator(calc)`即可将DFT-D4挂载到DFT计算流程中。

---

## 5. DFT-D4与D3计算结果差异对比

在特定测试体系中，DFT-D4与D3的能量计算结果差异约为50 meV/atom，力的梯度变化约为20 meV/A。这种差异表明D4与D3在结构优化过程中会产生不同的结果。

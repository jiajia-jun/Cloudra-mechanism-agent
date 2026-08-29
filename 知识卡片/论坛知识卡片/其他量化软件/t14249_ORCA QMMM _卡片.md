---
key: t14249
title: ORCA QMMM ����
url: http://bbs.keinsci.com/thread-14249-1-1.html
domain: 其他量化软件
source: keinsci
year: 2019
cards: 5
---

# ORCA QMMM ���� — 知识卡片

## 1. ORCA 4.2.0 QM/MM 概述与文件支持

ORCA 4.2.0 版本引入了对 QM/MM（量子力学/分子力学）计算的支持，具备读取 top 和 pdb 文件的能力。该软件能够与 Chemshell 结合进行多种计算任务，包括几何结构优化、势能面扫描、过渡态优化以及频率计算。ORCA 可直接读取 top 与 pdb 文件，减少了文件格式转换的繁琐步骤，便于开展相关研究。

---

## 2. 力场文件 ORCAFF.prms 的格式与要求

ORCA 声称支持读取 top 文件，但实际上直接读取的格式仅限于 CHARMM 类型的 top 文件。对于 VMD 或 QWikMD 生成的 CHARMM.psf 文件以及 AMBER 的 prmtop 文件，软件均不提供直接支持，且将 AMBER 格式转换为 CHARMM.psf 也是不可行的。若需使用非原生支持的拓扑文件，需利用 parmed 等工具将 CHARMM/GMX/AMBER 格式转换为 ORCA 专属的力场参数文件 ORCAFF.prms。

---

## 3. QM/MM 体系原子索引的起始编号

在 QM/MM 输入文件中，QM 原子（QMatom 或 ActiveAtom）的索引是从 0 开始计数的。这与 ORCAFF.prms 文件中的索引编号习惯不同，后者通常从 1 开始计数。

---

## 4. QM/MM 几何优化的控制参数

在进行 QM/MM 几何优化时，建议设置特定的几何控制参数以避免优化停滞。可以在输入块中设置最大迭代次数（MaxIter）为 50，坐标系统设为冗余内坐标，收敛标准设为宽松，以确保优化过程能够顺利完成。

```text
%geom
 MaxIter 50
 coordsys redundant
 Convergence loose
end
```

---

## 5. ORCA QM/MM 计算的输出文件特点

ORCA 在进行 QM/MM 计算时，输出信息会被拆分为多个独立文件，这与 Gaussian 将所有信息输出到一个日志文件中的方式不同。ORCA 会生成轨迹文件（后缀为 .dcd）、独立的 SCF 文件、梯度文件，以及包含能量变化（deltaE）、梯度均方根（RMS(Grad)）等数据的 CSV 文件。生成的 CSV 文件使用逗号作为分隔符，但部分区域可能错误地使用分号分隔，存在已知的格式 BUG。

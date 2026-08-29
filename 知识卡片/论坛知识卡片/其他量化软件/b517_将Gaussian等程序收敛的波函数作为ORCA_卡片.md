---
key: b517
title: 将Gaussian等程序收敛的波函数作为ORCA的初猜波函数的方法
url: http://sobereva.com/517
domain: 其他量化软件
source: blog
year: 2019
cards: 14
---

# 将Gaussian等程序收敛的波函数作为ORCA的初猜波函数的方法 — 知识卡片

## 1. ORCA与Gaussian的SCF收敛性特点对比

ORCA是功能强大的量子化学程序，但在SCF收敛方面表现不如Gaussian稳定，且在产生初猜波函数的灵活性上也不如Gaussian。Gaussian用户可以利用GaussView构建片段组合波函数作为初猜，或使用stable=opt自动优化出稳定波函数，这对双自由基和反铁磁性耦合体系研究尤为重要。

---

## 2. Multiwfn转换波函数的功能

Multiwfn程序支持载入.fch、.molden、GAMESS-US/Firefly输出文件等包含基组定义和轨道信息的格式，并能导出.mkl文件。.mkl文件是老版本Molekel的输入文件，可以通过ORCA自带的orca_2mkl工具转换为.gbw文件，从而作为ORCA的初猜波函数。

---

## 3. 基组类型的一致性要求

ORCA基于球谐型高斯函数进行计算，因此若使用Multiwfn将其它程序的波函数转换为ORCA的初猜，源程序计算时也必须使用球谐型高斯函数（如在Gaussian中使用def2-SVP或5d关键词），以保证基函数类型的一致性。

---

## 4. 使用Multiwfn导出.mkl文件的步骤

在Multiwfn中载入波函数文件后，依次选择“其它功能 (Part 1)”、“导出文件”、“导出mkl文件”，输入文件名并确认该文件是给ORCA作为初猜使用。程序会对.mkl文件进行特殊处理，随后可利用orca_2mkl工具将其转换为.gbw文件。

---

## 5. ORCA读取.gbw初猜波函数的设置

将生成的.gbw文件与ORCA输入文件置于同一目录下，ORCA会自动读取同名的.gbw文件作为初猜波函数。若文件名不同，需在ORCA输入文件中添加moread关键词，并通过%moinp "filename.gbw"指定路径。

---

## 6. 计算示例：丁烷双自由基的波函数转换流程

在Gaussian中使用B3LYP/def2-SVP和stable=opt计算丁烷双自由基C4H8，通过formchk生成.fch文件。使用Multiwfn将该.fch文件导出为.mkl文件，再利用orca_2mkl工具生成.gbw文件，最后在ORCA中使用UKS B3LYP/G def2-SVP读取该.gbw文件进行计算。

---

## 7. 波函数转换对SCF收敛的影响

使用Gaussian收敛的波函数作为ORCA的初猜时，ORCA的SCF迭代通常能迅速收敛，第一轮迭代的能量和密度矩阵变化即极小。若Gaussian和ORCA均使用HF方法，ORCA甚至可能仅需一次迭代即可收敛。

---

## 8. 基组一致性的注意事项

为确保Gaussian收敛的波函数在ORCA中也能收敛，必须保证两者使用的基组精确一致。例如，Gaussian默认使用笛卡尔型d基函数，而ORCA总是使用球谐型，因此在Gaussian中需使用5d关键词（尽管ORCA用户较少使用Pople基组）。

---

## 9. 分子坐标对齐的注意事项

Gaussian计算时会自动将分子调整至标准朝向，导致最终波函数中的坐标可能与原始输入不同。为避免坐标不匹配，应在ORCA输入文件中使用标准朝向的坐标，或在Gaussian计算时加入nosymm关键词禁止重新定向。

---

## 10. 避免基组原始定义被修改

Gaussian在计算广义收缩基组（如ANO、Dunning相关一致性基组）时，会自动去除重复指数或收缩系数极小的原始高斯函数，而ORCA不做此处理。为保持一致，建议在Gaussian计算时加入int=NoBasisTransform关键词。

---

## 11. 避免去除线性依赖基函数

建议在Gaussian计算中添加IOp(3/32=2)关键词，特别是在使用弥散函数时，以防止程序自动去除线性依赖的基函数。这有助于确保Gaussian和ORCA使用完全一致的基函数，提高波函数转换的成功率。

---

## 12. DFT积分格点精度的建议

若在遵循基组和坐标一致性要求后，ORCA的SCF仍无法收敛，建议在Gaussian和ORCA中均使用更高质量的DFT积分格点精度，并在ORCA计算中关闭RI（分辨率恒等）近似。

---

## 13. chk到gbw的批量转换脚本功能

chk2gbw.sh脚本可以批量将当前目录下的.chk文件转换为.gbw文件，并自动生成包含moread关键词和%moinp设置的ORCA输入文件。脚本运行过程中需调用formchk、Multiwfn和orca_2mkl工具。

---

## 14. gbw到chk的批量转换功能

使用Multiwfn自带的gbw2chk.sh脚本，可以将当前目录下的所有.gbw文件转换为同名的.chk文件。转换后的.chk文件可被Gaussian通过guess=read关键词读取，利用ORCA的波函数作为初猜进行计算，处理UHF/UKS波函数需使用2021年10月1日及以后更新的Multiwfn版本。

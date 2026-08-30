---
key: t16499
title: ��ORCA�û������ԼMultiwfn�����ӱ��澲���Ʒ�����ʱ�ķ���
url: http://bbs.keinsci.com/thread-16499-1-1.html
domain: 其他量化软件
source: keinsci
year: 2020
cards: 7
---

# ��ORCA�û������ԼMultiwfn�����ӱ��澲���Ʒ�����ʱ�ķ��� — 知识卡片

## 1. Multiwfn 静电势计算速度

Multiwfn 内部计算静电势的代码经过优化，计算速度获得了巨大的提升。Multiwfn 使用的高效静电势算法相关论文发表在 PCCP 期刊上。关于 Multiwfn 计算静电势速度的详细介绍可参考特定文献链接。

---

## 2. Multiwfn 与 Gaussian cubegen 的速度对比

Multiwfn 生成静电势格点的速度已经显著超过 Gaussian 自带的 cubegen。通过 Multiwfn 可以直接读取 Gaussian 源文件以及利用 cubegen 生成格点文件，对比测试显示 Multiwfn 在耗时上更短。相关的详细对比数据已在博客文章中发布。

---

## 3. Multiwfn 处理 ORCA 文件生成静电势

ORCA 用户可以将 gbw 或 molden 文件载入 Multiwfn。在测试案例中，处理 100 个原子的体系仅需约 2 秒即可完成静电势计算。

---

## 4. Multiwfn 读取 .fch 文件与 Gaussian 兼容性

Multiwfn 可以将 .fch 文件作为输入文件。这表明在读取波函数信息方面，Multiwfn 具备与 Gaussian 程序相当的兼容能力。

---

## 5. ORCA 用户使用orca_vpot生成静电势

若用户希望继续使用 ORCA 程序生成的静电势，可以在 ORCA 输出文件的特定位置直接输出数值或使用 orca_vpot 工具。生成的数据同样可以载入 Multiwfn 进行后续的静电势绘图分析。

---

## 6. def2-TZVP 基组下的静电势计算

在使用 def2-TZVP 基组进行积分精度的静电势计算时，不需要进行额外设置。直接使用 Multiwfn 内部计算静电势功能即可获得结果，过程无任何阻碍。

---

## 7. Multiwfn 未来版本的静电势绘图优化

未来版本的 Multiwfn 将进一步优化静电势绘图功能，以提高效率。届时用户在进行静电势可视化时可能不再需要进行额外的中间处理步骤。

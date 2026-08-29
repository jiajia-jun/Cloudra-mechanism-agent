---
key: t29458
title: ����ABCluster��Multiwfn�Զ������л����������ļ�����ȫ���Ż�
url: http://bbs.keinsci.com/thread-29458-1-1.html
domain: 半经验与构象搜索
source: keinsci
year: 2022
cards: 15
---

# ����ABCluster��Multiwfn�Զ������л����������ļ�����ȫ���Ż� — 知识卡片

## 1. ABCluster 软件简介与 rigidmol 模块

ABCluster 是广泛使用的团簇结构优化遗传算法软件。软件支持原子团簇、分子团簇及 rigidmol 等多种团簇类型的搜索。其中的 rigidmol 模块适合对刚性分子进行快速团簇结构预测，ABCluster 官网 Stories 页面展示的多个大气化学算例使用了该模块。

---

## 2. 获取 rigidmol 预备文件的旧版流程

旧版 ABCuster 中，生成 rigidmol 所需的分子文件（如原子类型）较为麻烦。流程通常包括手动指定原子类型，或使用 CHARMMGen 生成并随后进行繁琐的格式转换。这种手动生成方式效率较低且容易出错。

---

## 3. ABCluster 3.1 及 topgen 工具的功能增强

从 ABCluster 3.1 版本开始，软件集成了自带的 topgen 功能。该功能结合了 Multiwfn 的文档功能，能够自动生成处理刚性分子团簇所需的全部文件。这使得构建 ABCluster 全局优化的输入文件变得更加简便。

---

## 4. 准备钳形配体结构的计算步骤

准备钳形配体（pincer）结构需先使用 GaussView 构建初始模型并进行几何优化。优化需在 Gaussian 中运行，推荐使用 `B3LYP/6-31g(d)` 级别并开启 `geom=connectivity`。优化完成后，需使用 `formchk` 命令将 `.chk` 文件转换为 `.fchk` 文件，并将优化后的结构坐标提取为 `.xyz` 文件。

---

## 5. Gaussian 输入文件示例

在 Gaussian 中对钳形配体进行优化的输入文件内容如下。该任务使用 24 核 CPU 和 20GB 内存，检查点文件命名为 `pincer.chk`。计算结束后将得到结构和波函数信息。

```
%nprocs=24
%mem=20GB
%chk=pincer.chk
#b3lyp/6-31g(d) geom=connectivity

tile

0 1
[ coordinates ]
```

---

## 6. 使用 Multiwfn 计算 RESP 电荷

使用 Multiwfn 对 `pincer.fchk` 进行计算可以得到 RESP 电荷。操作流程为启动 Multiwfn 后依次输入 `7`、`18`、`1` 和 `y`。计算结果将自动存储在 `pincer.chg` 文件中。

---

## 7. 电荷计算方法的选择建议

对于主客体体系或涉及配位键的体系，RESP 拟合电荷可能会产生非物理的对称性。在这种情况下，推荐使用更健壮且物理意义明确的 Hirshfeld 电荷。Multiwfn 实现了高效的 Hirshfeld 电荷算法，相关细节可参考 Phys. Chem. Chem. Phys. 2021, 23, 20323-20328 期刊论文。

---

## 8. topgen 命令的执行与输出

在准备包含配体信息的 `pincers.xyz` 文件后，执行 `topgen pincers.xyz` 命令可进行拓扑分析。该命令将输出分析过程日志，并生成 5 个特定格式的文件供后续使用。

---

## 9. topgen 生成的文件说明

topgen 运行后会生成 5 个文件，分别用于不同的目的。`pincer.gjf` 是 Gaussian 输入文件；`pincer-cycles.txt` 包含原子环结构信息；`pincer-bonding.xyz` 包含成键信息；`pincer-rigid.xyz` 用于 rigidmol 优化；`pincer.psf` 包含拓扑信息用于 NAMD 或 CHARMM。

---

## 10. topgen 中的原子类型推断与电荷调整

topgen 在生成 `.rigid.xyz` 和 `.psf` 文件时会使用图表示学习算法推断原子类型，相关算法发表于 J. Chem. Phys. 2022, 156, 204108。程序会计算总电荷（如示例中的 1.8360），用户可能需要根据目标总电荷调整数值，或利用 Multiwfn 重新拟合 RESP 电荷。

---

## 11. 手动修正电荷到 topgen 生成文件的方法

若需将 Multiwfn 计算的电荷（如氧原子电荷 -0.1977931830）替换到 topgen 生成的文件中，需同时修改 `pincer-rigid.xyz` 和 `pincer.psf`。在 `pincer-rigid.xyz` 中，将数值替换到参数列（如 epsilon 之前）；在 `pincer.psf` 中，将数值替换到对应原子行的电荷列。

---

## 12. rigidmol 全局优化的输入文件配置

进行 rigidmol 全局优化需要配置 `.cluster` 和 `.inp` 文件。`.cluster` 文件定义分子组成（如 1 个 pincer 和 13 个水分子）及搜索范围（如 `* 20.0000`）。`.inp` 文件设置遗传算法参数，如种群大小 100、最大代数 100 等。

---

## 13. 钳形配体-水分子团簇配置示例

针对 1 个钳形配体和 13 个水分子的体系，`pincer-wat.cluster` 文件内容如下。文件指定了组分数目、各自的坐标文件以及搜索箱的大小。水分子模型使用 `tip4p.xyz`，配体使用 `pincer-rigid.xyz`。

```
2
pincer-rigid.xyz 1
tip4p.xyz 13
* 20.0000
```

---

## 14. 钳形配体-水分子团簇优化参数示例

`pincer-wat.inp` 文件设置了优化的具体参数。种群大小设为 100，最大迭代代数为 100，保存 30 个低能异构体。输出文件前缀设为 `pincer-wat`。

```
pincer-wat.cluster # cluster file name
100 # population size
100 # maximal generations
3 # scout limit
10.0 # amplitude
pincer-wat # save optimized configuration to .xyz and .gjf
30 # number of LMs to be saved
```

---

## 15. rigidmol 计算的执行与结果查看

执行 `rigimol pincer.inp > pincer.out` 命令即可开始全局优化计算。计算完成后，全局最小值结构通常保存在 `pincer-wat-LM` 目录下的 `0.xyz` 文件中。优化结果能够显示水分子围绕配体形成的氢键网络结构。

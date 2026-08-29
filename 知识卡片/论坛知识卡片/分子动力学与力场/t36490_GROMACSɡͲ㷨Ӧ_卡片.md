---
key: t36490
title: GROMACS��ɡ�Ͳ����㷨Ӧ�����
url: http://bbs.keinsci.com/thread-36490-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2023
cards: 15
---

# GROMACS��ɡ�Ͳ����㷨Ӧ����� — 知识卡片

## 1. 伞形采样算法原理

伞形采样是一种增强采样算法，广泛应用于计算生物分子模型中结合自由能、构象变化以及结合/解离过程。该算法通过引入偏差势能，迫使体系在Phi/Psi等二面角旋转或跨越能垒时进行采样，从而克服能垒限制。该算法通常用于计算溶剂/结合自由能、结合自由能以及受体-配体解离等过程。

---

## 2. 伞形采样的理论基础

常规分子动力学模拟（无偏差分子动力学模拟）难以观察到跨越较大能垒的稀疏事件，因为系统处于热力学稳定态或亚稳态时，相关构象之间的跃迁概率极低。伞形采样通过施加外部偏差势能，强制体系沿反应坐标跨越能垒，实现在有限时间内完成采样。后续需通过加权直方图分析方法（WHAM）重构出沿反应路径的平均力势（PMF）。

---

## 3. GROMACS 伞形采样基本步骤

在 GROMACS 中进行伞形采样主要包含三个步骤。首先需确定反应坐标，通过 mdp 文件中的 pull code 进行设置。其次需要沿着反应坐标生成一系列窗口，并确保每个窗口有足够的重叠。最后通过 WHAM 计算沿反应路径的平均力势（PMF），根据计算结果选择作为窗口的数据。

---

## 4. Pull code 基础参数设置

Pull code 用于控制伞形采样的牵引参数。`pull = yes` 开启牵引功能；`pull_ngroups = 2` 设置牵引组数量；`pull_group1_name` 和 `pull_group2_name` 指定牵引组名称（对应 index 文件）；`pull_coord1_type = umbrella` 指定使用伞形采样；`pull_coord1_geometry` 设置几何类型（如 distance）；`pull_coord1_dim = N N Y` 指定牵引维度（N代表关闭，Y代表开启）；`pull_coord1_rate` 设置牵引速率；`pull_coord1_k` 设置弹簧力常数；`pull_coord1_start = yes` 自动将初始参考距离添加到 pull-coord1-init。

---

## 5. Pull geometry 类型：distance

`distance` 模式通过计算两组质心之间的距离来进行牵引。该模式下，牵引向量即连接两组质心的向量，无需手动指定方向。使用时需注意，牵引距离必须小于盒子周期性边界长度的一半，否则容易产生错误。该模式适用于需要两组质心直接相互靠近或远离的场景，如分子跨膜或结合过程。

---

## 6. Pull geometry 类型：direction

`direction` 模式通过固定的 `pull-coord-vec` 向量在 x、y、z 方向进行牵引。牵引距离同样必须小于盒子周期性边界长度的一半。该模式适用于需要严格控制牵引方向的应用场景，如沿膜法线方向的跨膜或结合过程，能够限制粒子在特定方向上的运动。

---

## 7. Pull geometry 类型：direction-periodic

`direction-periodic` 模式与 `direction` 类似，但支持使用周期性边界条件进行相对距离计算。当粒子移动距离超过盒子长度的一半时，会自动映射到周期性镜像中。该模式常用于通过牵引改变参考位置，且粒子可能离开原始盒子的情况。该模式无法用于 NPT 系综，因为盒子大小可能发生变化。

---

## 8. Distance 模式应用于跨细膜体系的限制

在使用 `distance` 模式实现分子跨膜时，直接将溶质（SOLU）和膜（MEMB）设为两个牵引组可能无法实现跨膜，因为溶质与膜的距离通常大于膜厚度的二分之一，导致溶质无法穿过膜。解决方法包括：创建一个虚拟组（POT，如选择一个水分子），固定在膜中心附近或稍远位置（如 1nm），将 SOLU 和 POT 设为牵引组，通过改变 SOLU 和 POT 的距离驱动跨膜；或选择距离膜较远的原子作为牵引组。

---

## 9. Direction 模式应用于跨细膜体系的设置

使用 `direction` 模式实现跨膜需要定义两组，通常将溶质映射为 SOLU，将膜原子映射为参考坐标。确定溶质与膜的初始位置关系后，设置 `pull-coord1-vec` 向量即可开始牵引。该方法需要手动指定牵引方向向量（如 `0.0 0.0 1.0`）。

---

## 10. Direction-periodic 模式应用于跨细膜体系的注意事项

`direction-periodic` 模式应用于跨膜的思路与 `direction` 类似，但粒子可以跨越周期性边界。使用时需确认 Increasing distance 要小于 Mirror distance 1 和 2 之和，GROMACS 会自动处理相对距离计算。对于跨膜过程，距离变化通常不超过 Increasing distance 的一倍，计算相对简单。

---

## 11. Pull code 示例：distance 模式

在 `distance` 模式下，`pull_group2_name` 建议实施位置约束，以确保参考组在模拟过程中位置不发生明显变化。参数示例包括：`pull_coord1_geometry = distance`，`pull_coord1_dim = N N Y`，`pull_coord1_rate = 0.005`，`pull_coord1_k = 1500`。该配置通常配合位置约束文件使用以固定参考组。

---

## 12. Pull code 示例：direction 模式

在 `direction` 模式下，需要指定 `pull_coord1_geometry = direction` 以及牵引向量 `pull-coord1-vec`。参数示例包括：`pull_group2_name = MEMB`（将参考组设为膜），`pull_coord1_dim = N N Y`，`pull_coord1_rate = 0.005`，`pull_coord1_k = 1500`，`pull-coord1-vec = 0.0 0.0 1.0`。该向量定义了溶质运动的方向。

---

## 13. Pull code 示例：direction-periodic 模式

在 `direction-periodic` 模式下，需额外设置周期性边界相关参数。参数示例包括：`pull-group1-pbcatom` 和 `pull-group2-pbcatom`（指定 PBC 时的参考原子索引），`pull-pbc-ref-prev-step-com = yes`（使用上一步的质心作为参考以处理周期性边界），`pull_coord1_geometry = direction-periodic`。该模式仅适用于 NVT 系综。

---

## 14. 伞形采样参数选择注意事项

选择 `distance` 或 `direction` 模式时，必须保证牵引距离小于盒子最小边长的一半。`direction-periodic` 模式只能用于 NVT 系统的模拟，若体系需要使用 NPT，则应避免使用此模式。弹簧力常数 `k` 的选择取决于体系大小，体系越大所需力常数通常越大；对于小体系，1000-1500 kJ mol^-1 nm^-2 通常足够；对于蛋白质-配体结合体系，可能需要更大的力常数。

---

## 15. 伞形采样模拟流程与均衡

伞形采样作为增强采样方法，通常需要实现一个完整的模拟过程，包括预均衡和正式采样。在计算自由能之前，必须确保体系达到平衡状态，去除非平衡态的数据对结果的影响。

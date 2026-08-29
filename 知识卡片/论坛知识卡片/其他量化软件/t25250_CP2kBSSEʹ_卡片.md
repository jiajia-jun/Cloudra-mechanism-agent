---
key: t25250
title: CP2k��BSSE��ʹ��
url: http://bbs.keinsci.com/thread-25250-1-1.html
domain: 其他量化软件
source: keinsci
year: 2021
cards: 8
---

# CP2k��BSSE��ʹ�� — 知识卡片

## 1. BSSE 产生原理与 Boys-Bernardi 校正

使用高斯基组计算分子间相互作用能时，基组叠加误差(BSSE)源于分子 A 的基函数延伸到了分子 B 的空间，反之亦然。校正方法要求在计算复合物 AB 时，计算分子 A 所用的基函数应包含分子 B 的基函数，以消除因基组不完备性导致的能量低估。该能量校正公式为 $E_{BSSE}=[E(A)-E_{AB}(A)] + [E(B)-E_{AB}(B)]$，其中 $E_{AB}(A)$ 表示将 B 设为鬼原子(无核电子势)后计算片段 A 的能量。

---

## 2. CP2K 中 BSSE 计算的运行类型设置

在 CP2K 输入文件中进行 BSSE 计算时，首先需要将 `RUN_TYPE` 设置为 `BSSE`。此设置指定程序执行基组叠加误差校正的相关计算流程。

---

## 3. CP2K 中鬼原子的定义方法

需要在 `&KIND` 字段中定义涉及复合物 AB 中各元素的实原子和鬼原子。鬼原子在特定位置拥有基函数但不具备原子核和电子密度，定义时需保留 `ELEMENT`、`BASIS_SET`、`POTENTIAL` 等参数，并添加 `GHOST` 关键字。例如定义氧鬼原子块为 `&KIND O_ghost`，内含 `ELEMENT O`、`BASIS_SET TZVP-MOLOPT-GTH`、`POTENTIAL GTH-PBE` 和 `GHOST`，并以 `&END KIND` 结束。

---

## 4. CP2K 中片段的定义与原子列表

在 `&BSSE` 模块中使用 `&FRAGMENT` 关键字划分复合物中的片段，每个片段对应一个分子。使用 `LIST` 关键字指定该片段包含的原子编号，例如 `LIST 1..3` 表示前三个原子属于第一个片段，注意需使用两点 `..` 而非连字符 `-`。

---

## 5. CP2K 中 GLB_CONF 配置参数的含义

`&CONFIGURATION` 中的 `GLB_CONF` 关键字用于指定包含哪些片段，`1 1` 表示片段 1 和 2 同时存在，`1 0` 表示仅片段 1 存在，`0 1` 表示仅片段 2 存在。该参数控制计算体系中哪些片段作为整体参与当前步计算。

---

## 6. CP2K 中 SUB_CONF 实体与鬼原子转换参数

`&CONFIGURATION` 中的 `SUB_CONF` 关键字用于指定片段的形态类型，`1` 代表实原子片段，`0` 代表鬼原子片段。例如 `SUB_CONF 1 0` 表示第一个片段为实原子，第二个片段为鬼原子，常用于计算单体在对方基函数下的能量。

---

## 7. CP2K 中 BSSE 计算的配置组合示例

针对 H2O..HF 体系，需设置多个 `&CONFIGURATION` 块以覆盖不同组合。全实复合物配置为 `GLB_CONF 1 1`、`SUB_CONF 1 1`；H2O 单体实配置为 `GLB_CONF 1 0`、`SUB_CONF 1 0`；HF 单体实配置为 `GLB_CONF 0 1`、`SUB_CONF 0 1`；HF 为鬼原子配置为 `GLB_CONF 1 1`、`SUB_CONF 1 0`；H2O 为鬼原子配置为 `GLB_CONF 1 1`、`SUB_CONF 0 1`。

---

## 8. CP2K 中电荷与多重度设置

在每个 `&CONFIGURATION` 块中，必须使用 `CHARGE` 和 `MULTIPLICITY` 关键字指定当前构型的电荷与多重度。示例中所有构型均设置为 `CHARGE 0` 和 `MULTIPLICITY 1`，表示各步计算均在中性单重态下进行。

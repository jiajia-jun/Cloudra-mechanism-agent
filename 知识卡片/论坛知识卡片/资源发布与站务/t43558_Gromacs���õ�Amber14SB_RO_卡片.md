---
key: t43558
title: Gromacs���õ�Amber14SB_ROC_lipid17������
url: http://bbs.keinsci.com/thread-43558-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2024
cards: 6
---

# Gromacs���õ�Amber14SB_ROC_lipid17������ — 知识卡片

## 1. 蛋白质力场参数

体系中的蛋白质使用 Amber14SB 力场进行参数化，体系中包含 10 个蛋白质分子。

---

## 2. RNA 力场参数

RNA 模拟采用 ROC 力场，该力场是专门针对 RNA 模拟开发的 OL3 力场的一种改进版本。

---

## 3. 脂质力场参数

脂质使用 Lipid17 力场，处理过程中涉及的脂质模型为 3 层结构的脂质。

---

## 4. 初始构象文件

提供了已经构建好的包含 246 个脂质的 GROMACS GRO 格式构象文件，该混合体系是通过 Packmol 软件进行分子堆积构建的。

---

## 5. 原子命名规范

为便于后续修改，模型中不同组分的原子命名规则进行了区分：蛋白质、RNA 和水分子中的原子名称添加 "_n" 后缀，而脂质中的原子名称则添加 "_l" 后缀以示区分。

---

## 6. 力场兼容性说明

目前 Amber 系列力场（包括 D. E. Shaw Research 开发的 DES-Amber）涉及特定原子类型之间的 Lennard-Jones 势能调整，因此本力场文件不适用于对现存体系进行直接覆盖修改。

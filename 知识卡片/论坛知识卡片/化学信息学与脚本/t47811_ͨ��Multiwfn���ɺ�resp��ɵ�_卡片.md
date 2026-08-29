---
key: t47811
title: ͨ��Multiwfn���ɺ�resp��ɵ�chg�ļ���ʹ��һ��Сpyһ����resp����û���mol2��
url: http://bbs.keinsci.com/thread-47811-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2024
cards: 5
---

# ͨ��Multiwfn���ɺ�resp��ɵ�chg�ļ���ʹ��һ��Сpyһ����resp����û���mol2�� — 知识卡片

## 1. 使用 Avogadro 和 CGenFF 生成 GROMACS 拓扑的准备步骤

使用 GROMACS 进行 MD 模拟构建参数时，可将对接软件生成的 PDB 文件用 Avogadro 打开并另存为 mol2 格式。此过程会自动给每个元素加氢，之后将 mol2 文件上传至 CGenFF 官网以生成力场参数。Avogadro 默认使用 Gasteiger 或 Gasteiger-Marsili 电荷，该计算方式精度有限，通常利用 Multiwfn 生成 RESP 电荷来替换 Gasteiger 电荷。

---

## 2. Avogadro 生成的 mol2 文件格式示例

将对接生成的 PDB 文件导入 Avogadro 并加氢后，保存为 mol2input.mol2 格式，此时文件中包含默认的 Gasteiger 电荷。文件头部的 `@<TRIPOS>MOLECULE` 部分包含 `GASTEIGER` 标识，`@<TRIPOS>ATOM` 部分列出了原子坐标及对应的电荷值（如 `-0.5033`）。

---

## 3. Multiwfn 生成的 RESP 电荷文件格式

通过 Multiwfn 计算生成的 `resp.chg` 文件包含了原子坐标及重新计算的高精度电荷。文件格式通常为每一行包含元素符号、X/Y/Z 坐标以及电荷值（如 `-0.5406591096`），电荷值的有效位数比 Gasteiger 电荷更多。

---

## 4. mol2 文件中的电荷替换结果

使用 Python 脚本可以将 Multiwfn 计算出的 RESP 电荷替换进 Avogadro 生成的 mol2 文件中。替换后的 mol2 文件在 `@<TRIPOS>ATOM` 部分保留了原有的原子类型和坐标信息，但最后一列的电荷值已更新为 RESP 计算结果（例如氧原子电荷从 `-0.5033` 变为 `-0.5406591096`）。

---

## 5. 使用 Python 脚本合并电荷与 mol2 文件

执行电荷替换需要准备 `input.chg`（RESP 电荷文件）、`input.mol2`（原始结构文件）和 `chg_mol2.py`（Python 脚本）并将其置于同一目录下。脚本内部需正确设置输入文件的路径，运行后脚本会读取两个输入文件并将合并后的结果输出为 `output.mol2`。

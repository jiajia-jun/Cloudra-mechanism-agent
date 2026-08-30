---
key: t25708
title: Rosetta�еĳ���������ܣ��������£�
url: http://bbs.keinsci.com/thread-25708-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2021
cards: 4
---

# Rosetta�еĳ���������ܣ��������£� — 知识卡片

## 1. Rosetta 处理 PDB 文件中 occupancy 为 0 的原子

PDB 文件中若原子的 occupancy（占据数）为 0，Rosetta 默认会忽略该原子，可使用命令行参数强制处理。
- -ignore_zero_occupancy false

---

## 2. Rosetta 处理 occupancy 为 0 原子的行为

强制读取后，occupancy 为 0 的原子若同时存在 B-factor，Rosetta 将使用该 B-factor 值作为用户影响。

---

## 3. Rosetta 处理 PDB 文件中未识别的残基

若 PDB 文件中存在未定义的残基，旧版本 Rosetta 报错，可通过参数忽略或处理。
- -ignore_unrecognized_res

---

## 4. 新版本 Rosetta 对未识别残基的处理逻辑

新版本 Rosetta 对未识别的原子会自动进行参数化，不报错且会打印 pdb_ 相关信息。为得到精确的构模结果，建议进行 params 修改。

---
key: t22649
title: SBKJC�����Ƽ�������鶨�壨Դ��GAMESS������ϵUFF�뾶
url: http://bbs.keinsci.com/thread-22649-1-1.html
domain: 量子化学方法
source: keinsci
year: 2021
cards: 5
---

# SBKJC�����Ƽ�������鶨�壨Դ��GAMESS������ϵUFF�뾶 — 知识卡片

## 1. GAMESS 模拟 La、Ce 等锕系元素的 SBKJC 基组缺陷

在 GAMESS 中使用 SBKJC 基组对双原子 La、Ce 体系进行模拟时会出现严重问题，表现为边界角错误或无法收敛报错。GAMESS 目前不具备针对此类锕系元素 SBKJC 基组的综合计算支持能力。

---

## 2. Mokit 实现锕系元素高斯 SCF 计算

Mokit 能够实现对 La-Lu 共 15 种元素在高斯基组下的 SCF 计算。Mokit 将计算结果导出并提交给 GAMESS 进行后续处理，从而绕过了 GAMESS 直接使用该基组时的报错问题。

---

## 3. La-Lu 元素 SBKJC 基组定义来源

La-Lu 系列元素的 SBKJC 基组推荐定义可从 Mokit 软件包中直接获取。这些基组的高斯基函数格式已经按照 Mokit 的标准进行了适配和转换。

---

## 4. SBKJC 基组数据提取方式

用户可以直接从 Mokit 的 txt 文资料件中复制对应镧系元素的基组及其高斯函数式。该文资料件包含了经过转换的高斯基组数据，可供提取使用。

---

## 5. 基组格式转换与兼容性检查

从 Mokit 获取的基组格式可能需要适配目标程序的输入要求。用户在使用时需注意检查格式是否兼容，以免因格式遗漏或错误导致计算失败。

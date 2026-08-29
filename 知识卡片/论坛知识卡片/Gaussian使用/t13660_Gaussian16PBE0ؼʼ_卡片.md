---
key: t13660
title: Gaussian16����PBE0�ؼ��ʼ����ʵ������PBE0-DH˫�ӻ�����
url: http://bbs.keinsci.com/thread-13660-1-1.html
domain: Gaussian使用
source: keinsci
year: 2019
cards: 6
---

# Gaussian16����PBE0�ؼ��ʼ����ʵ������PBE0-DH˫�ӻ����� — 知识卡片

## 1. Gaussian中PBE0功能键名的正确写法

在Gaussian软件中，PBE0泛函应当写为PBE1PBE。在Gaussian 09版本中，直接写入PBE0会被程序视为未知关键词而报错。

---

## 2. Gaussian关键词的简化规则

Gaussian允许对关键词进行简化，只要包含主体词即可，特定程度下的缩写能被识别。例如empiricaldispersion=GD3BJ可以简写为em=GD3BJ。

---

## 3. G16及以后版本对PBE0关键词的识别变化

从Gaussian 16开始，程序支持对PBE0这一关键词的识别。若在G16中写入PBE0，程序不会报错，但实际执行的是双杂化泛函PBE0-DH计算。

---

## 4. PBE0与PBE0-DH计算结果的差异与SCF能量提取

PBE0-DH双杂化泛函会引入MP2相关能修正，其计算结果与普通PBE0不同。若已按PBE0-DH完成了计算，输出文件末尾MP2=后的数值即为该双杂化泛函的能量；若需普通PBE0数据，应提取SCF Done部分的能量。

---

## 5. G16中使用PBE0关键词的注意事项

由于G16会将PBE0关键词识别为PBE0-DH双杂化泛函，若需要标准PBE0泛函的计算结果，必须写入全称PBE1PBE。若原本意图是PBE0-DH计算，则无需修改。

---

## 6. Gaussian不同版本B.01中PBE相关键名的对应关系

在Gaussian B.01及之前版本中，PBE相关功能键名的对应关系如下：PBE对应泛函PBE；PBEPBE对应泛函PBE；PBE1PBE对应泛函PBE0；PBE0对应泛函PBE0-DH。

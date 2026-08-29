---
key: t51400
title: Multiwfn��֧�����µķ�����ָ��HOMAc��HOMER�ļ���
url: http://bbs.keinsci.com/thread-51400-1-1.html
domain: 波函数与电子结构分析
source: keinsci
year: 2025
cards: 6
---

# Multiwfn��֧�����µķ�����ָ��HOMAc��HOMER�ļ��� — 知识卡片

## 1. Multiwfn 新版本支持的分析指标

Multiwfn 新版本开始支持基于哈密顿量的 HOMAc 和 HOMER 指标计算。这两个指标的定义分别发表于 Phys. Chem. Chem. Phys., 25, 16763 (2023) 和 J. Org. Chem., 90, 1297 (2025)。它们是对传统 HOMA 指标参考键长 $R_{ref}$ 依赖性缺点的改进。

---

## 2. HOMAc 指标的特性与适用性

HOMAc 指标适用于动态芳香性比较。与 HOMA 相比，HOMAc 与 $\text{NICS}(1)_{zz}$ 具有更好的相关性。

---

## 3. HOMER 指标的特性与适用性

HOMER 指标适用于激发 T1 态的芳香性研究。对于基态与激发态同时分布的体系，基于 HOMA 的分析会完全失效，而 HOMER 不受此影响。

---

## 4. NICS(1)zz 指标的局限性

$\text{NICS}(1)_{zz}$ 指标在应用于某些体系时，其数值倾向于 0。这限制了其在特定场景下对芳香性的判断准确性。

---

## 5. 芳香性指数在 Multiwfn 中的计算方式

Multiwfn 支持的分析指数涵盖了多种方法，其中包括 HOMAc 和 HOMER。相关的计算细节和具体方法可在《Multiwfn 中的计算》文档中查阅，网址为 http://原作者.com/176。

---

## 6. Multiwfn 版本发布信息

支持上述新指标的 Multiwfn 版本发布于 2025 年 2 月 4 日。该版本被标记为 3.2(8) 版本。

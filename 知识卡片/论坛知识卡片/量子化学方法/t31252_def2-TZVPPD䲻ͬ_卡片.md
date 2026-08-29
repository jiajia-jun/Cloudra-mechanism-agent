---
key: t31252
title: ����def2-TZVPPD������䲻ͬ�ĸ�������ļ򵥲���
url: http://bbs.keinsci.com/thread-31252-1-1.html
domain: 量子化学方法
source: keinsci
year: 2022
cards: 9
---

# ����def2-TZVPPD������䲻ͬ�ĸ�������ļ򵥲��� — 知识卡片

## 1. ORCA def2-TZVPPD 基组的辅助基组设置

ORCA 在使用 def2-TZVPPD 基组时需手动指定辅助基组以利用 RI-J 加速。两种设置方案分别为手动指定 def2/J 和 def2-TZVPPD/C，或使用 autoaux 自动生成辅助基组。autoaux 方式仅计算单点能且假设几何结构一致，适用于几何结构已固定的后续化学应用计算。

---

## 2. PWPB95 D3 计算输入命令方案一

使用 def2/J 和 def2-TZVPPD/C 辅助基组的 PWPB95 D3 计算命令如下：
PWPB95 D3 def2-TZVPPD def2/J def2-TZVPPD/C RIJCOSX tightSCF noautostart miniprint nopop SCFConvForced NOTRAH

---

## 3. PWPB95 D3 计算输入命令方案二

使用 autoaux 自动辅助基组的 PWPB95 D3 计算命令如下：
PWPB95 D3 def2-TZVPPD autoaux RIJCOSX tightSCF noautostart miniprint nopop SCFConvForced NOTRAH

---

## 4. Alder-ene 反应计算对比案例

该计算案例针对 Alder-ene 反应体系进行了不同辅助基组设置的测试。对比结果展示了使用手动指定辅助基组与 autoaux 自动生成的输出文件差异。

---

## 5. 脱水缩合反应计算对比案例

该计算案例针对脱水缩合反应体系进行了不同辅助基组设置的测试。对比结果展示了使用手动指定辅助基组与 autoaux 自动生成的输出文件差异。

---

## 6. 辅助基组设置的能量误差结论

对于所测试的有机反应体系，def2-TZVPPD 基组搭配手动指定的 def2/J 和 def2-TZVPPD/C 辅助基组，与搭配 autoaux 自动生成的辅助基组相比，二者能量数据差异小于 0.03 kcal/mol。在该误差范围内，使用 autoaux 方案可以被视为可接受的近似。

---

## 7. def2-TZVPPD 辅助基组选择建议

def2-TZVPPD 基组搭配手动指定的 def2/J 和 def2-TZVPPD/C 辅助基组也是可行的方案之一。

---

## 8. autoaux 自动辅助基组的内存占用

使用 autoaux 自动生成辅助基组似乎比手动指定 def2/J 和 def2-TZVPPD/C 辅助基组占用更多的内存（或磁盘交换空间）。这可能是导致前者计算耗时较长的原因。

---

## 9. 计算日志文件示例

提供的对比数据基于两个 ORCA 输出日志文件，分别记录了使用 def2/J 手动指定辅助基组与使用 autoaux 自动辅助基组的计算过程。

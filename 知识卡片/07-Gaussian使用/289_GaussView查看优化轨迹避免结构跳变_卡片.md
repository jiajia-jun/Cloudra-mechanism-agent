---
id: 289
title: GaussView观看Gaussian优化轨迹时避免结构跳变的方法
url: http://sobereva.com/289
domain: Gaussian使用
topic: GaussView查看优化轨迹避免结构跳变
cards: 7
---

# GaussView查看优化轨迹避免结构跳变 — 知识卡片

## 1. GaussView查看优化轨迹

在GaussView中打开Gaussian优化输出文件时勾选Read Intermediate Geometries复选框，即可查看几何优化轨迹，这对于了解优化过程中结构的变化非常重要。

---

## 2. 结构跳变的原因

Gaussian默认将每一步结构旋转平移成标准朝向（Standard orientation），导致结构细微变化可能在经过标准朝向处理后与上一步产生巨大的朝向差异，从而在GaussView播放轨迹时出现结构跳变；使用nosymm关键词虽可利用Input orientation坐标避免跳变，但会损失利用对称性加速计算的好处。

---

## 3. G16版本限制

Gaussian 16已经解决了因标准朝向导致的180度翻转问题，但截至G16 A.03版本，仍未能解决由此类原因导致的如90度翻转等跳变问题。

---

## 4. 两种坐标输出形式

Gaussian优化过程的每一步不仅输出Standard orientation坐标，还输出Input orientation坐标，其中Input orientation是相对于初始输入文件里朝向的坐标。

---

## 5. 解决跳变的基本原理

GaussView默认读取Standard orientation坐标从而导致跳变，只要将其修改为读取Input orientation坐标，即可避免优化轨迹出现跳变。

---

## 6. 修改输出文件的具体操作

修改Gaussian输出文件，将所有"Standard orientation:"替换成任意字符使GaussView无法识别，然后将所有"Input orientation:"替换成"Standard orientation:"，即可欺骗GaussView读取正确的坐标以实现连续轨迹播放。

---

## 7. 输出Input orientation的限定条件

当原子数超过50时，Gaussian默认不输出Input orientation，必须在输入文件中使用geom=printinputorient关键词来强行要求输出。

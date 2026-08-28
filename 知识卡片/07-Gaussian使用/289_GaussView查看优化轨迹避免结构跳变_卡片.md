---
id: 289
title: GaussView观看Gaussian优化轨迹时避免结构跳变的方法
url: http://sobereva.com/289
domain: Gaussian使用
topic: GaussView查看优化轨迹避免结构跳变
cards: 1
---

# GaussView查看优化轨迹避免结构跳变 — 知识卡片

## 1. GaussView播放优化轨迹的结构跳变原因

GaussView播放Gaussian优化轨迹时会出现结构突然跳变或翻转，是因为GaussView读取的是输出文件中的"Standard orientation"坐标；Gaussian默认将每一步的结构旋转平移成标准朝向以利用对称性，导致微小的结构变化在转换成标准朝向后可能产生巨大的视觉差异。
- 即使使用nosymm关闭对称性可以避免跳变，但会失去对称性加速计算的优势，不是理想方法。

## 通过修改输出文件解决轨迹跳变的方法
解决GaussView轨迹跳变的方法是修改输出文件，将文本中的"Standard orientation:"替换为任意字符使其无法被识别，并将"Input orientation:"替换为"Standard orientation:"；这样做是让GaussView误将原本相对于初始输入朝向的"Input orientation"坐标当作"Standard orientation"读取，从而实现轨迹的连续播放。
- 2017-Jul-1补充：G16解决了示例中的180度翻转问题，但A.03版本仍存在因相同原因导致的如90度突变。

## 强制输出Input orientation坐标的条件
当体系原子数超过50时，Gaussian默认不输出Input orientation坐标，必须在计算输入文件中加入`geom=printinputorient`关键词来强行要求输出，以便进行上述修改操作。

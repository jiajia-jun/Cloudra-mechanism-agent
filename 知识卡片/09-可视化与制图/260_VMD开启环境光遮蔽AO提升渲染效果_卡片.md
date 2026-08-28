---
id: 260
title: 在VMD里使用环境光遮蔽改进渲染效果
url: http://sobereva.com/260
domain: 可视化与制图
topic: VMD开启环境光遮蔽AO提升渲染效果
cards: 3
---

# VMD开启环境光遮蔽AO提升渲染效果 — 知识卡片

## 1. 环境光遮蔽在VMD Tachyon渲染器中的效果

在较新版本的VMD中，使用环境光遮蔽可以改进内建Tachyon渲染器的渲染效果，使体系在光线照射下的阴暗区域柔和、自然地表现出来，效果不逊色于povray渲染甚至更舒适。开启环境光遮蔽会令Tachyon渲染耗时增加很多。

---

## 2. VMD中开启环境光遮蔽的设置步骤

开启环境光遮蔽需在display setting里把Shadows和Amb. Occl.打开，将Drawing method设为物体占体积较大的显示方式（如VDW方式），材质设定为AO开头的类型（如AOEdgy），然后通过file-render选择内建的Tachyon渲染。

---

## 3. 渲染材质与显示方式的细节调整

在display setting里可以对Shadows和Amb. Occl.的程度进行调节，在graphics-material里可以进一步对材质特征进行调节。

---
id: 260
title: 在VMD里使用环境光遮蔽改进渲染效果
url: http://sobereva.com/260
domain: 可视化与制图
topic: VMD开启环境光遮蔽AO提升渲染效果
cards: 5
---

# VMD开启环境光遮蔽AO提升渲染效果 — 知识卡片

## 1. 环境光遮蔽对VMD渲染效果的改进

在较新版本的VMD中，可以使用ambient occlusion（AO,环境光遮蔽）来改进自带的Tachyon渲染器的渲染效果。这可以使体系在光线照射下呈现的阴暗区域柔和、自然地表现出来，丝毫不逊色于用povray渲染，甚至看着更舒服一些。

---

## 2. 开启环境光遮蔽的操作步骤

开启AO的做法很简单，在display setting里面把Shadows和Amb. Occl.打开，把Drawing method设为那种物体占的体积比较大的显示方式，比如VDW方式，材质设定为AO开头的比如AOEdgy。然后file-render，选择用内建的Tachyon渲染就行了。

---

## 3. 开启环境光遮蔽的耗时影响

开了Shadows和Amb. Occl.这两项之后会令Tachyon渲染耗时增加很多。

---

## 4. 病毒颗粒渲染实例显示设置

病毒颗粒渲染实例使用了quicksurf方式来快速显示体系的表面，用radial方式着色（越靠外越红）。选择方式输入all not (z>20 and x>20 and y>20)来给体系开了个小口。

---

## 5. 环境光遮蔽渲染效果的调节

在display setting里可以对Shadows和Amb. Occl.的程度进行调节，在graphics-material里可以再对材质特征进行调节。

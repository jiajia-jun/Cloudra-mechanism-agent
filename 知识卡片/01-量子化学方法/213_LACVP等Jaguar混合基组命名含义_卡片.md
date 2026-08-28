---
id: 213
title: LACVP这类方式命名的基组的含义
url: http://sobereva.com/213
domain: 量子化学方法
topic: LACVP等Jaguar混合基组命名含义
cards: 7
---

# LACVP等Jaguar混合基组命名含义 — 知识卡片

## 1. LACVP命名来源与基本含义

这类基组的命名源自Jaguar程序，详见Jaguar手册。它们属于混合基组，对轻原子使用全电子基组，对重原子使用Hay和Wadt开发的Los Alamos赝势基组，故开头两个字母是LA。这类赝势对于超过Kr的元素考虑了质量-速度和Darwin相对论校正。

---

## 2. LAV系列基组定义与收缩方式

LAV系列代表只考虑价层（V=valence），即lanl1系列：对于主族元素只考虑最高的s和p壳层，对过渡金属只考虑最高的s,p,d壳层。LAV1表示赝势基组完全收缩成为极小基（lanl1MB）；LAV2代表赝势基组最后一个层高斯函数去收缩成为双zeta基（lanl1DZ）；LAV3代表赝势基组所有s函数去收缩，且最后一层p和d高斯函数去收缩，算是准三zeta。

---

## 3. LAV1/2/3x后缀字母含义

LAV1/2/3x对于Na-Bi都是用相应赝势基组，x的字母代表对H-Ne这些轻元素用什么全电子基组。S=STO-3G，D=D95V，P=6-31G。有五种组合，即LAV1S、LAV2D、LAV2P、LAV3D、LAV3P。

---

## 4. LACV系列基组定义

LACV代表价层和亚价层都考虑进去（C代表最外层core轨道），即lanl2系列。LACV是双zeta，即lanl2dz；LACV3是Schrodinger公司的人自己搞的，对LACV做了去收缩，是准三zeta。

---

## 5. LACV系列基组对不同元素的具体处理

LACV系列基组除了自己定义了赝势的原子外，对于其它原子的处理各不相同：LACVD对于H-Ne用D95V，对于Na-Ar,Zn-Kr, Cd-Xe, Hg-Bi用的是LAV3D赝势基组；LACVP对于H-Ar用6-31G，对于Zn-Kr, Cd-Xe, Hg-Bi用的是LAV3P赝势基组。LACV3P对于H-Ar用6-311G，对于Zn-Kr, Cd-Xe, Hg-Bi用的是LAV3P赝势基组。

---

## 6. 衍生基组命名与注意事项

如果自行加上弥散或者极化，会衍生出不同的名字。这样的名字往往搞得很乱，不同文献中意义可能不一，应注意看文章的说明。例如有的文章中LACVP++**就是LACVP当中6-31G改为6-31++G**。LACVP+(2f)是LACV3P对赝势描述的原子加上两个f和一个弥散得到的。

---

## 7. LACVP命名规范的非主流性

LACVP这类方式命名是极度非主流的，绝对不要效仿某些文章来使用这种基组命名。基组选用的合理性详见：谈谈量子化学中基组的选择 (http://sobereva.com/336) 和 谈谈赝势基组的选用 (http://sobereva.com/373)。

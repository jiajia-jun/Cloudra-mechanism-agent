---
id: 571
title: 谈谈Gaussian产生downhill路径的功能
url: http://sobereva.com/571
domain: Gaussian使用
topic: Gaussian_downhill路径功能与实例
cards: 7
---

# Gaussian_downhill路径功能与实例 — 知识卡片

## 1. Gaussian的IRC=downhill功能定义

Gaussian程序的IRC关键词中的downhill选项可以以任意位置作为起点，通过IRC算法得到一条downhill轨迹。这条轨迹相当于在质权势能面上体系不断沿着受力方向行进而走出的理想轨迹，也可以认为是原子运动速度无穷慢的情况下原子走的真实运动轨迹。利用这个功能，可以考察体系从非平衡状态向极小点结构弛豫的真实过程。详见《在Gaussian中计算IRC的方法和常见问题》（http://sobereva.com/400）。

---

## 2. 吡咯T1态结构弛豫计算设置

研究吡咯在T1态势能面从基态极小点结构向T1态极小点结构弛豫的过程时，可使用关键词# b3lyp/6-31g(d) IRC(calcall,downhill,maxpoints=100)，初始结构采用B3LYP/6-31G*优化的基态极小点结构。设置maxpoints=100是为了让downhill轨迹尽可能跑得长一些，从而能走到尽可能接近极小点的位置。

---

## 3. 避免IRC校正步不收敛的参数设置

由于Gaussian默认的IRC算法HPC很不稳定，特别容易出现校正步不收敛的报错，因此可以使用calcall选项来很大程度上避免此问题，同时增加生成路径的精度。虽然calcall会造成耗时增加，但若不使用calcall，改用LQA算法虽然可以避免报错，却会导致downhill任务卡住（至少对于G09 D.01和G16 A.03经测试都有这个问题）。

---

## 4. downhill路径与几何优化路径的区别

downhill路径和几何优化路径并不相同，没有可替代关系。一方面，几何优化过程的步长是动态的，不像IRC或downhill轨迹那样是固定的；另一方面，几何优化只为寻找精确的极小点结构，不要求过程沿着质权势能面上体系受力方向行走，能量变化也不像downhill任务那样总是平滑下降的。downhill任务至多只能走到一个很接近于与初始结构最近的极小点结构的位置，必须进一步做几何优化才能精确定位。

---

## 5. 18碳环电场下downhill路径的输入设置

计算18碳环在电场下的downhill路径时，使用关键词#p wb97xd/6-311+G(2d) nosymm field=x+275 IRC(calcfc,ReCorrect=never,downhill,maxpoints=100)。其中field=x+275给体系沿X方向加了0.0275 a.u.的外电场，nosymm用于避免Gaussian自动调整体系朝向，ReCorrect=never用于去掉校正步以避免报错和节约时间。弥散函数的加入是为了确保电子被极化显著时的描述精度。

---

## 6. 使用ReCorrect=never的利弊

为了避开HPC算法校正步不收敛的报错，在不使用calcall和LQA（会导致任务卡住）的情况下，可以使用ReCorrect=never选项。这直接去掉了校正步，不仅完全避免了报错，还能节约一些时间，但代价就是得到的downhill路径在有的地方不那么平滑。对于18碳环在电场下的计算任务，实际发现这种不良影响不明显。

---

## 7. 18碳环电场下结构变形的数据提取方法

通过GaussView观看并导出downhill轨迹数据：在IRC观看界面左上角点Plots，选Plot Molecular Property，然后选Bond，输入最远的两个碳的序号，即可出现距离变化图。在相应图上点右键后选保存数据，即可将数据导出并使用Origin等软件绘制轴距曲线。图中蓝色箭头表示外加电场的方向，绿色曲线表示最长轴距离。

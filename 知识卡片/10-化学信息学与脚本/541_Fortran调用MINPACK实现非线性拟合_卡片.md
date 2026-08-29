---
id: 541
title: 基于Fortran使用Levenberg-Marquardt算法做非线性拟合
domain: 化学信息学与脚本
topic: Fortran调用MINPACK实现非线性拟合
cards: 9
---

## 1. 非线性拟合与Levenberg-Marquardt算法
非线性拟合通过调整系数最小化误差函数来实现，误差函数定义为所有拟合点上实际与拟合数据差值的平方和。Levenberg-Marquardt算法是使用最多、效率最高且效果最好的方法之一，它是一个迭代算法，结果依赖于初猜参数，并且需要导数信息。具体的算法细节可以参考Wikipedia页面。

---

## 2. MINPACK库介绍
MINPACK是一个Fortran 90语言的库，专门用于最小二乘极小化，其中包含实现Levenberg-Marquardt算法的子程序，并且还能使用Powell方法求解非线性方程组。使用现成的库如MINPACK可以避免自己编写Levenberg-Marquardt算法代码。

---

## 3. Morse势拟合乙烷碳碳键断裂案例背景
本例使用Morse势对乙烷碳碳键断裂的柔性扫描曲线进行拟合，扫描数据可以从Gaussian计算后用GaussView导出为.txt文件。Morse势表达式中额外引入了S参数用于上下移动曲线，因为扫描数据中可能没有点恰好落在势能曲线真正的精确谷底位置，拟合应允许曲线整体移动。

---

## 4. lmdif1子程序参数详解
代码核心调用语句为`call lmdif1(calcfiterr,ndata,nparm,parm(:),fiterr(1:ndata),tol,maxcall,info)`。参数含义分别为：lmdif1是MINPACK库的Levenberg-Marquardt算法子程序；calcfiterr是自写的计算误差子程序；ndata是数据点数目；nparm是拟合参数数目；parm是待拟合参数数组；fiterr是误差数组；tol是收敛限；maxcall是最大调用次数；info是运行状态信息。Jacobian矩阵由MINPACK库自动通过有限差分计算。

---

## 5. 拟合误差计算子程序规范
被lmdif1调用的calcfiterr子程序必须包含5个固定参数且数据类型需与例子一致：ndata（数据点数）、nparm（参数数）、parm（参数数组）、fiterr（误差数组）、iflag。该子程序调用calcfitval计算拟合值，并计算与真实值的差值，拟合点信息通过fitting_module传递。

---

## 6. 数据读取与预处理流程
程序从当前目录下的ethane_dissoc.txt文件读取数据到x和value数组，文件中能量单位为a.u.。代码将能量值转换为kJ/mol（乘以2625.5D0），并调整数值使得最低点的值为0，以避免数量级过大。

---

## 7. 拟合参数设置与初猜
代码中设置收敛限tol=1D-7，最大调用次数maxcall=5000，并对四个Morse势参数设置初猜值：D=300，k=2000，r0=1.5D0，S=0。S参数仅用于拟合时的垂直移动，实际使用Morse势时只考虑D、k、r0。

---

## 8. 拟合结果评价指标
拟合完成后输出D、k、r0、S参数值，并计算RMSE（均方根误差）和Pearson相关系数r及r^2。RMSE数值越小拟合精度越好，计算公式为`dsqrt(sum(fiterr(1:ndata)**2)/ndata)`。r和r^2通过stddevarray（计算标准偏差）和covarray（计算协方差）函数求得，用于评估拟合质量。

---

## 9. 实际拟合结果与验证
程序运行输出的拟合结果为D=409.2492，k=2830.1767，r0=1.5093，S=-2.6847，RMSE=9.7965，Pearson相关系数r=0.998443，r^2=0.996888。这些结果与Origin拟合出的结果非常接近，且r^2接近1，表明拟合相当成功。

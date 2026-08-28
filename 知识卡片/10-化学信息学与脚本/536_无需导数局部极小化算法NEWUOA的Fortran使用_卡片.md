---
id: 536
title: 无需导数的局部极小化算法NEWUOA在Fortran中的使用简例
url: http://sobereva.com/536
domain: 化学信息学与脚本
topic: 无需导数局部极小化算法NEWUOA的Fortran使用
cards: 9
---

# 无需导数局部极小化算法NEWUOA的Fortran使用 — 知识卡片

## 1. NEWUOA算法简介与特点

NEWUOA是Powell于2004年提出的一种不需要导数信息的非约束性局部极小化算法。该算法不需要函数具有解析导数，适用于函数为黑箱或解析导数难以编写的情况。根据《Experimental Comparisons of Derivative Free Optimization Algorithms》一文对比，相对于通过有限差分得到梯度的BFGS方法，多数情况下NEWUOA效率更高，即收敛到极小点所需计算函数值的次数更少。Fortran实现代码可在提供的链接下载。

---

## 2. 二元函数极小化代码示例

对二元函数 $F=(x_1-2)^2+(x_2-3.5)^2+x_1 x_2$ 进行极小化的Fortran代码需调用newuoa_min子程序。代码中需定义数组X存储变量，初猜设为0，并编写子程序CALFUN计算函数值。编译时需将源文件与newuoa_module.f90放在一起。
```fortran
PROGRAM test_newuoa
  use newuoa_module
  implicit real*8 (a-h,o-z)
  real*8,allocatable :: X(:)
  external CALFUN
  nvar=2
  allocate(X(nvar))
  X(:)=0
  call newuoa_min(CALFUN, X, RHOBEG=0.1D0, RHOEND=1D-6, IPRINT=2, MAXFUN=50000)
END PROGRAM

subroutine CALFUN(X,F)
  real*8 :: X(:),F
  F=(X(1)-2)**2+(X(2)-3.5D0)**2+X(1)*X(2)
end subroutine
```

---

## 3. newuoa_min子程序参数设置规则

newuoa_min子程序包含关键控制参数：RHOBEG和RHOEND分别定义置信半径的初值和终值，且RHOEND<=RHOBEG。Powell建议将RHOBEG设为估计的参数最大变化量的十分之一。RHOEND控制最终X的收敛精度，要求精度越高应设得越小，一般用1E-6。MAXFUN设定最多调用CALFUN的次数，若达到此值未结束则判定失败。

---

## 4. IPRINT参数的输出控制选项

IPRINT参数决定newuoa_min运行过程中的屏幕输出信息量。0代表什么都不输出；1代表只输出最终结果；2代表每当更新RHO时输出当前最佳X及函数值；3代表每次调用CALFUN时都输出当前X及对应函数值。

---

## 5. 二元函数极小化运行结果示例

初猜为(0,0)时，NEWUOA算法经过37次函数调用达到收敛。最终结果为X(1)=0.333333、X(2)=3.333333，函数值F=3.916666666666666。该结果与解析解x1=1/3、x2=10/3精确一致。为了节约耗时可以将RHOEND设大，但这会降低优化参数的精度。

---

## 6. 多极小点函数的优化策略

当被极小化的函数有不止一个极小点时，仅靠一个初猜无法找到全局最低点。需要考虑不止一个初猜来寻找全部极小点或全局最低点。可以将NEWUOA与Differential Evolution (DE)等全局最小化算法结合使用，如J Cheminform, 8, 57 (2016)中结合DE和NEWUOA优化EEM电荷参数。

---

## 7. 单变量方程求解代码示例

对方程 $x+2\cos(x)-0.5=0$ 求解可转化为对 $|x+2\cos(x)-0.5|$ 进行极小化。Fortran代码中nvar设为1，初猜X(1)设为0，CALFUN计算绝对值表达式。
```fortran
PROGRAM test_newuoa
  use newuoa_module
  implicit real*8 (a-h,o-z)
  real*8,allocatable :: X(:)
  external :: CALFUN
  nvar=1
  allocate(X(nvar))
  X(1)=0
  call newuoa_min(CALFUN, X, RHOBEG=0.1D0, RHOEND=1D-6, IPRINT=1, MAXFUN=50000)
END PROGRAM

subroutine CALFUN(X,F)
  real*8 :: X(:),F
  F=abs(X(1)+2*cos(X(1))-0.5D0)
end subroutine
```

---

## 8. 单变量求解运行结果

对方程求解运行结果显示，经过24次函数调用达到收敛。最终结果为x=-0.83796，此时函数值F=2.144288913097370D-08。这表明x+2cos(x)与0.5之间仅相差2.1442889E-8，求解精度很高。

---

## 9. NEWUOA算法适用场景与局限

NEWUOA算法不仅适用于参数较少的情况，也可用于含有几百个参数的情况，但参数越多，收敛所需计算函数值的次数会明显越多。如果被优化的函数已经有解析梯度计算代码，NEWUOA价值不大，因为此时用BFGS达到收敛所需代价一般更少。Powell还开发过用于带约束条件的无需导数的局部极小化子程序。

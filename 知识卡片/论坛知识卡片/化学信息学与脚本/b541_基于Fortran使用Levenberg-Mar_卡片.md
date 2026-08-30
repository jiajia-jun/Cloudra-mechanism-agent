---
key: b541
title: 基于Fortran使用Levenberg-Marquardt算法做非线性拟合
url: http://sobereva.com/541
domain: 化学信息学与脚本
source: blog
year: 2020
cards: 13
---

# 基于Fortran使用Levenberg-Marquardt算法做非线性拟合 — 知识卡片

## 1. 非线性拟合在计算化学中的应用

非线性拟合在计算化学研究中应用广泛，例如在拟合力场参数时需要使用。Fortran语言在科学计算领域应用普遍，适合用于实现此类非线性拟合计算。

---

## 2. Levenberg-Marquardt算法特点

Levenberg-Marquardt算法通过迭代求解来最小化误差函数，是目前非线性拟合中效率最高、效果最好的常用方法之一。该算法的结果依赖于初猜参数，并且计算过程中需要导数信息。

---

## 3. MINPACK库与算法实现

MINPACK是一个基于Fortran 90语言的库，专门用于最小二乘极小化，其中包含实现Levenberg-Marquardt算法的子程序以及用于求解非线性方程组的Powell方法。使用者可以直接利用该库进行非线性拟合，无需自行编写核心算法代码。

---

## 4. 乙烷碳碳键断裂扫描数据拟合示例

本示例使用Morse势函数对乙烷碳碳键断裂的柔性扫描曲线进行拟合。扫描数据可由Gaussian计算后通过GaussView导出为.txt格式文件，拟合过程中需要读取该文件中的数据点。

---

## 5. Morse势拟合参数

Morse势的拟合参数包括D、k、r0以及用于整体上下移动势能曲线的参数S。增加S参数是因为扫描数据的最低点可能不在精确的势能谷底位置，允许曲线整体移动可以提高拟合精度。

---

## 6. Fortran程序读取与处理数据

程序启动后读取当前目录下的ethane_dissoc.txt文件，提取数据点位置x和数值value。程序会将电子能量单位从a.u.转换为kJ/mol，并调整数值使得最低点的值为0，以避免数量级过大。

---

## 7. lmdif1子程序调用参数

核心调用语句为`call lmdif1(calcfiterr,ndata,nparm,parm(:),fiterr(1:ndata),tol,maxcall,info)`。其中lmdif1是MINPACK库的子程序，tol为收敛限，maxcall为最大调用次数，info用于返回运行状态信息。

---

## 8. 误差计算子程序calcfiterr

calcfiterr子程序由lmdif1调用，必须包含5个固定参数且数据类型需与示例一致。该子程序负责计算各个拟合点基于当前参数的真实值与拟合值之间的误差，供算法优化使用。

---

## 9. 拟合点数据的模块传递

由于calcfiterr子程序的固定接口不包含拟合点信息，拟合点数据通过fitting_module模块传递。该模块定义了存储x和value的数组，实现了数据在不同子程序间的共享。

---

## 10. 自动差分计算Jacobian矩阵

本示例中MINPACK库自动通过有限差分法计算Jacobian矩阵所需的导数信息。这省去了编写解析导数代码的步骤，但意味着calcfiterr的调用次数不直接等于算法的迭代次数。

---

## 11. 拟合结果评估指标

程序输出拟合得到的D、k、r0、S参数值，并计算RMSE（均方根误差）以评估拟合精度。程序还会计算真实值与拟合值的Pearson相关系数r及其平方r^2，数值越接近1表示拟合效果越好。

---

## 12. 拟合输出示例

运行程序后会输出加载的数据点数量、收敛状态、拟合参数值以及RMSE和相关系数。随后列出每个数据点的键长、输入值、拟合值及误差，示例中r^2达到0.996888，表明拟合成功。

---

## 13. Multiwfn中的拟合应用

Multiwfn程序的主功能300子功能2使用非线性拟合方法将球对称化的原子径向密度拟合成多个Slater type orbital (STO)或Gaussian type function (GTF)的线性组合。相关代码实现细节可参考Multiwfn源代码中的fitatmdens子程序。

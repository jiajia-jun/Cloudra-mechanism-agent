---
key: t30942
title: һ����DLPNO-CCSD(T)�Ż�18̼���Ľṹ��˼·
url: http://bbs.keinsci.com/thread-30942-1-1.html
domain: 反应机理与过渡态
source: keinsci
year: 2022
cards: 14
---

# һ����DLPNO-CCSD(T)�Ż�18̼���Ľṹ��˼· — 知识卡片

## 1. DLPNO-CCSD(T)几何优化限制

DLPNO-CCSD(T)方法不具备解析梯度功能，因此无法直接用于几何优化操作，需采用替代方案。

---

## 2. ORCA对称性处理限制

ORCA软件内部不支持基于对称性的几何优化，针对具有对称性的体系（如D9h结构）需自行编写程序进行优化。

---

## 3. 18碳环结构优化方法

对于18碳环体系，推荐使用PWPB95-D4/def2-TZVP方法进行几何优化，并可配合NEWUOA优化算法使用。

---

## 4. 18碳环HF计算稳定性

18碳环体系在进行HF计算时RHF方法存在不收敛问题，建议改用DFT方法以获得稳定结果。

---

## 5. ORCA支持的DFT方法

ORCA支持M062X等DFT计算方法，这些方法可用于结构优化或作为后续高级计算的参考态。

---

## 6. NEWUOA优化算法调用参数

在Fortran程序中调用NEWUOA优化算法时，可设置RHOBEG为0.1D-1，RHOEND为1D-4，最大函数评估次数MAXFUN为50000。

---

## 7. NEWUOA优化初始坐标设定

在优化18碳环结构时，可将键长变量X(1)初始化为1.3436D0，X(2)初始化为1.2242D0作为优化起点。

---

## 8. ORCA输入文件计算层级设置

在自动生成的ORCA输入文件中，计算方法行应设置为"! PWPB95 D4 def2-TZVP RIJK def2/JK def2-TZVP/C TightSCF"。

---

## 9. 18碳环优化构型坐标构建

18碳环的Z型结构坐标可通过内坐标方式定义，键角设为160.00000000度，二面角设为0.00000000度。

---

## 10. Fortran调用ORCA的Windows路径格式

在Windows环境下通过Fortran调用ORCA时，路径格式需为`E:\Baidunetdiskdownload\orca503\orca 4.inp > 4.out`。

---

## 11. ORCA能量提取命令

从ORCA输出文件中提取最终单点能的命令为`grep 'FINAL SINGLE' 4.out | awk '{print $5}' > 4.txt`。

---

## 12. NEWUOA优化输出数据格式

优化过程中的能量和坐标数据输出格式为`print "(3D20.12)",ene,X(1),X(2)`。

---

## 13. NEWUOA优化收敛过程记录

NEWUOA算法会记录当前的RHO值、函数评估次数、当前最小值F以及对应的X数组，例如当RHO为1.0000D-04时，评估次数为22。

---

## 14. 18碳环优化最终结果

经过NEWUOA算法优化后，18碳环的最小能量值为-6.850962343688360D+02，对应的键长参数X(1)为1.278239D+00，X(2)为1.278164D+00。

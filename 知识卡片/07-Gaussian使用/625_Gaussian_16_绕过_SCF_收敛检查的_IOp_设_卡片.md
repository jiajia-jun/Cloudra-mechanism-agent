---
id: 625
title: 令Gaussian 16中SCF未收敛到默认收敛限也能继续做后续计算的方法
url: http://sobereva.com/625
domain: Gaussian使用
topic: Gaussian_16_绕过_SCF_收敛检查的_IOp_设
cards: 1
---

# Gaussian_16_绕过_SCF_收敛检查的_IOp_设 — 知识卡片

## 1. Gaussian 16默认SCF收敛限及其导致的强制终止问题

Gaussian 09版开始默认收敛限为tight（相当于SCF=conver=8），在所有量子化学程序中几乎最严。Gaussian 16引入规则：若SCF未达到默认收敛限且任务涉及能量导数计算（如几何优化、振动分析）或后HF、TDDFT等多行列式/多组态方法，程序在SCF模块运行后会报错"SCF Error... SCF has not converged. Gradients and post-SCF results would be GARBAGE!!"并终止。
## SCF收敛精度检查的触发机制Link 701和Link 801
从Gaussian 16开始，调用Link 701和Link 801模块开始时会调用SCFChk检查SCF收敛性，未达默认收敛限即终止。Link 701是计算单电子积分一阶或二阶导数的模块，所有算能量导数的任务都会经历它；Link 801是初始化双电子积分变换的模块，TDDFT、双杂化、后HF等多行列式/组态任务都会经历它。
## 关闭Link 701中SCF收敛性检查的IOp设置
对于需要经历Link 701的任务，可以通过IOp(7/127=-99)来关闭SCF收敛性检查。实际上不必须设置为-99，只要是比-100更正的值都可以。
## 关闭Link 801中SCF收敛性检查的IOp设置
对于需要经历Link 801的任务，可以通过IOp(8/117=-99)来关闭SCF收敛性检查。该设置允许SCF未收敛到默认限也能进行后续TDDFT、双杂化、后HF等计算。
## 允许低SCF收敛限进行几何优化的输入行示例
在Gaussian 16中使用# B3LYP/6-31G* SCF=conver=6 opt，因SCF未收敛到默认SCF=conver=8会报错。若写为# B3LYP/6-31G* SCF=conver=6 opt IOp(7/127=-99)，则可跳过检查让几何优化继续进行。
## 全局默认关闭SCF收敛性检查的配置方法
可在Default.Rou（Windows版）或Default.Route（Linux版）文件中加入一行-#- IOp(8/117=-99) IOp(7/127=-99)。这会使这两个IOp设置对所有后续计算默认启用，从而避免遇到SCF未达默认限而终止的问题。
## varacc机制对SCF=conver=x设置的影响
Gaussian默认在SCF前期用较低精度算电子积分（提示Integral accuracy reduced to 1.0D-05 until final iterations），此时SCF=conver=x不起实际作用，仍会迭代到满足tight收敛标准才结束。若想让SCF=conver=x总是如实生效，应在SCF关键词中同时写上novaracc。
## 确保低收敛限如实生效的完整输入示例
建议输入行写为# B3LYP/6-31G* SCF(conver=6,novaracc) opt IOp(7/127=-99)。这可确保每一轮如实迭代到conver=6的程度就视为收敛；若想让novaracc默认启用，可在Default.Rou/Route里的-#-后面加上scf=novaracc。
## 低收敛限几何优化结果的适用性限制
SCF=conver=6情况下的优化只能算作预优化，实际发表用的结构必须在默认的SCF收敛限下优化得到。绝对不能把SCF=conver=6时几何优化的结果当做最终使用的结构。

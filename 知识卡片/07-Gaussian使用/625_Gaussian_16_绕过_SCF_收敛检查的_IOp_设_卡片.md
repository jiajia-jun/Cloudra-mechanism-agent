---
id: 625
title: 令Gaussian 16中SCF未收敛到默认收敛限也能继续做后续计算的方法
url: http://sobereva.com/625
domain: Gaussian使用
topic: Gaussian_16_绕过_SCF_收敛检查的_IOp_设
cards: 8
---

# Gaussian_16_绕过_SCF_收敛检查的_IOp_设 — 知识卡片

## 1. Gaussian 16默认的SCF收敛限

Gaussian程序从09版开始默认的收敛限成为了tight，相当于SCF=conver=8关键词设的收敛限。Gaussian 16加入了一个规则，如果SCF收敛精度没达到默认的收敛限，且任务涉及计算能量导数（如几何优化、振动分析）或使用后HF、TDDFT等方法，程序将报错终止。

---

## 2. Gaussian 16强制终止SCF未收敛任务的机制

Gaussian 16在调用Link 701、Link 801模块开始时都会调用SCFChk做SCF收敛性检查。Link 701是计算单电子积分导数的模块（所有算能量导数的任务都会经历它），Link 801是初始化双电子积分变换的模块（TDDFT、双杂化、后HF等任务都会经历它）。若SCF未收敛到默认限，程序会报错提示“SCF has not converged. Gradients and post-SCF results would be GARBAGE!!”并终止。

---

## 3. 关闭Link 701的SCF收敛检查

对于需要经历Link 701的任务（如几何优化、振动分析），可以通过IOp(7/127=-99)来关闭SCF收敛性检查。实际上只要值比-100更正都可以，例如在输入行中写入`# B3LYP/6-31G* SCF=conver=6 opt IOp(7/127=-99)`即可让几何优化继续进行。

---

## 4. 关闭Link 801的SCF收敛检查

对于需要经历Link 801的任务（如TDDFT、双杂化、CCSD(T)），可以通过IOp(8/117=-99)来关闭SCF收敛性检查。该选项同样只要值比-100更正即可生效，这使得在SCF未达到默认收敛限时也能执行后续计算。

---

## 5. 全局设置默认关闭SCF收敛检查

为了避免每次输入繁琐的IOp，可以在Default.Rou（Windows版）或Default.Route（Linux版）文件中添加一行`-#- IOp(8/117=-99) IOp(7/127=-99)`。这样设置后，这两个IOp会对之后所有计算默认启用，程序将不再因SCF未收敛到默认限而报错终止。

---

## 6. SCF积分精度对收敛限设置的影响

Gaussian默认在SCF计算前期用精度较低的方式算电子积分（提示Integral accuracy reduced to 1.0D-05 until final iterations），此时SCF=conver=x的设置可能不起实际作用，程序仍会迭代到满足tight收敛标准才结束。如果想让SCF=conver=x总是如实生效，应当在SCF关键词里同时写上novaracc。

---

## 7. 确保SCF收敛限设置如实生效的组合写法

为了让SCF收敛到指定精度（如conver=6）即视为收敛，必须结合使用novaracc关键词，例如写作`# B3LYP/6-31G* SCF(conver=6,novaracc) opt IOp(7/127=-99)`。这确保每一轮迭代都如实按照conver=6的标准判断收敛，而不是受积分精度降低策略的影响。

---

## 8. SCF收敛限放宽结果的使用限制

SCF=conver=6情况下的几何优化只能算得上预优化，绝对不能将此时的结果当做最终发表用的结构。实际发表用的结构必须在默认的SCF收敛限下优化得到，初学者必须严格遵守这一规则。

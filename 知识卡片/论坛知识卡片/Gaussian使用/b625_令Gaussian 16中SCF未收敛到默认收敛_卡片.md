---
key: b625
title: 令Gaussian 16中SCF未收敛到默认收敛限也能继续做后续计算的方法
url: http://sobereva.com/625
domain: Gaussian使用
source: blog
year: 2021
cards: 8
---

# 令Gaussian 16中SCF未收敛到默认收敛限也能继续做后续计算的方法 — 知识卡片

## 1. Gaussian 16 SCF 默认收敛限制

Gaussian 09 及以后的版本默认使用 SCF=conver=8 (即 Tight) 作为收敛标准，这在量子化学程序中属于非常严格的精度要求。Gaussian 16 增加了强制性检查机制，若 SCF 未达到此默认收敛限且涉及计算能量导数（如几何优化、振动分析）或后 HF 方法，程序将在 SCF 模块结束后报错终止。该设计旨在防止因 SCF 收敛精度不足导致计算结果不可靠，且此检查无法通过常规手册或 IOp 文档描述的方法关闭。

---

## 2. SCF 收敛检查触发的报错情形

当 Gaussian 16 执行几何优化、振动分析、双杂化泛函、TDDFT 或后 HF 等涉及能量导数或多行列式的任务时，若 SCF 未收敛到默认限，程序会调用 Link 701 或 Link 801 进行检测并报错。报错信息包含 "SCF Error" 以及 "SCF has not converged. Gradients and post-SCF results would be GARBAGE!!"，导致任务强制终止。

---

## 3. 严格收敛限造成的计算困难

对于过渡金属团簇、使用小核赝势的镧系锕系配合物或存在较大外电场的体系，SCF 往往极难收敛到默认的 Tight 标准。在几何优化的初始阶段，由于结构偏离极小点较远，电子结构复杂，达到默认收敛限的难度更大，导致常规的 SCF 收敛辅助方法（如阻尼、Level shifting）有时也难以奏效，阻碍了计算进程。

---

## 4. 绕过 SCF 默认收敛检查的原理

Gaussian 16 在计算单电子积分导数时调用 Link 701，在初始化双电子积分变换时调用 Link 801，这两个 Link 都会调用 SCFChk 模块检查收敛性。可以通过设置特定的 IOp 值来关闭这些检查：对于需要经历 Link 701 的任务（如几何优化），使用 IOp(7/127=-99)；对于需要经历 Link 801 的任务（如 TDDFT），使用 IOp(8/117=-99)。这些 IOp 值只要比 -100 更正即可生效。

---

## 5. 绕过 SCF 收敛检查的命令示例

为了在 SCF 未达到默认收敛限时继续进行几何优化，可以在输入行中添加 IOp(7/127=-99)。例如，使用 `# B3LYP/6-31G* SCF=conver=6 opt IOp(7/127=-99)` 可以让优化任务在 SCF 收敛到相对较松的 conver=6 标准后继续进行，类似于 Gaussian 09 的行为。对于 TDDFT 等任务，则需添加 IOp(8/117=-99)。

---

## 6. 全局设置绕过 SCF 收敛检查

为了避免在每次计算任务中手动输入 IOp，可以在配置文件中设置全局默认值。在 Windows 版的 Default.Rou 或 Linux 版的 Default.Route 文件中，添加 `-#- IOp(8/117=-99) IOp(7/127=-99)`，即可使之后的所有计算默认忽略 SCF 默认收敛限的检查，解决因不满足收敛限而报错终止的问题。

---

## 7. 变精度积分对收敛限设置的影响

Gaussian 默认在 SCF 前期使用较低精度计算电子积分（提示 Integral accuracy reduced to 1.0D-05），此时即便设置了较松的 SCF=conver=x，程序仍可能会迭代至满足 Tight 标准才结束。为了确保 SCF=conver=x 的设置在每一轮迭代中如实生效，需要在 SCF 关键词中同时加入 novaracc 选项，即使用 `SCF(conver=6,novaracc)`。

---

## 8. SCF 宽收敛限优化的应用限制

使用 SCF=conver=6 等宽收敛限进行几何优化仅适用于预优化阶段，目的是让结构接近极小点以便后续更容易收敛。绝对不能将 SCF=conver=6 下得到的优化结构作为最终发表结果，最终发表使用的结构必须在默认的 SCF 收敛限（SCF=conver=8）下重新优化得到，以确保精度。

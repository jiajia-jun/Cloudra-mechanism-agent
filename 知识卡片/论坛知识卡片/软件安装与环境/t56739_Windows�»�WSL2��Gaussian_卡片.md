---
key: t56739
title: Windows�»�WSL2��Gaussian��9950x�ĵ������⼰�������
url: http://bbs.keinsci.com/thread-56739-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2025
cards: 10
---

# Windows�»�WSL2��Gaussian��9950x�ĵ������⼰������� — 知识卡片

## 1. AMD Ryzen 9950X 双 CCD 温度与频率差异

AMD Ryzen 9950X 处理器在运行 Gaussian 计算时，若未进行手动优化，两个 CCD（CCD1 和 CCD2）之间存在显著的温度与频率差异。CCD1 的温度通常比 CCD2 高 10-20 摄氏度，且 CCD1 的平均频率可达 5.5 GHz（峰值 5.7 GHz），而 CCD2 平均频率仅 3-4 GHz（峰值 5.6 GHz）。

---

## 2. Ryzen 9000 系列 CCD 频率差异原因

Ryzen 9000 系列 CPU 的两个 CCD 芯片体质不同，即便开启 PBO（Precision Boost Overdrive），CCD1 的加速频率可达 5.7 GHz，而 CCD2 在同等电压下最高仅能达到 5.5 GHz。默认情况下系统倾向于让体质较好的 CCD1 承担主要负载，导致其温度较高。

---

## 3. WSL2 逻辑核与物理核的对应关系

在 WSL2 环境中，vmmemWSL 进程的逻辑核编号与物理核心（CCD）的对应关系可能呈现特定的间隔模式。例如在 9950X 上，CPU0 与 CPU1 属于同一物理核心的 SMT 线程，CPU2 与 CPU3 属于同一物理核心；而 CPU0 与 CPU16、CPU0 与 CPU31 则分别对应不同的 CCD 芯片。

---

## 4. Linux 进程绑核原理

在 Linux（包括 WSL2）下，可以通过测试不同线程组合（如 CPU0+CPU1、CPU0+CPU16、CPU0+CPU31）对应的 vmmemWSL 进程运行情况，来确定逻辑核与物理核的映射关系。观察发现，逻辑核 n 与 n+1 通常对应同一物理核心的 SMT 线程，而逻辑核 n 与 n+16（在 16 核 CCD 上）或特定远距离编号则对应不同 CCD。

---

## 5. Gaussian 计算时间对比（未优化）

在未进行核心绑定的 WSL2 环境下，使用 16 核并行（`%nproc=16`）运行 Gaussian 计算任务（输入文件 test0397，关键字 `b3lyp/def2svp force scf=novaracc`），耗时约为 6 分 26 秒至 6 分 45 秒。此时不同核心分配方式导致的计算时间差异不明显。

---

## 6. 核心负载分布不均问题

默认的 Gaussian 并行设置（如 `%nproc=16`）会导致负载集中在单个 CCD（如 CCD1）上，使得该 CCD 下的核心温度升高（可达 98 摄氏度），而另一个 CCD 温度较低（约 85 摄氏度）且频率较低。这种负载不均限制了双 CCD 处理器的整体性能发挥。

---

## 7. 手动绑核优化方案

通过手动指定线程亲和性，将计算任务均匀分配到两个 CCD 的物理核心上（即避免使用同一物理核心的 SMT 线程，确保跨 CCD 分配），可以实现双 CCD 在相近的低温下运行。测试显示，优化后 CCD1 和 CCD2 的温度差异减小，整体功耗降至约 220 W。

---

## 8. 绑核优化后的计算效率

在实施手动绑核使双 CCD 均衡负载后，同样的 Gaussian 计算任务（test0397）耗时缩短至 6 分 01 秒。相比未优化时的 6 分 26 秒至 6 分 45 秒，性能提升显著，且优于单纯关闭 SMT 线程后的性能。

---

## 9. Process Lasso 设置 CPU 关联性

为了避免每次启动 WSL2 都手动修改进程亲和性，可以使用 Process Lasso 工具对 `vmmemWSL` 进程设置默认的 CPU 关联性。通过勾选“所有偶数 CPU”或根据 CPU 物理布局选择特定的核心组合，可以自动实现均衡的跨 CCD 调度。

---

## 10. 多任务计算优化思路

在同时运行多个 Gaussian 计算任务时，利用 Process Lasso 设置不同的 CPU 关联性规则，可以确保每个任务占用不同 CCD 的核心，从而最大化利用硬件资源并提高总吞吐量。此思路同样适用于 Windows 原生 Gaussian (G16W) 及其他平台的多核优化。

---
key: t16405
title: Gaussian 16���������WSL�е����Ч��
url: http://bbs.keinsci.com/thread-16405-1-1.html
domain: Gaussian使用
source: keinsci
year: 2020
cards: 7
---

# Gaussian 16���������WSL�е����Ч�� — 知识卡片

## 1. WSL 与 VMWare/VMVirtualBox 运行 Gaussian 16 的效率对比

在 R9 3950x 平台及特定测试环境下，WSL 运行 Gaussian 16 的效率接近原生 Linux，性能损失仅约 10%。测试结果显示 VirtualBox 的效率高于 VMWare，且不同软件（如 ORCA）在不同虚拟环境中的表现可能存在差异。

---

## 2. 测试硬件与软件配置

测试平台包括 AMD R9 3950X 处理器、B450 芯片组及双通道 DDR4 3200 64GB 内存，散热设置为刚好 4 风扇且仅降压 1W。操作系统为 Ubuntu 18.04 LTS (宿主机 Windows 10 Pro for Workstation)，虚拟机软件版本为 VMWare Workstation 15.5.1 和 Oracle VM VirtualBox 6.1.4，均安装了对应增强工具。

---

## 3. 测试用例与 Gaussian 16 版本

测试计算对象为含 16 个原子的体系，内存设置为 16GB，任务类型为频率计算，测试参考来源于 computational-chemistry.com 的 Ryzen Threadripper Gaussian16 benchmark。使用的 Gaussian 16 版本为 b.01，默认链接了 sse4.2 线性代数库，未使用 g16w。

---

## 4. WSL 的适用场景与优势

WSL 非常适合仅安装 Windows 10 且需同时兼顾办公、娱乐及计算任务的用户。WSL 环境下的 Gaussian 16 计算任务与用户日常操作互不干扰，具备较好的稳定性。

---

## 5. WSL 下的线程栈限制问题

在 WSL 中运行 xtb 时需设置 `export OMP_STACKSIZE=1000m`，而 Gaussian 16 直接使用此设置会报错 "Error: specified stack size exceeds hard limit"。WSL 默认账户权限允许执行 `ulimit -s unlimited` 命令来解决 Gaussian 16 和 xtb 的运行限制。

---

## 6. 虚拟机环境下的文件传输稳定性问题

VirtualBox 环境下使用共享文件夹可能存在不稳定现象，具体表现为计算过程中出现小偏差或偶发文件传输失败。遇到文件传输卡住或无法移动的情况时，可通过重启虚拟机解决。

---

## 7. Hyper-V 虚拟化对 WSL 的影响

开启 Hyper-V 功能会导致 WSL 性能大幅下降，测试中性能减半。若需在 WSL 中获得良好计算性能，应避免开启 Hyper-V。

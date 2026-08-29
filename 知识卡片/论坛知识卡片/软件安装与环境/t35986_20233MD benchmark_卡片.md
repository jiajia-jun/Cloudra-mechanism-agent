---
key: t35986
title: 2023��3��MD benchmark������ƪ����W790ƽ̨�׷����ԣ��������룩
url: http://bbs.keinsci.com/thread-35986-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 17
---

# 2023��3��MD benchmark������ƪ����W790ƽ̨�׷����ԣ��������룩 — 知识卡片

## 1. Intel W790平台硬件配置

测试平台基于Intel W790芯片组，使用了两款CPU型号：Intel Xeon w7-2495X 和 Intel Xeon w9-3495X。操作系统环境为 Ubuntu 22.04.2 LTS Desktop，内核版本 Linux 5.19.0-35-generic x86_64，编译器为 GNU 11.3。软件环境配置了 CUDA Toolkit 12.1 和 NVIDIA GPU Driver 530.30.02。

---

## 2. W790平台BIOS与超频设置

在ASUS主板的BIOS设置中，开启了ASUS MultiCore Enhancement [Enabled - Removelimits]，并将CPU Core Ratio设置为 [By Core Usage]。DIGI+ VRM配置中选择 CPU Load-line Calibration [Level 7]，Internal CPU Power Management中设置 Maximum CPU core Temperature 为 [105]。针对3495X核心电压设为Auto，针对2495X核心电压offset设置为+0.15V。

---

## 3. CPU核心电压与频率稳定性

CPU核心电压设置不宜过高，否则可能引起系统不稳定。在降压超频前，必须保证核心电压足够高以确保系统稳定运行，然后再逐步尝试降低电压。

---

## 4. 3495X全核频率设置bug

在Linux环境下使用Sync All Cores方式对3495X进行全核频率设置时，存在导致功耗突然飙升至360W甚至黑屏的bug。为避免此问题，建议使用Per Core方式设置频率，或者通过mlc等工具进行内存延迟测试以验证CPU是否处于稳定状态。

---

## 5. W790平台CPU散热配置

测试中使用了ABEE SPR360水冷散热器，该散热器设计功耗为920W。在测试期间，3495X的功耗达到650W，核心温度控制在100摄氏度以内。

---

## 6. GROMACS多线程性能限制

由于GROMACS对多线程支持的局限性，在W790平台上，CPU核心数超过32个后，性能提升不再明显。对于支持超线程的CPU，其1个物理核心被视为2个逻辑核心参与计算。

---

## 7. CPU核间延迟对GROMACS性能的影响

CPU核间延迟对GPU加速的GROMACS计算性能有显著影响。测试数据显示，在开启前8个核心时，2495X和3495X与Ryzen 9 7950X及Core i9-13900KF的性能差异明显；但在核心数超过8个后，前两者的性能优势逐渐缩小直至与后两者持平。 Ryzen 9 7950X和Core i9-13900KF在核心数超过8个后，性能不再随核心数增加而增长。

---

## 8. GPU-resident模式下的CPU与GPU配比

在GROMACS的GPU-resident模式下，1块RTX 4090显卡通常对应8~12个CPU核心即可满足需求。对于单卡配置，CPU核心数过多（如32核）并不会带来显著的性能提升，可能造成硬件资源浪费。

---

## 9. 多GPU卡配置建议

若配置2块RTX 4090，建议CPU核心数至少在16核以上；若配置3块RTX 4090，建议CPU核心数在24核以上（如w7-2495X）以平衡资源。在实际使用中，建议为每个GPU分配独立的计算任务或编写脚本控制任务分配，避免多任务争抢同一逻辑核心。

---

## 10. w9-3495X运行量子化学计算的超频设置

运行Gaussian和ORCA时，w9-3495X采用了降压超频策略，核心电压offset设置为-0.1V，全核频率设定为4.5GHz。

---

## 11. w9-3495X与EPYC在Gaussian中的性能对比

在关键词为"b3lyp 3-21g force scf=novaracc"的测试中，w9-3495X在全核频率4.5GHz下，表现优于双路EPYC 7T83和双路Xeon 8375C。在耗时较长的测试项目中，w9-3495X能够追平双路EPYC 9554；但在小任务测试中，单路EPYC 9554表现优于w9-3495X。

---

## 12. w9-3495X在ORCA中的性能表现

在ORCA测试中，w9-3495X全面领先于双路EPYC 7T83和双路Xeon 8375C。与双路EPYC 7T83相比，w9-3495X表现出显著的性能优势。

---

## 13. 高负载下CPU频率波动现象

在Gaussian和ORCA计算过程中，SCF迭代阶段CPU负载较高，但在CPU进行低负载阶段（如两步计算之间的切换），频率会大幅下降。测试观察到CPU频率从高频瞬间跌落至2.9GHz甚至1.9GHz（base clock），且从降频恢复到升频的响应较慢，影响了整体计算效率。BIOS默认设置下，CPU核间延迟问题也存在，进一步影响了性能发挥。

---

## 14. w9-3495X内存带宽瓶颈

w9-3495X仅支持8通道DDR5 4800MT/s内存，而AMD EPYC 9004系列支持12通道DDR5 4800MT/s。尽管w9-3495X的全核频率可达4.5GHz，但其内存带宽相对较弱，这被认为是其难以全面超越双路EPYC 9554的主要原因之一。

---

## 15. w9-3495X Cinebench R23 跑分数据

在降压超频设置下，w9-3495X在Cinebench R23测试中获得108016pts的成绩，测试耗时仅2分钟。该成绩是在无高温、无功耗限制的条件下取得的。

---

## 16. 2024年CPU架构展望

预计2024年发布的CPU将采用新架构，Intel可能推出基于Redwood Cove (Intel 4)微架构的Granite Rapids-SP和基于Lion Cove微架构的Arrow Lake-S。AMD将推出Zen5架构，据称在IPC（每时钟周期指令数）方面将有较大提升。对于内存带宽密集型任务，新一代平台的内存性能有望进一步增强。

---

## 17. 测试数据来源

本次测试的原始数据已整理为文件 MD_benchmark_data_Mar2023_Pub2.xlsx，可通过阿里云盘链接下载，提取码为 n2k7。

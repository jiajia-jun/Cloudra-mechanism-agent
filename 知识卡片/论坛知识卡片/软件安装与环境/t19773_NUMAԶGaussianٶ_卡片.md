---
key: t19773
title: NUMA���Զ�Gaussian�����ٶ�Ӱ���С�о�
url: http://bbs.keinsci.com/thread-19773-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2020
cards: 18
---

# NUMA���Զ�Gaussian�����ٶ�Ӱ���С�о� — 知识卡片

## 1. NUMA 架构定义

NUMA 是非统一内存访问架构。在多处理器系统中，每个 CPU 访问本地内存速度快，访问远程内存速度慢。单个主板上的多片 CPU 构成多个 NUMA 节点，每个节点包含 CPU 和对应的内存。

---

## 2. NUMA 对计算任务的影响

如果计算任务只使用部分 CPU，任务可能只在一个 NUMA 节点上运行，此时 NUMA 特性影响不大。当并行计算跨多个 NUMA 节点时，CPU 访问远程内存会增加延迟，影响计算效率。

---

## 3. NUMA 优化策略

在内存带宽受限的任务中，应尽量将任务分布在单个 NUMA 节点内以最大化利用本地内存带宽。在内存延迟敏感的任务中，可通过 `nprocshared` 参数限制核心数以避免跨节点访问。测试不同 NUMA 策略对性能影响较大。

---

## 4. 使用 MLC 工具测试内存延迟

使用 Intel® Memory Latency Checker 工具可以测试不同 NUMA 节点间的内存访问延迟和带宽。测试命令为 `sudo ./mlc`。EPYC 7742 等平台跨节点访问内存的延迟显著高于本地节点访问。

---

## 5. 使用 numactl 工具

Linux 系统支持 NUMA，可使用 `yum install numactl` 或 `sudo apt-get install numactl` 安装 numactl 工具。使用 `dmesg | grep NUMA` 可查看系统是否支持 NUMA。

---

## 6. 查看 NUMA 硬件配置

使用 `numactl --hardware` 命令可以查看系统的 NUMA 节点配置、节点对应的 CPU 编号及内存大小。使用 `numactl -s` 可以查看当前的 NUMA 策略设置。

---

## 7. numactl 绑定 CPU 与内存

使用 `numactl --cpunodebind=0 --membind=0` 命令可以将进程绑定在指定的 NUMA 节点上运行，既限制使用的 CPU 也限制使用的内存。`-C=0,20` 参数用于指定具体的 CPU 核心编号。

---

## 8. numactl 内存分配策略

`--localalloc` 策略仅在当前 NUMA 节点分配内存。`--membind=1` 强制仅在指定节点分配内存。`--preferred=0` 优先在指定节点分配内存，不足时在其他节点分配。`--interleave=0,1` 策略在多个节点间交叉分配内存。

---

## 9. 监控进程的 NUMA 资源使用

使用 `numastat -p l502.exe` 可以查看 Gaussian 进程在不同 NUMA 节点上的内存占用情况。使用 `ps -U $USER -L -o pid,cpuid,pcpu,comm | grep l502 | sort -nk 2` 可以查看进程具体运行在哪些 CPU 核心上。

---

## 10. Gaussian 中的 NUMA 设置方法

Gaussian 支持 NUMA 设置的方法包括：使用 numactl 命令行、使用 Gaussian 输入文件中的 `%cpu` 选项绑定 CPU，或使用 xbench 测试脚本（2.0 版本起）。推荐使用 numactl 或 xbench 进行设置。

---

## 11. Local 策略设置

Local 策略指任务尽量使用最少的 NUMA 节点。使用 `numactl --cpunodebind=1 --membind=1 g16 test397.inp` 可将任务限制在单个 NUMA 节点内。xbench 中使用 `-N loc` 参数启用此策略。

---

## 12. Distributed 策略设置

Distributed 策略指将线程均匀分布在不同 NUMA 节点的 CPU 上。使用 `numactl -C 0-10,22-32 g16 test397.inp` 可指定跨节点的 CPU 核心。xbench 中使用 `-N dist` 参数启用此策略。

---

## 13. Remote 策略设置

Remote 策略指 CPU 使用与其分离的远程内存，使用命令如 `numactl --cpunodebind=0 --membind=1 g16 test397.inp`。此策略通常用于测试，实际应用中性能较差，xbench 不直接支持。

---

## 14. Semi 策略设置

Semi 策略适用于同时运行多个任务的情况，单个任务尽量使用单个 NUMA 节点，多个任务分布在不同节点。xbench 使用 `-N semi` 参数实现此策略，例如 `xbench.sh -n 11 -t 2 -r 3 -N semi`。

---

## 15. 双路 Xeon 平台 DFT 计算效率对比

在 Xeon E5-2699V4 双路平台上进行 DFT 计算时，使用单个 NUMA 节点效率通常最高。跨节点访问会带来内存带宽瓶颈和延迟增加，导致并行效率下降。

---

## 16. 双路 Xeon 平台 Remote 策略性能

Remote 策略下，计算速度变慢明显，测试显示远程内存延迟比本地高约 1.5 倍。这表明内存延迟对计算速度有显著负面影响。

---

## 17. 双路 Xeon 平台 Freq 计算 NUMA 影响

在双路 Xeon 平台进行 Freq 计算时，NUMA 效应不明显。这是因为 Freq 计算是内存密集型任务，受限于内存带宽而非延迟，且受 `%nprocshared` 设置影响较大。

---

## 18. EPYC 平台并行扩展效率测试

在 EPYC 7742 双路平台上测试显示，Local 策略下并行度达到 64 核时出现拐点，耗尽一个 NUMA 节点资源后开始使用第二个节点时速度下降。Local 策略在资源未耗尽时可节省节点间通讯成本。

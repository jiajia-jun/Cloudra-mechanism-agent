---
key: t31593
title: �����Ƽ����߳�ƽ������Process Lasso
url: http://bbs.keinsci.com/thread-31593-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2022
cards: 7
---

# �����Ƽ����߳�ƽ������Process Lasso — 知识卡片

## 1. Windows 平台多线程调度问题

Windows 在多核 CPU（特别是双路 E5 2696v3）上的多线程调度优化不如 Linux。在双路服务器上运行 GROMACS 或 ORCA 计算时，Windows 平台存在任务只压在一个 CPU 上而另一个 CPU 空闲的情况。手动指定进程亲和性无法解决 GROMACS 仅启动单个线程或 ORCA 的 SCF 频率无法刷新的问题。

---

## 2. 高负载下的系统响应延迟

在 Windows 上运行高负载计算任务时，线程间可能存在相互干扰，导致系统响应缓慢，影响日常办公操作。长时间运行计算任务时，这种系统卡顿现象尤为明显。

---

## 3. Process Lasso 的 ProBalance 功能

ProBalance 功能通过动态调整进程优先级来限制占用资源过多的进程，从而保证前台程序和系统响应的流畅性。即使后台运行高负载计算任务（如计算化学模拟），启用 ProBalance 后也能避免系统卡顿，保障办公操作不受影响。

---

## 4. Windows 的 CPU 组与 64 核阈值

Windows 操作系统对 CPU 核心数的管理存在 64 个逻辑核心的阈值限制。在 48 核工作站上，系统会建立一个包含 48 个核心的 CPU 组；而在 72 核工作站上，系统会建立两个 CPU 组，每组包含 36 个核心。如果不进行特殊处理，应用程序默认只能运行在第一个 CPU 组的 36 个核心上。

---

## 5. Group Extender 功能的作用

Group Extender 功能用于打破 Windows 默认的 CPU 组限制，使应用程序能够跨越 CPU 组使用所有可用的物理核心。该功能允许进程分配到所有可用的 CPU 核心上，从而提高在超过 64 核心的系统上的运行效率。

---

## 6. Group Extender 对 ORCA 进程的影响

关闭 Group Extender 功能时，`orca_scf_mpi.exe` 的 CPU groups 数值为 1，进程仅被限制在一个 CPU 上运行。开启 Group Extender 后，`orca_scfhess_mpi.exe` 的 CPU groups 显示为 0,1，表明进程可以跨越系统的默认分组限制并分配到所有 CPU 上。通过通配符匹配（如 `orca*`），Group Extender 同样适用于以 orca 开头的进程，对 GROMACS 和 VMware 等软件也有效。

---

## 7. Instance balancer 功能模式

Instance balancer 功能用于控制系统中每个副本实例的核心分配，支持绑定逻辑核心。该功能提供两种模式：Dynamic core count 模式允许对选定的进程进行动态精确选择，Fixed core count 模式则强制选定的进程只能使用固定数量的核心。

---
Process Lasso 官方文档及参考链接：
- Process Lasso 官方文档: https://bitsum.com/processlasso-docs/#groupextend
- Windows 多核调度的解释: https://bitsum.com/general/the-6 ... groups-and-windows/

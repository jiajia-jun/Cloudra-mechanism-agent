---
key: t40486
title: DIY NASС�� | Mini�����ܼ�Ⱥ���𣨵�һ����
url: http://bbs.keinsci.com/thread-40486-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2023
cards: 16
---

# DIY NASС�� | Mini�����ܼ�Ⱥ���𣨵�һ���� — 知识卡片

## 1. DIY NAS 硬件选型与成本

组装 DIY NAS 可通过购买散件节省成本，成品的散件价格相比打包销售存在差异。基于 CX3 Pro 芯片的 HP544+FLR 被选为网卡方案。硬盘方面依据 Backblaze 的硬盘故障率报告，选择了希捷 EXOS X18 18TB HDD，其可靠性被认为优于 HGST 和 WDC Ultrastar 系列。

---

## 2. SSD 兼容性与 PCIe 配置

在 PCIe Gen 3 平台上使用 PCIe Gen 4 SSD（如三星 970 EVO Plus）时，需要注意 SSD 发热问题，推荐搭配散热片使用。LGA 3647 平台的 CPU 拥有 44+4 条 PCIe Lane，适合连接大量 NVMe 设备，有助于避免带宽瓶颈。

---

## 3. 存储系统架构设计

该存储系统基于 Ubuntu Server、OpenZFS 和 NFS over RDMA (RoCE) 构建，未直接使用 TrueNAS Scale。系统设计旨在最大化 IO 性能，包括 192GB RAM 的 ARC、2 块固态 7100 1TB 组成的 Cache VDEV、2 块英特尔 Optane 900P 280GB 组成的 SLOG VDEV，以及 3 块固态 7100 1TB 组成的 Metadata (Special) VDEV。

---

## 4. 数据池 VDEV 配置策略

Data pool 包含 2 组由 6 块硬盘组成的 RAID Z1 VDEV。为防止 VDEV 中多块硬盘同时故障，每组 RAID Z1 VDEV 中的硬盘来源被错开，确保硬盘分属不同购买批次。HDD 盘标被移除以便区分，其中带 I 指示灯的连接至 SFF-8643 接口，带 E 指示灯的通过 SFF-8087 接口连接至 HBA。

---

## 5. RoCE 网络配置与优势

RoCE (RDMA over Converged Ethernet) 允许绕过操作系统内核，实现服务器与客户端之间的直接内存访问，显著降低延迟并提高吞吐量。挂载目录后，存储读写操作可通过 RDMA 网络进行，同时支持通过传统以太网进行管理。Windows SMB 默认支持 RDMA。

---

## 6. 网卡聚合与绑定问题

mellanox 40G 网卡支持 LACP 链路聚合，但在实际使用中存在多 IP 配置的困难。网卡的聚合模式（Bonding）在系统中表现异常，IP 地址可能发生漂移或无法按预期工作，最终通过修改配置文件和调整网卡状态得以解决。

---

## 7. 硬盘供电线材转换

为了提高供电可靠性，3 块 HDD 分别连接了不同的 4P 电源接口。由于系统机箱自带 SATA 供电线不足，使用了 4P 转 SATA 的供电转接线，连接至系统机箱的背板。

---

## 8. 系统初始化与 BIOS 设置

组装完成后，需在 BIOS 中将 PCIe 链路速率强制设为 Gen 3，因为某些 SSD 在 Auto 模式下可能会降速至 Gen 2 或 Gen 1。系统盘配置为 BIOS 级别的 RAID 1。安装 Windows 系统可进行基础压力测试，Cinebench R23 得分可达 19655 pts。

---

## 9. Ubuntu Server 安装与配置

Ubuntu Server 22.04.3 LTS 在安装初期可选择安装 Desktop GUI 以便操作。安装 RDMA 驱动后，可使用 `ibv_devinfo -v` 命令验证 RDMA 设备状态。网络配置使用 netplan，设置集群内 IP 为 `10.0.0.3`，DNS 与 Windows PC 一致为 `192.168.31.1`，并设置 MTU=9000。

---

## 10. 网络连通性测试

使用 `ping` 命令测试服务器、交换机和客户端之间的 MTU 设置，确保 MTU=9000 配置正确，避免网络丢包或性能下降。ZFS pool 创建完成后，可使用 `zpool status` 命令查看存储池状态。

---

## 11. ZFS 性能调优参数

ZFS 模块参数优化需写入 `/etc/modprobe.d/zfs.conf` 文件。关键参数包括：`l2arc_noprefetch=0`、`zfs_arc_lotsfree_percent=2`、`zfs_arc_max=191106155315`（约 192GB）、`l2arc_write_boost=10000000000` 以及 `l2arc_write_max=10000000000`。

---

## 12. ZFS ARC 内存限制计算

ZFS ARC 最大内存值计算命令为 `grep '^MemTotal' /proc/meminfo|awk '{printf "%d", $2 * 1024 * 0.95}'`。针对专用 NAS 系统，建议将 ARC 最大值设为系统总内存的 95%，仅保留 5% 给系统使用。此外，可根据数据集特性手动设置 `atime=off` 以提升性能。

---

## 13. FIO 性能测试配置 (顺序写)

FIO 测试配置需保存为 `.fio` 文件。顺序写测试使用 128KiB 数据块、64GiB 文件大小、Sync 模式，关键参数包括 `ioengine=libaio`、`direct=1`、`iodepth=4`、`bs=128k`、`rw=write`。

---

## 14. FIO 性能测试配置 (随机读)

随机读测试使用 8KiB 数据块、64GiB 文件大小，关键参数包括 `bs=8k`、`size=64G`、`rw=randread`、`iodepth=32`。

---

## 15. FIO 性能测试配置 (混合读写)

混合读写测试（7:3 比例）使用 8KiB 或 128KiB 数据块，文件大小可为 64GiB 或 256GiB，关键参数包括 `rw=randrw`、`rwmixread=70`、`iodepth=32`。

---

## 16. NAS GPU 加速扩展

该 NAS 可安装 2 块 TITAN V 显卡配合 650W 电源独立供电，用于 ReaxFF 模拟计算。机箱外部使用内存架支撑 3 个电源，显卡算力可用于解决未完成的计算任务。

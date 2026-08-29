---
key: t46228
title: DIY NASС�� - ʵ�����ŶӰ�
url: http://bbs.keinsci.com/thread-46228-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2024
cards: 17
---

# DIY NASС�� - ʵ�����ŶӰ� — 知识卡片

## 1. DIY NAS 硬件配置与组件选择

DIY NAS 硬件配置基于 Supermicro 主板和机箱，硬盘采用 12 块 20TB HDD 组建 RAID Z2。系统使用 TrueNAS Scale 24.04，配置了双路冗余电源（市电+UPS）、256GiB 内存用于 ARC 以及 3.84TB NVMe SSD 用于 L2ARC。该配置移除了 Special VDEV 和 SLOG VDEV，整机硬件成本约为 6800 CNY。

---

## 2. WD Ultrastar DC HC560 硬盘特性与价格

WD Ultrastar DC HC560 20TB SATA HDD 的价格水平接近 HC550，当前 HDD 市场处于加价状态。相比于 HC550，HC560 的单盘价格仅高出约 100 CNY。

---

## 3. Supermicro MF51-ES3 主板平台特点

Supermicro MF51-ES3 主板已停产多年，具备低功耗特性，适用于低频使用场景。该板提供 3 根 PCIe x16 插槽，CPU 单核性能较强，适合搭配 W-21xx 或 W-22xx 系列处理器进行 DIY GPU 或 NAS 组装。W-2135（6c12t）在该平台上全核频率可达 4.4GHz，价格已降至约 110 CNY。

---

## 4. 服务器级主板开关控制与散热

Supermicro 主板未在 PCB 上设置电源开关和重启按钮，需通过 BMC 进行控制。机箱后部 CRPS 电源模块被小碰撞挡住，尾部的排气口也被遮挡，导致电源散热受阻，需要调整风扇顺序并解开理线带以改善气流。

---

## 5. 机箱空间与硬件兼容性

该机箱官方支持 160mm 长度的电源，拆除 2.5 英寸硬盘架和电源转接卡后，可安装 260mm 长度的 CRPS 模块。机箱底部有 3 个 3.5 英寸安装位，但在安装 12038 风扇或 LSI 9300-16i HBA 等长卡时，需注意是否与 HDD 托架或风扇排发生冲突。

---

## 6. PCIe 扩展与存储系统配置

系统配置了 1 块 Intel 7100 SSD 和 1 块 Optane P4800X 组成 Mirror 用于安装操作系统。下置硬盘背板将原 PWM 4Pin 风扇接口改为不支持调速的接口，需注意风扇全速运行带来的噪音。

---

## 7. ZFS 参数优化配置

在 TrueNAS Scale 24.04 中，通过编辑 /etc/modprobe.d/zfs.conf 文件并添加特定参数可优化 ZFS 性能。配置内容如下：
options zfs l2arc_noprefetch=0
options zfs l2arc_write_boost=10000000000
options zfs l2arc_write_max=10000000000
此配置允许内核在将数据写入 HDD 时同时写入 L2ARC，利用 L2ARC 的 SSD 写入带宽来提升性能。

---

## 8. FIO 顺序写入性能测试 (128KiB)

使用 FIO 对 64GiB 文件进行 128KiB 数据块的顺序写入测试，iodepth 设为 4。测试结果显示平均带宽为 1770MiB/s (1856MB/s)，平均 IOPS 为 14.2k。

---

## 9. FIO 随机读取性能测试 (8KiB)

使用 FIO 对 64GiB 文件进行 8KiB 数据块的随机读取测试，iodepth 设为 32。测试结果显示平均读取带宽为 293MiB/s (307MB/s)，平均 IOPS 为 37.5k。

---

## 10. FIO 随机混合读写性能测试 (8KiB)

使用 FIO 对 64GiB 文件进行 8KiB 数据块的随机混合读写测试，读写比例为 7:3，iodepth 设为 32。测试结果显示读取平均带宽为 159MiB/s，IOPS 为 20.4k；写入平均带宽为 68.4MiB/s，IOPS 为 8749。

---

## 11. FIO 随机读取性能测试 (128KiB)

使用 FIO 对 256GiB 文件进行 128KiB 数据块的随机读取测试，iodepth 设为 32。测试结果显示平均读取带宽为 1485MiB/s (1557MB/s)，平均 IOPS 为 11.9k。

---

## 12. FIO 随机混合读写性能测试 (128KiB)

使用 FIO 对 256GiB 文件进行 128KiB 数据块的随机混合读写测试，读写比例为 7:3，iodepth 设为 32。测试结果显示读取平均带宽为 816MiB/s，IOPS 为 6527；写入平均带宽为 350MiB/s，IOPS 为 2799。

---

## 13. FIO 工具 issued rwts 统计信息解读

FIO 测试结果中 issued rwts 行展示了读、写、丢弃、同步等 I/O 操作的总数、短操作数和丢弃操作数。例如，输出参数 total=1467743,629409,0,0 表示读、写操作的总数分别为 1467743 和 629409，而丢弃与同步操作数均为 0。

---

## 14. FIO 工具 latency 参数配置说明

FIO 测试中的 latency 参数行用于定义延迟统计的目标值、滑动窗口、百分位深度等配置。示例参数 target=0, window=0, percentile=100.00%, depth=32 表明未设定特定延迟目标，滑动窗口关闭，统计百分比为 100%，且 I/O 队列深度为 32。

---

## 15. FIO 工具 READ 带宽与性能指标解读

FIO 输出的 READ 行显示了测试过程中的读取带宽、数据量及耗时。例如，bw=816MiB/s (856MB/s) 表示平均读取带宽为 816MiB/s，io=179GiB (192GB) 表示累计读取数据量为 179GiB，run=224864-224864msec 表示测试运行时间为 224864 毫秒。

---

## 16. FIO 工具 WRITE 带宽与性能指标解读

FIO 输出的 WRITE 行记录了写入操作的性能数据。参数 bw=350MiB/s (367MB/s) 代表平均写入带宽为 350MiB/s，io=76.8GiB (82.5GB) 代表累计写入数据量为 76.8GiB，run=224864-224864msec 代表写入测试持续时间为 224864 毫秒。

---

## 17. Windows PC SMB 协议重定向读写操作

Windows PC 环境下通过 SMB 协议进行文件共享时，读写操作会被重定向。相关测试图表展示了在此类网络配置下的 I/O 性能表现及数据流向。

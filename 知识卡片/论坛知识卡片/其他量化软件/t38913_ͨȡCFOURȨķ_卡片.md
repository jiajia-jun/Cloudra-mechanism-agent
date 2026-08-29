---
key: t38913
title: ͨ�������ȡCFOUR��Ȩ�ķ���
url: http://bbs.keinsci.com/thread-38913-1-1.html
domain: 其他量化软件
source: keinsci
year: 2023
cards: 9
---

# ͨ�������ȡCFOUR��Ȩ�ķ��� — 知识卡片

## 1. CFOUR 软件许可协议签署方式

CFOUR 软件下载需要签署版权文件 license agreement。传统的签署方式是通过传真将文件发送至 +49 6131 3923895，但该方式目前较为繁琐。

---

## 2. CFOUR 许可文件电子签署流程

获取空白许可文件的链接为 https://cfour.uni-mainz.de/cfour/index.php?n=Main.MainLicense?action=print。操作流程为下载空白文件、打印签名、扫描为 PDF，然后通过电子邮件发送给管理员。

---

## 3. CFOUR 许可费用与审核周期

许可文件处理费约为 48 欧元（约合人民币 400 元），提供发票。审核周期案例显示：2023 年 7 月 12 日收到邮件，2023 年 7 月 19 日收到账号，历时约一周。

---

## 4. CFOUR 安装参考资源

CFOUR 官方下载地址为 https://cfour.uni-mainz.de/cfour/index.php?n=Main.Download。中文安装教程可参考 原作者.com/150 或相关论坛帖。

---

## 5. CFOUR 编译环境依赖

安装新版 CFOUR 需要准备 icpc 和 c++ 编译器，以及英特尔新版 MKL 库（需包含 libmkl_solver_ilp64.a 文件）。

---

## 6. CFOUR 编译参数配置

安装参数需与编译器版本匹配，使用 mpich2 时，应将 ./configure FC=ifort 替换为 ./configure FC=ifort CC=icc CXX=icpc。

---

## 7. CFOUR 配置命令示例

完整的 CFOUR 配置命令示例为：FC=ifort CC=icc CXX=icpc MPIFC=mpif90 ./configure --with-blas="$MKLPATH/libmkl_intel_ilp64.a -Wl,--start-group $MKLPATH/libmkl_intel_ilp64.a $MKLPATH/libmkl_intel_thread.a $MKLPATH/libmkl_core.a -Wl,--end-group -qopenmp -lpthread" --enable-mpi=mpich --with-mpirun="mpirun -np \$CFOUR_NUM_CORES" --with-exenodes="mpirun -np \$CFOUR_NUM_CORES" --prefix=/home/nxu/softwares/cfour_mpi。

---

## 8. CFOUR 与 Gaussian 计算效率对比

对于高对称性体系，CFOUR 运行 CCSD(T) 的效率比 Gaussian 高 2 至 3 倍，且内存控制表现较好。对于无对称性体系，CFOUR 可能比 Gaussian 09 慢，且在处理长链体系时可能存在问题。

---

## 9. CFOUR 集群并行读写注意事项

CFOUR 在集群计算中存在显著的 IO 瓶颈。若未将临时文件目录放置于从节点的本地硬盘，而是使用主节点的共享硬盘，会严重拖慢计算速度。

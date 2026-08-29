---
id: 9
title: mpich2多节点并行运算的设置
url: http://sobereva.com/9
domain: 软件安装与环境
topic: MPICH2多节点并行环境配置与SSH互信
cards: 19
---

# MPICH2多节点并行环境配置与SSH互信 — 知识卡片

## 1. 设置Intel Fortran编译器环境变量

如果Fortran编译器安装了ifort，在编译前需要设置FC环境变量指向ifort的可执行文件路径。运行命令`export FC=/opt/intel/fce/10.0.023/bin/ifort`以确保编译过程使用Intel编译器。

---

## 2. MPICH2源码编译与安装步骤

将mpich2-1.0.6.tar.gz复制到/sob目录并解压，进入解压后的目录运行配置和编译命令。依次执行`./configure`、`make`和`make install`来完成MPICH2的安装。

---

## 3. 配置MPD守护进程配置文件

运行`touch /etc/mpd.conf`创建配置文件并设置权限为700，随后在文件中添加密码短语。修改`chmod 700 /etc/mpd.conf`，并在mpd.conf中加入内容`secretword=<secretword>`（例如secretword=ltwd）。

---

## 4. 配置/etc/hosts文件实现主机名解析

修改/etc/hosts文件，将IP地址与主机名对应，以便在Linux中使用主机名代替IP地址。文件内容应设置为`192.168.0.2 vmware1`和`192.168.0.3 vmware2`。

---

## 5. 配置mpd.hosts文件指定计算节点

修改/root/mpd.hosts文件，列出参与并行计算的所有主机名。该文件内容应包含`vmware1`和`vmware2`。

---

## 6. 在节点1上配置SSH免密登录

在vmware1节点上运行`ssh-keygen -t rsa`并全程按回车使用默认设置生成RSA密钥。将公钥复制为授权密钥，执行`cd /root/.ssh`和`cp id_rsa.pub authorized_keys`，最后运行`ssh vmware1`并输入yes建立本机信任连接。

---

## 7. 在节点2上同步SSH密钥

在vmware2节点上运行`ssh-keygen -t rsa`并使用默认设置，将vmware1中/root/.ssh/目录下的所有文件复制覆盖到vmware2的/root/.ssh/目录。执行`chmod 700 /root/.ssh/*`设置文件权限，并运行`ssh vmware1`输入yes完成信任。

---

## 8. 验证SSH免密登录配置

无论在vmware1还是vmware2上，执行`ssh vmware1`或`ssh vmware2`都应能不输入密码直接登录。运行命令`ssh vmware1 date`，如果显示日期则说明SSH配置无误。

---

## 9. 启动MPD守护进程

在任意一台电脑上输入`mpdboot -n 2`在两台电脑上同时启动mpd，其中-n 2代表启动2台主机上的mpd。若提示无法打开mpd.hosts，需使用`mpd.hosts -n 2 -f /root/mpd.hosts`指定文件位置并启动。

---

## 10. 检查并行计算节点状态

运行`mpdtrace`命令查看当前有哪些电脑可以参与并行运算。执行后应当显示`vmware1`和`vmware2`，表明节点已正确加入并行环境。

---

## 11. 使用mpirun运行并行程序

假设两台电脑均为双核，运行`mpirun -np 4 sander.MPI xxxxxxxxxx`可在两台电脑上同时调用总共4个核心运行sander。使用mpirun运行的并行程序必须存在于两台电脑的相同位置上。

---

## 12. 退出MPD守护进程

若要退出mpd，在命令行输入`mpdallexit`即可关闭所有节点上的MPD守护进程。

---

## 13. 多节点并行运算配置注意事项

两台电脑的mpich2安装位置最好保持一致，且/etc/mpd.conf中设置的密码应当相同。这些一致性要求是确保多节点并行运算正常运行的必要条件。

---

## 14. 验证多节点并行运算功能

运行`mpirun -np number /sob/mpich2-1.0.6/examples/cpi`来验证是否可以正常进行多节点并行运算，其中number为使用的核心数。cpi是MPICH2提供的一个测试程序。

---

## 15. 网络硬件对并行效率的影响

多节点并行运算时CPU不能100%满载是正常的，性能受限于网络连接方式。将100M网换到1000M网会有好处，使用InfiniBand、Myrinet等专适于HPC的连接方式效果更佳，建议使用超五类或者六类网线。

---

## 16. 虚拟机环境下的并行运算性能

在VMware Station 6下使用Fedora虚拟机进行双节点并行测试，这种方式可解决旧版本VMware不支持4核的问题。经测试，该方式速度可达实际Fedora中单节点4核速度的82%，实际运算速度等于单核的三倍。

---

## 17. 虚拟机网络模式选择

在VMware6中测试虚拟机的网络应使用vmnet1（host-only）方式，这样虚拟机之间以及主机之间可以互相访问并共享上网。此方式下网卡虚拟为82545EM千兆网卡，双虚拟机互连速度足够。

---

## 18. 虚拟机数据吞吐量监控误区

在系统监视器中双虚拟机并行跑Amber的数据吞吐量往往显示只有十几兆，这是因为数据传输是瞬间进行的，持续几秒不传输。若将监控速度间隔调成0.25s，会发现峰值远高于100M网限制，1秒一次的检测会取平均值导致误判。

---

## 19. VMware Team模式对并行运算的作用

在VMware6中可以将多个虚拟机建立一个Team，Team内虚拟机间可建立高速网络连接，但测试显示相对于vmnet1方式速度没有提升。Team方式开机关机必须同时进行，不够灵活，对跑amber9没有太大作用。

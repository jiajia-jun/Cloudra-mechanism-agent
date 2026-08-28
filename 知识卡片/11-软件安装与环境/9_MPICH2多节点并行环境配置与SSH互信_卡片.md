---
id: 9
title: mpich2多节点并行运算的设置
url: http://sobereva.com/9
domain: 软件安装与环境
topic: MPICH2多节点并行环境配置与SSH互信
cards: 1
---

# MPICH2多节点并行环境配置与SSH互信 — 知识卡片

## 1. mpich2多节点并行运算设置概述

在单节点mpich2并行设置基础上，建立多节点并行运算是计算化学工作者的必备能力。本文以root用户和fedora7系统为例，详细讲解通用的多节点设置方法，假设使用名为vmware1和vmware2的两台电脑，IP分别为192.168.0.2和192.168.0.3。

## 安装mpich2的步骤
首先设置Fortran编译器环境变量，如若使用ifort则运行export FC=/opt/intel/fce/10.0.023/bin/ifort。将mpich2-1.0.6.tar.gz复制到/sob并解压，进入目录后依次运行./configure、make、make install完成编译安装。

## 配置mpd.conf文件
运行touch /etc/mpd.conf创建配置文件，并执行chmod 700 /etc/mpd.conf设置权限。在mpd.conf文件中添加内容secretword=<secretword>，例如设置secretword=ltwd。

## 配置/etc/hosts文件
修改/etc/hosts文件内容，将主机名与IP对应，内容改为192.168.0.2 vmware1和192.168.0.3 vmware2。这样在Linux系统中就可以直接使用主机名称来代替IP地址。

## 配置mpd.hosts文件
修改/root/mpd.hosts文件，将内容改为vmware1和vmware2，列出参与并行运算的节点名称。此文件用于指定多节点并行运算涉及的计算机列表。

## 节点间SSH免密互通设置方法
为实现MPICH2在两台电脑间传输数据，必须配置SSH免密登录。在vmware1中运行ssh-keygen -t rsa并使用默认设置生成密钥，进入/root/.ssh目录，执行cp id_rsa.pub authorized_keys，最后运行ssh vmware1并回答yes建立本机信任连接。

## 节点间SSH免密互通同步操作
在vmware2中运行ssh-keygen -t rsa使用默认设置。将vmware1中的/root/.ssh/*文件全部复制覆盖到vmware2的/root/.ssh/目录中，并运行chmod 700 /root/.ssh/*将文件设为root专用。在vmware2上运行ssh vmware1并回答yes。

## SSH免密登录验证
测试SSH连接时，无论在vmware1还是vmware2，执行ssh vmware1或ssh vmware2都应能直接登录无需输入密码。可以使用命令ssh vmware1 date进行验证，如果显示了日期则说明配置无误。

## 启动mpd守护进程
在任意一台电脑中输入mpdboot -n 2，即可在两台电脑上同时启动mpd守护进程，其中-n 2代表启动2台机器上的mpd。若提示无法打开mpd.hosts但文件确实存在于root下，应使用mpd.hosts -n 2 -f /root/mpd.hosts指定文件位置并启动。

## 检查并行运算节点
运行mpdtrace命令可以察看当前有哪些电脑可以参与并行运算。配置正确后，命令输出应当显示vmware1和vmware2，表明这两个节点已准备就绪。

## 执行并行计算程序
假设两台电脑均为双核，运行mpirun -np 4 sander.MPI xxxxxxxxxx即可在两台电脑上同时运行sander程序，自动调用总共4个核心。注意使用mpirun运行的并行程序必须存在于两台电脑的相同路径位置上。

## 退出mpd守护进程
如果需要退出mpd，输入mpdallexit命令即可关闭所有节点上的mpd守护进程。

## 多节点并行运算注意事项
两台电脑的mpich2安装位置最好保持一致，且/etc/mpd.conf中设置的密码secretword应当相同，以确保多节点并行通信正常。

## 验证多节点并行运算
运行mpirun -np number /sob/mpich2-1.0.6/examples/cpi可以验证多节点并行运算是否正常，其中number为使用的核心数。cpi是一个内置的测试程序。

## 网络连接对并行效率的影响
在多节点并行运算中，CPU无法100%满载是正常的，这在一定程度上受限于网络连接方式。将100M网络升级到1000M网络会有所改善，若使用InfiniBand或Myrinet等专适于HPC的连接方式效果更好，但以太网因成本低更为常用。

## VMware虚拟机多节点并行测试环境
以上内容在VMware Station 6、XP SP2、Q6600环境下建立两台双核虚拟机测试通过。VMware6中Fedora系统网卡虚拟为82545EM千兆网卡，双虚拟机互连速度足够，这种方式可解决VMware版本不支持4核的问题。

## 虚拟机并行运算的效率表现
经测试，双虚拟机双节点并行方式可以达到实际Fedora中单节点4核速度的82%，实际运算速度等于单核的三倍。测试中虚拟机网络采用vmnet1即host-only方式，便于虚拟机之间、主机之间互相访问及共享上网。

## 虚拟机网络数据吞吐量监控
在双虚拟机中运行Amber并行任务，系统监视器显示的数据吞吐量往往最高才十几兆，容易让人误以为虚拟的是100M网。若将监控速度间隔调成0.25s，会发现峰值数据吞吐速度远高于100M网限制，因为数据传输是瞬间完成随后静默几秒，1秒一次的检测取平均值会造成误解。

## VMware Team模式对并行运算的影响
在VMware6中可将多个虚拟机建立一个Team，Team内虚拟机之间及与外界封闭，并可建立无速度上限的高速网络连接。经测试，这种Team方式相对于vmnet1连接方式速度没有丝毫提升，且开机关机必须同时进行缺乏灵活性，对跑amber9作用不大。

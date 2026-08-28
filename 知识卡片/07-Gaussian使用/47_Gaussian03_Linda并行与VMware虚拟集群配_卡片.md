---
id: 47
title: Gaussian03的Linda并行设置与VMware的虚拟集群
url: http://sobereva.com/47
domain: Gaussian使用
topic: Gaussian03_Linda并行与VMware虚拟集群配
cards: 17
---

# Gaussian03_Linda并行与VMware虚拟集群配 — 知识卡片

## 1. Gaussian03 Linda并行环境配置准备

本文使用Gaussian03 C.02版本，压缩包自带Linda程序7.1版，无需另行下载。压缩包内linda-exe子目录包含了已编译好的.exel后缀的专用于Linda并行的高斯子程序。跨节点运算必须使用ACSI的Linda软件，Linda提供了虚拟共享内存(VSM)环境将集群主机结合为全局逻辑共享内存，使基于OpenMP并行的Gaussian能在集群环境中运行。
- 压缩包下载地址：http://pan.baidu.com/s/1qWyKTmG

---

## 2. VMware虚拟机Host-only网络配置

使用VMware的Host-only模式组建虚拟集群，实际主机、虚拟机f71、虚拟机f72组成内部局域网。在Edit-Virtual Network Editor中查看Host-only（如VMnet1）的子网（如192.168.153.0），将虚拟机IP设为该子网地址（如192.168.153.3和192.168.153.4），子网掩码为255.255.255.0，并设置对应的主机名（f71、f72）。虚拟机网络连接需设为Use host-only networking，并关闭防火墙和selinux。

---

## 3. 虚拟机克隆与网络去重

在VMware中新建配置好的虚拟机f71后，使用full clone方式克隆出f72。为避免MAC地址冲突，启动f72时先断开网络，在网络配置界面删除原有网卡并添加新网卡，设置好静态IP和主机名后重启。f71也需配置静态IP和主机名。完成配置后，主机和两台虚拟机之间应能互相ping通。

---

## 4. 虚拟机系统基础配置与工具安装

在虚拟机中安装Fedora7-64bit系统时，需选择安装Software Development大类。安装完成后，需安装VMware Tools：解压VMwareTools-6.0.1-55017.tar.gz并运行vmware-install.pl，按回车完成默认设置。这支持主机与虚拟机间的文件拖放、文本复制及目录共享。建议对配置好的虚拟机使用take snapshot制作镜像以便恢复。

---

## 5. 节点hosts文件配置

f71和f72两个节点都需要修改/etc/hosts文件，删除默认内容，添加IP地址与主机名的对应关系。配置内容应统一为：192.168.153.3 f71和192.168.153.4 f72。修改完成后需要重启系统。

---

## 6. Gaussian03程序部署与环境变量

在f71和f72上将高斯压缩包解压到/sob/g03，并建立/sob/g03/scratch目录作为临时文件目录。在/root/.bashrc中添加环境变量：export g03root=/sob、source /sob/g03/bsd/g03.profile、export GAUSS_SCRDIR=/sob/g03/scratch、export GAUSS_LFLAGS='-vv -nodelist "f71 f72"'。GAUSS_LFLAGS中的-nodelist指定并行运算节点，-vv开启详细输出。

---

## 7. Gaussian03 Linda路径与权限修改

在/sob/g03、/sob/g03/bsd、/sob/g03/linda-exe、/sob/g03/linda7.1/intel-linux2.4-rh8/bin文件夹下执行chmod 700 *设定权限。需修改/sob/g03/ntsnet文件和/sob/g03/linda7.1/intel-linux2.4-rh8/bin/LindaLauncher文件中的路径，将/haydn/s0/scratch/frisch/g03/linda7.1/intel-linux2.4-rh8/替换为实际路径/sob/g03/linda7.1/intel-linux2.4-rh8/。

---

## 8. Linda配置文件tsnet.config修改

Linda默认跨节点连接方式为rsh，本文使用ssh。需修改默认全局配置文件/sob/g03/linda7.1/common/lib/tsnet.config，将Tsnet.Node.lindarsharg参数后的rsh改为ssh。其他参数保持不变，Linda参数详细含义可参考http://www.lindaspaces.com/downloads/lindamanual.pdf第三章。

---

## 9. 节点间SSH免密登录配置

配置f71与f72之间的SSH免密登录。在f71和f72上均运行ssh-keygen -t rsa并按回车使用默认设置生成密钥。在f71上执行cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys。将f71中/root/.ssh/下全部文件复制覆盖到f72的/root/.ssh/目录。在f72上执行chmod 700 /root/.ssh/*，并分别在f71运行ssh f72、f72运行ssh f71，回答yes建立信任。

---

## 10. SSH免密登录验证与Linda调用测试

测试SSH配置是否成功：在f71输入ssh f72 date，在f72输入ssh f71 date。如果都不需要密码并显示日期，说明无密码SSH设置成功，Linda即可调用ssh在远程节点上直接执行指令。若必须使用rsh，则需按附录2设置rsh、rcp、rlogin无需密码连接，且不必修改tsnet.config。

---

## 11. Gaussian03 Linda并行任务启动方式

Gaussian03 Linda并行输入文件中使用%NprocLinda=n和%Nprocshared=m，代表使用n个节点，每个节点使用m个核心，总计n*m个核心。运行时将单机命令g03替换为g03l，例如：g03l < ltwd.gjf |tee a.out。若在其它节点上看到高斯并行子程序启动且有较高CPU占用率，说明配置成功。

---

## 12. Gaussian03中FMM方法对Linda并行的限制

Gaussian03中绝大部分支持单机SMP并行的功能也支持Linda并行，但FMM(Fast Multipole method)除外。FMM用于加快电子积分计算，在无对称性体系原子数大于等于60时自动开启。FMM不支持Linda并行，开启后其它节点虽有L502启动但无CPU占用。在Gaussian03中需用NoFMM关键字关闭它以发挥Linda加速作用；Gaussian09 B01及以后版本Linda已支持FMM。

---

## 13. NFS共享Gaussian程序配置方法

如果不希望每个节点都存储一份程序，可使用NFS共享。在f71上开启NFS和rpcbind服务，在/etc/exports添加/sob/g03 192.168.153.4(rw,no_root_squash)并重启NFS服务。在f72上建立/sob/g03文件夹，执行mount f71:/sob/g03 /sob/g03挂载目录。可将挂载命令加入f72的/etc/profile实现开机自动挂载。NFS共享对计算速度无明显影响。

---

## 14. Fedora7下开启无需密码rsh服务

下载并安装xinetd-2.3.14-12.fc7.x86_64.rpm和rsh-server-0.17-44.fc8.x86_64.rpm。运行setup命令开启rsh、rlogin、rexec服务。在/etc/securetty末尾添加rsh、rlogin、rexec三行。在/root下创建.rhosts文件，添加192.168.153.4 root和192.168.153.3 root。重启xinetd服务后，运行netstat -an |grep 514应显示listen。此时rsh、rcp、rlogin应可无需密码使用。

---

## 15. VMware虚拟集群并行效率测试数据

测试使用HF/Aug-cc-PV5Z计算CH4单点，%mem=300MB。f71+f72虚拟集群Linda并行(%NprocLinda=2, %Nprocshared=2)耗时181.486s，f71+f72(%NprocLinda=2, %Nprocshared=1)耗时434.970s，单虚拟机f71双核SMP(%Nproc=2)耗时316.976s，实际主机双核SMP(%Nproc=2)耗时401.394s，实际主机四核SMP(%Nproc=4)耗时169.368s。

---

## 16. 虚拟机集群并行效率结论与优势

测试显示两台双核虚拟机Linda并行(181s)比实际操作系统四核SMP(169s)稍慢但差距不大，比单虚拟机双核快近一倍(181s vs 316s)。跨节点双核(434s)比单节点双核(316s)慢。虚拟机运行计算化学程序通常比实际运行慢10%左右。VMware虚拟机便于中断计算、迁移、恢复系统状态及在Windows下运行Linux计算。

---

## 17. Gaussian09 Linda节点指定方式变更

针对Gaussian09的补充说明：G09中不建议依靠GAUSS_LFLAGS指定节点列表，也不建议用%NProcLinda指定节点数。应直接在输入文件中使用%LindaWorkers=f71,f72,f73...来指定参与计算的节点名称。GAUSS_LFLAGS不再用于定义节点列表，但可用于控制输出冗余度，如export GAUSS_LFLAGS='-vv'。

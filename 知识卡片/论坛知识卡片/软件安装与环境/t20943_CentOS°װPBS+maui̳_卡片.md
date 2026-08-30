---
key: t20943
title: CentOS�°�װPBS+maui�̳�
url: http://bbs.keinsci.com/thread-20943-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2020
cards: 20
---

# CentOS�°�װPBS+maui�̳� — 知识卡片

## 1. 修改主机名与 hosts 文件

为便于管理计算集群，需修改每个节点的主机名及 hosts 文件。执行命令 `sudo vi /etc/hostname` 修改主机名，执行 `sudo vi /etc/hosts` 填入对应 IP 地址和主机名。需参照 `ifconfig` 中的信息填写对应的 IP 地址，并添加所有计算节点的 IP 及对应主机名。
- sudo vi /etc/hostname
- sudo vi /etc/hosts

---

## 2. 检查并安装 OpenSSH

配置 SSH 免密登录前，需确保每个节点均安装了 openssh。若节点未安装 SSH，需执行安装命令 `sudo apt-get install ssh`。每个节点均需进行此项检查与安装操作。
- sudo apt-get install ssh

---

## 3. 生成 SSH 公钥与私钥

每个节点需分别执行 `ssh-keygen -t rsa` 生成公钥和私钥。执行命令后连续按 3 次回车键即可，`-t` 参数指定使用的加密协议类型（如 rsa 或 dsa）。生成的公钥文件位于 `~/.ssh/id_rsa.pub`，私钥文件位于 `~/.ssh/id_rsa`。
- ssh-keygen -t rsa

---

## 4. 节点本地公钥授权配置

每个节点需将本节点的公钥追加到授权文件中。执行 `cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys` 追加公钥，并执行 `chmod 700 ~/.ssh/authorized_keys` 修改权限。此步骤在每台机器上独立执行。
- cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
- chmod 700 ~/.ssh/authorized_keys

---

## 5. 合并各节点公钥实现免密登录

需将各节点的公钥合并，使任意节点间可免密登录。以 192.168.0.192 节点为例，执行相关命令获取并分发其他节点的公钥，最后使用 `scp` 将合并后的 authorized_keys 文件分发回各节点。执行 `cat ~/.ssh/authorized_keys` 查看文件内容，确认已包含 3 个节点的公钥（共 3 行）。
- ssh 192.168.0.193 cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
- ssh 192.168.0.191 cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
- scp ~/.ssh/authorized_keys 192.168.0.193:~/.ssh/authorized_keys
- scp ~/.ssh/authorized_keys 192.168.0.191:~/.ssh/authorized_keys

---

## 6. 安装 Torque 前的依赖库安装

在 Master 节点安装 Torque 之前，需先安装必要的依赖库文件。使用 `yum` 安装 libxml2-devel, openssl-devel, gcc, gcc-c++, boost-devel, libtool 等软件包。
- sudo yum install libxml2-devel openssl-devel gcc gcc-c++ boost-devel libtool

---

## 7. Torque 源码解压与配置

下载并解压 Torque 安装包（如 torque-6.1.2.tar.gz），执行 `./configure` 配置安装路径及服务器信息。配置参数包括前缀路径 `/usr/local/torque`、支持 scp 协议及默认服务器名称 master。若编译过程中出现警告或错误，可在 make 命令中添加 `-w -fpermissive` 标志。
- tar -zxvf torque-6.1.2.tar.gz
- ./configure --prefix=/usr/local/torque --with-scp --with-default-server=master
- sudo make
- sudo make install
- sudo make packages

---

## 8. Torque 服务脚本配置

将 Torque 的服务启动脚本复制到系统启动目录下。执行 `cp` 命令复制 pbs_server, pbs_sched, pbs_mom, trqauthd 脚本，并使用 `chkconfig` 将这些服务添加到系统服务中并设置开机自启。
- sudo cp contrib/init.d/{pbs_{server,sched,mom},trqauthd} /etc/init.d/
- for i in pbs_server pbs_sched pbs_mom trqauthd; do sudo chkconfig --add $i; sudo chkconfig $i on;done

---

## 9. 配置 Torque 环境变量

编辑 `/etc/profile` 文件，添加 Torque 和 Maui 的 bin、sbin 路径及库文件路径（LD_LIBRARY_PATH）。修改完毕后执行 `source /etc/profile` 使环境变量生效。同时编辑 `/etc/ld.so.conf` 包含 `/usr/local/lib`，并执行 `ldconfig` 更新动态链接库缓存。
- export PATH=/usr/local/torque/bin:$PATH
- export PATH=/usr/local/torque/sbin:$PATH
- export LD_LIBRARY_PATH=/usr/local/torque/lib:$LD_LIBRARY_PATH
- export PATH=/usr/local/maui/bin:$PATH
- export PATH=/usr/local/maui/sbin:$PATH
- export LD_LIBRARY_PATH=/usr/local/maui/lib:$LD_LIBRARY_PATH
- sudo /sbin/ldconfig /etc/ld.so.conf

---

## 10. 初始化 Torque 服务与账号

切换到 Torque 源码目录，执行 `torque.setup` 初始化 Torque 管理账号（示例为 yjy）。随后执行 `qterm` 停止服务，再启动所有 Torque 相关服务。
- ./torque.setup yjy
- qterm
- for i in pbs_server pbs_sched pbs_mom trqauthd; do sudo service $i start;done

---

## 11. 配置计算节点信息

编辑 `/var/spool/torque/server_priv/nodes` 文件，填入主控节点及各计算节点的名称与 CPU 核数。示例中 master 和 slave01 均配置了 20 个核（np=20）。
- sudo vi /var/spool/torque/server_priv/nodes
- master np=20
- slave01 np=20

---

## 12. 配置 MOM 服务与日志

编辑 `/var/spool/torque/mom_priv/config` 文件，设置 pbs_server 指向 master 主机名，并设置日志事件级别为 255。配置完成后需重启所有 Torque 服务。
- sudo vi /var/spool/torque/mom_priv/config
- $pbsserver master
- $logevent 255
- for i in pbs_server pbs_sched pbs_mom trqauthd; do sudo service $i restart;done

---

## 13. Torque 任务队列测试与配置

执行 `echo sleep 7 | qsub` 提交测试作业，使用 `qstat -a -n` 查看作业状态。使用 `qmgr` 命令创建默认执行队列（如 AMD），并设置队列类型、状态及默认资源。最后将该队列设置为服务器默认队列。
- echo sleep 7 | qsub
- qstat -a -n
- qmgr -c 'create queue AMD'
- qmgr -c 'set queue AMD queue_type = execution'
- qmgr -c 'set queue AMD started = true'
- qmgr -c 'set queue AMD enabled = true'
- qmgr -c 'set queue AMD resources_default.nodes = 1'
- qmgr -c 'set server default_queue = AMD'

---

## 14. 计算节点安装 Torque 客户端与 MOM

从 Master 节点将 torque-package 安装包及服务脚本复制到计算节点（如 slave01）。在计算节点上执行安装脚本安装 clients 和 mom 组件。
- scp torque-package-{mom,clients}-linux-x86_64.sh slave01:torque6
- scp contrib/init.d/{pbs_mom,trqauthd} slave01:/etc/init.d/
- ./torque-package-clients-linux-x86_64.sh --install
- ./torque-package-mom-linux-x86_64.sh --install

---

## 15. 计算节点 MOM 配置与服务启动

在计算节点编辑 `/var/spool/torque/mom_priv/config` 文件，指定服务器为 master 并配置日志。将 pbs_mom 和 trqauthd 设置为系统服务并启动。需注意提交作业时，计算节点与主控节点的用户名及 UID/GID 需完全一致。
- $pbsserver master
- $logevent 255
- for i in pbs_mom trqauthd; do sudo chkconfig --add $i; sudo chkconfig $i on;done
- for i in pbs_mom trqauthd; do sudo service $i start;done

---

## 16. 修改计算节点堆栈大小限制

为防止计算中出现堆栈溢出问题，需修改计算节点的堆栈大小限制为 unlimited。通过 `sed` 命令修改 `/etc/rc.d/init.d/pbs_mom` 和 `/usr/lib/systemd/system/pbs_mom.service` 文件。
- sudo sed -i '/END INIT INFO/s//&\nulimit -s unlimited/' /etc/rc.d/init.d/pbs_mom
- sudo sed -i '/LimitSTACK/s/=.*/=infinity/' /usr/lib/systemd/system/pbs_mom.service

---

## 17. 编译安装 Maui 调度器

在 Master 节点解压 Maui 源码，使用提供的脚本进行编译安装。配置前缀为 `/usr/local/maui` 并指定 PBS 路径。修改 Makefile 中的链接库参数，安装后配置服务脚本及动态链接库路径。最后关闭系统自带的 pbs_sched 服务。
- ./configure --prefix=/usr/local/maui --with-pbs=/usr/local/torque
- sed -i '/PBSLDFLAGS/s#= .*-ltorque.*#= -L/usr/local/torque/lib -ltorque#' Makefile
- make -j4
- make install
- chkconfig pbs_sched off

---

## 18. 快速进入作业目录的脚本配置

为方便快速进入作业提交目录，可在 `~/.bashrc` 中定义 `cdjob` 函数。该函数通过 `qstat` 获取作业信息，解析 `PBS_O_WORKDIR` 并切换到对应作业的工作目录。使用方法为输入 `cdjob` 加上作业 ID。
- function cdjob(){ ... }
- cdjob [jobid]

---

## 19. 配置 CPU 与 GPU 分区队列示例

通过 `qmgr` 命令可针对不同硬件特性（如 CPU 或 GPU）创建独立的队列。设置 `resources_default.neednodes` 属性指定队列所需的节点类型，并设置队列为执行状态（Execution）。最后可创建一个包含所有节点的通用队列（all）并设为默认。
- qmgr -c 'creat queue CPU'
- qmgr -c 'set queue CPU resources_default.neednodes = CPU'
- qmgr -c 'creat queue GPU'
- qmgr -c 'set queue GPU resources_default.neednodes = GPU'
- qmgr -c 'creat queue all'
- qmgr -c 'set server default_queue = all'

---

## 20. 卸载 Torque 与 Maui

若需重新安装或彻底删除 Torque 和 Maui，需先停止所有相关服务并关闭开机自启。删除 `/var/spool/torque`、`/usr/local/torque` 和 `/usr/local/maui` 目录以清除所有配置与程序文件。
- for i in pbs_server pbs_sched pbs_mom trqauthd maui.d; do sudo service $i stop;done
- for i in pbs_server pbs_sched pbs_mom trqauthd maui.d; do sudo chkconfig $i off;done
- sudo rm -r /var/spool/torque
- sudo rm -r /usr/local/torque
- sudo rm -r /usr/local/maui

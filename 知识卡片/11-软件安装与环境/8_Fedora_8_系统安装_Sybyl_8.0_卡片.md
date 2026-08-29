---
id: 8
title: Fedora 8安装sybyl 8.0
domain: 软件安装与环境
topic: Fedora_8_系统安装_Sybyl_8.0
cards: 15
---

## 1. 安装Sybyl 8.0所需的ISO文件与下载来源
Sybyl 8.0安装需要下载CD1和DVD1两个镜像文件，crack文件包含在DVD1中无需单独下载。下载链接为。

---

## 2. 挂载ISO镜像的命令与目录设置
使用mount命令将ISO镜像挂载到指定目录，需先创建/mnt/iso和/mnt/iso2目录。挂载命令为`mount -o loop /sob/SYBYL80DVD1.iso /mnt/iso`和`mount -o loop /sob/SYBYL80_TBS.iso /mnt/iso2`。

---

## 3. 安装前的KornShell环境准备
Sybyl 8.0安装需要使用ksh环境，通过yum安装ksh并进入ksh shell。操作命令为`yum install ksh`，随后输入`ksh`进入环境。

---

## 4. Sybyl 8.0主程序安装步骤与参数配置
进入/mnt/iso目录执行`./install.sh`，全选no，浏览器设置为/usr/bin/firefox，安装目录设为/sob/sybyl8.0。中途换盘时分别输入/mnt/iso2和/mnt/iso，全安装好后退出以避免循环安装。

---

## 5. License文件的配置与存放路径
将/mnt/iso/crack/license.dat拷贝到/usr/local/flexlm/licenses目录下，同时拷贝到/sob/AdminTools10.8/tables目录下并改名为license_file。

---

## 6. /etc/hosts文件的必要配置
检查/etc/hosts文件，必须包含`127.0.0.1 localhost`这句话，如果没有则需手动添上。

---

## 7. PATH环境变量配置
编辑/root/.bashrc文件，添加路径`PATH=$PATH:/sob/trigo:/sob/AdminTools10.8/bin/linux`。保存后在终端输入bash使环境变量生效。

---

## 8. 启动Sybyl 8.0图形界面的命令
先运行`lmgrd triposlm`，再运行`sybyl8.0`，即可进入Sybyl程序的图形界面。

---

## 9. 安装DVD2的空间要求与环境变量
安装DVD2需要确保硬盘有10G空间，挂载后需设置环境变量`export TA_ROOT=/sob/sybyl8.0`。说明书原本提到使用trigo -shell sybyl8.0命令。

---

## 10. DVD2安装时的文件属性检查
检查/sob/sybyl8.0/tables/linux/.tapedate文件的owner属性，应确保为当前用户（如root）。若不是，使用`chown root -R /sob/sybyl8.0`进行修改。

---

## 11. DVD2的安装过程与特征
DVD2挂载后进入目录执行`source./install.sh`，安装过程不需要ksh环境。安装时间极长，完成后会产生42.7万个文件。

---

## 12. 系统时间的限制条件
系统时间设置不能太早也不宜太后，经验验证2008年8月14日这个时间点没有问题。

---

## 13. 挂载目录错误导致的安装中断提示
如果将ISO挂载到/mnt/cdrom目录并运行install.sh，可能会提示"You should not start the installer from the cdrom directory."。解决方法是挂载到别的位置，或者将文件拷贝到硬盘上安装。

---

## 14. os.py错误的解决方法
如果在点击install按钮后终端出现关于os.py的错误导致安装终止，应当使用ksh。通过`yum install ksh`安装并进入ksh后重新安装即可解决。

---

## 15. TCP端口打开失败的排查
如果运行lmgrd triposlm提示"Failed to open the TCP port number in the license"，需检查/etc/hosts文件中是否包含`127.0.0.1 localhost`，没有则加上。

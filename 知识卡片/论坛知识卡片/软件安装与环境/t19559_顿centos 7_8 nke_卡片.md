---
key: t19559
title: �����顿centos 7/8 ����nkernel���Լ�����֮����װNvidia������cuda 11          ..
url: http://bbs.keinsci.com/thread-19559-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2020
cards: 16
---

# �����顿centos 7/8 ����nkernel���Լ�����֮����װNvidia������cuda 11          .. — 知识卡片

## 1. 查看当前系统内核版本

使用 `uname -r` 命令可以查看当前系统正在使用的内核版本号，这是进行内核升级或验证操作前的必要检查步骤。

---

## 2. 导入 ELRepo 公钥

在安装 ELRepo 源之前，必须使用 `sudo rpm --import https://www.elrepo.org/RPM-GPG-KEY-elrepo.org` 命令导入该仓库的 GPG 公钥以确保软件包安全性。

---

## 3. 安装 ELRepo 源

针对 CentOS 7 系统，使用 `sudo yum install https://www.elrepo.org/elrepo-release-7.el7.elrepo.noarch.rpm` 安装；针对 CentOS 8 系统，使用 `sudo yum install https://www.elrepo.org/elrepo-release-8.el8.elrepo.noarch.rpm` 安装。

---

## 4. 安装主线内核

使用 `sudo yum --enablerepo=elrepo-kernel install kernel-ml` 命令可以从 ELRepo 仓库安装最新的主线版本内核，安装完成后需执行 `sudo reboot` 重启系统。

---

## 5. 修改默认启动内核

编辑 `/etc/default/grub` 文件，将 `GRUB_DEFAULT` 的值修改为 `0`，这表示系统启动时将默认加载 GRUB 菜单中的第一个内核项（即刚安装的新内核）。

---

## 6. 生成 GRUB 配置文件

修改默认启动项后，必须执行 `sudo grub2-mkconfig -o /boot/grub2/grub.cfg` 命令来重新生成配置文件，使之前的设置生效。

---

## 7. Kernel 更新后的驱动失效现象

更新内核后，执行 `nvidia-smi` 可能会报错提示无法与 NVIDIA 驱动通信，这是因为原有的显卡驱动与新内核版本不匹配。

---

## 8. 安装 DNF 包管理器

在 CentOS 7 上使用 `sudo yum install dnf` 安装 DNF 工具，目的是为了使用其 `--allowerasing` 参数来解决后续安装中的依赖冲突问题。

---

## 9. 安装匹配版本的内核开发包

从 ELRepo 网站下载与当前安装的 kernel-ml 版本号一致的 kernel-ml-devel 和 kernel-ml-header 包，使用 `sudo dnf --allowerasing --enablerepo=elrepo-kernel install kernel-ml*-XXX*` 命令进行安装，其中 XXX 代表具体的版本号。

---

## 10. 安装匹配版本的 GCC

如果安装显卡驱动时报错提示内核构建使用的 GCC 版本与当前系统 GCC 版本不一致，需要安装匹配的 GCC 版本（如 GCC 9）来避免编译失败。

---

## 11. CentOS 7 启用 GCC 9

在 CentOS 7 上，依次执行 `sudo yum install centos-release-scl`、`sudo yum install devtoolset-9` 和 `source scl_source enable devtoolset-9` 命令来安装并启用 GCC 9。

---

## 12. CentOS 8 启用 GCC 9

在 CentOS 8 上，使用 `sudo dnf install gcc-toolset-9` 安装后，执行 `source /opt/rh/gcc-toolset-9/enable` 来启用 GCC 9，可将此命令加入 `~/.bashrc` 以实现永久生效。

---

## 13. 安装 NVIDIA 显卡驱动

执行 `sudo sh NVIDIA-Linux-x86_64-450.66.run` 运行 NVIDIA 驱动安装包，安装过程中若提示内核版本不匹配，需确认当前内核版本与驱动兼容性，安装完成后使用 `nvidia-smi` 验证。

---

## 14. 安装 CUDA 11

运行 `sudo sh cuda_11.0.3_450.51.06_linux.run` 安装 CUDA 11，安装过程中可以取消勾选驱动安装选项以避免覆盖已安装的驱动。

---

## 15. 配置 CUDA 环境变量

将以下三行配置添加到 `~/.bashrc` 文件中：`export CUDA_HOME=/usr/local/cuda`、`export PATH="/usr/local/cuda/bin:$PATH"`、`export LD_LIBRARY_PATH="/usr/local/cuda/lib64:$LD_LIBRARY_PATH"`，随后执行 `source ~/.bashrc` 使环境变量生效。

---

## 16. 验证 CUDA 安装

通过进入 `/usr/local/cuda/samples/1_Utilities/deviceQuery` 目录，依次执行 `make` 和 `./deviceQuery` 编译并运行测试程序，根据输出结果可以验证 CUDA 是否安装成功并能正确识别 GPU。

---
key: t25609
title: ʹ��VMware��Centos����վ��װcp2k���ԣ������������վϵͳ
url: http://bbs.keinsci.com/thread-25609-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 11
---

# ʹ��VMware��Centos����վ��װcp2k���ԣ������������վϵͳ — 知识卡片

## 1. CP2K 在笔记本与超算站上的编译环境差异

CP2K 可在个人笔记本电脑和超算站进行编译。笔记本电脑上的编译过程可作为在超算站进行编译前的验证步骤，确保编译过程无误，避免因编译错误浪费超算站的计算资源或机时。

---

## 2. 虚拟机与系统环境要求

CP2K 的编译环境可建立在 VMware 虚拟机中。实测在配置为 i7-9750H 处理器和 Windows 10 系统的笔记本电脑上，使用 VMware 16 Pro 安装 CentOS 8.3 系统，能够顺利完成 CP2K 的安装与运行。

---

## 3. CentOS 系统版本选择

CP2K 在 CentOS 系统中的安装可参考特定教程。虽然 CentOS 7.6 和 CentOS 8.3 均可用于编译 CP2K，但针对 CP2K 的编译安装，推荐使用 CentOS 8.3 版本，该版本在实际测试中未出现问题。

---

## 4. 超算站系统环境限制

部分超算站仅支持 CentOS 7 系统。对于计划在超算站运行 CP2K 的用户，若超算站系统为 CentOS 7，建议本地调试环境也使用对应的 CentOS 7 版本，以保证环境一致性。

---

## 5. 本地编译与超算站运行的性能差异

CP2K 在超算站运行的计算速度通常优于笔记本电脑。实测数据显示，超算站单节点 32 核的计算速度约为笔记本电脑 6 核速度的 3 倍；若仅使用 32 核中的 6 核，效率也高于笔记本电脑的 6 核，这可能与笔记本 CPU 架构较旧有关。

---

## 6. VMware 版本与线程支持

VMware 16 Pro 在 Windows 和 Linux 系统上均可安装。需要注意的是，VMware 16 Pro 最多仅支持分配 32 个线程，若计算任务需求超过此限制，则需直接使用物理机系统。

---

## 7. CentOS 8.3 安装配置

在 VMware 中安装 CentOS 8.3 时，Base Environment（基础环境）建议选择 Workstation。在软件选择阶段，建议勾选 GNOME Applications、Legacy UNIX Compatibility、Development Tools 和 Scientific Support。

---

## 8. CP2K Toolchain 编译参数

使用 toolchain 编译 CP2K 时，推荐使用的命令参数为 `--with-sirius=no --with-openmpi=install --with-plumed=install --with-elpa=no`。该配置中移除了 elpa 模块，以避免因 elpa 的 bug 导致程序运行时出现计算卡死的现象。

---

## 9. 虚拟机迁移至超算站的方法

将 VMware 虚拟机迁移至超算站需复制虚拟机文件。操作步骤为：将笔记本电脑上 Centos 8.3 的虚拟机文件复制到超算站，随后在超算站的 Linux 系统下使用 VMware 打开该虚拟机文件，即可启动系统。

---

## 10. 迁移后重编译 CP2K 的效果

将虚拟机迁移至超算站后，通过删除 toolchain/install 文件夹并重新运行 `./install_cp2k_toolchain.sh` 等命令进行重编译，生成的 CP2K 程序运行效果优于直接使用笔记本编译的程序。这表明在目标计算平台上进行本地编译有助于提升性能。

---

## 11. Intel MKL 与 GNU 编译器的性能对比

对于 CP2K 和 Quantum ESPRESSO (QE) 等计算化学软件，使用 Intel 编译器（含 Intel MKL）编译的版本在性能上通常优于使用 GNU 编译器编译的版本。在超算站使用 32 核运行 `cp2k.popt` 时，通过 test 测试，Intel 版本展现出显著的性能优势。

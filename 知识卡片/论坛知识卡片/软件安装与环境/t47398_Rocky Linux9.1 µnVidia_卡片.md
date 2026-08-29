---
key: t47398
title: Rocky Linux9.1 �µ�nVidia������װ��CUDAtoolkit��װ�̳�
url: http://bbs.keinsci.com/thread-47398-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 10
---

# Rocky Linux9.1 �µ�nVidia������װ��CUDAtoolkit��װ�̳� — 知识卡片

## 1. GROMACS的GPU加速安装与参考资源

GROMACS是分子动力学模拟中常用的软件，利用GPU加速可显著提升计算速度。安装GPU加速版GROMACS前需先配置好CUDA toolkit。针对显卡和CUDA toolkit的安装，可参考相关教程中的详细步骤与指导。

---

## 2. 禁用nouveau驱动：配置blacklist

修改配置文件`/usr/lib/modprobe.d/dist-blacklist.conf`，需在文件末尾添加配置内容。具体操作包括在文件末尾添加`blacklist nouveau`和`options nouveau modest=0`，并确保之前关于`blacklist nvidiafb`的行被注释掉。此步骤需要root权限。

---

## 3. 禁用nouveau驱动：卸载与验证

执行`rmmod nouveau`命令卸载nouveau模块，随后通过`lsmod | grep nouveau`检查是否还有相关信息。若命令无返回信息，则证明nouveau已成功禁用；若仍有输出，则说明禁用未成功，需检查之前的步骤。

---

## 4. 安装nVidia驱动的顺序与权限

安装顺序应先安装nVidia驱动，再安装CUDA toolkit，以避免安装程序出现无图形界面的问题。通过MobaXterm将驱动文件（如`NVIDIA-Linux-x86_64-555.42.02.run`）传入服务器，在右键菜单“Permission”中勾选“Execute”赋予执行权限。

---

## 5. 执行nVidia驱动安装

在命令行中执行`./NVIDIA-Linux-x86_64-555.42.02.run`进行安装。安装过程中通常只会出现安装向导，按照提示完成安装即可。文件名需根据实际下载的版本进行对应。

---

## 6. CUDA toolkit版本选择与安装

从nVidia官网下载对应版本的CUDA toolkit，注意版本不能超过显卡驱动的版本，建议驱动与工具包使用同一版本。文件（如`cuda-Linux-x86_64-555.42.02.run`）传入服务器后需赋予执行权限并运行。

---

## 7. CUDA toolkit安装选项

运行CUDA安装程序后，在选择安装选项时，X提示若被选中则不选，仅选择“CUDA toolkit”进行安装。这种方式可避免图形界面相关的配置干扰。

---

## 8. 配置CUDA环境变量

编辑`~/.bashrc`文件，添加PATH和LD_LIBRARY_PATH配置。需添加的语句为`export PATH="/usr/local/cuda-12.5/bin:$PATH"`和`export LD_LIBRARY_PATH="/usr/local/cuda-12.5/lib64:$LD_LIBRARY_PATH"`，注意路径中的版本号应根据实际安装版本修改。

---

## 9. 验证CUDA与驱动安装

安装完成后，通过`nvcc -V`命令可查看编译器及CUDA toolkit的版本信息以验证安装成功。`nvidia-smi`命令也可用于查看相关信息。

---

## 10. 启动图形界面服务

若在MobaXterm远程登录时没有图形界面且需要显示，可使用root权限执行`systemctl start gdm.service`。此命令用于启动GNOME Display Manager以调出图形界面。

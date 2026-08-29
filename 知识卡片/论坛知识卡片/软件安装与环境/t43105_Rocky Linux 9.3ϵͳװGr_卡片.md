---
key: t43105
title: Rocky Linux 9.3ϵͳ��װ��Gromacs, Gaussian, xtb, ORCA, SVM�ȳ���װ
url: http://bbs.keinsci.com/thread-43105-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 45
---

# Rocky Linux 9.3ϵͳ��װ��Gromacs, Gaussian, xtb, ORCA, SVM�ȳ���װ — 知识卡片

## 1. Rocky Linux 9.3 系统硬件配置参考

单路16核工作站的硬件配置方案适用于计算化学软件安装与运行。配置包括 AMD Ryzen 9 7950X CPU、技嘉 B650M AORUS Elite AX 主板、RTX 4090 显卡、64GB DDR5 内存、8TB 希捷 IronWolf Pro 硬盘、海韵 FOCUS GX-1000 电源及 Corsair 4000D 机箱。

---

## 2. Rocky Linux 9.3 启动盘制作

使用 Rufus 或 Image Writer 等工具将 Rocky Linux 9.3 镜像写入 U 盘。制作过程耗时约 10 分钟，若遇到内存不足报错，建议参考特定教程或更换工具尝试。

---

## 3. 硬盘数据备份与分区操作

在进行系统安装前需备份硬盘数据并清理旧数据。可使用 Windows 系统 U 盘进入单路16核工作站的 BIOS，通过 Dell Partition 界面操作硬盘分区，例如删除旧系统分区或恢复出厂设置。

---

## 4. 硬盘初始化与系统重装引导

若需彻底重装系统，可使用 DiskGenius V4.9.3 等工具删除硬盘所有分区并重建为空闲分区。完成后关机并拔除 Windows 系统 U 盘，插入 Rocky Linux 9.3 安装 U 盘以启动安装程序。

---

## 5. Rocky Linux 9.3 系统安装选项

在安装界面选择 "Custom Operating System" 进行 Linux 版本自定义安装可缩短安装时间至约 7 分钟。选择 "Server" 或 "Server with GUI" 安装时间较长，约需 10 分钟。

---

## 6. 系统基础更新与内核检查

系统安装完成后需执行 `yum -y update` 进行更新。使用命令 `rpm -qa | grep kernel` 查看当前系统内核版本，若存在多个内核版本，在安装 NVIDIA 驱动前需删除旧内核以避免冲突。

---

## 7. 旧版本内核卸载命令

针对 Rocky Linux 9.3 系统，需使用 `yum remove` 命令逐个卸载指定的旧内核及其相关组件。需卸载的包包括 kernel-devel、kernel-core、kernel-modules 和 kernel，版本号需根据实际情况确认。

---

## 8. 系统邮件通知配置

安装 s-nail 软件包并编辑 `/etc/s-nail.rc` 文件可配置邮件发送功能。配置内容包括设置 v15-compat、发件人地址、SMTP 服务器地址及认证信息，以便在计算任务结束时发送通知邮件。

---

## 9. 邮件发送测试命令

配置完成后，使用 `echo "Normal termination of Gaussian 16" | mail -s "G16" jin@163.com` 命令可测试邮件发送功能。该命令会将指定的正文和主题发送至目标邮箱。

---

## 10. MobaXterm 远程连接使用

在 Windows 系统上使用 MobaXterm 可远程连接 Rocky Linux 系统进行文件管理和命令操作。MobaXterm 支持 SSH 连接，提供左侧文件浏览窗口，并支持通过双击打开文件或使用快捷键修改窗口颜色。

---

## 11. 默认 Python 版本检查

Rocky Linux 9.3 系统默认安装 Python 3.9。使用 `python -V` 和 `which python` 命令可查看当前 Python 版本及可执行文件路径，通常位于 `/usr/bin/` 目录下。

---

## 12. 编译安装 Python 3.7 依赖包

在编译安装 Python 3.7 前，需使用 `yum` 安装 zlib-devel、bzip2-devel、openssl-devel、ncurses-devel、sqlite-devel、readline-devel、tk-devel、gcc 和 make 等必要的依赖库。

---

## 13. 系统 Python 路径备份

为避免冲突，安装新版本 Python 前需备份原有的 Python 可执行文件。执行 `mv /usr/bin/python /usr/bin/python.bak` 命令对原文件进行重命名备份。

---

## 14. Python 3.7 源码编译安装

解压 Python-3.7.12 源码包后，使用 `./configure prefix=/usr/local/python37` 配置安装路径。执行 `make -j && make install` 命令进行编译和安装。

---

## 15. Python 3.7 环境变量配置

将编译安装的 Python 3.7 可执行文件链接到系统路径，执行 `ln -s /usr/local/python37/bin/python3 /usr/bin/python`。在 `/etc/profile` 文件中添加 `PATH=/usr/local/python37/bin:$PATH` 并执行 `export PATH` 以生效。

---

## 16. Yum 命令兼容性修复

修改系统默认 Python 版本后，需编辑 `/usr/bin/yum` 文件，将首行 shebang 修改为 `#!/usr/bin/python3.9`，以确保 yum 命令能正常调用原有的 Python 3.9 解释器。

---

## 17. Python 依赖库安装

使用 `python -m pip install numpy pandas` 命令可为 Python 环境安装 numpy 和 pandas 数据库库。这些库是运行计算化学相关脚本（如 NMR 和 ECD 计算）的必要依赖。

---

## 18. Environment Modules 编译安装

Environment Modules 需下载 modules-5.3.1 源码包进行手动编译安装。安装前需确保安装了 tcl 和 tcl-devel 依赖，配置参数指定安装前缀为 `/usr/local/Modules` 及模块文件目录。

---

## 19. Environment Modules 环境变量激活

创建软链接将 Modules 初始化脚本链接到 `/etc/profile.d/` 目录，以便系统启动时自动加载。在用户目录下的 `.bashrc` 文件中添加 `source /usr/local/Modules/init/bash` 命令以激活 module 功能。

---

## 20. 设置Module环境变量

在CentOS 9和7.6上，设置MODULEPATH环境变量可以识别系统内置的module命令。在Rocky Linux 9.3上，必须在配置文件中添加该环境变量设置才能使用module命令管理Python等软件环境。
- export MODULEPATH=/usr/local/Modules/modulefiles:\$MODULEPATH

---

## 21. 启用Module系统

在Rocky Linux 9.3中，通过在配置文件中添加source命令来初始化module系统。编辑`/etc/profile`文件添加初始化脚本，再执行`/etc/profile.d/module.sh`即可完成启用。
- source ~/.bashrc
- vi /etc/profile
- source /usr/local/Modules/init/profile.sh
- source /etc/profile.d/module.sh

---

## 22. 创建Python Modulefile

在`/usr/local/Modules/modulefiles/`目录下创建Python配置文件，通过Tcl脚本定义Python版本、安装路径及环境变量。该文件配置了版本号、安装目录、帮助信息以及PATH和LD_LIBRARY_PATH的预加载路径。
- vi /usr/local/Modules/modulefiles/python
- #%Module
- set python_version 3.7.12
- set python_home /usr/local/python37
- proc ModulesHelp { } {
- puts stderr "Sets upthe environment for Python $python_version"
- }
- module-whatis "Sets up the environment for Python$python_version"
- setenv PYTHON_VERSION $python_version
- prepend-path PATH $python_home/bin
- prepend-path LD_LIBRARY_PATH $python_home/lib

---

## 23. Module常用命令

Module系统提供了管理环境变量的命令，包括查看可用模块、加载模块、清除模块设置及修改变量路径。`set`用于设置模块内部变量，`setenv`用于设置用户环境变量，`prepend-path`和`append-path`分别用于在路径前或后添加环境变量。
- module avail
- module load python
- module purge
- set
- setenv
- prepend-path
- append-path

---

## 24. SVM-M脚本修改

在集群上使用SVM-M时，如果系统不支持`q16`命令，需要将`autonmr.sh`脚本中的调用指令修改为标准的Gaussian执行命令。对于使用PBS等非自定义调度系统的集群，不需要进行此项修改。
- q16 $queue $a > /dev/null 2>&1
- g16 $a.com > $a.log

---

## 25. 禁用系统默认Nouveau驱动

安装NVIDIA驱动前需要禁用系统默认的Nouveau开源驱动，这可以通过修改`modprobe`配置文件和GRUB配置文件实现。在黑名单配置中添加`blacklist nouveau`，并在GRUB命令行参数中加入`rd.driver.blacklist=nouveau`和`nouveau.modeset=0`。
- lsmod | grep nouveau
- vim /usr/lib/modprobe.d/dist-blacklist.conf
- blacklist nouveau
- options nouveau modeset=0
- vi /etc/default/grub
- GRUB_CMDLINE_LINUX="crashkernel=1G-4G:192M,4G-64G:256M,64G-:512Mresume=/dev/mapper/cs_tjgpu-swap rd.lvm.lv=cs_tjgpu/rootrd.lvm.lv=cs_tjgpu/swap rhgb quiet rd.driver.blacklist=nouveaunouveau.modeset=0"
- grub2-mkconfig -o /boot/grub2/grub.cfg

---

## 26. 重建Initramfs并切换运行模式

禁用Nouveau驱动后，需要备份并重建initramfs镜像文件，并将系统默认运行目标切换为多用户模式。切换至命令行模式可以避免图形界面干扰驱动安装，安装完成后可通过systemctl命令重启或停止图形服务。
- mv /boot/initramfs-$(uname -r).img /boot/initramfs-$(uname-r).img.bak
- dracut /boot/initramfs-$(uname -r).img $(uname -r)
- systemctl set-default multi-user.target
- systemctl stop gdm.service
- systemctl start gdm.service

---

## 27. 安装NVIDIA驱动前的内核准备

安装NVIDIA驱动前需更新系统并安装与当前内核版本匹配的`kernel-devel`和`kernel-devel`。如果已安装的内核版本与开发包版本不一致，需卸载不一致的旧内核包以确保驱动编译成功。
- yum update
- yum install kernel-devel kernel-headers -y
- yum list | grep kernel-devel
- rpm -qa | grep kernel
- rpm -aq | grep kernel-devel
- yum remove kernel-5.14.0-362.el9.x86_64
- yum remove kernel-modules-core-5.14.0-362.el9.x86_64
- ls /usr/src/kernels

---

## 28. 运行NVIDIA驱动安装程序

赋予NVIDIA驱动安装文件执行权限后，运行安装程序。若内核源码路径非标准，需通过`--kernel-source-path`参数指定正确的内核路径，安装过程中通常选择不安装32位兼容库。
- chmod +x *
- ./NVIDIA-Linux-x86_64-525.116.04.run
- ./NVIDIA-Linux-x86_64-535.129.03.run --kernel-source-path=/usr/src/kernels/5.14.0-378.el9.x86_64

---

## 29. 验证NVIDIA驱动安装

使用`nvidia-smi`命令可以查看GPU状态和驱动版本信息，实时监控GPU使用情况可使用`watch -n 10 nvidia-smi`命令。命令输出版本信息及GPU列表表明驱动安装成功。
- nvidia-smi
- watch -n 10 nvidia-smi

---

## 30. 卸载旧版本NVIDIA驱动与CUDA

安装新版本NVIDIA驱动（如545系列）前，必须彻底卸载旧版本驱动（如535系列）及CUDA工具包。卸载过程包括使用yum移除相关软件包、删除本地CUDA目录以及运行官方卸载脚本。
- yum remove nvidia-*
- rpm -qa|grep -i nvid|sort
- yum remove kmod-nvidia-*
- yum -y remove cuda-*
- yum remove *cublas* *cuda*
- rm -rf /usr/local/cuda*
- nvidia-uninstall
- /usr/local/cuda/cuda-uninstaller

---

## 31. NVIDIA驱动与CUDA版本匹配

Gromacs的GPU加速功能依赖于匹配的NVIDIA驱动和CUDA版本。若仅安装驱动而未安装CUDA工具包，Gromacs编译时GPU支持将被禁用；且NVIDIA驱动的大版本号（如545）需与CUDA安装包的大版本号（如545.23.08）严格对应。
- cuda_12.3.2_545.23.08_linux.run
- NVIDIA-Linux-x86_64-545.29.02.run

---

## 32. 安装CUDA 12.3

下载并运行CUDA 12.3的runfile安装包，在安装向导中接受协议并取消Driver选项（因驱动已安装）。安装完成后需将CUDA的bin和lib64路径添加到用户环境变量PATH和LD_LIBRARY_PATH中。
- wget https://developer.download.nvidia.com/compute/cuda/12.3.2/local_installers/cuda_12.3.2_545.23.08_linux.run
- chmod +x *
- ./cuda_12.3.2_545.23.08_linux.run
- vi ~/.bashrc
- export PATH="/usr/local/cuda-12.3/bin:$PATH"
- export LD_LIBRARY_PATH="/usr/local/cuda-12.3/lib64:$LD_LIBRARY_PATH"
- source ~/.bashrc
- nvcc -V

---

## 33. Rocky Linux 9.3安装新版CMake

Rocky Linux 9.3默认的CMake版本过低，不满足Gromacs 2024.0的编译要求。可以通过EPEL源安装cmake3，或者从官网下载源码使用bootstrap脚本编译安装新版本CMake。
- yum install epel-release
- yum install cmake3
- cmake3 /V
- ./bootstrap --prefix=/root/soft/cmake3 -- -DCMAKE_USE_OPENSSL=OFF
- ./bootstrap --prefix=/usr --datadir=share/cmake --docdir=doc/cmake&& make
- make install
- cmake -version

---

## 34. 下载Gromacs 2024.0源码

从Gromacs官方FTP服务器下载2024.0版本的源码压缩包，并使用tar命令解压到安装目录。这是编译安装GPU加速版Gromacs的前置步骤。
- wget https://ftp.gromacs.org/gromacs/gromacs-2024.0.tar.gz
- tar xfz gromacs-2024.0.tar.gz

---

## 35. GROMACS 编译目录准备

编译 GROMACS 需首先进入源码目录并创建独立的构建目录。操作命令为 `cd gromacs-2024.0` 进入目录，随后执行 `mkdir build` 和 `cd build` 建立并进入构建文件夹。

---

## 36. GROMACS 编译参数配置 (cmake)

使用 `cmake ..` 配置编译选项时，需指定安装路径、FFT 库、回归测试下载、SIMD 指令集及 GPU 支持等关键参数。示例参数包括 `-DCMAKE_INSTALL_PREFIX`（如 `/root/soft/gmx_GPU_2024.0`）、`-DGMX_BUILD_OWN_FFTW=ON`、`-DREGRESSIONTEST_DOWNLOAD=ON`、`-DGMX_SIMD=AVX2_256`、`-DGMX_GPU=CUDA` 以及 `-DCUDA_TOOLKIT_ROOT_DIR`（如 `/usr/local/cuda-12.3`）。

---

## 37. GROMACS 多核编译与验证

执行编译、测试及安装的命令链为 `make -j && make -j check && make install`。使用 `make -j` 可启用多核编译以显著加快速度，若未加 `-j` 则仅进行单核编译。

---

## 38. GROMACS 环境变量设置

需在用户配置文件（如 `~/.bashrc`）中设置环境变量，包括通过 `source` 命令加载 GROMACS 的 RC 文件（如 `source /root/soft/gmx_GPU_2024.0/bin/GMXRC`）。建议设置 `export GMX_MAXBACKUP=-1` 以避免生成备份文件。

---

## 39. GROMACS GPU 支持验证

安装完成后，执行 `gmx -version` 命令可查看版本信息及支持特性。若输出信息中显示 GPU support 为 CUDA 状态，则表明 GPU 加速版本安装成功。

---

## 40. CREST 安装与配置

安装 CREST 需将下载的压缩包（如 crest.tgz）解压，并将解压后的文件放置于 xtb 程序目录内。配置完成后需赋予相应权限即可使用。

---

## 41. OpenMPI 配置参数

配置 OpenMPI 时可使用 `./configure` 指定安装前缀，例如 `./configure --prefix=/usr/local/openmpi` 或 `./configure --prefix=/root/soft/openmpi411 --disable-builtin-atomics`。

---

## 42. Shermo 解压安装

Shermo 的安装过程较为简单，通过解压命令 `unzip Shermo_2.5.zip -d Shermo_2.5` 将文件释放到指定目录即可完成部署。

---

## 43. 计算化学综合环境变量配置示例

在 `.bashrc` 中配置多个计算化学软件环境时，需包含 CUDA 路径、GROMACS 设置、Gaussian 路径与临时目录（g16root, GAUSS_SCRDIR）、XTB 路径（PATH, XTBPATH）、OpenMP 与 MKL 线程数（OMP_NUM_THREADS, MKL_NUM_THREADS）、ORCA 路径及别名、Multiwfn 与 Shermo 路径等。此外，常设置 `ulimit -s unlimited` 和 `export OMP_STACKSIZE` 以优化堆栈大小。

---

## 44. ORCA 运行权限设置

在使用 OpenMPI 运行 ORCA 时，需设置环境变量允许以 root 用户运行，具体指令为 `export OMPI_ALLOW_RUN_AS_ROOT=1` 和 `export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1`。

---

## 45. 计算化学软件自动化工作流

安装 GROMACS、Gaussian、ORCA、Multiwfn、Molclus 及 XTB 等软件后，可结合 ChatGPT 生成脚本。利用这些脚本可以进行构象搜索，并调用《NMR和ECD计算》中的脚本进行后续计算，最后自动将计算结果与实验数据对比并输出打分。

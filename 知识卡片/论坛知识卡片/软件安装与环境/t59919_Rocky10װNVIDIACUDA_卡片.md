---
key: t59919
title: Rocky10��װ��NVIDIA��CUDA��װCP2K��GROMACS����QMMM
url: http://bbs.keinsci.com/thread-59919-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2026
cards: 25
---

# Rocky10��װ��NVIDIA��CUDA��װCP2K��GROMACS����QMMM — 知识卡片

## 1. 操作系统选择与安装

Rocky Linux 10 可作为计算平台的基础操作系统。安装时需使用 Rufus 工具将 ISO 镜像写入 U 盘。安装过程中若遇到界面死机或卡顿，可通过按 F2 键进入安全模式进行操作。

---

## 2. 系统安装后网络配置

Rocky Linux 9 可能存在无 WiFi 驱动的问题，Rocky Linux 10 对 WiFi 支持较好。安装系统时应勾选 OpenSSH 服务以便远程连接，若配置了 WiFi，可通过 `ip a` 查询 IP 地址并使用 MobaXterm 进行远程访问。

---

## 3. 禁用 Nouveau 开源驱动

安装 NVIDIA 显卡驱动前需检查并禁用系统自带的 Nouveau 开源驱动。执行 `lsmod | grep nouveau` 若有输出则表示该驱动正在运行，需进行后续禁用操作。

---

## 4. 删除旧内核版本

为避免冲突，需删除系统中保留的旧版本内核。使用 `yum remove -y` 命令删除指定版本号的 kernel-devel、kernel-core、kernel-modules 等相关包。

---

## 5. 配置 Nouveau 黑名单文件

通过创建或编辑 `/etc/modprobe.d/blacklist-nouveau.conf` 文件来禁用 Nouveau。文件内容需包含 `blacklist nouveau` 和 `options nouveau modeset=0`。

---

## 6. 修改 GRUB 配置文件

编辑 `/etc/default/grub` 文件，在 `GRUB_CMDLINE_LINUX="..."` 行的末尾追加 `rd.driver.blacklist=nouveau nouveau.modeset=0`。

---

## 7. 更新 GRUB 配置

根据系统启动模式不同，使用不同的命令更新 GRUB 配置。BIOS 模式执行 `grub2-mkconfig -o /boot/grub2/grub.cfg`；UEFI 模式下，Rocky/RHEL 系统通常执行 `grub2-mkconfig -o /boot/efi/EFI/rocky/grub.cfg`。

---

## 8. 重建 initramfs 镜像

备份原有的 initramfs 镜像并使用 `dracut` 命令重新生成。命令示例为 `mv /boot/initramfs-$(uname -r).img /boot/initramfs-$(uname -r).img.bak` 后执行 `dracut /boot/initramfs-$(uname -r).img $(uname -r)`。

---

## 9. 切换系统运行级别

若安装的是图形界面版本，为避免 X server 占用显卡资源导致驱动安装失败，需切换至多用户文本模式。使用 `systemctl set-default multi-user.target` 并重启系统，或临时使用 `systemctl isolate multi-user.target`。

---

## 10. 验证 Nouveau 禁用状态

重启后再次执行 `lsmod | grep nouveau` 命令。若无任何输出，说明 Nouveau 驱动已被成功禁用。

---

## 11. 安装内核开发工具与编译环境

使用 `dnf` 安装驱动编译所需的依赖包。命令为 `dnf install -y kernel-devel-$(uname -r) kernel-headers-$(uname -r) gcc make dkms elfutils-libelf-devel`。

---

## 12. 验证编译环境与内核版本匹配

安装依赖后需确认内核版本、kernel-devel、kernel-headers 版本一致，并检查 gcc 和 make 版本。可使用 `uname -r`、`rpm -qa` 及 `gcc --version` 等命令进行验证。

---

## 13. NVIDIA 驱动安装准备

下载 NVIDIA 驱动运行文件（如 NVIDIA-Linux-x86_64-595.84.run）并添加执行权限。需注意 CUDA 版本与驱动版本的兼容性，例如 CUDA 13.2.1 对应驱动版本 595.58.03，但 595.84 驱动同属 595 系列亦可使用。

---

## 14. 执行 NVIDIA 驱动安装

在文本模式下运行驱动安装程序，安装过程中接受 DKMS 注册，拒绝 32 位兼容库安装，并允许修改 X 配置文件。若遇到 X 库路径警告，可安装 `pkgconf-pkg-config` 和相关 X11 开发包。

---

## 15. 解决 X 库路径警告

若安装驱动时出现 X library path 警告，可执行 `dnf install -y pkgconf-pkg-config xorg-x11-server-Xorg` 等命令安装必要依赖。若忽略该警告，后续仍需确认系统能否正常找到驱动模块。

---

## 16. 安装 CUDA Toolkit

下载与驱动版本匹配的 CUDA Toolkit（如 13.2.1）并执行安装。安装时建议取消勾选 Driver 选项，仅安装 Toolkit，以避免覆盖已安装的显卡驱动。

---

## 17. 配置 CUDA 环境变量

编辑用户目录下的 `.bashrc` 文件，添加 CUDA 的 bin 路径和库路径至环境变量。需添加 `export PATH="/usr/local/cuda-13.2/bin:$PATH"` 和 `export LD_LIBRARY_PATH="/usr/local/cuda-13.2/lib64:$LD_LIBRARY_PATH"`。

---

## 18. 验证 CUDA 安装

执行 `source ~/.bashrc` 使环境变量生效，随后运行 `nvcc -V` 和 `nvidia-smi` 验证 CUDA 编译器和驱动状态。

---

## 19. 安装网络代理工具

为解决 GitHub 等外网的访问问题，可安装 Clash Verge 等代理工具。若安装 RPM 包时遇到 gtk3 依赖报错，需先启用 CRB 仓库，命令为 `sudo dnf config-manager --set-enabled crb`。

---

## 20. CP2K 依赖工具链安装

进入 CP2K 源码的 toolchain 目录，运行 `install_cp2k_toolchain.sh` 脚本配置依赖。示例参数包括 `--with-openmpi` 和 `--with-dftd4`，建议使用普通用户权限执行。

---

## 21. CP2K 编译配置

使用 CMake 配置 CP2K 编译选项，开启全面支持并禁用部分实验性或不需要的模块。关键参数包括 `-DCP2K_USE_EVERYTHING=ON`、`-DCP2K_USE_DFTD4=ON` 以及指定安装前缀和数据目录。

---

## 22. GROMACS 编译环境准备

下载并解压 GROMACS 源码，创建 build 目录。为支持 CP2K 接口，需先找到 CP2K 安装目录下的 `.pc` 文件，并设置 `PKG_CONFIG_PATH` 环境变量指向该路径。

---

## 23. GROMACS CMake 配置

使用 CMake 配置 GROMACS，开启双精度、MPI 支持及 CP2K 接口。关键参数包括 `-DGMX_DOUBLE=ON`、`-DGMX_MPI=ON`、`-DGMX_CP2K=ON` 以及指定 CP2K 安装目录 `-DCP2K_DIR`。

---

## 24. GROMACS 编译与安装

执行 `make -j28` 进行多核编译，运行 `make check` 进行测试，最后执行 `make install`。若测试过程中涉及多线程分布失败，可尝试取消设置 `OMP_NUM_THREADS` 环境变量。

---

## 25. 验证 GROMACS 与 CP2K 耦合

将 GROMACS 的 bin 目录添加至 PATH 环境变量，运行 `gmx_mpi_d --version` 查看版本信息。输出信息中显示 "CP2K support enabled" 即表示双分子动力学 QMMM 计算环境已成功配置。

---
(注：原文关于 AI 生成安装指令的经验性描述已略去，仅保留具体技术步骤)

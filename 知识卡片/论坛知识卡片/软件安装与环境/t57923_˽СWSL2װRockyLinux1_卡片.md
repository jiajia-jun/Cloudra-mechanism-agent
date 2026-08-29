---
key: t57923
title: ˽��С����WSL2װRockyLinux10���������LMod����OpenMPI-4.1.8, ORCA-6.1.1�ȵıʼ�
url: http://bbs.keinsci.com/thread-57923-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2026
cards: 13
---

# ˽��С����WSL2װRockyLinux10���������LMod����OpenMPI-4.1.8, ORCA-6.1.1�ȵıʼ� — 知识卡片

## 1. WSL2 与 Rocky Linux 10 环境配置的硬件与系统特性

在 Windows 11 上使用 WSL2 运行 Rocky Linux 10 时，Linux 系统可能无法完全区分硬件的 P-core（能效核）与 E-core（性能核）。WSL2 的虚拟磁盘文件 ext4.vhdx 会随数据写入而自动扩容，且占用空间通常比实际文件大，应定期清理 Windows 回收站以释放空间。Linux 系统崩溃（如 segmentation fault）产生的报告文件会存储在 Windows 的 C:\Users\{username}\AppData\Local\Temp\wsl-crashes 目录下，需注意清理以防占用过多磁盘空间。

---

## 2. WSL2 与 Windows 之间的文件系统交互注意事项

在 WSL2 的 Linux 环境中访问 Windows 文件系统（如 /mnt/d）会导致 I/O 性能下降，计算任务的输入与输出文件应放置在 Linux 文件系统中运行。从 Windows 系统直接复制文件到 Linux 环境可能会附带 Zone.identifier 文件，建议使用 Linux 命令（如 cp）在文件系统内部传输文件以避免此类问题。

---

## 3. Rocky Linux 系统下的文件命名规范

在 Rocky Linux 系统中编写脚本或处理文件时，建议文件名仅包含 ASCII 字符，具体包括数字 0-9、大小写字母 A-Za-z、下划线 _、短横线 - 以及点 .。避免在文件名和注释中使用中文或非英文字符，以防止因编码问题导致的计算错误或兼容性问题。

---

## 4. Rocky Linux 10 在 WSL2 中的安装命令

在 Windows 命令行（CMD）中执行特定命令可将 Rocky Linux 10 安装至 WSL2，并指定虚拟磁盘的大小与类型。安装命令需包含 --from-file 指定源文件路径，--location 指定安装目录，--name 指定分发版名称，--vhd-size 指定磁盘大小（如 256GB），以及 --fixed-vhd 创建固定大小的虚拟硬盘。

---

## 5. WSL2 初始用户创建与配置

Rocky Linux 10 安装完成后会提示创建默认 UNIX 用户，该用户会被自动加入 wheel 组并拥有免密 sudo 权限。初始安装目录可能位于 /mnt/c/Users/{username}，建议使用 cd ~ 命令切换至用户家目录（如 /home/twilight）进行后续操作。

---

## 6. Rocky Linux 基础编译工具与依赖库安装

在 Rocky Linux 系统中，需使用 dnf 包管理器安装编译软件及运行库，包括 epel-release 源、GCC/G++/GFortran 14.3.1、Python 3、Git、Make 及 zlib-devel 等工具。这些基础工具是后续编译安装 OpenMPI 和其他计算化学软件的必要前提。

---

## 7. LMod 环境模块管理工具的安装与验证

LMod 是基于 Lua 语言的环境模块管理工具，可通过 sudo dnf install -y Lmod 命令直接安装。安装成功后，可通过执行 echo $LMOD_CMD、echo $MODULEPATH 和 module help 命令来检查 LMod 是否正确加载及其配置路径。

---

## 8. OpenMPI 4.1.8 的编译配置参数

编译 OpenMPI 4.1.8 时，需使用 sudo 权限执行配置命令，指定安装前缀为 /opt/openmpi418。配置命令建议使用 2>&1 | sudo tee configuring.log 将输出重定向至日志文件，随后执行 sudo make all install 进行编译安装。

---

## 9. OpenMPI 模块文件编写要点

OpenMPI 的模块文件（如 4.1.8-gnu14.3.1.lua）需使用 prepend_path 将 bin 和 lib 目录分别加入 PATH 和 LD_LIBRARY_PATH。由于 ORCA 等程序可能需要以 root 用户运行，模块文件中应包含 setenv("OMPI_ALLOW_RUN_AS_ROOT", "1") 和 setenv("OMPI_ALLOW_RUN_AS_ROOT_CONFIRM", "1") 设置。

---

## 10. ORCA 6.1.1 模块文件的依赖与别名设置

ORCA 6.1.1 的模块文件需要依赖 OpenMPI 模块，通过 load("openmpi/4.1.8-gnu14.3.1") 确保加载顺序。为方便调用，可使用 set_shell_function 定义 shell 函数，例如将 orca6 别名指向 /opt/orca_6_1_1_linux_x86-64_shared_openmpi418_avx2/orca 可执行文件。

---

## 11. Miniforge 的下载与校验

Miniforge 安装脚本可从 GitHub 官方仓库下载，下载后应使用 sha256sum 命令计算哈希值并与官网发布的数值进行比对，以确保文件完整性。文件名通常包含系统架构信息，下载命令示例为 sudo wget "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"。

---

## 12. Miniforge 的静默安装

Miniforge 支持使用 bash 命令的 -b（批处理模式）和 -p（指定路径）选项进行静默安装，目标路径可设置为 /opt/miniforge3。安装命令示例为 sudo bash Miniforge3-25.11.0-1-$(uname)-$(uname -m).sh -b -p /opt/miniforge3。

---

## 13. 使用 sh_to_modulefile 转换 Conda 环境变量

LMod 提供的 sh_to_modulefile 工具可以将 Shell 脚本（如 conda.sh 和 mamba.sh）转换为 Lua 语法的模块文件。转换过程中需注意将 printf 命令中的注释符和格式字符串调整为 Lua 语法（使用 -- 表示注释），并保留原有的 setenv 和 prepend_path 逻辑。

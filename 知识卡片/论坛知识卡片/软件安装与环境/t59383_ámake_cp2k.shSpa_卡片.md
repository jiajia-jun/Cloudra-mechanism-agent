---
key: t59383
title: ���á�make_cp2k.sh����Spack�������������밲װCP2K
url: http://bbs.keinsci.com/thread-59383-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2026
cards: 11
---

# ���á�make_cp2k.sh����Spack�������������밲װCP2K — 知识卡片

## 1. CP2K v2026.2 自动安装脚本 make_cp2k.sh

CP2K v2026.2 版本目录下提供了一个名为 make_cp2k.sh 的脚本，旨在利用 Spack 管理依赖并进行 CP2K 的编译。该脚本实现了下载依赖、配置环境以及 CMake 编译的全自动化，无需用户干预即可完成构建。

---

## 2. 脚本环境依赖要求

运行 make_cp2k.sh 脚本要求系统环境中的 Bash 版本大于等于 4，且 Python 版本大于等于 3.10。

---

## 3. 脚本中断与恢复机制

脚本执行过程中若检测到 spack/ 目录存在且未完成，会自动跳过下载步骤直接编译。若需从头重新构建，可使用 -bd 或 --build_deps 参数，或手动删除 spack 目录。推荐在遇到错误解决后使用 -uc none 配合恢复命令，确保能正确切换缓存或重新加载。

---

## 4. 版本与 MPI 模式选项 (-cv/-mpi)

-cv 或 --cp2k_version 用于指定 CP2K 的构建类型，支持 psmp、ssmp、ssmp-static、pdbg、sdbg，默认为 psmp。使用 -cv psmp 或 -cv pdbg 时默认启用 MPI（默认为 mpich），可通过 -mpi 或 --mpi_mode 指定为 openmpi。使用 -cv ssmp、-cv ssmp-static 或 -cv sdbg 时，-mpi 会自动设为 no。若手动指定版本与 MPI 选项冲突，脚本将忽略冲突指令按默认顺序执行。

---

## 5. 功能启用与禁用选项 (-df/-ef)

-df 或 --disable_feature 用于排除不需要的功能特性，以避免 Spack 下载和安装对应的依赖包。-ef 或 --enable_feature 用于手动指定需要安装的功能特性，其优先级高于 -ef all。默认配置相当于 -ef all -df dlaf，且若 GCC>=15 且存在 CUDA，会额外禁用 PEXSI。

---

## 6. 功能选项的互斥与覆盖规则

-df 和 -ef 选项不能同时使用，因为逻辑上无法同时实施。-ef 选项会覆盖 -ef all，即仅安装指定的特定功能。libvdwxc、spfft、spla、sirus 这四个功能存在复杂的相互依赖关系，启用其中任何一个可能导致其余三个也被启用。

---

## 7. 缓存模式选项 (-uc)

-uc 或 --use_cache 控制 Spack 在编译 CP2K 时的缓存方式。默认的 -uc folder 将压缩包存放在本地目录以便复用；-uc minio 使用 Podman 存储缓存；-uc no 不使用缓存，每次下载并在构建结束后清理，节省磁盘空间但重新构建耗时较长。

---

## 8. 外部依赖检测选项 (-ue)

-ue 或 --use_externals 通过 spack external find 检测系统中已有的库（如 Python）并将其纳入构建流程。某些依赖如 MPI 和数学库需在配置文件中指定路径才能被有效检测。若系统安装了 meson 可能导致冲突，Spack 会尝试使用自带 Python，解决冲突时可移除 -ue 并配合 -uc no 使用本地缓存。

---

## 9. 并行构建参数 (-j/-np)

-j M 设置全局编译并行任务数，若未指定则通过 nproc 获取 CPU 核心数作为默认值。-np N 设置 Spack 安装依赖包时的并行数，默认为 2。对于部分编译步骤较长的依赖（如 libxc），适当增加 -np 数值可提高构建速度。

---

## 10. 仅重编译 CP2K 选项 (-rc)

如果依赖安装已完成仅需重新编译 CP2K，可使用 -rc 或 --rebuild_cp2k。该选项将删除 build 和 install 目录并对 CP2K 进行重新编译，保留 spack 目录不变。

---

## 11. 回归测试选项 (-t)

构建完成后若需运行回归测试可使用 -t 或 --test。测试参数需额外指定，例如 -t "--mpiranks 2 --ompthreads 1 --maxtasks 24 --flagslow"。

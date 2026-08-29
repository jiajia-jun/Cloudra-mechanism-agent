---
key: t50811
title: Lmod��������Anaconda�ķ���
url: http://bbs.keinsci.com/thread-50811-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 8
---

# Lmod��������Anaconda�ķ��� — 知识卡片

## 1. Lmod 模块化管理 Anaconda 概述

Anaconda 是一个开源的 Python 发行版，包含了大量科学计算所需的库（如 numpy, scipy, Pandas）及强大的包和环境管理功能。为了避免在集群中单用户安装无法共享的问题，可将 Anaconda 安装在公共目录，并编写 Lmod 模块文件供集群用户统一调用。Lmod 是基于 Lua 和 TCL 语言的模块管理工具，支持丰富的环境配置和帮助文档，便于在 Linux 集群（如 Rocky Linux 9.5）上进行软件环境管理。

---

## 2. Lmod 与 Anaconda 的安装步骤

在 Rocky Linux 系统上，可通过 `dnf install Lmod` 命令直接安装 Lmod，其他 Linux 发行版需查阅对应安装方式。Anaconda 建议安装在公共目录（如 `/opt`），下载安装脚本后赋予执行权限（`chmod +x Anaconda3-2024.10-1-Linux-x86_64.sh`）并运行安装。安装过程中需将默认目录（/root/anaconda3）修改为公共目录（如 /opt/anaconda3），并在询问是否执行初始化时选择 no，防止写入个人账户配置文件。

---

## 3. Anaconda Lmod 模块文件创建规则

Lmod 模块文件通常放置在 `/etc/modulefiles` 目录下，建议以“软件名/版本号”的方式创建子目录和文件（如 `anaconda3/24.9.2.lua`）以管理不同版本。文件名中的版本号（如 24.9.2）应通过 `conda --version` 查询确认。Lua 编写的模块文件能够处理环境变量设置和 shell 命令执行，从而实现 Anaconda 环境的加载与卸载。

---

## 4. Anaconda 模块文件基础配置代码

模块文件中需设置 `ANACONDA_ROOT` 环境变量指向安装路径，并将 Anaconda 的 bin 目录添加至 PATH 环境变量。路径设置语句 `local base = pathJoin("/opt", myModuleName())` 中的 `/opt` 需根据实际安装位置进行修改。基础配置包含定义软件描述的 `whatis` 指令以及设置根目录和环境路径的 `setenv` 和 `prepend_path` 指令。

---

## 5. 模块加载时的 Conda 激活机制

模块文件通过 `execute{cmd="source " .. base .. "/etc/profile.d/conda."..myShellType(),modeA={"load"}}` 加载 Conda 的环境配置。加载模块时会自动执行 `execute{cmd="conda activate base",modeA={"load"}}` 激活 base 环境。若需默认激活其他自定义环境，可将代码中的 `base` 替换为对应环境名称，若不需要默认激活任何环境，可直接删除该行代码。

---

## 6. 模块卸载时的 CSH 环境清理

当 Shell 类型为 csh 时，模块卸载逻辑包含取消设置相关环境变量（`CONDA_EXE`, `_CONDA_ROOT` 等）和取消 conda 别名。代码执行 `execute{cmd="conda deactivate",modeA={"unload"}}` 退出当前 conda 环境，随后执行清理命令以彻底移除 conda 在 csh 环境下的配置残留。

---

## 7. 模块卸载时的 SH/BASH 环境清理

当 Shell 类型为 sh/bash 时，卸载模块需从 PATH 中移除 condabin 路径，并取消设置包括环境变量（`CONDA_EXE`, `CONDA_SHLVL` 等）和 shell 函数（`__conda_activate`, `conda` 等）在内的所有 Conda 相关配置。该过程同样先执行 `conda deactivate` 退出当前环境，再执行清理命令确保 Anaconda 完全退出系统环境。

---

## 8. 模块卸载时的环境切换注意事项

若当前环境已从 base 切换到其他环境（如通过 `conda activate ase` 切换到 ase 环境），直接执行 `module unload anaconda3` 可能无法完全退出 Anaconda。用户需先手动执行 `conda deactivate` 回退到 base 环境，再执行 `module unload anaconda3`，才能确保 Anaconda 及其子环境被完全卸载和清理。

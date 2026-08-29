---
key: t37403
title: Fedora/Debian Linux ��װ GIMIC 2.0 ʱ�ȹ��Ŀ��Լ�����취
url: http://bbs.keinsci.com/thread-37403-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 6
---

# Fedora/Debian Linux ��װ GIMIC 2.0 ʱ�ȹ��Ŀ��Լ�����취 — 知识卡片

## 1. GIMIC 与 ParaView 的应用场景

GIMIC 2.0 配合 ParaView 可用于绘制全空间动态环电流图和磁感应强度矢量图。该方法能够直观展示芳香性分子的磁响应性质，例如 C18Br6 体系。GIMIC 负责计算并生成 vti 文件，ParaView 负责后续的可视化渲染。

---

## 2. GIMIC 在 WSL Debian 上的 Python 路径报错

在 WSL Debian 环境下按照教程安装 GIMIC 2.0 时，执行 `./setup --omp` 可能提示找不到 Python 目录。这是因为系统环境中 Python 版本不兼容，GIMIC 需要特定的旧版本 Python。安装教程中提到的 CentOS 命令如 `apt-get install epel-release` 不适用于 Debian 环境。

---

## 3. 解决 GIMIC 安装时的 Python 版本依赖

若在安装 GIMIC 时遇到 Python 目录错误或运行 gimic 生成 vti 文件时报 `ImportError`，通常是因为 Python 版本过新（如 3.11.3）。解决方法是在 Anaconda 环境中通过命令 `conda install python=2.7` 将 Python 版本降级至 2.7，然后重新执行 `./setup --omp` 即可成功安装和运行。

---

## 4. 新版 OpenBabel 的命令与兼容性变化

Rocky Linux 或 Fedora 系统通过 `dnf install openbabel` 安装的是新版 OpenBabel（如 3.1.1），其命令行工具名称可能为 `obabel` 而非旧版的 `babel`，且输出格式存在差异。直接使用旧版教程中的 `xyz2cml.sh` 脚本会因为命令不存在或格式不匹配而报错。

---

## 5. 使用新版 OpenBabel 生成 CML 文件的脚本

针对新版 OpenBabel，可使用 GitHub 上适配的 `xyz2cml.sh` 脚本（地址：https://github.com/Usu171/GIMIC/blob/main/xyz2cml.sh）。该脚本首先通过 `obabel -ixyz mol.xyz -ocml -O mol.cml` 将坐标文件转换为 CML 格式，随后使用 awk 命令将坐标单位从埃转换为玻尔，生成 `mol-bohr.cml` 供 GIMIC 使用。

---

## 6. 坐标单位转换的 awk 命令

在处理 CML 文件时，需使用 awk 脚本将原子坐标从埃换算为玻尔（除以 0.529177）。核心逻辑包括判断行内容是否包含 `<atom id` 和 `hydrogenCount`，并对相应的坐标字段（第 8、10、12 字段或第 6、8、10 字段）执行除法运算，最终输出符合 GIMIC 要求的 `mol-bohr.cml` 文件。

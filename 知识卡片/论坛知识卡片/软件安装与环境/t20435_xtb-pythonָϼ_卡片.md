---
key: t20435
title: xtb-python���������ָ�ϼ���ASE�е���ʵ��
url: http://bbs.keinsci.com/thread-20435-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2020
cards: 8
---

# xtb-python���������ָ�ϼ���ASE�е���ʵ�� — 知识卡片

## 1. xtb GFN-xTB 的 PBC 优化算法支持

xtb-6.3.3 版本的 GFN-xTB 在进行周期性边界条件(PBC)计算时，仅支持 engine=inertial 这一种几何优化选项。
ASE (Atomic Simulation Environment) 作为支持 PBC 的 Python 模型接口，连接 xtb 计算时可支持多种优化算法。
ASE 支持的优化算法包括 BFGS、BFGSLineSearch、LBFGS、LBFGSLineSearch、GPMin、MDMin 和 FIRE。
使用 ASE 结合 xtb-python 模块是进行 GFN-xTB 周期性体系结构优化的较好选择。
xtb-6.3.3 版本的 GFN2-xTB 方法不支持 PBC。

---

## 2. xtb 软件环境变量配置

在 ~/.bashrc 文件中配置 xtb 环境变量是使用 xtb-6.3.3 版本的必要步骤。
需要配置 PATH 环境变量指向 xtb 的 bin 目录，例如 /mnt/d/xtb_Linux/xtb-6.3.3/bin。
需要设置 XTBPATH 环境变量指向 xtb 的 share 目录，例如 /mnt/d/xtb_Linux/xtb-6.3.3/share/xtb。
建议设置 ulimit -s unlimited 以解除栈内存限制。
配置完成后需要 source ~/.bashrc 使环境变量生效。

---

## 3. ASE 软件的安装与测试

ASE (Atomic Simulation Environment) 可以通过 pip3 命令直接进行全自动安装。
安装命令通常包含 numpy、scipy、matplotlib 和 ase 依赖包，如：pip3 install --upgrade --user numpy scipy matplotlib ase。
安装后需在 ~/.bashrc 中配置 Python 相关的环境变量，包括 PYTHONPATH 和 PATH。
运行 ase test 命令可以验证 ASE 是否安装成功，测试通常耗时约 1 分钟。
测试通过后会显示 Passes、Failures 和 Errors 的统计信息。

---

## 4. python-xtb 编译前的依赖准备

python-xtb 模块建议从源码编译安装，需要提前安装 Intel 全家桶编译器。
在 CentOS 系统下，需要使用 yum 安装 cmake 和 python3-devel 依赖包。
必须安装 cffi、numpy、meson 和 ninja 等 Python 模块以支持编译过程。
下载并解压 python-xtb-20.2.tar.gz 源码包是安装的第一步。

---

## 5. xtb.pc 文件配置

编译 python-xtb 前需要修改 xtb 安装目录下的 xtb.pc 文件，该文件通常位于 lib64/pkgconfig 目录下。
必须将 xtb.pc 文件中的 prefix=/ 修改为 xtb 的实际安装路径，例如 prefix=/mnt/d/xtb_Linux/xtb-6.3.3/。
正确配置 xtb.pc 是确保 meson 能够找到 xtb 库文件的关键步骤。

---

## 6. python-xtb 编译环境变量设置

在编译安装 python-xtb 之前，需要 source Intel 全家桶的环境变量脚本。
需要设置 PKG_CONFIG_PATH 环境变量指向 xtb 的 lib64/pkgconfig 目录。
需要在 ~/.bashrc 中配置 LD_LIBRARY_PATH 环境变量，包含 xtb 的 lib64 目录。
编译前需执行 source ~/.bashrc 以确保动态库路径生效。

---

## 7. python-xtb 的编译安装步骤

使用 meson 命令初始化构建目录，参数为 setup build --prefix=$PWD --default-library=shared。
使用 ninja 命令进行编译和安装，命令为 ninja -C build install。
最后使用 pip3 install -e . 命令完成 python-xtb 模块的安装。
安装完成后可以通过 pip3 list 命令查看已安装的 xtb-python 版本信息。

---

## 8. ASE 与 xtb-python 联合测试

解压测试包 ASE_xtb_test.7z 后，需要修改 test.sh 脚本中的 Intel 环境变量路径为实际路径。
执行 bash test.sh 脚本可运行基于 ASE 和 xtb-python 的测试算例。
测试算例通常针对周期性体系（如金刚石晶胞）进行几何优化。
测试输出包含初始几何能量、优化步骤、力收敛标准 (fmax) 和最终几何能量。
输出信息会显示优化算法（如 BFGSLineSearch）的具体迭代过程和耗时。

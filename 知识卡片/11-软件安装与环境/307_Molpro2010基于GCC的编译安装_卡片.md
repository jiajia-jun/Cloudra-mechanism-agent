---
id: 307
title: molpro2010的编译方法
url: http://sobereva.com/307
domain: 软件安装与环境
topic: Molpro2010基于GCC的编译安装
cards: 2
---

# Molpro2010基于GCC的编译安装 — 知识卡片

## 1. 编译环境与系统要求

Intel i7-2630QM CPU，RHEL6U1 64bit系统，root用户。MKL库来自Intel fortran & C compiler 12.1.0安装包（非必须）。尝试使用ifort+icc编译运行不正常，最终采用系统自带gcc+gfortran编译。

## 并行版本configure配置
进入molpro2010.1目录，运行 `./configure -mpp -auto-openmpi -gcc -gfortran`。所有提示按回车使用默认（安装目标路径依实际情况输入）。程序会自动下载、解压并编译openmpi-1.4.3到src/openmpi-install目录。

## 并行版本编译与测试步骤
运行 `make -j` 开始编译，大约8分钟完毕。编译完毕提示输入username时直接Ctrl+C中断。运行 `make MOLPRO_OPTIONS=-n4 quicktest` 进行4核快速测试，全面测试需将quicktest改为test。

## License文件放置
将license文件token更名为.token，并放置到/sob/molpro2010.1/lib目录下。

## 环境变量PATH与MOLPRO_OPTIONS配置
在.bashrc中添加 `export PATH=$PATH:/sob/molpro2010.1/bin`。设定默认运行参数环境变量，例如 `export MOLPRO_OPTIONS="-n 4 -s --no-xml-output -m 800m"` 代表自动用四核、不自动备份同名老文件、不生成.xml文件、分配6400MB内存。

## 运行验证示例
输入bash或重新打开shell使环境变量生效。编写包含几何结构、basis=cc-pvtz、hf、ccsd(T)的h2co.inp文件，在目录下运行 `molpro h2co.inp`，检查输出的h2co.out内容是否正常。

## 串行版本编译方法
将并行编译的相应步骤替换为运行 `./configure -gcc -gfortran`，然后执行 `make -j` 和 `make quicktest`。

## 重新编译前的清理操作
如果需要在其它选项下重新编译，先用 `make veryclean` 清掉编译生成的文件，然后再重新执行配置和编译步骤。

## 相关文档与辅助工具位置
程序手册、quickstart等文档pdf文件在压缩包的doc目录下。molproView安装见相关链接，Molpro产生的.molden文件可通过Multiwfn进行波函数分析。

---

## 2. OpenMPI离线处理方式

如果机器没有联网，可以自行获取openmpi压缩包并放到/root/.molpro/cache/openmpi-1.4.3.tar.gz目录，程序会直接自动使用该文件进行编译。

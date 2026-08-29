---
id: 307
title: molpro2010的编译方法
url: http://sobereva.com/307
domain: 软件安装与环境
topic: Molpro2010基于GCC的编译安装
cards: 4
---

# Molpro2010基于GCC的编译安装 — 知识卡片

## 1. molpro2010并行版本编译配置命令

在解压后的molpro2010.1目录下运行`./configure -mpp -auto-openmpi -gcc -gfortran`，系统会识别编译器和MKL库，所有提示按回车使用默认值，程序会自动下载、解压并编译openmpi-1.4.3到`src/openmpi-install`目录。

---

## 2. molpro2010并行版本编译与测试操作

运行`make -j`开始编译，编译完毕后若提示输入username则按Ctrl+C中断；将license文件token更名为.token并放入`/sob/molpro2010.1/lib`目录；运行`make MOLPRO_OPTIONS=-n4 quicktest`进行4核快速测试，全面测试需将quicktest改为test。

---

## 3. molpro2010环境变量及运行参数设置

在`.bashrc`中加入`export PATH=$PATH:/sob/molpro2010.1/bin`，并设置默认运行参数如`export MOLPRO_OPTIONS="-n 4 -s --no-xml-output -m 800m"`以指定使用4核、不自动备份、不生成.xml文件及分配6400MB内存，执行bash或重启shell生效。

---

## 4. molpro2010串行版本编译与测试

运行`./configure -gcc -gfortran`进行配置，接着执行`make -j`进行编译，最后运行`make quicktest`完成测试。

---
key: t32888
title: ����������wsl��ϵͳubuntu18�°�װvasp
url: http://bbs.keinsci.com/thread-32888-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 12
---

# ����������wsl��ϵͳubuntu18�°�װvasp — 知识卡片

## 1. WSL环境下安装VASP的系统环境准备

在WSL下的Ubuntu 18系统上使用Intel 2019编译器可以成功安装VASP 5.4.4。此安装过程主要参考针对CentOS系统的教程，并针对WSL和Ubuntu环境进行适配。

---

## 2. WSL环境的基础配置与工具安装

配置WSL环境时，若未安装gedit编辑器，需执行`sudo apt install gedit`进行安装。环境配置文件可通过`gedit ~/.bashrc`或vim命令进行编辑和修改。

---

## 3. Ubuntu环境下的GCC与G++版本管理

后续编译步骤需要在root账户下进行，并需配置gcc和g++版本。建议安装gcc-8和g++-8，并使用update-alternatives命令将其设为默认版本。

---

## 4. GCC与G++版本切换命令

执行命令`sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-8 60 --slave /usr/bin/g++ g++ /usr/bin/g++-8`可完成gcc和g++版本的配置与关联。

---

## 5. Intel编译器的环境变量设置

解压安装Intel 2019及FFT库之前，需设置编译器环境变量。需执行`source /opt/intel/compilers_and_libraries/linux/bin/compilervars.sh intel64`并配置相关库路径。

---

## 6. MKL库及环境变量配置

需source MKL的脚本并设置`LD_LIBRARY_PATH`，具体命令为`source /opt/intel/compilers_and_libraries/linux/mkl/bin/mklvars.sh intel64`。同时需要将MKL库路径添加至`LD_LIBRARY_PATH`环境变量中。

---

## 7. C++头文件路径设置

需设置`CPLUS_INCLUDE_PATH`环境变量，命令为`export CPLUS_INCLUDE_PATH=/usr/include/x86_64-linux-gnu/c++/8:$CPLUS_INCLUDE_PATH`。此步骤旨在解决编译过程中可能遇到的头文件路径问题。

---

## 8. VASP编译前的注意事项

在执行编译前，必须正确设置上述环境变量。若未进行设置或设置不当，可能会导致编译失败或出现报错。

---

## 9. AMD CPU处理器的编译优化

针对AMD CPU编译VASP时，需对`makefile.include`文件进行相应修改。可参考相关论坛帖子中针对AMD_5950x处理器的优化指令集进行配置。

---

## 10. VASP的编译执行

完成所有配置和`makefile.include`的修改后，执行`make all`命令进行编译。编译过程若顺利结束，即表示安装成功。

---

## 11. Ubuntu与CentOS安装差异

Ubuntu环境下的安装思路与CentOS基本一致，但需进行适配性修改。Ubuntu 18和22版本在Intel 2019下的编译可能遇到特定问题，需注意gcc和g++版本的兼容性。

---

## 12. WSL系统的跨平台文件操作优势

WSL系统在文件操作方面具有优势，文件迁移可直接在资源管理器中完成。部分操作可在Windows下的cmd控制台中实现，且与主机的资源交互配置较为便捷。

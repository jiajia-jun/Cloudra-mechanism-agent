---
key: t29123
title: Conda�����±���MPI���а�CP2K-9.1(��libint�⣬���ܼ����ӻ�����)
url: http://bbs.keinsci.com/thread-29123-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 12
---

# Conda�����±���MPI���а�CP2K-9.1(��libint�⣬���ܼ����ӻ�����) — 知识卡片

## 1. CP2K编译环境与依赖注意事项

CP2K的编译结果对系统版本、编译器和依赖库较为敏感，不同环境下编译可能出现如KS energy异常或某些模块缺失等问题。在Centos 8、gcc 8.5.0环境下使用toolchain编译时曾遇到过报错，寻找环境兼容性良好的编译方法是解决此类问题的关键。相较于手动编译，使用Conda安装CP2K-9.1可提供更稳定的运行环境。

---

## 2. CP2K-8.2的sirius模块报错问题

在尝试编译或运行CP2K-8.2时，可能会遇到关于`sirius_MOD_sirius_option_get_logical`的错误。该错误原因是SIRIUS模块进行了更新，导致与旧版本CP2K-8.2不兼容。升级到CP2K-9.1版本可以解决此兼容性问题。

---

## 3. CP2K-9.1的编译与功能验证

在特定服务器环境下使用Conda成功编译并运行了CP2K-9.1。经测试，官方例程可以正常运行，部分参数测试与原作者老师的测试结果相符。通过Conda安装的方式避免了libint库相关的问题，且不涉及可视化工具。

---

## 4. Miniconda安装命令

使用wget命令下载Miniconda安装脚本，版本为Miniconda3-py37_4.11.0-Linux-x86_64.sh。下载完成后，通过bash命令执行安装脚本，并根据提示输入yes并回车以完成安装。

---

## 5. Conda基础配置

安装Miniconda后，需在`.bashrc`文件中添加`conda config --set auto_activate_base false`。该设置可防止Conda环境自动激活，使终端启动时不默认进入base环境，保持系统环境整洁。

---

## 6. Conda环境创建与CP2K安装

创建一个名为`cp2k-v9.1`的Conda环境，并使用conda-forge渠道安装CP2K（默认版本为cp2k-9.1）。相关命令包括`conda create --name cp2k-v9.1`用于创建环境，以及`conda install -c conda-forge cp2k`用于安装软件。

---

## 7. CP2K数据目录配置

需从GitHub下载cp2k-9.1的源码包以获取数据目录。若GitHub访问缓慢，可使用ghproxy代理站进行下载，下载后使用tar命令解压，并将数据目录路径通过`export CP2K_DATA_DIR`写入`.bashrc`文件中。

---

## 8. 下载和解压CP2K源码

使用wget命令从GitHub或代理站下载`cp2k-9.1.tar.bz2`文件。下载完成后，使用`tar -jxvf`命令对文件进行解压，以获取其中的data目录等资源。

---

## 9. OpenMPI安装与共享库报错

在Conda环境下安装openmpi-4.1.1时，可能遇到`libmpi.so.40: cannot open shared object file`错误。这通常是因为Python环境中的MPI库无法被正确链接，需在`.bashrc`中正确配置库路径，但需注意避免Conda自带的openmpi与系统或Python环境产生冲突。

---

## 10. 验证CP2K安装与版本信息

安装完openmpi-4.1.1后，需重新打开终端或重新登录。激活`cp2k-v9.1`环境后，输入`cp2k.psmp -v`命令可查看CP2K的版本信息，以验证软件是否正确安装。

---

## 11. CP2K单核与多核运行命令

CP2K默认使用全核进行并行计算，提交任务可使用`nohup cp2k.psmp *.inp > *.out &`。若需将标准输出和错误输出分离，可使用`nohup cp2k.psmp *.inp 1 > *.out 2 > *.err &`命令。

---

## 12. MPI并行运行配置

使用MPI方式运行CP2K时，建议在`.bashrc`中设置`export OMP_NUM_THREADS=1`以限制OpenMP线程数。配置生效后，使用`mpirun -np 4 cp2k.psmp *.inp 1>*.out 2>*.err`命令可调用4个核心进行并行计算，具体的核数可根据实际情况修改。

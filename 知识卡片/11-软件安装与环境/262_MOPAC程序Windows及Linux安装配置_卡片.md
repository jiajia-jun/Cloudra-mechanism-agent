---
id: 262
title: MOPAC的安装方法
domain: 软件安装与环境
topic: MOPAC程序Windows及Linux安装配置
cards: 5
---

## 1. 下载MOPAC程序及版本选择建议
Windows版下载页面上最新的即可；Linux版建议下载"Download 64-bit MOPAC2016 for LINUX"，不要下载Latest open-source release下面的Linux版，否则安装时需要图形库；GPU版加速效果很有限，可以无视。

---

## 2. 使用Multiwfn创建MOPAC输入文件
启动Multiwfn，载入含有结构信息的文件，进入主功能100的子功能2，再选14，输入要产生的MOPAC输入文件路径，选一个理论方法如PM7；选择理论方法之前可以设置是否用溶剂模型、是否冻结原子、要做的任务之类。
- 支持的输入文件格式: xyz/pdb/gjf/fch/mol/mol2/mwfn等

---

## 3. Windows版MOPAC的安装与运行
运行.exe安装文件，一直点下一步，所有设置（包括安装目录）都用默认的；双击.mop文件运行，操作系统询问执行程序时选MOPAC；计算完成后在当前目录下会出现同名的.out输出文件和.arc archive文件。
- 命令行运行方式: 输入 `MOPAC H2O.mop`

---

## 4. Linux版MOPAC2016的安装配置
将压缩包解压到目标目录（如/sob/MOPAC2016），在用户主目录下的.bashrc文件末尾添加环境变量，重新进入终端使设置生效，然后给目录下的文件加上可执行权限。
- 环境变量设置
`export MOPAC_LICENSE=/sob/MOPAC2016`
`export PATH=$PATH:/sob/MOPAC2016`
`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/MOPAC2016`
- 添加权限命令: `chmod +x /sob/MOPAC2016/*`

---

## 5. Linux版MOPAC2016的运行方法
输入`MOPAC2016.exe yohane.mop`进行计算，计算后会在同目录下得到.out、.arc等文件。

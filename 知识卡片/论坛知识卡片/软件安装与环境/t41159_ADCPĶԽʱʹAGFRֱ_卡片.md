---
key: t41159
title: ADCP���ĶԽ�ʱʹ��AGFR���ֱ����Լ��������
url: http://bbs.keinsci.com/thread-41159-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 13
---

# ADCP���ĶԽ�ʱʹ��AGFR���ֱ����Լ�������� — 知识卡片

## 1. ADCP中的AGFR工具用途

ADCP (AutoDock CrankPep) 用于判断对接质量，在分析教程运行过程中需要使用AGFR (affinity map) 功能。AGFR能够生成亲和力图谱，但该功能十分底层，通常选择使用命令行进行操作。

---

## 2. AGFR基础命令格式

使用AGFR功能执行基础命令的格式如下：
agfr -r receptor.pdbqt -l peptide.pdbqt -asv 1.1 -o output

---

## 3. Numpy导入错误提示

在尝试获取affinity map时可能会遇到ImportError，提示导入numpy multiarray扩展模块失败。这通常意味着安装的numpy版本损坏或存在构建失败。

---

## 4. 错误环境路径信息

错误信息会指明当前使用的Python路径，例如 `/software/adcp/ADFRsuite_x86_64Linux_1.0/bin/python`。该路径是ADCP自带的Python环境，需确认此路径下的numpy配置。

---

## 5. 原始错误符号含义

错误日志中的原始错误为 `undefined symbol: PyUnicodeUCS4_FromObject`。这表明Python与numpy之间存在Unicode版本（UCS2与UCS4）不兼容的问题。

---

## 6. ADCP的Python版本依赖

ADCP是基于Python 2编写的程序，因此配套的numpy版本需要与该Python环境严格匹配。使用系统包管理器（如mamba）安装的numpy可能不兼容ADCP自带的Python 2。

---

## 7. 检查Python Unicode版本

为确保安装兼容的numpy版本，需使用ADCP目录下的Python执行以下命令检测Unicode版本：
${adcp_path}/bin/python -c "import sys;print(sys.maxunicode)"

---

## 8. Unicode版本数值解读

命令执行结果若显示65535则表示UCS2构建，若显示1114111则表示UCS4构建。如果输出为1114111（UCS4），则需要手动重新编译安装numpy。

---

## 9. 卸载原有Numpy

手动安装兼容版本前，需先卸载当前环境中可能存在的numpy，命令为：
${adcp_path}/bin/python -m pip uninstall numpy

---

## 10. 下载Numpy源代码

需下载特定版本的numpy源代码进行编译，推荐版本为1.16.6，命令如下：
wget https://github.com/numpy/numpy/archive/v1.16.6.tar.gz

---

## 11. 解压与编译Numpy

解压源码包并进入目录后，必须使用ADCP自带的Python进行编译，而非系统默认Python。操作命令如下：
tar -xvzf v1.16.6.tar.gz
cd numpy-1.16.6
${adcp_path}/bin/python setup.py build

---

## 12. 编译依赖处理

在执行setup.py build过程中，如果提示缺少cython，需使用对应的Python版本通过pip安装cython。

---

## 13. 编译完成验证

完成编译后，再次运行agfr命令将不再报错，程序可顺利执行并生成affinity map。

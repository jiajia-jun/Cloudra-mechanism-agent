---
key: t38871
title: EasyShermo: ���µ�ȫ�Զ��� Shermo ���������Ľű�
url: http://bbs.keinsci.com/thread-38871-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2023
cards: 9
---

# EasyShermo: ���µ�ȫ�Զ��� Shermo ���������Ľű� — 知识卡片

## 1. SHERMO 热力学计算的高精度单点能输入需求

Shermo 计算热力学数据时默认使用优化计算提供的电子能量，若此精度不足，需通过修改配置文件或命令行参数指定更高精度的单点能。一种方式是修改 settings.ini 文件中的 E= 参数值为对应体系的电子能；另一种方式是在运行 Shermo 时添加 -E xxx 参数。正确输入高精度电子能可确保最终热力学数据的准确性。

---

## 2. EasyShermo 自动化工具的设计目的

EasyShermo 是一个基于 Python 编写的脚本工具，旨在解决通过 Shell 脚本批量调用 Shermo 时匹配优化结构与高精度单点能的繁琐问题。该工具能够全自动地提取高精度单点能，并将其与对应的优化频率计算文件匹配，随后调用 Shermo 计算热力学数据并将结果写入文资料件。使用此工具可实现全自动化流程，仅需整理计算文件和配置参数即可。

---

## 3. 单点能提取规则与关键字匹配

EasyShermo 支持从 Gaussian 或 ORCA 的输出文件中提取电子能量。对于 ORCA 文件，脚本通过正则表达式提取 "FINAL SINGLE POINT ENERGY" 之后的数值。对于 Gaussian 文件，脚本按优先级查找特定关键字：若存在 "CCSD(T)=" 则提取该值用于 CCSD(T) 计算；若不存在则查找 "MP2=" 提取 MP2 能量；若仍不存在则查找 "HF=" 提取 HF 能量。

---

## 4. EasyShermo 的运行逻辑与文件匹配策略

EasyShermo 首先读取所有单点计算文件中的电子能量并按顺序存储在列表中。随后按顺序处理优化频率文件，对每个优化文件执行 Shermo n_opt.out -E xxx 命令，其中 xxx 为之前提取的对应高精度单点能。该过程要求优化文件与单点文件的命名顺序（如前缀数字）必须一一对应，脚本即利用此顺序关系将能量与文件关联。

---

## 5. EasyShermo 的程序构成与文件说明

EasyShermo 由 main.py、config.py、easyShermo.py、settings.ini 及相关数据文件组成。main.py 作为程序入口；config.py 用于读取配置文件 settings.ini；easyShermo.py 包含核心逻辑，实现文件读取、能量提取及调用 Shermo。settings.ini 包含 Shermo 运行参数及路径设置，其中约 90% 的参数与原版 Shermo 的 settings.ini 保持一致。

---

## 6. EasyShermo 配置文件中的路径与软件设置

settings.ini 文件需设置 Shermo 可执行文件的路径以及单点计算所使用的程序类型。用户需指定 "shermoPath" 为 Shermo.exe 的绝对路径，并根据实际情况设置 "spFile" 参数：值为 1 代表使用 Gaussian 进行单点计算，值为 2 代表使用 ORCA。

---

## 7. EasyShermo 的目录结构与输入文件要求

使用 EasyShermo 需在当前目录下创建 opt 和 sp 两个文件夹。所有优化频率输出文件（如 n_opt.out）需放置于 opt 文件夹中，所有单点计算输出文件（如 n_sp.out）需放置于 sp 文件夹中。脚本会自动读取这两个目录下的文件进行匹配处理。

---

## 8. EasyShermo 的执行与输出文件生成

在配置好目录和参数后，运行命令 `Python main.py` 即可启动自动化流程。程序运行过程中会在控制台输出相关信息，包括从 sp 文件读取的能量及正在执行的 Shermo 命令。运行结束后，output 文件夹中会生成与优化输入文件同名的 txt 文件（如 n_opt.txt），其中包含 Shermo 计算得到的完整热力学数据。

---

## 9. EasyShermo 的 Windows 可执行版本与示例下载

除 Python 脚本版本外，EasyShermo 还提供了使用 Go 语言编译的 Windows 可执行程序，用户无需安装 Python 环境即可直接双击运行。相关的程序安装包及包含计算输入输出文件的示例压缩包均可从 GitHub 页面或帖子的附件中下载获取。

---
id: 199
title: 产生Gaussian的IRC和SCAN任务每个点的波函数文件的工具：IRCsplit和SCANsplit
url: http://sobereva.com/199
domain: Gaussian使用
topic: IRCsplit与SCANsplit提取路径点波函数
cards: 10
---

# IRCsplit与SCANsplit提取路径点波函数 — 知识卡片

## 1. IRCsplit和SCANsplit程序的功能

IRCsplit和SCANsplit程序用于将Gaussian产生的IRC路径或SCAN（刚性扫描）任务中每个点的坐标提取出来，生成一批新的单点任务输入文件。通过批量执行这些文件，可以获得路径上所有点的.wfn或.chk文件，以便利用Multiwfn等程序分析反应过程中电子结构的变化。

---

## 2. IRC任务输出文件的注意事项

使用IRCsplit处理IRC任务时，Gaussian输入文件的Route section中不要使用geom=check关键词，否则输出信息会与平时不符而无法被程序识别。

---

## 3. IRC任务单点模板文件的编写规则

用户需创建一个与IRC任务对应的普通单点文件作为模板，文件中不要写%chk，Route section只定义理论方法和基组（可添加vshift等帮助收敛的关键词）。坐标部分必须是过渡态结构的笛卡尔坐标，文件末尾必须空两行。

---

## 4. IRCsplit程序的交互操作步骤

启动IRCsplit后，依次输入IRC输出文件路径、单点模板文件路径、输出文件类型选项（1为.wfn，2为.chk，3为两者皆有）、输出路径及名称前缀。随后输入前后方向需要提取的点数（如20,20），最后回车退出。

---

## 5. 提取IRC点数的参数规则

在IRCsplit中输入点数时（例如20,20），程序将提取过渡态结构加上正向最近的20个点和逆向最近的20个点，总共41个结构。输入的点数不能超过实际计算中产生的点数。

---

## 6. IRCsplit生成文件的批量执行方法（Windows）

在Windows下，将script目录下的runall.bat拷贝至存放.gjf文件的目录并双击运行，可调用G09执行所有.gjf文件；运行chk2fch.bat可将生成的.chk文件转换为.fch文件。使用前需将Gaussian目录添加至PATH环境变量并设置GAUSS_EXEDIR环境变量。

---

## 7. IRCsplit生成文件的批量执行方法（Linux）

在Linux下，将script下的runall.sh和chk2fch.sh拷贝至相应目录并运行，即可调用Gaussian计算当前目录下所有.gjf文件，并调用formchk将.chk文件转换为.fch文件。

---

## 8. IRCsplit处理rcfc关键词的限制

如果在IRC任务中使用了rcfc关键词，由于过渡态结构信息不会出现在输出文件中，IRCsplit生成的对应于过渡态结构的.gjf文件将会是空的，需要用户自行处理。

---

## 9. SCANsplit程序的功能与限制

SCANsplit程序用于处理Gaussian的SCAN任务，使用方法与IRCsplit几乎一致，但仅支持刚性扫描（Rigid Scan），不支持柔性扫描。

---

## 10. SCANsplit程序的交互操作示例

启动SCANsplit后，依次输入SCAN任务输出文件路径（如examples\H2O2.out）、对应的单点模板文件路径（如examples\H2O2_SP.gjf）、输出文件类型选项（如2仅生成.chk）、输出路径及名称前缀，最后回车退出。

---
id: 292
title: GaussView保存输入文件时内坐标变量不用字母表示的解决方法
url: http://sobereva.com/292
domain: Gaussian使用
topic: GaussView内坐标变量字母化及Multiwfn替代方案
cards: 5
---
## 1. GaussView内坐标变量显示数字的问题

GaussView保存Gaussian输入文件时，若取消write cartesian选项以保存内坐标形式，内坐标变量可能直接显示为数字而非字母变量。这表现为原子连接行直接列出具体键长和键角数值。
- 问题是GaussView软件不人性化的表现，没有直接选项控制变量用字母表示。

---

## 2. GaussView内坐标字母变量的变通解决法

解决GaussView内坐标变量显示数字的方法是先将体系保存为.mol等其他格式，随后重新载入该文件，再保存为Gaussian输入文件。重新载入后保存的文件内坐标将显示为字母变量。
- 操作步骤为先存为.mol格式，载入后再次保存，即可得到含字母变量（如B1、A1）的内坐标输入文件。

---

## 3. Multiwfn生成Gaussian输入文件的功能

Multiwfn程序可用于生成Gaussian输入文件，支持从大量格式（如xyz/pdb/pqr/mol/mol2/cif/gjf/wfn/cub/fch/molden/mwfn等）载入结构信息。若将settings.ini文件里的iloadGaugeom设为1，还可直接从Gaussian输出文件里载入结构信息。
- Multiwfn可在http://原作者.com/multiwfn免费下载，完整介绍见http://原作者.com/379。

---

## 4. Multiwfn生成Z矩阵格式输入文件

在Multiwfn中载入结构信息后，输入gi进入Gaussian输入文件保存界面。若先输入zmat命令，再输入文件路径，则生成的Gaussian输入文件为内坐标形式且所有几何参数通过变量表示。
- 此功能在2021-Jul-9及以后更新的版本中才支持。

---

## 5. Multiwfn生成带数值的Z矩阵格式输入文件

在Multiwfn的Gaussian输入文件保存界面中，若先输入zmat2命令，再输入文件路径，则生成的Gaussian输入文件也是内坐标形式，但几何参数直接以变量值形式表示而非字母变量。
- 此功能在2021-Jul-9及以后更新的版本中才支持。

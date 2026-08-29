---
key: t35694
title: �������ļ���cp2k molden file����Cell��Nval section
url: http://bbs.keinsci.com/thread-35694-1-1.html
domain: 其他量化软件
source: keinsci
year: 2023
cards: 7
---

# �������ļ���cp2k molden file����Cell��Nval section — 知识卡片

## 1. CP2K Molden 文件与 Multiwfn 的兼容性问题

CP2K 输出的 molden 文件默认包含 [Cell] 和 [Nval] section，直接导入 Multiwfn 可能会导致程序崩溃。
- 解决此兼容性问题需要使用后处理脚本对文件进行修补。

---

## 2. cp2kMoldenPostProcessingToMultiwfn.py 的运行方式

脚本 cp2kMoldenPostProcessingToMultiwfn.py 提供了多种使用方式以修复 molden 文件。
- 方式一：在 IDE 中运行脚本模块，需设置变量 moldenFileName 为待处理 molden 文件的绝对路径。
- 方式二：通过命令行运行 `python cp2kMoldenPostProcessingToMultiwfn.py -i [molden文件绝对路径]`，支持 `--help` 查看帮助。

---

## 3. 伪势参数的配置规则

配置脚本需指定 CP2K 数据库路径以正确获取元素价电子数信息。
- 参数 `pseudoPotentialFile` 仅支持 'GTH_POTENTIALS'。
- 参数 `pseudoPotentialPath` 必须填写 CP2K 数据目录的绝对路径，且路径中的反斜杠建议使用双反斜杠转义（如 `D:\\cp2k-2023.1\\data\\`）。

---

## 4. 函数与赝势类型设置

脚本配置项 `functional` 和 `boolSmallCorePseudoPotential` 用于定义计算参数。
- `functional` 对应 DFT 计算所用的方法（如 PBE）。
- `boolSmallCorePseudoPotential` 决定是否使用小核赝势，True 为使用，False 为不使用。

---

## 5. 赝势数据库生成器路径

`pseudoPotentialDatabaseGenerator` 指向用于读取赝势文件的脚本 `_cp2kImportNumOfValenceElectrons.py`。
- 此项通常无需修改，除非为了支持更多种类的赝势文件格式。
- `pPDGPath` 需设置为该生成器脚资料件所在的绝对路径。

---

## 6. 输入输出路径配置

路径配置决定了 molden 文件的读取与输出位置。
- `moldenFileName` 设定待处理的 molden 文件绝对路径；若通过 stdin 提供文件，则 stdin 优先级高于此设置。
- `outMoldenPath` 指定添加 [Nval] 信息后生成的新 molden 文件的保存目录。

---

## 7. Multiwfn 调用开关

配置项控制脚本是否在处理完 molden 文件后自动调用 Multiwfn。
- `multiwfnPath` 需设定为 Multiwfn 程序所在的安装目录。
- `boolCallMultiwfn` 设为 True 时启用自动调用，False 时不调用。

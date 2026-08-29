---
key: t59758
title: gau_g_xTB�������糤��gau_xtb ˼·��չ�� g-xTB ���ܼ��� Gaussian External �ӿ�
url: http://bbs.keinsci.com/thread-59758-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2026
cards: 18
---

# gau_g_xTB�������糤��gau_xtb ˼·��չ�� g-xTB ���ܼ��� Gaussian External �ӿ� — 知识卡片

## 1. g-xTB 与 Gaussian 联用的基本原理

g-xTB 结合了 Gaussian 的几何优化、过渡态搜索控制功能与 xTB 的快速半经验计算优势。在此模式下，Gaussian 负责优化步进、过渡态及频率扫描流程控制，xTB 则负责提供能量、梯度和 Hessian。该方式在执行常规 DFT 计算前，可用于以较低系统成本构建构型、频率及过渡态的初始结构。

---

## 2. 接口脚本 gau_xtb 的作用

gau_xtb 脚本作为连接器，支持通过 Gaussian External 接口调用 g-xTB 执行程序，并将 g-xTB 产生的繁重计算参数反馈给 Gaussian。用户在使用时需将 Gaussian 的 opt、freq 和过渡态筛选计算与 g-xTB 提供的梯度及 Hessian 相结合。

---

## 3. 软件依赖与版本信息

该接口工具要求 xTB 可执行文件支持 --gxtb 选项。当前版本适配的具体环境为：g-xTB distribution label v2.0.1，主执行文件版本为 xtb version 6.7.1 (26dd68d)，且日期为 2026-05-14。

---

## 4. 环境变量 GXTB_HOME 的设置

解压安装包后，需设置环境变量 `GXTB_HOME` 指向 g-xTB 的安装根目录（例如 `export GXTB_HOME=/path/to/gxtb-install-root`）。脚本默认调用该路径下的 `$GXTB_HOME/bin/xtb` 可执行文件。

---

## 5. Gaussian 坐标文件转换脚本

目录下的 `scripts/build_genxyz.sh` 脚本用于在当前目录上编译将 Gaussian 输出坐标转换为 xyz 文件的工具。这是进行数据转换的前置步骤。

---

## 6. 工具安装与测试命令

安装完成后，可运行 `scripts/smoke_check.sh` 进行自检。若仅查看 wrapper 支持的参数选项，可执行 `/path/to/gau_g_xTB/xtb.sh --help`。

---

## 7. Gaussian 中的溶剂化结构优化输入示例

使用 g-xTB 进行 COSMO 溶剂化结构优化的 Gaussian 输入卡示例如下：`#p opt external="/path/to/gau_g_xTB/xtb.sh" --parallel 4 --solvent cosmo:ch2cl2 UGBS nosymm`。

---

## 8. Gaussian 中的频率计算输入示例

使用 g-xTB 进行频率计算的 Gaussian 输入卡示例如下：`#p freq external="/path/to/gau_g_xTB/xtb.sh" --parallel 4 --solvent cosmo:ch2cl2 UGBS nosymm`。

---

## 9. 过渡态搜索与筛选输入示例

使用 g-xTB 进行过渡态筛选及优化的 Gaussian 输入卡示例如下：`#p opt(ts,calcfc,noeigen,nomicro) external="/path/to/gau_g_xTB/xtb.sh" --parallel 4 --solvent cosmo:ch2cl2 UGBS nosymm`。

---

## 10. 导数层级与对应参数

Gaussian 在调用外部程序前会写入导数级别，xtb.sh 内部对应的参数映射为：derivative level 0 对应 --sp，derivative level 1 对应 --grad，derivative level 2 对应 --hess --grad。

---

## 11. 传递 g-xTB 特定参数的方法

若需在 g-xTB 模式下修改特定数值，可使用 --xtb-arg 将参数直接传递给底层程序，例如：`--xtb-arg --etemp --xtb-arg 300`。溶剂等隐式模型参数（如 `--solvent cosmo:ch2cl2`）也会通过 wrapper 传递给底层程序。

---

## 12. 压缩包内容结构

压缩包解压后的目录包含核心文件与子目录：`gau_g_xTB/xtb.sh`（Gaussian 调用入口）、`extderi.py`（数据格式转换）、`src/`（Fortran 源码）、`scripts/`（构建与测试脚本）、`examples/`（示例输入）以及文档文件 `README.md`、`VERSION.md`、`NOTICE.md`。

---

## 13. extderi.py 与 genxyz 的功能

`extderi.py` 负责将 xTB/g-xTB 输出的能量、梯度和 Hessian 转换为 Gaussian External 接口所需的格式。`src/genxyz.f90` 和 `src/extderi.f90` 则是相应的 Fortran 转换器源代码。

---

## 14. 资源来源与致谢

该工具基于原作者老师（原作者.com）原 gau_xtb 的思路设计，利用 Gaussian External 接口连接 Gaussian 与 xTB。代码中的 Fortran gen/extderi lineage 功能归功于 Dr. Tian Lu。

---

## 15. 学术引用建议

研究者在发表论文时，建议引用原始接口文献：Tian Lu, gau_xtb: A Gaussian interface for xtb code, http://原作者.com/soft/gau_xtb (accessed month day, year)。

---

## 16. 故障排查：genxyz 未编译

若出现 genxyz 不可执行或未运行的情况，通常是因为未在当前目录下执行编译脚本 `scripts/build_genxyz.sh`。

---

## 17. 故障排查：底层 xTB 参数不兼容

若底层 xTB/g-xTB 不支持某些隐式模型参数（如 --gxtb），程序会报错退出。此时需检查 `$GXTB_HOME/bin/xtb` 是否支持相应选项，或调整 Gaussian External 调用参数。

---

## 18. 日志文件位置

调试或出错时，可检查当前目录下的 `gau_xtb_command.log`、`xtbout` 和 `xtb.err` 文件以获取详细信息。

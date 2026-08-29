---
key: t26263
title: Basis Set Exchange��������Abse
url: http://bbs.keinsci.com/thread-26263-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2021
cards: 18
---

# Basis Set Exchange��������Abse — 知识卡片

## 1. Basis Set Exchange (BSE) 脚本简介与安装环境

Basis Set Exchange 脚本基于 BSE 的 API 开发，旨在替代频繁访问网站手动下载基组的繁琐过程。该脚本可在 Linux 和 Windows 系统下运行，要求使用 Python 3.6 或以上版本，推荐通过 Anaconda 安装 Python 环境。

---

## 2. 安装 basis_set_exchange 库

使用 BSE API 需先安装 Python 库，命令为 `pip install basis_set_exchange`。BSE API 官方文档提供了查询和获取基组的功能，安装此库后即可通过命令行调用 Abse.py 脚本进行后续操作。

---

## 3. Abse.py 脚本下载与路径配置

脚资料件需下载至本地目录（如 ~/scripts），并使用 `chmod +x` 赋予执行权限。需将脚本所在目录添加到系统 PATH 环境变量中（通过修改 ~/.bashrc 并 source），以便全局直接使用 `Abse.py` 命令。

---

## 4. 验证 Abse.py 安装与查看帮助

执行命令 `Abse.py -h` 可验证脚本是否安装成功，并查看完整的帮助信息和可用参数列表。

---

## 5. 通过元素列表筛选基组

使用 `-e` 参数指定体系中的元素（如 "c,h,o,n,s,co,ir"），结合 `-l` 参数可列出特定类型的基组。例如 `Abse.py -e "c,h,o,n,s,co,ir" -l "t:ecp"` 将列出包含这些元素的所有含有效势（ECP）的基组。

---

## 6. 通过 gjf 文件筛选基组

使用 `-f` 参数读取当前目录下指定 gjf 文件中的元素信息，并结合 `-l` 参数进行筛选。例如 `Abse.py -f "*.gjf" -l "s:tz;t:noecp"` 将列出 gjf 文件中所有元素对应的三重 Zeta（tz）且不含赝势的基组。

---

## 7. 基组信息概览参数说明

查看基组详情时，输出包含以下关键信息：BF/GP（基函数/高斯原函数数量）、contractions（收缩情况，反映 Zeta 阶数）、min_exponents X 100（最小指数乘以 100，用于判断弥散性）、以及计算耗时预估。其中 BF 影响后 HF 计算耗时，GP 影响 DFT 耗时。

---

## 8. 混合基组设置方法

支持为不同元素指定不同的基组，使用分号和冒号分隔。例如 `Abse.py -e "C,H,O,N,Cl,I,Hg,Au" -b "cc-pvdz;I,Hg,Au:cc-pvdz-pp;ecp:I:lanl2dz"` 表示大部分元素用 cc-pvdz，重元素用赝势基组，且特定元素单独指定 ECP。

---

## 9. 将基组写入 gjf 文件

使用 `-o gjf` 参数可将选定基组写入 gjf 文件末尾。例如 `Abse.py -f "*.gjf" -b "jun-cc-pvdz" -o gjf` 会将基组追加到当前目录所有 gjf 文件末尾，若文件包含 `[autobse]` 标记则会自动替换。

---

## 10. 生成独立的 gbs 基组文件

使用 `-o gbs` 参数可将基组输出为独立的 .gbs 文件，便于在 Gaussian 中通过 `@` 符号调用。例如 `Abse.py -e "5-10,Ir" -b "cc-pvdz;Ir:cc-pvdz-pp" -o gbs` 会将相关元素的基组写入 autobse.gbs 文件。

---

## 11. 同时生成 gbs 文件并修改 gjf 引用

使用 `-o gjfgbs` 可生成 .gbs 文件并复制一份 gjf 文件（可通过 `-a` 重命名），在其中添加 `@filename.gbs` 行。例如 `Abse.py -f "*.gjf" -b "def2-tzvpd" -o gjfgbs:def2tzvpd -a _def2TZVPD` 会生成引用基组文件的新 gjf 输入文件。

---

## 12. 导出其他格式的基组文件

通过 `-o` 参数指定格式前缀和文件名，可导出 BSE 支持的其他格式。例如 `Abse.py -e "C" -b "may-cc-pvdz" -o gau:` 输出 Gaussian 格式到标准输出；`Abse.py -f "abc*.gjf" -b "pc-2" -o o:` 输出 ORCA 格式。

---

## 13. 导出基组参考文献

使用 `-o ref:` 可导出基组对应的参考文献，支持 txt、endnote、bib 等格式。例如 `Abse.py -e "C" -b "ano-r" -o ref:bib:anor` 会将 C 元素 ANO-R 基组的参考文献以 BibTex 格式保存到 anor.bib 文件。

---

## 14. 查询特定基组的详细信息

使用 `-i` 参数可直接查询特定基组的详细信息，无需指定元素。例如 `Abse.py -i "def2-SV(P)"` 可显示该基组的描述、元素范围、Zeta 阶数及包含的元素等元数据。

---

## 15. 查询特定族或类别的基组

使用 `-i` 参数查询基组族名，可了解该系列下的目标基组、适用元素范围和用途。例如 `Abse.py -i "dunning_pp"` 可查看 Dunning 赝势基组系列的相关信息。

---

## 16. 参数 -l (list) 的详细筛选规则

`-l` 参数支持按 substring（名称包含字符串）、type（类型如 gto/ecp）、family（族如 dunning）、role（角色如 orbital/fit）进行筛选。例如 `-l "f:dunning_dk"` 查看属于 Dunning_DK 族的基组；`-l "t:nogto"` 仅列出赝势基组。

---

## 17. 参数 -o (output) 与文件名处理

`-o` 用于指定输出类型（gjf, gbs, ref 等），若格式后跟冒号和文件名则保存到文件，否则输出到屏幕或默认文件名（如 autobse.gbs）。使用 `-a` 参数可为输出文件添加后缀，避免覆盖原文件（如 `-a "_new"`）。

---

## 18. 基组去收缩与通用化选项

使用 `--basis_options` 可设置基组的高级处理选项，如 `ucontract_general`（去收缩为通用基组）、`uncontract_spdf` 等。这些选项默认为 False，仅在需要特殊处理基组结构时开启。

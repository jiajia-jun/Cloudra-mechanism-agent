---
key: t20052
title: Multiwfn���ָ���С���� MUA 3.0
url: http://bbs.keinsci.com/thread-20052-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2020
cards: 14
---

# Multiwfn���ָ���С���� MUA 3.0 — 知识卡片

## 1. MUA 3.0 脚本功能与用途

MUA (Multiwfn Update Assistant) 3.0 是一个用于 Multiwfn 的辅助脚本，支持 Linux 和 Windows 平台。该脚本旨在简化 Multiwfn 的更新流程，自动处理相关配置。版本发布日期为 2021/03/24。

---

## 2. MUA 3.0 -p 参数修改配置

使用 -p 选项可以修改 settings.ini 中的指定参数或执行相关操作。该选项支持显示帮助信息、设置静默模式和指定线程数等功能。
- `mua -p ?`
- `mua -p "isilent 0"`
- `mua -p 'nthreads 12 iuserfunc 23'`

---

## 3. MUA 3.0 -e 参数编辑文件

使用 -e 选项可以直接编辑或处理指定的输入文件路径。使用时需提供具体的文件名作为参数。
- `mua -e ?`
- `mua -e CP2K_diamond_2x2_DZVP-MOLOPT.inp`

---

## 4. MUA 3.0 -i 参数插入数据

使用 -i 选项可以在 [Atoms] 区域之前插入指定数据。该功能适用于需要预处理输入文件的场景。

---

## 5. MUA 2.0 脚本简介

MUA (Multiwfn Update Assistant) 2.0 是一个整合了 Linux 和 Windows 版本的 All-in-One 脚本。发布于 2020/10/31，支持更新 Multiwfn、下载 PDF 文档以及处理新旧版本的覆盖与备份。

---

## 6. MUA 2.0 基本使用步骤

下载 MUA 脚本后，需进入脚本所在目录并执行 bash 命令。更新完成后，需重新登录终端或 source ~/.bashrc 以使环境变量生效。
- `cd <path-to-MUA>`
- `bash ./MUA`
- `bash ./MUA -d1 -w`
- `source ~/.bashrc`

---

## 7. MUA 2.0 脚本配置注意事项

使用脚本前应检查并修改图示中的偏置设置，特别是解压缩工具的路径（默认为 unzip 或 7z）。在双系统或多系统环境下，需确保脚本识别到正确的平台系统，同一台机器只需配置一次。

---

## 8. Windows 环境下执行 Linux 命令

在 Windows 环境下（如使用 MobaXterm 或 cmder 等终端），可以直接执行 Linux 命令。若需解压 rar 文件，需安装 7-Zip 并创建软链接到 /usr/bin/7z。
- `ln -s "C:\Program Files\7-Zip\7z.exe" /usr/bin/7z`
- `7z x <foo.rar>`

---

## 9. MUA 常用选项与参数说明

MUA 脚本提供多种选项用于控制更新、设置路径和检查状态。常用选项包括检查更新、下载最新版、指定平台（Linux/Windows）、显示用户配置及列出下载源。
- `mua`
- `mua -h`
- `mua -c`
- `mua -d1`
- `mua -SL`
- `mua -SW`
- `mua -M`
- `mua -U`
- `mua -L`

---

## 10. MUA 路径与系统设置选项

MUA 支持通过命令行参数指定外部程序路径和系统设置，包括线程数、OpenMP 栈大小、Multiwfn 路径、ORCA/Gaussian 执行目录及解压命令。路径中若包含空格，需使用引号括起来，且在 Linux 和 Windows 下用法通用。

---

## 11. MUA 历史版本 1.1 更新内容

版本 1.1 (2020/10/29) 新增了 -w 选项，用于在更新时交互式询问用户是否使用脚本更新 Multiwfn。新增 -c 选项用于版本检测，并建议使用 alias (如 sob) 以简化操作。
- `bash ./config_Multiwfn_settings.sh -d 1 -w`

---

## 12. Windows 专用配置脚本 config_Multiwfn_settingsWin.sh

Windows 平台可使用专门的配置脚本 `config_Multiwfn_settingsWin.sh`。该脚本支持设置 Gaussian 和 ORCA 的路径、线程数及栈大小，并支持通过 alias (如 sobWin) 调用。
- `bash ./config_Multiwfn_settingsWin.sh -d 1`
- `bash ./config_Multiwfn_settingsWin.sh -d 1 -w -g 'C:\\G16W\\' -o 'C:\\orca new\\' -n 2 -s 200000000`

---

## 13. config_Multiwfn_settings.sh 1.0 版本参数

1.0 版本脚本支持通过命令行参数直接配置 Multiwfn 的 settings.ini 文件。支持的参数包括 -g (Gaussian 目录)、-o (ORCA 目录)、-m (Multiwfn 目录)、-r (用户根目录) 和 -d (下载指定 Zip 文件，1 为默认)。
- `./config_Multiwfn_settings.sh -d 1`
- `./config_Multiwfn_settings.sh -r ~`

---

## 14. 安装更新后的备份机制

脚本安装新版本成功后，会自动将旧的 Multiwfn 备份为 Multiwfn-old。用户应在安装成功后检查配置信息，并确认无误后手动删除旧备份。

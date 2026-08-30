---
key: t49082
title: Gaussian�Զ������ύ�ű�
url: http://bbs.keinsci.com/thread-49082-1-1.html
domain: Gaussian使用
source: keinsci
year: 2025
cards: 14
---

# Gaussian�Զ������ύ�ű� — 知识卡片

## 1. Gaussian 自动提交脚本功能

该脚本适用于安装了 SLURM 系统的环境，用于解决无法排队提交 Gaussian 任务的问题，通过 Shell 脚本实现并行提交与管理。

---

## 2. 并发控制机制与临时文件

脚本不使用线程间通信或 wait 命令等待，而是通过临时文件 count.tmp 作为管道传递数据，并在任务结束后自动删除该文件。

---

## 3. MAXNUM 参数定义

MAXNUM 参数用于控制同时提交的任务数量上限，设置时需根据实际硬件资源情况调整，例如设置为 4。

---

## 4. ONLY_PARENT 参数定义

ONLY_PARENT 参数设为 1 时仅遍历当前目录下的 gjf 文件，设为 0 时则执行当前目录及其子文件夹下的 gjf 文件。

---

## 5. 脚本执行权限与后台运行

需使用 chmod +x 命令赋予 Shell 脚本执行权限，并使用 ./runparallel & 方式在后台运行，运行时会提示正在计算中的文件。

---

## 6. 超配计算问题

超配计算即总使用核数超过物理核数（如 128 核系统跑 4 个 64 核任务），可能导致计算效率降低，脚本需对此进行限制。

---

## 7. v2.1 版本更新：单文件多任务检测

v2.1 版本增加逻辑判断：若单个文件提交数（如链式任务）导致当前核心数加上该文件所需核心数超过总上限，则不再提交该任务。

---

## 8. v2.1 版本更新：核心数识别机制

脚本通过读取 gjf 文件中的 %nproc 或 %nprocshared 关键字判断任务所需核心数（不区分大小写）；若未指定，则使用 DEFAULT_CORES 默认值。

---

## 9. v10.2 版本来源

v10.2 版本脚本参考了北京导航科训的内容及 tsmonitor.sh 脚本，结合了 highlight 的功能，支持显示脚本开始和结束的信息。

---

## 10. 脚本安装路径与配置

将脚本放置在 /home/yourname/Script 目录，并修改 .bashrc 文件添加别名（如 alias rg16="..."），随后执行 source ./bashrc 或重新登录生效。

---

## 11. DEFAULT_CORES 参数

DEFAULT_CORES 参数用于指定当 gjf 文件中未包含 %nproc 或 %nprocshared 关键字时，任务默认使用的 CPU 核心数。

---

## 12. LEFT_CORES 参数

LEFT_CORES 参数用于预留 CPU 核心数以防止系统过载，脚本会确保剩余可用核心数不低于 LEFT_CORES 值。

---

## 13. ENABLE_NOTIFICATION 参数

ENABLE_NOTIFICATION 参数设为 1 时开启通知功能，需在脚本 221/226 行替换 device_key 等信息，默认设为 0 即关闭通知。

---

## 14. rg16 脚本调用方式

通过别名 rg16 可直接执行脚本，支持在当前目录处理 gjf 文件、指定目录（-d 参数）或指定特定文件列表（-f 参数），并建议结合 nohup 在后台运行。

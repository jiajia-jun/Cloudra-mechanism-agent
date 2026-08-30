---
key: t27273
title: Gaussian TDDFT����̬����/͸��̬����׷�ٽű�
url: http://bbs.keinsci.com/thread-27273-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2022
cards: 3
---

# Gaussian TDDFT����̬����/͸��̬����׷�ٽű� — 知识卡片

## 1. TDDFT态间跃迁追踪脚本

使用含时密度泛函理论(TDDFT)进行构型优化时，设置 `nstates=5` 和 `root=1` 可以同时追踪前5个激发态的势能面。该脚本能够提取 Gaussian 输出文件(out文件)中 S1 至 S5 激发态的能量数据并生成 txt 文件。生成的数据可直接导入 Excel 软件进行作图分析。

---

## 2. 脚本使用路径限制

states_tracker.sh 脚本仅适用于处理无空格的英文路径下的目标文件。在使用前需确保文件路径符合无空格且为英文的要求，否则脚本可能无法正常运行。

---

## 3. 脚本权限设置

在 Linux 或 Unix 环境下使用 states_tracker.sh 脚本前，必须对脚资料件赋予执行权限。用户可通过 `chmod` 命令修改文件权限，或将脚本所在目录添加至环境变量 PATH 中以便直接调用。

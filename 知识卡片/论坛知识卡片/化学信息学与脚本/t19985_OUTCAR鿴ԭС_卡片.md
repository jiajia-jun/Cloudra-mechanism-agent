---
key: t19985
title: ������OUTCAR�鿴ԭ��������С�ű�
url: http://bbs.keinsci.com/thread-19985-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 3
---

# ������OUTCAR�鿴ԭ��������С�ű� — 知识卡片

## 1. extforce.sh 脚本原理

该脚本的核心思路分为两步：首先从 OUTCAR 文件中提取所有的 TOTAL-FORCE 行信息，即获取每个原子的受力向量；其次利用 for 循环调用 screenforce.py 逐一筛选每个原子的受力情况。脚本会对比原子受力与 EDIFFG 阈值，将未达到收敛标准的原子编号存入 lt_ediffg_${i}.dat 文件中（i 为对应原子序号），生成的数据文件可使用 p4vasp 进行查看以辅助分析。

---

## 2. 使用前的参数配置

在使用脚本前，需在 extforce.sh 中设置体系内的原子总数变量 N_atoms；在 screenforce.py 中设置相应的力收敛标准变量 ediffg。如果系统环境仅支持 python2，需将 screenforce.py 中的 print 语法修改为 Python 2 兼容格式。

---

## 3. 脚本执行要求与命令

执行脚本需确保 extforce.sh、screenforce.py 与 OUTCAR 文件位于同一目录下。在满足环境要求的前提下，通过执行命令 ./extforce.sh 即可运行脚本。

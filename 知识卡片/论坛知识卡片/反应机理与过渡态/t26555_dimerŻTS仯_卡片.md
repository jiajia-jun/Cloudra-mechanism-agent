---
key: t26555
title: ���dimer�����Ż�TS�����仯��һ��С�ű�
url: http://bbs.keinsci.com/thread-26555-1-1.html
domain: 反应机理与过渡态
source: keinsci
year: 2021
cards: 9
---

# ���dimer�����Ż�TS�����仯��һ��С�ű� — 知识卡片

## 1. 监测Dimer法过渡态优化的Shell脚本

此脚本旨在监测CP2K程序使用Dimer方法进行过渡态优化过程中的能量变化。脚本通过解析CP2K输出文件提取能量数据，计算相对于初始能量的差值，并调用Gnuplot绘制能量变化曲线。该方案适用于需要实时或事后分析过渡态搜索过程能量演化的场景。

---

## 2. 脚本依赖工具与运行环境

运行此监控脚本需要系统已安装Gnuplot工具以生成图表。在CentOS 8环境下可通过yum命令直接安装Gnuplot；推荐使用MobaXterm等支持图形窗口回显的终端工具进行远程Linux连接，以便在Windows端直接查看生成的图像。

---

## 3. 脚本存放与路径配置方法

将脚资料件放置于用户目录下的script文件夹（如~/script）中。需要在.bashrc配置文件中添加环境变量export PATH=$PATH:/home/xxx/script，从而实现在任意目录下直接调用DMmonitor.sh脚本。

---

## 4. 提取初始体系总能量的命令

命令`grep ENERGY ${inf} |head -1|awk '{print NR-1,"\t",$9}' > energy.txt`用于提取输出文件中的第一个SCF能量作为初始参考能量。根据论坛经验，此处的能量通常对应于Dimer优化开始前的rotations步骤中的第一个能量值，取文件第一行数据即可满足需求。

---

## 5. 提取过渡态优化步骤能量的命令

命令`grep "Informations at step" ${inf} -B 12|grep ENERGY |awk '{print NR,"\t",$9}' >> energy.txt`用于提取Dimer优化过程中的能量数据。通过-B 12参数向前回溯12行来抓取每个优化步骤前的能量状态，awk命令中的print NR部分用于记录优化步数。

---

## 6. 计算能量差值与单位转换

命令`cat energy.txt | awk 'NR==1{a=$2} NR>1{print NR-1,"\t",($2-a)*27.2114}' > deltaE.txt`负责计算每一步过渡态优化能量与初始能量的差值。脚本将energy.txt文件第一行设为初始能量并存入变量a，后续行计算与a的差值，并乘以27.2114将单位转换为电子伏特，输出仅包含优化步数编号（1, 2, 3...）。

---

## 7. Gnuplot绘图基本设置

脚本使用Gnuplot的`set multiplot layout 2,1`指令开启双图布局模式，并使用`set grid`添加网格线。`set xlabel "steps"`和`set ylabel "Energy Variation (eV)"`分别设置x轴和y轴的标签。

---

## 8. Gnuplot图像绘制参数详解

绘图命令`plot "deltaE.txt" u 1:2 w lp lw 1 lc rgb "dark-blue" ps 1 pt 7`中，u 1:2指定使用数据文件的第1列和第2列。参数w lp代表连线加点（linespoints），lw 1设置线宽，lc rgb "dark-blue"指定深蓝色线条，ps 1和pt 7分别控制点的大小和类型。

---

## 9. 图形窗口持久化与清理

Gnuplot执行参数`-p`（persist）确保在脚本执行结束后图形窗口不会自动关闭。脚本末尾使用rm命令删除生成的中间文件（energy.txt, deltaE.txt, last10E.txt），以避免下次运行时数据累积到当前文件中。

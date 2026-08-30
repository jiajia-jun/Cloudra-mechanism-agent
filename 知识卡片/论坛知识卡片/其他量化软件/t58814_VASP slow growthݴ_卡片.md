---
key: t58814
title: VASP slow growth�����ݴ���
url: http://bbs.keinsci.com/thread-58814-1-1.html
domain: 其他量化软件
source: keinsci
year: 2026
cards: 4
---

# VASP slow growth�����ݴ��� — 知识卡片

## 1. VASP慢增长方法的数据后处理

VASP慢增长方法产生的数据可以通过自定义脚本进行后处理。相关方法可参考 J. Am. Chem. Soc. 2020, 142, 5773-5777 中的描述。处理过程涉及提取特定数据并计算积分值。
- 脚本用于提取和计算反应坐标与能垒变化
- 参考文献出处

---

## 2. 数据提取与计算Shell脚本

以下Shell脚本用于提取REPORT文件中的cc和b_m数据，并计算积分值。脚本会提示输入ICONST设定的周期和需要查看的文件序号。
```sh
#!/bin/sh

grep cc REPORT | awk '{print $3}' > cc.dat

grep b_m REPORT | awk '{print $2}' > bm.dat

read -p "ICONST设定的周期: " period

read -p "需要查看的文件序号: " index

sed -n "${index}~${period}p" bm.dat > bm.txt

sed -n "${index}~${period}p" cc.dat > cc.txt

first=$(head -n1 cc.txt)

last=$(tail -n1 cc.txt)

echo -e "\n"

echo "处理完成，数据已保存到 integral.dat"

echo "从 $first Å 到 $last Å"

paste cc.txt bm.txt | awk 'NR==1 {x_prev=$1;y_prev=$2;sum=0;max=0;max_x=$1;print $1,$2,0;next} {dx=$1-x_prev;sum+=dx*($2+y_prev)/2;if(NR==2||sum>max){max=sum;max_x=$1} print $1,$2,sum;x_prev=$1;y_prev=$2} END {printf "Max Integral: %.6f eV at x = %.6f Å\n",max,max_x>"/dev/stderr"}' > integral.dat
```
- 脚本内容及文件名 (REPORT, cc.dat, bm.dat, integral.dat)
- 使用 read 获取用户输入 period 和 index
- 使用 sed 和 awk 进行数据处理与数值积分
- 输出最大积分值及其对应的 x 坐标到 stderr

---

## 3. 脚本使用参数与输入

运行脚本时需要输入两个参数。第一个参数对应ICONST文件中设定的周期，第二个参数对应需要查看的文件序号。
- 输入参数 x 对应 ICONST 设定的周期
- 输入参数 y 对应需要查看的文件序号
- ICONST 文件定义了约束设置
- 序号用于指定从第几行开始提取数据

---

## 4. 输出文件与绘图数据

脚本运行结束后会生成 integral.dat 文件，并打印最大值信息。该文件包含三列数据，分别用于绘图。
- 输出文件名为 integral.dat
- 终端会打印最大积分值及其位置
- 文件第一列为 cc 数据
- 文件第二列为 bm 数据
- 文件第三列为积分值
- 数据可直接导入 Origin 进行绘图

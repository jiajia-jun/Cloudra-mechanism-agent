---
id: 75
title: Potential energy distribution (PED)计算软件GAR2PED使用简介
url: http://sobereva.com/75
domain: 波函数与电子结构分析
topic: GAR2PED软件计算振动势能分布PED
cards: 9
---

# GAR2PED软件计算振动势能分布PED — 知识卡片

## 1. PED分析的基本概念与原理

PED(Potential energy distribution)是将简正振动模式分解的分析方法，可以获得每种基团特征振动模式产生的贡献百分比，从而容易地了解简正振动模式的本质特点。基本原理关系式为Λ=L^(T)FL，其中F是力常数矩阵，L是F的本征向量矩阵，Λ是对角矩阵diag(λ1,λ2...)。根据谐振势模型，第N种简正振动模式中内坐标i的力常数贡献量通过百分比公式η(i,N)=F(i,i)L(i,N)^2/(∑[j]F(j,j)L(j,N)^2)*100%表达。

---

## 2. PED计算公式与数学推导

PED分析基于公式Λ=L^(T)FL，将λ_N明确写成分量加和形式，即λ_N=Λ(N,N)=∑[i]∑[j]L^(T)(N,i)F(i,j)L(j,N)=∑[i]∑[j]F(i,j)L(j,N)L(i,N)。其中只有i=j的贡献才是最主要的，通过比较每个内坐标i的力常数对λ_N的贡献量F(i,i)L(i,N)^2就可以了解哪个内坐标对第N种简正振动模式有主要贡献。若不用内坐标，而改成以基团特征振动向量作为基，得到的就是各个基团各种特征振动模式对简正振动模式的贡献百分比。

---

## 3. GAR2PED软件的来源与兼容性

GAR2PED是读取Gaussian的Freq任务的archive信息来计算PED等信息的工具，由Martin和Alsenoy于1995年开发，支持的最重元素为Br。程序最初给Gaussian94用，虽然现在的Gaussian功能已扩充，但GAR2PED仍可以兼容最新的Gaussian09版本，主要用于计算PED。

---

## 4. GAR2PED在Windows下的编译方法

使用CVF6.5编译器编译，把所有.f文件（除了pullarc.f）加入工程里编译，结果命名为gar2ped.exe。清空工程后，将pullarc.f单独放进工程里，编译结果命名为pullarc.exe。注意！如果用于Windows版Gaussian结果分析，必须把pullarc的line29的1\\1\\改为1|1|，因为Windows版Gaussian的archive部分每项使用|分隔。

---

## 5. GAR2PED在Windows下的运行流程

将Gaussian的Freq任务（无需#P，不要把opt和freq任务一起执行）的运行结果命名为test.log，放在pullarc.exe所在目录下，运行pullarc test。如果屏幕正确显示archive信息的第一行，输入y，将得到test.xyz和test.arch。然后把test.arch里面的|全都替换成\。

---

## 6. GAR2PED在Linux下的运行流程

将Gaussian的Freq任务输出文件的archive部分的开头1\1\改成1|1|，执行pullarc test，得到test.xyz和test.arch。之后把test.arch中的开头的1|1|改回1\1\。之后运行gar2ped test读入test.arch并计算，若想算PED，在问skip internal part时输入n进入设定PED的界面。

---

## 7. GAR2PED的输出文件说明

运行gar2ped test后输出的test.out包含运行结果（含PED信息）。test.nomo.N.xyz是第N个简正振动模式动画每一帧坐标，可用VMD观看动画。test.nomos.xyz是所有简正振动模式向量。test.xyznew是根据当前力常数矩阵按牛顿法优化的下一步分子结构。test.apt.xyz是GAPT电荷。

---

## 8. GAR2PED中PED坐标的定义与操作

进入设定PED的界面后要依次定义3N-6或3N-5（线性）个坐标，每个简正振动模式将分解为这些坐标的贡献。操作包括：按1加入键伸缩项；按3输入原子序号加入甲基特征变形运动模式；按4输入原子序号加入sp3亚甲基变形运动模式；按13加入C-O-H弯曲振动模式；按2输入B、C原子序号加入扭转项。随时按-1查看还剩几个坐标没有定义，全部设好后输入0退出。

---

## 9. PED结果输出格式与解读规则

输出的POTENTIAL ENERGY DISTRIBUTION表格显示了每种简正振动模式由哪些设定的特征振动模式所组成，特征振动模式编号顺序就是输入时的顺序，表格中只输出贡献大于5%的成分。根据振动模式的主要成分可以指认它的特征，建议同时对照Gview的振动模式的动画来考察结果合理性。负号表示该基本振动模式相位在简正振动模式中是相逆的。

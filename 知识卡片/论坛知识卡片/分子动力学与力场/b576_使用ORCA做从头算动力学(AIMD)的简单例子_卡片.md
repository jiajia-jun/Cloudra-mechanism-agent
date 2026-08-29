---
key: b576
title: 使用ORCA做从头算动力学(AIMD)的简单例子
url: http://sobereva.com/576
domain: 分子动力学与力场
source: blog
year: 2020
cards: 21
---

# 使用ORCA做从头算动力学(AIMD)的简单例子 — 知识卡片

## 1. 从头算动力学(AIMD)的定义与优势

基于量子化学方法的动力学被称为从头算动力学。相比于基于经典力场的动力学，其关键优势在于精度高、普适性强、能够描述化学反应，代价是耗时相差多个数量级。

---

## 2. ORCA程序在AIMD方面的特点

ORCA量子化学程序具有做BOMD形式从头算动力学的功能，使用方便且本身做DFT效率高，是做孤立体系AIMD的首选程序之一。虽然不支持准经典动力学或基于原子距离自动结束任务等特性，但对于普通AIMD模拟，其易用性和速度优于Gaussian的ADMP或BOMD。

---

## 3. ORCA与周期性体系AIMD的适用性

ORCA只适合跑孤立体系的从头算动力学。如果是做周期性体系的从头算动力学，CP2K是最佳的选择。

---

## 4. ORCA 5.0版本AIMD功能的更新

对于ORCA 5.0及以后版本，Multiwfn自动设置的热浴是CSVR（优于Berendsen热浴），并且在run命令后支持CenterCOM选项以消除整体质心运动，此时不再需要constraint add center命令。

---

## 5. [Al(H2O)6]3+与NH3质子转移过程

在真空中，NH3向带正电的[Al(H2O)6]3+逐渐靠近，水上的一个质子转移到了氨气分子上形成NH4+，由于静电互斥，NH4+逐渐远离[Al(H2O)5(OH)]2+。

---

## 6. 使用Multiwfn生成ORCA的AIMD输入文件

启动Multiwfn载入结构文件，依次输入 oi（生成ORCA输入文件）、0（选择任务类型）、6（分子动力学），再选择计算级别（如1对应B97-3c），即可在当前目录生成ORCA的AIMD标准输入文件。

---

## 7. ORCA的AIMD输入文件关键参数设置示例

在输入文件中需设置内存如 %maxcore 10000，并行核数如 %pal nprocs 10 end，以及动力学参数如 timestep 1.0_fs、initvel 298.15_K。

---

## 8. ORCA动力学输入文件中的热浴设置

示例中使用了 Berendsen 热浴控温在 298.15 K，时间常数为 30.0 fs，设置行格式为 thermostat berendsen 298.15_K timecon 30.0_fs。

---

## 9. ORCA动力学轨迹文件的输出设置

设置 dump position stride 1 format xyz filename "pos.xyz" 可以将每一步的坐标写入当前目录下的 pos.xyz 文件，生成多帧 xyz 格式的轨迹文件。

---

## 10. ORCA动力学中的质心约束

设置 constraint add center 0..22 可以将指定原子的质心约束在初始位置，以防止模拟过程中因数值问题导致的整体漂移。

---

## 11. ORCA 5.0及以上版本的质心处理方式

对于ORCA 5.0及以后版本，应删除 constraint add center 相关行，并在运行步数设置后添加 CenterCOM 选项（例如 run 2000 CenterCOM）来消除整体质心运动。

---

## 12. ORCA动力学输入文件中的续跑设置

输入文件中的 restart ifexists 行默认被注释。如果需要续跑且当前目录下存在同名的 .mdrestart 文件，取消注释该行即可让任务延续之前的状态继续运行。

---

## 13. ORCA AIMD的并行效率与核数建议

ORCA做DFT的AIMD并行效率不理想，对于小体系，使用过多核数可能导致速度变慢。一般建议设为10核，当机器核数较多时，宜通过CPU内核绑定运行多个AIMD任务来充分利用资源。

---

## 14. ORCA AIMD的步数限制建议

对于ORCA 4.2.1等版本，如果一次运行的步数过多（达到2000步左右），之后每一步的耗时可能逐渐上升。建议每次运行不宜超过3000步，若需更长时间模拟，应分多段进行。

---

## 15. ORCA运行AIMD时的屏幕输出信息

ORCA在运行AIMD时会实时显示当前步数、时间、SCF计算耗时、梯度计算耗时、温度、动能、势能等信息。每一步的总耗时约为 t_SCF 与 t_Grad 之和。

---

## 16. ORCA AIMD产生的输出文件说明

ORCA运行AIMD会产生 complex.md.log（MD模块输出信息）、complex.mdrestart（用于续跑的文件）、complex-md-ener.csv（记录时间、耗时、温度、能量等信息的csv文件）以及 pos.xyz 轨迹文件。

---

## 17. 使用VMD播放ORCA生成的AIMD轨迹

启动VMD载入 pos.xyz 文件，建议在文本窗口输入 bt（自动更新每帧连接关系）和 bw（背景变白），并将 Drawing Method 改为 CPK 来查看轨迹动画。

---

## 18. 使用VMD测量动力学过程中的原子距离变化

在VMD图形窗口按键盘2键，点击两个原子中心可添加 Bond label 显示距离。在 Graphics - Labels 的 Bonds 选项中点击 Graph 可预览或在大窗口中显示距离随时间的变化曲线。

---

## 19. ORCA做AIMD的计算能力与体系规模

以几十核的双路服务器运算能力，使用B97-3c方法在ORCA中跑几十原子有机体系的几十ps动力学是可行的。

---

## 20. 结合xtb与ORCA进行AIMD模拟的策略

在用ORCA跑昂贵的DFT动力学之前，建议先用xtb基于GFN-xTB方法跑半经验动力学，以摸索温度、初始结构等条件，再进行DFT计算，从而节省时间。

---

## 21. 利用Multiwfn分析ORCA动力学轨迹的电子结构

利用Multiwfn可以对ORCA AIMD过程的电子结构进行深入分析，考察化学键、弱相互作用、电荷分布等随时间的变化。这需要通过脚本批量处理MD过程中保存的gbw文件或轨迹文件来实现。

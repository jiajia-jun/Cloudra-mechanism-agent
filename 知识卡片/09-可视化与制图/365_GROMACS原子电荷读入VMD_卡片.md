---
id: 365
title: 将GROMACS的原子电荷信息读入VMD的方法
domain: 可视化与制图
topic: GROMACS原子电荷读入VMD
cards: 7
---

## 2. VMD对GROMACS数据的支持限制
VMD可以载入GROMACS的gro、trr、xtc文件，但不会载入速度、受力、电荷；显示偶极矩、计算静电势、绘制红外光谱的插件以及相关脚本和选择语句都依赖于原子电荷。

---

## 3. gmxoutchg程序获取与兼容性
将GROMACS的原子电荷信息读入VMD需先下载gmxoutchg程序；gmxoutchg.exe是Windows版可执行文件，没后缀的gmxoutchg是Linux下可执行文件；此程序兼容GROMACS 2016.1、2018.8和2019.3版。

---

## 4. 导出tpr文件中的电荷数据
tpr文件里蕴含了模拟所需的一切信息，包括原子电荷；使用GROMACS里的dump命令将二进制的tpr文件转化成文该资料件dump.txt，执行命令：gmx dump -s test.tpr > dump.txt。

---

## 5. 生成VMD可用的电荷文件
将dump.txt放到gmxoutchg.exe所在目录下，运行gmxoutchg.exe；程序会在当前目录下产生charge.txt，其中包含体系所有原子的原子电荷，顺序和结构文件里的原子顺序完全一致；第一列、第二列、第三列分别是原子电荷、分子序号、原子序号。

---

## 7. 验证VMD中电荷载入的方法
使用[atomselect top all] get charge命令可以把所有原子的原子电荷输出出来以验证是否正确载入；也可以将Coloring method设成Charge，通过颜色（RWB刻度下越红越负，越蓝越正）直接检验。

---

## 8. 利用电荷数据可视化偶极矩
有了原子电荷信息可以直接使用VMD的依赖于原子电荷的插件，例如通过Extensions-Visualization-Dipole Moment Watcher可以观看基于原子电荷计算的偶极矩矢量。

---

## 9. 替代方案及其精度缺陷
使用命令 gmx editconf -f nico.tpr -mead nico.pqr 可以将tpr里对应的原子电荷输出到nico.pqr的电荷那一列，载入VMD时也会读入其中的原子电荷；但这种做法致命缺点是原子电荷保留精度太低，只有两位小数，涉及静电作用分析时误差可能较大。

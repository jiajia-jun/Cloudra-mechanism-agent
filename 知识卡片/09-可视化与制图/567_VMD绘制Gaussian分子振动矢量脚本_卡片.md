---
id: 567
title: 在VMD中绘制Gaussian计算的分子振动矢量的方法
domain: 可视化与制图
topic: VMD绘制Gaussian分子振动矢量脚本
cards: 10
---

## 1. VMD脚本绘制Gaussian振动矢量简介
VMD是免费、灵活且图像效果好的化学体系可视化程序，适用于绘制Gaussian的freq任务产生的振动矢量，弥补了GaussView箭头太细、头部不够粗、作图选项不够灵活且收费的不足。

---

## 2. 脚本兼容性与示例文件
绘图脚本至少对于VMD正式版中最新的1.9.3、Gaussian 09和16是完全适用的。示例以绘制多巴胺的振动矢量为例，文件包中包含dopamine.out（多巴胺的Gaussian freq任务输出文件）。

---

## 3. 转换输出文件为VMD结构文件
需要把Gaussian的.out文件转化成VMD可识别的结构文件格式（如.pdb或.mol2）。可以将文件载入GaussView后另存为相应格式，或者启动Multiwfn载入文件，选主功能100的子功能2导出。

---

## 4. 脚本配置与执行步骤
将文件包里的drawarrow.tcl和GauNorm.tcl放到VMD目录下，用文本编辑器打开GauNorm.tcl，把set filename后面的文件名改为dopamine.out。启动VMD并载入多巴胺的结构文件，在VMD文本窗口输入source GauNorm.tcl执行脚本，读入振动矢量信息并定义名为norm的绘制命令。

---

## 5. 绘制振动矢量的基本命令
在VMD文本窗口输入norm 4，可以把4号振动模式通过箭头画出来。默认使用黄色绘制箭头。

---

## 6. 箭头长度与半径的参数设置
norm命令后可接第2个参数设置箭头长度是正则矢量的几倍（数值越大箭头越长，默认是3）。norm命令后可接第3个参数设置箭头的半径（默认为0.05）。例如norm 5 6 0.07代表用6倍长度、0.07的半径绘制第5个振动矢量。

---

## 7. 箭头颜色的修改方法
默认使用黄色绘制箭头，如需更改颜色，将GauNorm.tcl中draw color后面的yellow改成其它颜色名（如cyan）。

---

## 8. 线型体系的参数设置
GauNorm.tcl开头有set ilinear语句，如果当前体系是线型体系，必须把后面的值改为1。

---

## 9. 冻结原子数的参数设置
如果在Gaussian做freq或opt freq任务中冻结了N个原子的笛卡尔坐标，运行source GauNorm.tcl之前必须把里面set nfreeze后面的值设为N（默认为0，即没有原子被冻结）。

---

## 10. 箭头始端位置的修改方法
若希望让箭头的始端位于各个原子上（和GaussView的风格一致），需将文件包里的drawarrow2.tcl放到VMD目录下，把GauNorm.tcl里的两处drawarrow都改为drawarrow2并保存。

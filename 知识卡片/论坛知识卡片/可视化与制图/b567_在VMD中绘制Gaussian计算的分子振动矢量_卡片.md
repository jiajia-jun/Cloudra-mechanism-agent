---
key: b567
title: 在VMD中绘制Gaussian计算的分子振动矢量的方法
url: http://sobereva.com/567
domain: 可视化与制图
source: blog
year: 2020
cards: 12
---

# 在VMD中绘制Gaussian计算的分子振动矢量的方法 — 知识卡片

## 1. VMD绘制Gaussian振动矢量的优势

Gaussian用户常使用GaussView或ChemCraft查看频率任务产生的振动矢量。GaussView 6显示的振动矢量箭头过细且头部不够粗，导致可视性差且作图效果不美观。VMD是免费、灵活且图像效果优异的化学体系可视化程序，适合用于绘制此类矢量。

---

## 2. 必需的脚本与文件

用户需下载绘图脚本和示例文件压缩包。该脚本包兼容VMD正式版（至少至1.9.3版本）以及Gaussian 09和16版本。

---

## 3. 准备结构文件

将Gaussian频率输出文件（如dopamine.out）放入VMD目录。该文件需转换为VMD可识别的结构文件格式（如.pdb或.mol2），可通过GaussView另存为或使用Multiwfn主功能100的子功能2导出。

---

## 4. 脚本配置步骤

将drawarrow.tcl和GauNorm.tcl文件放入VMD目录。使用文本编辑器打开GauNorm.tcl，将开头的set filename后的文件名修改为实际的Gaussian输出文件名（如dopamine.out）。

---

## 5. 加载脚本与数据

启动VMD并载入分子结构文件，在VMD文本窗口输入source GauNorm.tcl执行脚本。该操作会读取振动矢量信息并定义名为norm的绘图命令。

---

## 6. 绘制指定模式的振动矢量

在VMD文本窗口输入norm命令加模式序号即可绘制对应振动矢量。例如输入norm 4可绘制第4号振动模式。

---

## 7. 箭头长度与半径参数设置

norm命令支持第二个参数设置箭头长度为正则矢量的倍数（默认为3），支持第三个参数设置箭头半径（默认为0.05）。输入norm 5 6 0.07表示用6倍长度、0.07的半径绘制第5个振动矢量。

---

## 8. 箭头颜色修改

脚本默认使用黄色绘制箭头。若需更改颜色，需在GauNorm.tcl文件中修改draw color后面的颜色名称（如将yellow改为cyan）。

---

## 9. 线型体系的设置

GauNorm.tcl脚本开头包含set ilinear语句。若计算体系为线型分子，必须将该语句后的值修改为1。

---

## 10. 冻结原子坐标的设置

如果在Gaussian的freq或opt freq任务中冻结了N个原子的笛卡尔坐标，在执行source GauNorm.tcl之前，必须将脚本中set nfreeze后的值设为N（默认值为0）。

---

## 11. 箭头起始位置调整

若希望箭头始端位于各个原子上（类似GaussView风格），需使用drawarrow2.tcl。将该文件放入VMD目录，并将GauNorm.tcl中的两处drawarrow修改为drawarrow2后保存。

---

## 12. 多巴胺分子振动矢量绘制示例

对于多巴胺分子，输入norm 17 5命令并设置CPK显示方式（Drawing method选CPK，Sphere Scale设为0.6），可获得理想的振动矢量图。此方法展示的信息与GaussView一致，但箭头显示效果更佳。

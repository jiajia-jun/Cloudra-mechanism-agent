---
id: 567
title: 在VMD中绘制Gaussian计算的分子振动矢量的方法
url: http://sobereva.com/567
domain: 可视化与制图
topic: VMD绘制Gaussian分子振动矢量脚本
cards: 1
---

# VMD绘制Gaussian分子振动矢量脚本 — 知识卡片

## 1. VMD绘制Gaussian振动矢量的优势

Gaussian用户通常使用GaussView或ChemCraft查看freq任务产生的振动矢量，但GaussView 6显示的振动矢量箭头太细且头部不够粗，视觉效果不佳且作图选项不灵活。VMD是免费、灵活且图像效果极佳的化学体系可视化程序，适合用于绘制高质量的振动矢量图。VMD可从 http://www.ks.uiuc.edu/Research/vmd/ 免费下载。

## 脚本下载与软件兼容性
笔者编写的绘图脚本和示例文件可从 http://sobereva.com/attach/567/file.zip 下载。该脚本至少对VMD正式版最新的1.9.3、Gaussian 09和16版本是完全适用的。

## 准备结构文件
以绘制多巴胺振动矢量为例，需将包内的dopamine.out（Gaussian freq任务输出文件）转换为VMD可识别的结构文件格式。方法包括：将文件载入GaussView并另存为.pdb或.mol2文件；或使用Multiwfn（http://sobereva.com/multiwfn），载入文件后选主功能100的子功能2导出为.pdb或.xyz文件。

## 脚本配置与基本执行步骤
将drawarrow.tcl和GauNorm.tcl放入VMD目录，用文本编辑器打开GauNorm.tcl，把开头的set filename后的文件名改为dopamine.out。启动VMD并载入多巴胺结构文件，在VMD文本窗口输入source GauNorm.tcl执行脚本，此时读入振动矢量信息并定义了名为norm的绘制命令。输入norm 4即可画出4号振动模式的箭头。

## 振动矢量箭头参数设置
norm命令后可接第2个参数设置箭头长度为正则矢量的倍数（默认为3），可接第3个参数设置箭头半径（默认为0.05）。例如，norm 5 6 0.07代表用6倍长度、0.07的半径绘制第5个振动矢量。

## 箭头颜色修改方法
脚本默认使用黄色绘制箭头，若需更改颜色，应将GauNorm.tcl中draw color后面的yellow改为其他颜色名（如cyan）。

## VMD显示效果示例
输入norm 17 5命令，并将分子显示方式设为CPK（在Graphics - Representation里把Drawing method改为CPK，Sphere Scale设为0.6），可获得理想的视觉效果，比GaussView的箭头更清晰美观。

## 线型体系的设置
GauNorm.tcl开头包含set ilinear语句，如果当前体系是线型体系，必须将该语句后面的值改为1。

## 冻结原子坐标的设置
如果在Gaussian的freq或opt freq任务中按照《在Gaussian中做限制性优化的方法》（http://sobereva.com/404）冻结了N个原子的笛卡尔坐标，必须在运行source GauNorm.tcl之前把脚本中set nfreeze后面的值设为N（默认为0）。

## 修改箭头起始位置风格
若希望箭头始端位于各个原子上（与GaussView风格一致），需将文件包里的drawarrow2.tcl放入VMD目录，把GauNorm.tcl里的两处drawarrow都改为drawarrow2并保存，之后再按前述方法绘图。

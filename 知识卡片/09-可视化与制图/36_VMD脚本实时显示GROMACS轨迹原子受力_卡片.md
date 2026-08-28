---
id: 36
title: 使VMD实时显示gromacs轨迹中原子的受力
url: http://sobereva.com/36
domain: 可视化与制图
topic: VMD脚本实时显示GROMACS轨迹原子受力
cards: 6
---

# VMD脚本实时显示GROMACS轨迹原子受力 — 知识卡片

## 1. 从GROMACS轨迹提取特定原子受力

结合gmxdump和grep可以从.trr文件中提取指定序号原子的受力数据，虽然速度较慢但很方便；若要使每一行对应一帧结构，需确保.mdp文件中的nstxout和nstfout参数相同。
- 命令：gmxdump -f all.trr |grep "f. 977" > force.txt
- 原子序号从0开始算

---

## 2. VMD读取并解析受力数据文件

将生成的force.txt放入VMD启动后的默认文件夹，通过Tcl脚本循环读取文件行，利用scan解析受力数值并存入数组，数组索引对应帧号。
- 脚本代码：
set i 0;set fx 0;set fy 0;set fz 0
set force [open force.txt r]
while {[gets $force line] >= 0} {
scan [string range $line 16 55] "%f,%f,%f" fx fy fz
set f(x$i) $fx;set f(y$i) $fy;set f(z$i) $fz
incr i
}
close $force

---

## 3. 定义VMD显示受力的绘图过程

定义showforce过程，利用graphics命令绘制红箭头表示受力方向和大小，箭头由圆柱和锥体组成，长度与受力大小成正比。
- 绘图参数：圆柱半径0.3，分辨率20；锥体半径1.0，分辨率20
- 坐标计算：中间点为坐标加受力除以400，头部点为坐标加受力除以300
- 过程代码：
proc showforce {args} {
global vmd_frame
global f
global atom
graphics 0 delete all
set sel [atomselect top "index $atom" frame $vmd_frame(0)]
set x [$sel get x]
set y [$sel get y]
set z [$sel get z]
set init "$x $y $z"
set middle "[expr $x+$f(x$vmd_frame(0))/400] [expr $y+$f(y$vmd_frame(0))/400] [expr $z+$f(z$vmd_frame(0))/400]"
set after "[expr $x+$f(x$vmd_frame(0))/300] [expr $y+$f(y$vmd_frame(0))/300] [expr $z+$f(z$vmd_frame(0))/300]"
graphics 0 color red
graphics 0 cylinder $init $middle radius 0.3 filled yes resolution 20
graphics 0 cone $middle $after radius 1.0 resolution 20
$sel delete
}

---

## 4. 实现受力显示随帧更新的联动机制

使用trace命令跟踪vmd_frame(0)变量，当进度条移动更新帧号时，自动触发showforce过程重绘箭头。
- 命令：trace variable vmd_frame(0) w showforce

---

## 5. 开启与关闭实时受力显示

通过set命令指定原子序号即可显示受力箭头；若需停止显示，使用trace vdelete删除跟踪并清除绘图对象。
- 开启显示：set atom 977
- 关闭显示：trace vdelete vmd_frame(0) w showforce; graphics 0 delete all

---

## 6. 使用脚本文件简化操作流程

将数据读取和绘图过程整合进showforce.tcl文件，放入VMD默认文件夹，在VMD中载入轨迹后依次执行source和set命令即可快速使用。
- 操作步骤：启动VMD并载入轨迹 -> 控制台运行source showforce.tcl -> 运行set atom 977

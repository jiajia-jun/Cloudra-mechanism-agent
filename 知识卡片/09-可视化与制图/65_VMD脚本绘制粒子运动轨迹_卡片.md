---
id: 65
title: 显示粒子运动轨迹的VMD脚本
domain: 可视化与制图
topic: VMD脚本绘制粒子运动轨迹
cards: 5
---

## 1. VMD粒子运动轨迹绘制脚本代码
以下Tcl脚本用于在VMD中将粒子运动轨迹连线，通过循环读取相邻帧的原子坐标并绘制线条和圆球来实现路径可视化；脚本参数包含起始帧、结束帧、帧间隔和原子选择范围。
```tcl
proc showtrj {fps1 fps2 space selection} {
set selnow [atomselect top $selection frame $fps1]
set selnext [atomselect top $selection frame $fps1]
set num [$selnow num]
for {set fps $fps1} {$fps<$fps2} {incr fps $space} {
$selnow frame $fps
$selnext frame [expr $fps+$space]
$selnow update
$selnext update
for {set i 0} {$i<$num} {incr i 1} {
draw line [lindex [$selnow get {x y z}] $i] [lindex [$selnext get {x y z}] $i]
draw sphere [lindex [$selnext get {x y z}] $i] radius 0.12
puts "Frame $fps done"

---

## 2. 脚本使用方法参数说明
该VMD脚本的使用方法格式为`showtrj 最初帧 最末帧 帧数间隔 选择范围`，用户需要按照此顺序输入四个参数来控制轨迹绘制的起止时间和具体对象。

---

## 3. 轨迹颜色设置与alanin示例
绘制轨迹前可以使用`draw color red`命令将轨迹颜色设定为红色（默认为蓝色）；对于VMD自带的alanine轨迹，执行`showtrj 1 95 1 "index 1 61"`可以显示第1至95帧中两末端C原子的运动路径。

---

## 4. 轨迹圆球绘制与帧间隔设置
若不希望绘制每一帧的圆球，需将脚本中的`draw sphere [lindex [$selnext get {x y z}] $i] radius 0.12`语句删除；对于帧数较多的情况（如1000帧），可以通过设置较大的帧间隔（如50）来加快绘制速度并避免线条过密。

---

## 5. 蛋白CA原子轨迹绘制示例
对于某蛋白平衡状态1ns内的运动轨迹，可以通过运行`showtrj 0 1000 50 "name CA"`来绘制CA原子的运动路径，该命令每50帧绘制一次以适应高帧数数据。

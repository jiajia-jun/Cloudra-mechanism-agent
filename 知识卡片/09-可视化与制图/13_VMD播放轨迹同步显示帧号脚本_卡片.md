---
id: 13
title: 使VMD播放轨迹时同步显示帧号
url: http://sobereva.com/13
domain: 可视化与制图
topic: VMD播放轨迹同步显示帧号脚本
cards: 2
---

# VMD播放轨迹同步显示帧号脚本 — 知识卡片

## 1. VMD同步显示轨迹帧号的操作步骤

将提供的TCL代码保存为showframe.tcl文件并放入vmd文件夹，启动VMD后在文本控制台运行source showframe.tcl。
- 载入轨迹后，轨迹ID必须是1，因为vmd_frame(1)代表ID=1体系当前的帧号。
- 一旦检测到帧号变化，系统会调用sdf命令在三维坐标(0,0,0)处绘制当前帧号。
- 播放轨迹时，帧数会同步显示，旋转图像调整文字位置到合适区域（如屏幕右下角），然后将ID=0的图层（显示帧数的文字层）fix住（鼠标点ID右边的F字母），即可在录制轨迹动画时同步显示帧数。

---

## 2. 同步显示帧号的TCL代码

使用以下TCL代码实现帧号追踪与显示功能：
```
trace variable vmd_frame(1) w sdf
mol new
proc sdf {args} {global vmd_frame
graphics 0 delete all
graphics 0 color 8
graphics 0 text {0 0 0} "[expr $vmd_frame(1)*1]ps" size 6}
```

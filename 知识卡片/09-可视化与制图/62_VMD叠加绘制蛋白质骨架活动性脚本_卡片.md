---
id: 62
title: VMD里通过叠加方式表现蛋白质骨架活动性的脚本
url: http://sobereva.com/62
domain: 可视化与制图
topic: VMD叠加绘制蛋白质骨架活动性脚本
cards: 5
---

# VMD叠加绘制蛋白质骨架活动性脚本 — 知识卡片

## 1. 叠加法表现蛋白质骨架活动性的原理

透明材质的物体在叠加时颜色会变深，利用这一特性绘制轨迹中每一帧的骨架（CA原子），叠加后颜色的深浅直观反映不同位置的活动性，并可与B因子/RMSF相互对照。

---

## 2. 绘图前的材质与显示设置

在Material窗口选择Transparent并点击Create New，将新材质命名为a；在控制台执行draw material a和draw color iceblue（或orange等颜色）；将Display-Render mode设为GLSL以支持透明效果。

---

## 3. 绘制骨架结构的TCL脚本定义

将下述代码复制到VMD控制台执行，可自定义supshow命令用于绘制：
```tcl
proc supshow {fps1 fps2 space} {
 for {set fps $fps1} {$fps<$fps2} {incr fps $space} {
 set selca [atomselect top "name CA" frame $fps]
 set calist [$selca get {x y z}]
 for {set n 0} {$n<[expr [$selca num]-2]} {incr n 1} {
 draw cylinder [lindex $calist $n] [lindex $calist [expr $n+1]] radius 0.1 filled yes resolution 20
 }
 $selca delete
 echo "frame" $fps "done"
 }}
```

---

## 4. 脚本参数与执行方式

载入轨迹并Align以消平动转动后，执行supshow 1 80 2表示从第1帧到第80帧每2帧绘制一次骨架结构；控制台会实时输出绘制进度。

---

## 5. 结果分析与材质调整

绘制完毕后调整材质a的opacity和Ambient属性，线条颜色深叠加多的区域（如中间alpha螺旋）活动性小，外侧虚散的区域活动性大；若显卡较老不支持GLSL则无透明效果。

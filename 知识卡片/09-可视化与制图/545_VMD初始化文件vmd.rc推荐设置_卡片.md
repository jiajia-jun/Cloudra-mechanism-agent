---
id: 545
title: VMD初始化文件(vmd.rc)我的推荐设置
domain: 可视化与制图
topic: VMD初始化文件vmd.rc推荐设置
cards: 12
---

## 1. VMD初始化文件路径与载入顺序
VMD启动时会执行初始化文件中的命令；对于Windows版，文件名为vmd.rc且位于VMD目录下；对于Linux版，文件名为.vmdrc，VMD依次在当前目录、~/.vmdrc、$VMDDIR/.vmdrc中搜索，若找不到则使用默认设置；Linux下安装目录（如/usr/local/lib/vmd/.vmdrc）的文件不会在未配置VMDDIR环境变量时自动载入，通常需在用户主目录下自行创建。

---

## 2. 设置默认显示样式与线宽
VMD默认的Lines显示方式线宽过细，使用命令`mol default style {Lines 2.0}`可将默认显示方式改为两倍粗细的Lines，以便更清晰地观察。

---

## 3. 关闭默认雾化效果
VMD默认开启雾化效果，会使远处的物体颜色混入背景色，导致黑色背景下物体颜色不够鲜艳或白色背景下物体显得模糊；使用命令`display depthcue off`可以关闭此雾化效果。

---

## 4. 设置默认背景色与坐标轴
在初始化文件中添加`#color Display Background white`可设置默认白背景（需去掉#号生效）；添加`#axes location Off`可设置默认不显示坐标轴（需去掉#号生效）。

---

## 5. 启用GLSL渲染模式
VMD默认的Normal渲染模式对某些材质显示效果差，且Transparent材质无法正确显示透明；使用命令`display rendermode GLSL`将默认渲染模式设为GLSL可获得更好的显示效果。

---

## 6. 调整显示距离以减少边缘畸变
为避免画面边缘物体产生严重畸变，使用命令`display distance -8.0`进行调整；这会导致窗口左下方的坐标轴不可见，需要时可通过Display - Axes - Origin将其显示在窗口中央。

---

## 7. 快速切换背景颜色的自定义命令
定义过程`proc bw {} {color Display Background white}`和`proc bb {} {color Display Background black}`后，在VMD文本窗口输入bw可立刻切换为白背景，输入bb可立刻切换为黑背景。

---

## 8. 自定义快捷键控制帧播放
使用`user add key Right {animate next}`、`user add key Left {animate prev}`、`user add key Up {animate goto [expr $vmd_frame([molinfo top])+10]}`、`user add key Down {animate goto [expr $vmd_frame([molinfo top])-10]}`可设置快捷键：左右键分别前进/后退1帧，上下键分别增加/后退10帧，方便轨迹观看。

---

## 9. 手动更新键连接关系的快捷键
使用`user add key b {mol bondsrecalc all; topo retypebonds}`设置快捷键b；在图形窗口激活时按b键，可让VMD根据当前结构重新判断原子间的连接关系。

---

## 10. 实时自动更新键连接关系
定义bt命令：`proc bt {} { global vmd_frame; trace variable vmd_frame([molinfo top]) w updatebond }`及`proc updatebond {args} { mol bondsrecalc all; topo retypebonds }`；输入bt后，每当top体系的帧号变化，会自动调用updatebond命令更新连接关系，此操作对大体系可能导致播放卡顿。

---

## 11. 取消实时更新键连接关系
定义bn命令：`proc bn {} { global vmd_frame; trace vdelete vmd_frame([molinfo top]) w updatebond }`；输入bn可取消对帧号的跟踪，即停止自动更新键连接关系。

---

## 12. 开启并优化雾化效果
定义fog命令：`proc fog {} { display depthcue on; display cuemode Linear; display cuestart 1.75; display cueend 2.5 }`；输入fog可开启雾化并使用线性模式及特定参数，使近距离物体不受影响而远处的原子适当雾化以减少视觉干扰；若需微调，可通过Display - Display Settings修改Cue Start和Cue End参数。

---
key: b545
title: VMD初始化文件(vmd.rc)我的推荐设置
url: http://sobereva.com/545
domain: 可视化与制图
source: blog
year: 2020
cards: 12
---

# VMD初始化文件(vmd.rc)我的推荐设置 — 知识卡片

## 1. VMD初始化文件路径与载入顺序

VMD启动时会读取初始化文件以执行其中的配置命令。Windows版本的初始化文件名为vmd.rc，位于VMD安装目录下；Linux版本的文件名为.vmdrc，程序会依次在当前目录、用户主目录(~/.vmdrc)以及环境变量$VMDDIR指定的目录中搜索，若找不到则使用默认设置。

---

## 2. 默认显示线条粗细设置

VMD默认的显示方式是Lines，但默认线宽较细，视觉清晰度不足。通过在初始化文件中添加`mol default style {Lines 2.0}`，可将默认线条显示样式设置为2.0倍粗细。

---

## 3. 关闭默认雾化效果

VMD默认开启雾化效果，使远处的物体颜色混入更多背景色，导致黑色背景下物体颜色不够鲜艳或白色背景下物体显得模糊。使用`display depthcue off`命令可以关闭默认的雾化效果，提升显示清晰度。

---

## 4. 默认背景色设置

初始化文件中的`#color Display Background white`行默认被注释。若需VMD启动后默认使用白色背景，应删除行首的注释符号#；同理，`#axes location Off`行用于控制默认不显示坐标轴。

---

## 5. 渲染模式设置

VMD默认的Normal渲染模式对部分材质显示效果较差，且无法正确显示Transparent材质的透明效果。使用`display rendermode GLSL`命令可将默认渲染模式设置为显示效果更佳的GLSL模式。

---

## 6. 图形窗口距离与畸变控制

画面边缘物体常因透视产生严重畸变，使用`display distance -8.0`命令可以充分改善此问题。该设置会导致原本位于窗口左下方的坐标轴消失，需要时可通过菜单Display - Axes - Origin将坐标轴显示在窗口中央。

---

## 7. 背景色切换命令

定义`proc bw {} {color Display Background white}`和`proc bb {} {color Display Background black}`两个自定义命令。在VMD文本窗口输入bw可立即将背景切换为白色，输入bb可立即将背景切换为黑色。

---

## 8. 轨迹播放快捷键设置

配置`user add key Right {animate next}`等命令可为图形窗口设置快捷键。在窗口激活状态下，按右键和左键可分别前进或后退1帧；按上键和下键可分别前进或后退10帧，便于轨迹查看。

---

## 9. 手动重建连接关系的快捷键

设置`user add key b {mol bondsrecalc all; topo retypebonds}`后，在图形窗口激活时按b键。该操作会基于当前帧结构重新计算所有分子的成键关系并重新类型化键。

---

## 10. 实时自动更新连接关系

定义`bt`命令及其关联的`updatebond`过程后，输入bt可开启帧号跟踪。每当当前顶层分子的帧号发生变化时，程序会自动重新计算成键关系，这适用于播放过程中键连接发生变化的体系，但大体系下可能会引起播放卡顿。

---

## 11. 停止实时更新连接关系

定义`bn`命令用于取消对帧号的跟踪。输入`bn`将停止自动更新连接关系的功能，恢复为手动控制或静态显示。

---

## 12. 自定义雾化效果命令

定义`proc fog {}`命令可开启雾化并应用特定参数设置。该命令设置雾化模式为Linear，起始距离为1.75，结束距离为2.5，使远处原子适度雾化以减少对近处物体观察的干扰；若需微调，可通过Display - Display Settings修改Cue Start和Cue End参数。

---
id: 652
title: 在VMD中使用GaussView的元素着色的方法
url: http://sobereva.com/652
domain: 可视化与制图
topic: VMD应用GaussView元素配色方案
cards: 1
---

# VMD应用GaussView元素配色方案 — 知识卡片

## 1. VMD默认元素着色的局限性

VMD软件虽然支持按元素着色，但其自带的元素着色定义很少，对绝大多数元素都统一使用褐色显示，这导致无法区分不同元素且颜色不美观。
- 具体版本限制：此问题至少存在于笔者撰文时的最新正式版1.9.3版。

## 下载与放置GaussView颜色配置文件
从链接 http://sobereva.com/attach/652/gview_color.tcl 下载gview_color.tcl文件，并将该文件放到VMD的启动目录下。
- 确定目录的方法：该目录为VMD启动后在文本窗口里输入pwd命令后显示的目录。

## 修改vmd.rc文件启用配置
在VMD的vmd.rc文件末尾加入一行代码 proc gview {} {source gview_color.tcl}，以定义调用GaussView配色方案的过程。
- 相关参考：如果不了解vmd.rc文件，可参考《VMD初始化文件 的推荐设置》，链接为 http://sobereva.com/545。

## 应用GaussView元素配色方案
启动VMD后，在文本窗口里输入gview命令，即可将默认的元素着色方案替换成和GaussView相同的方案。
- 使用方法：载入含有元素信息的结构文件（如pdb、xyz等），在Graphics - Representation里把Coloring Method设为Element即可看到效果。

## 设置与GaussView接近的显示参数
在Graphics - Representation中将Drawing Method设为CPK，Bond Radius设为0.2，Material设为AOShiny，可以使VMD的显示图像特征尽可能接近GaussView。
- 这种设置主要针对原子球体的显示风格进行匹配。

## 模拟GaussView的白色键显示
若要实现与GaussView统一的白色键显示效果，需将当前Representation里的Bond Radius设为0使键不显示，再新建一个Representation。
- 新Representation的参数：Drawing Method选CPK，Sphere Scale设为0，Bond Radius设为0.15，Coloring Method选ColorID并指定为白色。

## VMD无法模拟GaussView的多重键显示
尽管可以通过调整原子半径、光源方向和材质微调使图像更像GaussView，但GaussView里对多重键的显示效果在VMD中无法通过设置来模仿。
- 这是VMD软件在渲染特定化学键特征方面的固有局限。

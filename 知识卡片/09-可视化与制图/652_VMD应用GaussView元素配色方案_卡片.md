---
id: 652
title: 在VMD中使用GaussView的元素着色的方法
url: http://sobereva.com/652
domain: 可视化与制图
topic: VMD应用GaussView元素配色方案
cards: 4
---
## 1. 在VMD中应用GaussView元素配色方案的操作步骤

下载gview_color.tcl文件并放入VMD启动目录下，在VMD的vmd.rc文件末尾添加proc gview {} {source gview_color.tcl}，启动VMD后在文本窗口输入gview命令即可将默认元素着色方案替换为GaussView配色。
- 下载地址：http://原作者.com/attach/652/gview_color.tcl
- VMD启动目录指VMD启动后输入pwd命令显示的目录
- 参考文献链接：《VMD初始化文件(vmd.rc)我的推荐设置》http://原作者.com/545

## 2. VMD中模拟GaussView显示效果的参数设置

在Graphics - Representation中将Drawing Method设为CPK，Bond Radius设为0.2，Material设为AOShiny，Coloring Method设为Element，可使VMD显示效果接近GaussView。

---

## 3. VMD中模拟GaussView白色键色的具体方法

建立两个Representation：第一个将Bond Radius设为0使键不显示；第二个Drawing Method选CPK，Sphere Scale设为0，Bond Radius设为0.15，Coloring Method选ColorID并指定为白色，即可实现类似GaussView的白色键显示效果。

---

## 4. VMD与GaussView显示效果的差异与限制

VMD无法模仿GaussView对多重键的显示效果，除此之外可以通过微调原子半径、光源方向和材质来进一步接近GaussView的图像特征。

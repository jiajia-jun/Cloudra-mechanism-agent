---
id: 483
title: 在VMD里将cube文件瞬间绘制成效果极佳的等值面图的方法
url: http://sobereva.com/483
domain: 可视化与制图
topic: VMD脚本快速绘制高质量Cube等值面
cards: 11
---

# VMD脚本快速绘制高质量Cube等值面 — 知识卡片

## 1. showcub.vmd脚本的安装与加载位置

showcub.vmd脚本位于Multiwfn程序包的examples\scripts目录下，需要将该文件拷贝到VMD启动后的当前工作目录，并在该目录下的vmd.rc文件末尾插入source showcub.vmd，保存文件后重启VMD即可使脚本定义的命令生效。

---

## 2. cub命令绘制单个cube文件等值面

cub命令用于绘制单个cube文件的等值面图，正值和负值部分分别默认用绿色和蓝色显示，默认等值面数值为0.05和-0.05；若在命令后指定参数如cub MIO 0.02，则将正值和负值部分等值面数值分别设为0.02和-0.02。

---

## 3. cubiso命令修改单个等值面数值

cubiso命令用于在使用cub命令后修改当前载入格点数据的等值面数值，例如输入cubiso 0.015会将正值和负值部分等值面数值分别设为0.015和-0.015。

---

## 4. cub2命令绘制两个cube文件等值面

cub2命令用于同时绘制两个cube文件的等值面，例如cub2 eri nozomi，两个文件分别用绿色和蓝色表示，等值面数值默认为0.05，且若格点数据含有负值部分则不显示；若指定参数如cub2 eri nozomi 0.02，则二者的等值面数值都设为0.02。

---

## 5. cub2iso命令修改双文件等值面数值

cub2iso命令用于在使用cub2命令后将已载入的两套cube文件对应的等值面数值统一修改为指定值，例如cub2iso 0.015代表将两套数据的等值面数值都设为0.015。

---

## 6. cub和cub2命令的数据清理机制

每次使用cub或cub2命令之前，脚本会自动将之前载入的格点数据从VMD中清掉，因此这两个命令可以反复使用无数次而不会产生数据冲突。

---

## 7. VMD渲染图片的操作流程

将Multiwfn的examples\scripts目录下的VMDrender_full.bat拷贝到VMD目录下，在VMD里选择File - Render，渲染器选Tachyon，点击Start Rendering，然后双击执行VMDrender_full.bat，即可在VMD目录下得到渲染好的full.bmp图像。

---

## 8. 改善空穴-电子重叠显示的材质调整

为清晰展现空穴与电子分布的交叠特征，可在Graphics - Representation中将Material改为EdgyGlass，并分别对electron.cub和hole.cub应用该材质，使二者的交叠在图形窗口中清晰可见。

---

## 9. 调节VMD渲染亮度的参数设置

编辑VMDrender_full.bat文件，将-trans_raster3d改为-trans_vmd，将-fullshade改为-mediumshade，再次运行脚本可解决图像偏亮的问题，使亮度适中。

---

## 10. 调节渲染图像的曝光度和灰度

可在Photoshop等图像编辑程序中调整曝光度（如Ctrl+Alt+E增加0.6）或灰度系数校正（Gamma改为0.7），以优化图像亮度和密度差特征的显示效果。

---

## 11. 调节阴影和图像尺寸的渲染参数

在VMDrender_full.bat中加入-shadow_filter_off可避免因等值面产生大量阴影导致图像较暗；.bat里-res后面的数字定义渲染出来的图像尺寸，设得越小则Tachyon渲染耗时越低。

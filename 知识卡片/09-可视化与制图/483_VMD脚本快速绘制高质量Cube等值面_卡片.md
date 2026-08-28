---
id: 483
title: 在VMD里将cube文件瞬间绘制成效果极佳的等值面图的方法
url: http://sobereva.com/483
domain: 可视化与制图
topic: VMD脚本快速绘制高质量Cube等值面
cards: 1
---

# VMD脚本快速绘制高质量Cube等值面 — 知识卡片

## 1. showcub.vmd脚本的获取与安装路径

showcub.vmd脚本位于Multiwfn程序包的examples\scripts目录下，需要将此文件拷贝到VMD目录（即VMD启动后在命令行窗口运行pwd命令显示的目录）中。
- 脚本获取路径：Multiwfn程序包内的examples\scripts目录

## showcub.vmd脚本的自动加载配置方法
将showcub.vmd拷到VMD目录后，需用文本编辑器编辑该目录下的vmd.rc文件（针对Windows版VMD），在文件末尾插入一行source showcub.vmd并保存，重启VMD后脚本中定义的命令即生效。
- 配置文件：vmd.rc
- 加载命令：source showcub.vmd

## cub命令绘制单个cube文件等值面
cub命令用于将VMD目录下的指定.cub文件绘制成等值面图，正值和负值部分分别显示为绿色和蓝色，使用默认等值面数值0.05和-0.05，命令格式为cub 文件名（不含扩展名）。
- 默认等值面数值：正值0.05，负值-0.05
- 颜色设置：正值绿色，负值蓝色
- 示例命令：cub MIO

## cub命令自定义等值面数值
在使用cub命令绘制单个cube文件时，可以通过在文件名后添加参数来直接设定正值和负值部分的等值面数值，例如cub MIO 0.02表示将等值面数值分别设为0.02和-0.02。
- 命令格式：cub 文件名 数值
- 示例命令：cub MIO 0.02

## cubiso命令调整当前等值面数值
cubiso命令用于在已使用cub命令绘制等值面后，将当前载入的格点数据的正值和负值部分的等值面数值统一修改为指定值，例如输入cub2iso 0.015会将等值面数值设为0.015和-0.015。
- 命令格式：cubiso 数值
- 示例命令：cubiso 0.015

## cub2命令同时绘制两个cube文件等值面
cub2命令用于将VMD目录下的两个.cub文件同时绘制成等值面，分别用绿色和蓝色表示，默认等值面数值均为0.05，且此命令只显示正值部分，不显示负值部分。
- 默认等值面数值：0.05
- 颜色设置：绿色和蓝色
- 示例命令：cub2 eri nozomi

## cub2命令自定义双文件等值面数值
使用cub2命令时，可在两个文件名后添加参数来统一设定两者的等值面数值，例如cub2 eri nozomi 0.02表示将两个文件的等值面数值都设为0.02。
- 命令格式：cub2 文件名1 文件名2 数值
- 示例命令：cub2 eri nozomi 0.02

## cub2iso命令调整双文件等值面数值
cub2iso命令用于在已使用cub2命令后，将已载入的两套cube文件对应的等值面数值都修改为指定值，例如输入cub2iso 0.015会将两个等值面数值都设为0.015。
- 命令格式：cub2iso 数值
- 示例命令：cub2iso 0.015

## cub和cub2命令的数据清理机制
每次使用cub或cub2命令之前，脚本会自动将之前载入的格点数据从VMD中清空，因此这两个命令可以反复使用无数次而不会产生数据冲突。
- 功能特性：自动清空旧数据

## 使用Tachyon渲染器渲染VMD图像
在VMD中通过File - Render选择Tachyon渲染器（注意不选带internal的版本）并点击Start Rendering，再运行Multiwfn程序包examples\scripts目录下的VMDrender_full.bat批处理文件，可在VMD目录下生成名为full.bmp的渲染图像。
- 渲染器选择：Tachyon
- 批处理文件：VMDrender_full.bat
- 输出文件：full.bmp

## 自旋密度等值面的显示与渲染
将自旋密度格点数据导出为cube文件（如spindensity.cub）并移至VMD目录，输入cub spindensity 0.01可快速显示自旋密度等值面（绿色为正，蓝色为负），配合VMDrender_full.bat可渲染出具有立体感和阴影的高质量图像。
- 推荐等值面数值：0.01
- 参考实例：丁烷双自由基自旋密度

## 空穴-电子分布等值面的显示方法
将电子和空穴格点数据导出为cube文件（如electron.cub和hole.cub），使用cub2 electron hole命令载入，并利用cub2iso命令尝试不同数值（如0.002）以获得清晰的空穴和电子分布特征。
- 推荐尝试数值：0.002
- 命令组合：cub2 electron hole; cub2iso 0.002

## 空穴-电子分析中的EdgyGlass材质设置
为了在空穴-电子分析图中清晰展现空穴与电子分布的交叠特征，应进入Graphics - Representation，将Material修改为EdgyGlass，并分别对两个cube文件进行此设置。
- 推荐材质：EdgyGlass
- 设置路径：Graphics - Representation

## VMDrender_full.bat的亮度与阴影调节
若使用VMDrender_full.bat渲染的图像偏亮，可编辑.bat文件，将-trans_raster3d改为-trans_vmd，将-fullshade改为-mediumshade，再次运行脚本可降低图像亮度。
- 修改参数1：-trans_raster3d 改为 -trans_vmd
- 修改参数2：-fullshade 改为 -mediumshade

## 后期处理调整图像曝光度
若渲染后的图像亮度仍不理想，可以使用Photoshop等图像编辑程序调整曝光度（如Ctrl+Alt+E快捷键）或灰度系数（Gamma），例如将曝光度增加0.6或将Gamma设为0.7，以达到最佳视觉效果。
- 示例调整：曝光度+0.6，Gamma 0.7

## 密度差图的渲染与材质建议
对于密度差图，若使用VMDrender_full.bat渲染导致阴影过于复杂不便分析，建议采用-trans_vmd和-mediumshade选项进行渲染，并在后期调整Gamma值至0.7，以获得清晰的特征展现。
- 推荐设置：-trans_vmd, -mediumshade
- 后期调整：Gamma 0.7

## LOL-pi等值面的绘制与渲染
对于非平面体系的LOL-pi等值面图（如苯甲酮），使用cub命令载入格点数据文件并将等值面设为0.5，直接通过VMDrender_full.bat渲染即可获得效果理想的图像。
- 推荐等值面数值：0.5

## VMDrender_full.bat避免阴影过暗的选项
如果在VMDrender_full.bat中加入-shadow_filter_off选项，可以避免由于等值面产生大量阴影而使得图像较暗的问题。
- 添加选项：-shadow_filter_off

## 渲染图像尺寸与计算耗时的关系
VMDrender_full.bat文件中-res参数后面的数字定义了渲染图像的尺寸，该数值设置得越小，Tachyon渲染的耗时就越低。
- 控制参数：-res

## 等值面光滑度与格点间距的关系
等值面的光滑程度与计算格点数据时的格点间距有直接关系，间距越小等值面越光滑，但计算成本也越高，详细讨论见《Multiwfn FAQ》Q39。
- 参考文献链接：http://sobereva.com/452

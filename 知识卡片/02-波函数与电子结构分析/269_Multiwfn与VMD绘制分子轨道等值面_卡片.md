---
id: 269
title: 使用Multiwfn观看分子轨道
url: http://sobereva.com/269
domain: 波函数与电子结构分析
topic: Multiwfn与VMD绘制分子轨道等值面
cards: 26
---

# Multiwfn与VMD绘制分子轨道等值面 — 知识卡片

## 1. 推荐阅读的补充文章

作者补充了《使用Multiwfn+VMD快速绘制高质量分子轨道等值面图》（http://sobereva.com/447）和《用VMD绘制艺术级轨道等值面图的方法》（http://sobereva.com/449），配有演示视频，介绍了基于脚本方便快速地将Multiwfn与VMD结合绘制轨道图像的方法，建议看完本文后阅读。

---

## 2. 引用要求与相关资源

使用Multiwfn绘制轨道图用于发表文章或给别人代算时，必须按照Multiwfn启动时的提示正确引用Multiwfn。如果不了解Multiwfn，建议阅读《Multiwfn FAQ》（http://sobereva.com/452）和《Multiwfn入门tips》（http://sobereva.com/167）。

---

## 3. 观看轨道的输入文件类型选择

Gaussian、Q-Chem、PSI4用户使用fch文件；ORCA、Molpro、MRCC、NWChem、xtb、Dalton、deMon2k、BDF用户使用molden文件；GAMESS-US用户需将输出文件后缀改为.gms。详情参见《详谈Multiwfn支持的输入文件类型、产生方法以及相互转换》（http://sobereva.com/379）。

---

## 4. 非标准molden文件的处理与周期性体系

Molcas、CFour、Turbomole等生成的非标准.molden文件需先用molden2aim程序转换成标准.molden文件（见Multiwfn手册5.1节）。Multiwfn可观看CP2K产生的包含晶胞信息的.molden文件来显示周期性体系轨道（http://sobereva.com/588），具体例子见http://sobereva.com/634。

---

## 5. 主功能0的启动与轨道信息显示

启动Multiwfn并输入文件名后输入0进入图形界面，文本窗口显示HOMO、LUMO能量及Gap（例如HOMO: -0.246291 a.u., LUMO: 0.003620 a.u., Gap: 0.249912 a.u.）。图形界面中绿色和蓝色分别代表轨道相位的正负部分。

---

## 6. 轨道选择的快捷操作

在图形界面右下角输入框支持输入轨道序号或标签，如h代表HOMO，l代表LUMO，h-1代表HOMO-1，l+2代表LUMO+2，ha-3代表alpha HOMO-3，lb+2代表beta LUMO+2。

---

## 7. 等值面数值(Isovalue)与显示质量

Isovalue默认值为0.05，比gview默认的0.02大，对于大体系或分布广的轨道需设为0.02或更小。如果等值面有棱有角，应在图形窗口上方选择Isosur. quality增加格点数，或在settings.ini里把nprevorbgrid改大。

---

## 8. 图形界面视角调整与控制

旋转使用鼠标左键拖动或界面按钮；缩放使用鼠标滚轮或Ctrl+左键上下拖动；沿屏幕旋转使用Ctrl+左键左右拖动；平移使用Shift+左键拖动（涉及鼠标拖动的操作仅限2025-Jun-3及以后更新的版本）。

---

## 9. 图像保存、布局与标签设置

点击Save picture保存图像，尺寸和格式由settings.ini里的graph3Dsize和graphformat调整。若窗口显示不全，可把settings.ini里的imodlayout设为1或2。原子标签类型可通过Other settings里的Set atomic label type或settings.ini里的iatmlabtype3D修改。

---

## 10. 多轨道显示与键/原子设置

选中"Show+Sel.isosur#2"可同时显示两条轨道，第二条轨道正负相位分别为黄绿色和紫色。"Bonding threshold"控制成键阈值，"Ratio of atomic size"设为4.0时原子球半径等于Bondi范德华半径，设为0则不显示原子球。

---

## 11. 颜色自定义方法

原子标签颜色和键颜色分别通过settings.ini里的atmlabRGB和bondRGB参数（RGB分量0~1）调节。原子球颜色通过settings.ini里的atmcolorfile指定文件（如基于examples目录下的element_color.txt修改）来设定。

---

## 12. 轨道信息汇总与导出

点击Orbital info. - Show all可在文本窗口输出所有轨道的能量、占据数和自旋类型，可复制轨道能量列。Orbital info.里提供选项只输出占据轨道或输出最高到LUMO+10的轨道。

---

## 13. 等值面显示风格与光源调节

Isosur#1 style菜单提供5种显示风格：Solid face、Mesh、Transparent、Solid face+mesh、Points。若渲染效果不好，可选择Other settings里的Set lighting调节5个光源的开启状态。

---

## 14. 开壳层波函数的轨道编号

非限制开壳层波函数中，前x个轨道是alpha，后x个是beta。查看beta轨道可用负值输入，如输入-7查看第7号beta轨道（程序会自动转换为对应的总序号）。

---

## 15. 里德堡轨道的显示设置

查看里德堡轨道时，为防止等值面被截断，应选择Other settings里的Set extension distance，输入较大的值（如12 Bohr）。

---

## 16. 工具菜单功能

Tools菜单包含保存绘图设置到GUIsettings.ini、测量键长/键角/二面角、批量绘制轨道图形（详见视频演示：https://www.bilibili.com/video/av69765564/）、通过原子序号得到片段所有原子序号等功能。

---

## 17. 绘制高质量轨道图的推荐流程

建议流程：进入主功能0选择轨道并设置isovalue -> 关闭坐标轴并调整视角和标签大小 -> 用Set lighting调整光源 -> 选择Isosur. quality（中体系High quality，大体系Very high quality） -> 保存图片并缩小至50%以抗锯齿。

---

## 18. 显示指定原子贡献的轨道部分

在主菜单选6进入波函数修改功能，选-3并输入原子序号（如2,3,5,6），可将所有轨道在其余原子上的展开系数清零，再次进入主功能0即仅显示指定原子贡献的轨道部分。此操作不可逆，需重启Multiwfn恢复。

---

## 19. 绘制轨道波函数的曲线图

启动Multiwfn后依次输入：文件名 -> 3（绘制曲线图） -> 4（绘制轨道波函数） -> 轨道序号 -> 0（调整延展距离） -> 4（延展距离4Bohr） -> 1 -> 输入定义直线的两个原子序号。

---

## 20. 绘制轨道波函数的平面图

启动Multiwfn后依次输入：文件名 -> 4（绘制平面图） -> 4（绘制轨道波函数） -> 轨道序号 -> 2（等值线图） -> 选择平面类型（如3为YZ平面） -> 输入平面位置参数。

---

## 21. 导出单个轨道的cube文件

在主菜单选择5，依次选择4（轨道波函数）、输入轨道序号、选择格点质量（如2为中等质量格点），选-1可直接观看等值面，选2将格点数据导出为MOvalue.cub。

---

## 22. 批量导出多个轨道到单一cube文件

在主菜单选择200，选3，输入轨道序号（如20,23,25-30），选择格点质量，选2将选中轨道的格点数据导出到单一cube文件（orbital.cub），方便在VMD中查看。

---

## 23. 使用VMD查看轨道的显示设置

将orbital.cub拖入VMD，在Graphics-Representation中：首先将Drawing Method改为CPK并调小Sphere Scale；然后新建Representation，设Drawing Method为Isosurface，Isovalue设为0.03（正相位）或-0.03（负相位），Draw设为Solid Surface，Coloring Method设为ColorID选择颜色，Vol下拉框选择具体轨道。

---

## 24. VMD图像背景、保存与状态恢复

将背景改为白色：Graphics-Colors-Display-Background-White；关闭坐标轴：Display-Axes-Off；保存图像：File-Render选Tachyon。保存显示设置：Extensions-Visualization-View Master -> Create New -> File-Save as保存为.tcl文件，下次通过File-Load visualization state载入。

---

## 25. 查看轨道展开系数

载入文件后进入主功能6，选选项4并输入轨道序号，文本窗口会输出该轨道的展开系数，包含基函数序号、所属原子、壳层序号、基函数类型和系数数值。

---

## 26. 计算轨道的体积

Multiwfn还可以计算轨道的体积，具体方法参见《使用Multiwfn计算轨道的体积》（http://sobereva.com/734）。

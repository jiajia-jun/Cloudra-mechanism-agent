---
key: b449
title: 用VMD绘制艺术级轨道等值面图的方法（含演示视频）
url: http://sobereva.com/449
domain: 可视化与制图
source: blog
year: 2018
cards: 11
---

# 用VMD绘制艺术级轨道等值面图的方法（含演示视频） — 知识卡片

## 1. VMD与Multiwfn绘制轨道图的版本要求

使用Multiwfn结合VMD绘制高质量轨道等值面图时，必须使用Multiwfn官网提供的最新版本。VMD必须使用1.9.3版本，使用其他版本可能导致操作步骤不兼容或效果差异。若基于此方法发表文章或进行代算，必须引用Multiwfn启动时提示的原始文献。

---

## 2. 演示体系的轨道格点数据设置

以石墨烯片段体系为例，将第183号轨道的等值面数值设为0.02。在绘制前需将配置文件showorb.txt中的倒数第二行修改为3，使Multiwfn通过high quality grid（高质量格点）模式计算分子轨道的格点数据。

---

## 3. VMD原子颜色与材质的脚本设定

VMD脚本VMDrender.txt包含预设的参数，可将碳原子（C）颜色定义为tan（RGB值0.700000, 0.560000 0.360000），使其比默认深青色更柔和。脚本同时调整了Opaque材质的mirror属性（设为0.15）以开启反光效果，并设置outline（轮廓深度为4.000000）和outlinewidth（轮廓粗度为0.5），为原子添加勾边效果以防与背景混淆。

---

## 4. VMD轨道等值面材质与光照的脚本设定

VMDrender.txt脚本将Glossy材质的ambient属性设为0.1，diffuse属性设为0.600000，opacity（不透明度）设为0.75，shininess设为1.0，使轨道等值面呈现微透明且具有光泽的质感。脚本将正值等值面颜色设为ColorID 12（淡绿色），负值部分设为ColorID 22（淡蓝色），并开启额外的3号光源以增强图像亮度。

---

## 5. VMD视角距离与显示参数的调整

通过在VMD文本窗口输入`display distance -7.0`将视角拉远，可避免窗口边缘物体因近大远小产生严重畸变。配合输入`display height 10`设置显示高度，可以抵消因距离拉远导致的图像变小问题，保持物体在视图中的合理比例。

---

## 6. 生成VMD场景的Tachyon输入文件

在VMD中调整分子缩放使其充满图形窗口后，选择File - render，使用Tachyon渲染器点击Start Rendering。此操作会在VMD目录下生成vmdscene.dat（Tachyon输入文件）和vmdscene.dat.bmp（默认设置渲染图像），后者可删除，后续将利用输入文件进行手动参数渲染。

---

## 7. 使用Tachyon渲染高分辨率高质量图像

将Multiwfn自带的批处理文件VMDrender_full.bat拷贝至VMD目录，该文件调用命令`tachyon_WIN32.exe vmdscene.dat -format BMP -o full.bmp -trans_raster3d -res 2000 1500 -fullshade -numthreads 4 -aasamples 24`。该命令使用-trans_raster3d透明着色选项，输出2000x1500像素的full.bmp图像，开启-fullshade阴影效果，设置4个线程数，并将抗锯齿样本数设为24以获得平滑效果。

---

## 8. Tachyon渲染参数的阴影控制选项

在VMDrender_full.bat的命令中加入`-shadow_filter_off`参数，渲染出的图像仍保留阴影效果，但透明的轨道等值面物体将不再产生阴影。相比之下，标准-fullshade模式下透明物体也会投射阴影，用户可根据对图像明暗程度的需求选择是否添加该参数。

---

## 9. 无阴影模式的快速渲染方法

VMDrender_noshadow.bat批处理文件与完整版的主要区别在于将-fullshade替换为-mediumshade。此模式生成的图像没有任何阴影效果，渲染速度通常比全阴影模式更快，视觉风格更为干净简洁。

---

## 10. 图像无法绘制的路径与版本排查

若无法绘制出图像或提示找不到文件，首先应确认使用的是最新版Multiwfn和VMD 1.9.3，且VMD未安装至C盘默认路径以免权限受限。需确保showorb.bat中的VMD路径设置正确（包含空格时需加双引号），且输入文件路径及showorb.txt文件位置无误。输入文件必须包含波函数信息（如.fchk），不可使用.xyz或.pdb等格式。

---

## 11. 图像绘制失败的命令行调试方法

当常规排查无法解决绘制问题时，可在命令行模式下进入Multiwfn目录，将.bat文件中的命令逐行输入运行。根据屏幕输出的错误提示判断具体原因，若无法自行解决，可将相关输出截图发布至Multiwfn官方论坛寻求技术支持。根据经验，绝大多数失败原因为路径书写错误。

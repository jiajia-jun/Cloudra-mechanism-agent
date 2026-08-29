---
id: 449
title: 用Multiwfn结合VMD绘制艺术级轨道等值面图的方法（含演示视频）
domain: 可视化与制图
topic: Multiwfn结合VMD绘制高质量轨道等值面图
cards: 11
---

## 1. VMD版本与Multiwfn引用要求
绘制轨道图必须使用Multiwfn官网最新版本和VMD 1.9.3版，不要使用其它VMD版本。若使用该方法绘制轨道图发表文章，必须引用Multiwfn启动时提示的原文；若替人代算，也必须明确告知对方这一点。

---

## 2. Multiwfn高质量格点数据生成设置
在绘制前需将showorb.txt文件里倒数第二行改为3，使得Multiwfn通过high quality grid格点计算分子轨道的格点数据。示例中以石墨烯片段的第183号轨道为例，等值面数值取0.02。

---

## 3. VMD原子颜色与材质的脚本修改参数
Multiwfn程序包中的examples\scripts\VMDrender.txt文件包含预设的渲染参数，可直接复制到VMD文本窗口执行。关键命令包括：`color change rgb tan 0.700000 0.560000 0.360000` 将碳原子颜色设为tan色；`material change mirror Opaque 0.15` 设置不透明材质反光属性；`material change outline Opaque 4.000000` 和 `material change outlinewidth Opaque 0.5` 设置原子轮廓；`material change opacity Glossy 0.75` 设置等值面微透明。

---

## 4. VMD显示视角与光照的调整命令
使用`display distance -7.0`让视角距离画面更远，避免窗口边缘物体因近大远小产生畸变；使用`display height 10`补偿因减小距离导致的图像变小；使用`light 3 on`开启额外的3号光源以增加图像亮度。

---

## 5. 等值面正负值颜色的设置方法
通过`mol modcolor 1 top ColorID 12`将正值部分等值面颜色修改为淡绿色；通过`mol modcolor 2 top ColorID 22`将负值部分等值面颜色修改为淡蓝色。

---

## 6. Tachyon渲染器输入文件的生成步骤
在VMD中适当缩放分子使其充满图形窗口，选择File - render，选择Tachyon并点击Start Rendering。这会在VMD目录下生成vmdscene.dat（Tachyon输入文件）和vmdscene.dat.bmp（默认渲染图像，可删除）。

---

## 7. Tachyon全阴影高质量渲染命令
将VMDrender_full.bat文件拷到VMD目录并运行，命令为`tachyon_WIN32.exe vmdscene.dat -format BMP -o full.bmp -trans_raster3d -res 2000 1500 -fullshade -numthreads 4 -aasamples 24`。参数`-trans_raster3d`提供最佳透明着色效果，`-res 2000 1500`设定像素，`-fullshade`包含阴影，`-numthreads 4`设为CPU物理核心数，`-aasamples 24`设定抗锯齿。

---

## 8. Tachyon阴影过滤效果的开启方法
在VMDrender_full.bat命令中添加`-shadow_filter_off`参数，此时透明材质的轨道等值面不会产生阴影，图像整体效果会比全阴影渲染更明亮。

---

## 9. Tachyon无阴影快速渲染命令
使用VMDrender_noshadow.bat进行渲染，其与全阴影渲染的区别在于将`-fullshade`替换为`-mediumshade`。此模式渲染速度更快，图像没有阴影效果，显得干净简洁。

---

## 10. 绘图失败的路径与版本排查
确保VMD未安装在C盘默认路径以免权限受限；确保showorb.bat中VMD路径正确且包含空格时使用双引号括起；确保输入文件路径正确且格式包含波函数信息（如.xyz或.pdb不行）；必须使用Multiwfn最新版和VMD 1.9.3版。

---

## 11. 绘图失败的命令行调试方法
若无法绘图，进入系统命令行并定位到Multiwfn目录，将.bat文件里的命令逐行输入运行。根据屏幕提示判断错误原因。根据经验，90%的失败原因是路径书写错误。

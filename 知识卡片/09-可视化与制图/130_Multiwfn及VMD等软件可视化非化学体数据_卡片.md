---
id: 130
title: 谈谈体数据3：用Multiwfn、Gaussview、Molekel、VMD观看龙虾、盆景、骨盆、大脑
url: http://sobereva.com/130
domain: 可视化与制图
topic: Multiwfn及VMD等软件可视化非化学体数据
cards: 1
---

# Multiwfn及VMD等软件可视化非化学体数据 — 知识卡片

## 1. 龙虾体数据获取与参数

Volrenapp老版体数据库提供名为lobster.raw.gz的龙虾CT扫描体数据，点数为301x324x56，格子比例为1:1:1.4。此数据为8bit精度，下载后需解压为lobster.raw并使用vodaconv转换为cube文件。

## 龙虾体数据转换操作
将lobster.raw拷至vodaconv目录，运行vodaconv.exe，依次输入：文件名lobster.raw，点数301,324,56，间距0.1,0.1,0.14（保持1:1:1.4比例），原点直接回车（自动设为中心），数据类型1（8bit整数），缩放选项2（不做scale），输出文件名lobster.cub。

## Cube文件体积膨胀原因
转换后的lobster.cub文件大小为69.5MB，远大于原始lobster.raw文件的5.2MB，这是因为.raw是二进制文件每个数据点占1字节，而cube文件记录字符数据每个数据点需13个字符，导致体积膨胀约13倍。

## Multiwfn显示大型体数据设置
在Multiwfn的settings.ini文件中将aug3D参数从默认的6改为16，确保坐标轴足够长以显示完整龙虾；启动Multiwfn载入lobster.cub，选择功能0显示等值面。

## Multiwfn显示龙虾的等值面设置
在Multiwfn中显示龙虾时需将等值面数值设为50。默认的0.05值过小会导致图像被CT扫描噪音或空气信号掩盖；8bit整数数据范围在0~255，需在该范围内调整数值以获得最佳图像效果。

## 转换文件中的氢原子标签
使用vodaconv转换raw文件为cube文件时，程序会在原点自动加入一个氢原子标签以保持兼容性，在Multiwfn中可通过取消勾选Show label复选框将其隐藏。

## 盆景体数据转换与参数
从Volrenapp数据库下载盆景体数据bonsai.raw.gz，使用vodaconv转换时输入点数256,256,256，间距直接回车使用默认值0.1,0.1,0.1（1:1:1比例），其他步骤与龙虾数据转换相同。

## GaussView显示盆景操作
启动GaussView打开bonsai.cub文件，进入Results-Surfaces/Contours，将Density设为50，点击Surface Actions-New surface生成等值面；可通过右键菜单View-Hydrogens屏蔽额外加入的氢原子。

## GaussView显示大型体数据的局限
GaussView显示大型体数据等值面速度很慢，对于256^3=1600万个点的体数据尚可显示，但对于更高精度如512^3=1.34亿个点的情况则无法实际应用。

## 16位骨盆体数据转换
在Volrenapp新版数据库下载Stented Abdominal Aorta 16Bits数据stent16.raw.zip，解压后使用vodaconv_LE.exe进行转换，因为该数据库16位整数数据为Little Endian顺序。

## 骨盆体数据转换参数
运行vodaconv_LE.exe，依次输入：文件名stent16.raw，点数512,512,174，间距0.8398,0.8398,3.2，原点回车，数据类型2（16bit整数），缩放选项2，输出文件名stent16.cube（Molekel要求后缀为.cube）。

## Molekel显示骨盆支架设置
在Molekel 5.4.0.8中打开stent16.cube，选择Surfaces-Grid data，在Value中填入1300以显示腹部动脉支架；若将Value设为700则可显示身体表层及背板结构。

## Molekel内存与显示设置
在Molekel中显示大型体数据需保证有1.5GB空余内存以全精度显示；若需节省内存或加快显示速度，可将Step Multiplier设为2或更大；Molekel在生成等值面时可能崩溃。

## 大脑DTI数据格式转换
从Volrenapp库下载DTI-B0.pvm，使用pvm2raw程序将其转换为DTI-B0.raw格式，再使用vodaconv.exe（Big Endian顺序）转换为DTI-B0.cub供VMD显示。

## VMD显示大脑等值面基础操作
将DTI-B0.cub拖入VMD，在Graphics-Representation中将Drawing Method设为Isosurface，Draw改为Solid surface，拖动Isovalue滑条至500左右即可看到大脑外层轮廓。

## VMD多层透明等值面设置
在VMD中将Display-Rendermode设为GLSL以支持透明效果，创建三个Isosurface显示方式：Isovalue 260（Transparent材质），Isovalue 720（Transparent材质，ColorID 4黄色），Isovalue 1250（Opaque材质，ColorID 1红色）。

## VMD显示大脑切片图
在VMD中建立VolumeSlice显示方式，拖动Slice Offset可查看不同位置的截面图；关闭Display-depth cueing可使切片图更鲜亮，配合Color scale设置可模拟黑白医疗影像效果。

## 使用Multiwfn提取大脑截面数据
启动Multiwfn载入DTI-B0.cub，利用主功能13提取XY平面数据，输入Z值-0.181埃（根据VMD中Z offset=0.44及体数据Z范围计算得出），数据将输出至output.txt。

## Sigmaplot绘制精细截面图
使用Sigmaplot导入Multiwfn生成的output.txt，选择contour plot的Filled color模式，X,Y,Z分别对应第1、2、4列，将绘图上下限设为100和1100，可获得比VMD更精细的截面图。

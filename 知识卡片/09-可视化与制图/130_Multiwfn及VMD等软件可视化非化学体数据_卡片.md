---
id: 130
title: 谈谈体数据3：用Multiwfn、Gaussview、Molekel、VMD观看龙虾、盆景、骨盆、大脑
url: http://sobereva.com/130
domain: 可视化与制图
topic: Multiwfn及VMD等软件可视化非化学体数据
cards: 11
---

# Multiwfn及VMD等软件可视化非化学体数据 — 知识卡片

## 1. 使用Multiwfn显示龙虾体数据

从Multiwfn 2.3版本开始支持读入cube文件并直接显示等值面。操作前需在settings.ini中将aug3D参数从默认的6改为16，以确保坐标轴足够长。载入lobster.cub后选择功能0，在默认isovalue为0.05时图像不可见，需在文本框输入50并回车才可显示龙虾。由于 lobster.raw 是8bit精度（范围0~255），需要在该范围内反复调整isovalue以消除噪音或空气信号干扰获得最佳效果。Multiwfn显示高格点数等值面的速度远低于Molekel和VMD。
- 原始数据：http://www.gris.uni-tuebingen.de/edu/areas/scivis/volren/datasets/datasets.html (lobster.raw.gz, 301x324x56, 比例1:1:1.4)
- vodaconv参数：文件名 lobster.raw，点数 301,324,56，间距 0.1,0.1,0.14，数据类型 1，scale类型 2，输出 lobster.cub

---

## 2. vodaconv转换raw文件导致体积增大的原因

cube文件体积远大于raw文件是因为文件存储格式不同。raw文件是二进制文件，8bit数据点仅占用1个字节；而cube文件记录的是字符数据，每个数据点需要13个字符来表达（即13字节），因此转换后的文件大小约为原始文件的13倍（如lobster.raw从5.2MB增至69.5MB）。
- 数据对比：lobster.raw (5.2MB) -> lobster.cub (69.5MB)

---

## 3. 使用GaussView显示盆景体数据

启动GaussView后，文件类型选Cube files并载入bonsai.cub。进入Results-Surfaces/Contours，将Density设为50（即isovalue），点击Surface Actions-New surface生成等值面。生成完毕后需拉远视角观察，并可通过View-Hydrogens屏蔽掉为了兼容性而自动加入的氢原子标签。
- 原始数据：bonsai.raw.gz (256,256,256, 1:1:1间距)
- 转换参数：间距使用默认0.1,0.1,0.1

---

## 4. GaussView处理大型体数据的性能限制

GaussView在显示大型体数据等值面时速度较慢，缺乏实际应用价值。处理几百万个点的体数据速度尚可，但对于256^3（约1600万）个点的数据已显得吃力，若体数据精度达到512^3（约1.34亿）个点则无法进行等值面显示。
- 性能阈值：256^3 = 16,777,216 points (勉强可用); 512^3 = 134,217,728 points (不可用)

---

## 5. 使用Molekel显示骨盆和动脉支架体数据

对于Volrenapp新版数据库中的16bit整数体数据（如Stented Abdominal Aorta），因其为Little Endian顺序，必须使用vodaconv_LE.exe进行转换。在Molekel中打开生成的stent16.cube，选择Surfaces-Grid data，在Value栏输入1300。由于数据量巨大，显示需1.5GB空余内存；若需节省内存或加快速度，可将Step Multiplier设为2或更大。
- 原始数据：stent16.raw.zip (512,512,174, 间距 0.8398,0.8398,3.2)
- 转换工具：vodaconv_LE.exe (针对Little Endian)
- 转换参数：数据类型 2，scale类型 2，输出后缀必须为.cube

---

## 6. Molekel中Isovalue设置对图像显示的影响

在Molekel中调整Isosurface的Value值可以改变显示的结构层次。将Value设为1300时主要显示腹部动脉支架等高密度物体；若将Value设为700，X射线易穿透的区域（如身体表层结构及扫描背板）也会被显示出来。Molekel在生成等值面过程中可能存在崩溃或不显示的bug。
- Value 1300：显示支架
- Value 700：显示表层及背板

---

## 7. VMD显示大脑体数据的等值面设置

启动VMD并载入DTI-B0.cub，在Graphics-Representation中将Drawing Method设为Isosurface，Draw改为Solid surface，拖动Isovalue滑条到500左右可见大脑外层轮廓。为了同时显示内外层结构，需建立三个Isosurface显示方式：第一个isovalue 260 (Transparent材质)；第二个isovalue 720 (Transparent材质, ColorID 4黄色)；第三个isovalue 1250 (Opaque材质, ColorID 1红色)。将Show选项从Box+Isosurface改为Isosurface以去除边缘。
- 渲染模式：Display-Rendermode设为GLSL以支持透明效果
- 外部渲染：可使用POVray获得更好效果

---

## 8. VMD中显示体数据切片图

在VMD中建立VolumeSlice显示方式，拖动Slice Offset滑条可查看不同位置的截面图。为了获得黑白医院风格的图像，需在Graphics-color-Color scale将Method设为BlkW，并将截面图的Coloring Method设为Volume。在Trajectory标签页调节Color Scale Data Range（如设为0到1000）可增强对比度，建议关闭Display中的所有光源。
- 操作路径：Graphics-Representation -> VolumeSlice
- 颜色设置：Method: BlkW; Coloring Method: Volume

---

## 9. 使用pvm2raw转换DTI大脑体数据格式

V3体数据可视化软件专用的pvm格式文件需先转换为raw格式。下载并运行pvm2raw程序，需建立内容为“pvm2raw DTI-B0.pvm DTI-B0.raw”的bat批处理文件并执行，生成DTI-B0.raw文件。随后使用vodaconv.exe（针对Big Endian顺序）将其转换为cube文件。
- 转换工具：pvm2raw.exe
- vodaconv参数：DTI-B0.raw，点数 128,128,58，间距回车，原点回车，数据类型 2，scale类型 2，输出 DTI-B0.cub

---

## 10. 使用Multiwfn提取指定平面数据

Multiwfn可利用主功能13（格点数据处理功能）提取指定平面的数据。载入cube文件后，通过统计信息得知Z范围（例如-2.85到2.85 bohr），根据VMD中的offset值计算实际坐标（如Z offset 0.44对应-0.181埃）。输入“13”进入功能，选“2”提取XY平面，输入计算出的Z值，数据将输出到output.txt。
- 操作步骤：输入 13 -> 2 -> Z值(埃)
- 坐标计算示例：((2.85*2)*0.44-2.85)*0.5292 = -0.181埃

---

## 11. 使用Sigmaplot绘制高质量大脑截面图

将Multiwfn提取的output.txt导入Sigmaplot（File-import file），选择contour plot按钮及Filled color模式。将数据设为XYZ Triplet，X、Y、Z分别对应第1、2、4列。在图像属性中将Plots-Scale的上下限设为100和1100以优化显示效果。此方法生成的图像比VMD直接显示的截面图更为精细。
- 绘图设置：XYZ Triplet (Cols 1,2,4); Scale: 100~1100

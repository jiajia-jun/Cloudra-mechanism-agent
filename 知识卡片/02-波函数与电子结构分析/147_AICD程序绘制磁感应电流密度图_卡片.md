---
id: 147
title: 使用AICD程序研究电子离域性和磁感应电流密度
domain: 波函数与电子结构分析
topic: AICD程序绘制磁感应电流密度图
cards: 11
---

## 1. 磁感应电流密度与电子离域性的关系
分子体系中外加磁场时，电子离域性强的区域会产生明显的感应环形电流。环电流方向遵循左手规则称为diamagnetic环电流，电流越大芳香性越强；方向相反称为paratropic环电流，电流越大反芳香性越强；无净电流则为非芳香性。富勒烯在磁场下的诱导电流被称为球电流，可参阅相关文献。

---

## 2. AICD函数的定义与意义
AICD（Anisotropy of the Induced Current Density）定义为电流密度张量与外磁场矢量的点乘，其公式见原文。AICD本质上反映相应位置电子对磁场感应的各向异性强度，是一个不依赖外场选取且与电子密度无直接关系的三维实空间标量函数。通过AICD等值面可以方便地研究电子离域性，无需考虑复杂的截面选取或外磁场方向问题。

---

## 3. AICD程序的获取与编译
AICD程序用于绘制AICD等值面和感应电流矢量。安装时将压缩包解压并运行 `make all` 编译，建议建立符号链接 `ln -s./AICD /usr/local/bin/AICD`。程序需读取Gaussian98/03的NMR计算输出的电流密度张量信息，生成cube文件和povray输入文件。

---

## 4. Gaussian源代码修改步骤
使用AICD必须修改Gaussian源代码并重新编译l1002模块以输出电流密度张量。在编译完Gaussian03后，将 `l1002.F.g03.diff` 拷到g03目录并执行 `patch < l1002.F.g03.diff`。若需启用轨道贡献分解功能，需在patch后的 `l1002.F` 中删除 `goto 12` 并在指定位置插入两行代码。之后删除 `l1002.a`，运行 `mg l1002.exe` 重新编译。

---

## 5. Gaussian输入文件轨道范围设定
在Gaussian输入文件末尾指定轨道范围以分析特定轨道的贡献。例如 `17 17` 代表选择17号轨道，`20 21` 代表选择20和21号轨道，即苯的三个pi轨道。若要分析所有sigma轨道应写 `1 16` 和 `18 19`，不写则代表考虑所有轨道。Gaussian输出文件中会列出被考虑（beruecksichtigt）和被忽略的轨道信息。

---

## 6. AICD程序基本命令参数
执行AICD分析的基本命令包含多个参数，如 `AICD -p 80000 -pov -b 0 0 1 -m 4 benzene_AICD.out`。`-p` 设定格点总数，`-pov` 输出povray文件，`-b` 设定磁场方向矢量（仅方向有关），`-m 4` 输出多视角图像。程序会生成 `.icd` 二进制文件及相关的 `.cub`、`.pdb` 和 `.pov` 渲染文件。

---

## 7. AICD程序重要辅助参数
AICD程序提供了若干重要选项以调节输出细节。`-l xxx` 设定等值面数值（默认0.05），`-s` 使等值面平滑但耗时增加，`-rot a b c` 调节视角方向，`-plane` 通过点和法矢定义截断平面。此外，`-nc` 不输出cube文件，`-maxarrow length` 去除超过指定长度的箭头（建议设为2.0）。

---

## 8. Povray渲染图像的操作步骤
将AICD生成的5个povray输入文件拷贝至安装了Povray的Windows文件夹中。双击后缀为 `.RenderMich.pov` 的文件，在窗口中设定分辨率及抗锯齿(AA)选项，点击Run按钮渲染。生成的图像会保存为png文件，黄色为AICD等值面，箭头为电流密度矢量，绿色大箭头为磁场方向。

---

## 9. 苯分子pi与sigma电子的AICD图像特征
苯分子的pi电子AICD图显示感应电流方向满足左手规则，表现为芳香性。sigma电子AICD图显示无整体离域，在C-C成键区和H原子附近产生局部环流。单独考虑pi电子时H原子和C-C sigma键区域无AICD等值面；单独考虑sigma电子时等值面较扁；考虑所有电子时则混合上述特征。

---

## 10. AICD使用的注意事项与常见问题
AICD输出的图像可能是分子的对应异构体，需检查并左右翻转修正。若使用nosymm关键词，需将Gaussian输出文件中的 `Input orientation:` 改为 `Standard orientation:`。渲染视野可通过修改 `.RenderMich.pov` 中的 `location` 值调整，分子朝向可通过 `-rot` 选项或修改 `.Rotate.inc` 调节。

---

## 11. Povray渲染的高级设置与技巧
渲染时可调整光源位置或使用平行光源以覆盖长体系边缘，例如设置 `light_source { < 0, 0, -160 > color rgb < 1.15, 1.15, 1.15 > parallel point_at < 0, 0, 2 >}`。若多视角图像重叠，需修改 `.RenderMich.pov` 中的 `translate` 参数。若只想显示电流箭头，需在文件中删除包含 `Isooberflaeche` 的段落。

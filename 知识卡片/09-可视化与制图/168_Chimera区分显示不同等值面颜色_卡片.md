---
id: 168
title: 在Chimera中用不同的颜色显示不同的等值面
url: http://sobereva.com/168
domain: 可视化与制图
topic: Chimera区分显示不同等值面颜色
cards: 9
---
## 1. Chimera软件等值面多色显示功能

Chimera是化学领域可视化软件中最方便的能自定义特定等值面颜色的软件，可以将电子定域化函数(ELF)等值面图中的孤对区域、共价键区域、内核区域以不同颜色表示。此软件可免费下载：http://www.cgl.ucsf.edu/chimera/。
- Chimera允许用户自定义特定等值面的颜色，解决了GaussView、Multiwfn、Chemcraft、VMD、Molekel等软件无法直接指定特定等值面颜色的问题。
- 该案例使用的是Chimera 1.6.2版，windows-64bit版大小是75MB。

---



---

## 2. 分子结构的线状显示设置

为了避免分子结构妨碍等值面观看，启动Chimera载入结构文件后，应通过Actions菜单将结构设置为细线显示并调整线宽。
- 操作步骤为：选择Actions-Atoms/Bonds-wire，然后选Actions-Atoms/Bonds-wire width-5。

---

## 3. 等值面显示的基本参数设置

在Chimera中载入cube文件后，通过Volume Viewer窗口设置等值面的数值、采样步长和基本颜色。
- 在Volume Viewer窗口的level框里输入目标函数值（如ELF=0.83）并回车。
- 将Step值设为1以获得更细腻的图像（默认值为2）。
- 基本颜色设置方法：点Color右边的框，把G拉到最右边，R、B拉到最左边（例如设为纯绿色）。

---

## 4. 特定区域(Blob)的颜色修改

在Chimera中，不相连的等值面被称为blob，利用tools-measure and color blobs工具可以给特定的blob（如氧的孤对电子区域）设定颜色。
- 选择操作方式：在Use mouse右边的方块中选择（默认是ctrl button 3，即按住ctrl然后点击鼠标右键）。
- 设定目标颜色：点击Color blob选项右边的色彩框，调整RGB值（例如孤对电子区域设为R最小，G和B最大，即青色）。
- 应用颜色：在等值面图上按住ctrl并用鼠标右键点击相应的blob。

---

## 5. 颜色设置的失效条件

一旦修改等值面函数值、对格点数据进行操作，或者更改某些显示方式，自己设定的各个blob的着色方式就会失效，而全都恢复为基本色彩。
- 用户在调整参数时需要注意此限制，避免重复着色工作。

---

## 6. 深度暗示效果的关闭

Chimera默认开启depth cueing效果，会使靠后方的等值面略暗；若想关闭此效果，需在主窗口进行相应操作。
- 操作路径：Tools-Viewing Controls-Effects，然后取消depth cueing。

---

## 7. 等值面透明度与背景颜色调整

可以通过Actions菜单调整等值面的透明度以及将背景颜色改为白色。
- 设置透明度：Actions-Surface-transparency-40%。
- 设置白色背景：Actions-Color-all options-background，然后点White框。

---

## 8. 等值面高级功能与工具

Chimera在显示等值面方面功能灵活强大，Volume Viewer窗口中的Features选项和Tools菜单中的工具可用于特殊目的和精细调整。
- Volume Features：选Features可在Volume Viewer窗口中出现对应选项进行精细调整。
- Volume Eraser：可以抹掉当前等值面中的指定一块区域。
- Measure Volume and Area：可以得到指定的blob的体积和面积。

---

## 9. ELF盆与等值面域的概念区别

ELF、LOL的basin（盆）和domain（域）概念不同，盆是由ELF的零通量面划分的区域，不能通过单一数值的等值面来表现。
- 域是指等值面包围的区域，该例子是数值为0.83的ELF定域化域的图像。
- 盆里面有个ELF极大点，所有的盆加和在一起就是整个分子的空间，表示盆的面上各个位置的函数值一般并不相同。
- 切勿把此例的图说成是ELF盆的图形。

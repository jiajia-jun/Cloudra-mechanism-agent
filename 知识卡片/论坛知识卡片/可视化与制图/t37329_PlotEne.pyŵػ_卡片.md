---
key: t37329
title: PlotEne.py�����ŵػ�����������ͼ
url: http://bbs.keinsci.com/thread-37329-1-1.html
domain: 可视化与制图
source: keinsci
year: 2023
cards: 9
---

# PlotEne.py�����ŵػ�����������ͼ — 知识卡片

## 1. Python脚本绘制能垒图的输入文件格式

plotene.py 脚本默认读取名为 ene.txt 的输入文件，支持通过命令行参数指定其他文件名。输入文件包含初始参数（如 gap、length）及反应物/过渡态/产物的数据行。数据行需按照特定顺序书写：先写反应物、过渡态、产物数据，最后写额外箭头（add）或关键路径（add start/end）信息，且小写顺序不得随意更改。

---

## 2. 反应物/过渡态/产物数据行的语法与参数

对应反应物、过渡态或产物的数据行以空格分隔，包含坐标数据及可选的绘图参数。color 参数后接三个数字，分别指定对应曲线的 RGB 值；width 参数后接两个数字，分别指定曲线和虚线的宽度。若省略 color 和 width，则默认使用 Origin 中的 short dot 样式，颜色为黑色，宽度为 1。

---

## 3. 箭头与关键路径数据行的语法

添加箭头或关键路径的数据行以 add 开头。对于简单箭头，直接在 add 后输入坐标；对于需要指向特定能垒点的箭头，使用 start 和 end 关键字：start 后接一个数字表示对应反应物/过渡态/产物的第几个数据点，end 后接一个数字表示终点的第几个数据点。start 和 end 关键字可省略，若省略则后续第一个数字表示对应数据的序号，第二个数字为偏移值。

---

## 4. Python 脚本的运行命令

执行脚本需要 Python 3 环境，可通过 `python --version` 查看版本。运行命令为 `python plotene.py [ene.txt]`，其中方括号内的 ene.txt 为输入文件名；若输入文件名为默认的 ene.txt，则可省略文件名参数。

---

## 5. 脚本生成的输出文件

脚本运行后会生成 plot0.txt、plot1.txt、plot2.txt 三个文资料件。这些文件分别包含反应路径、反应箭头和关键路径的数据，用于后续在 Origin 中导入绘图。

---

## 6. 在 Origin 中导入数据与绘制折线图

在 Origin 中新建 Workbook，将生成的 plot0.txt、plot1.txt、plot2.txt 文件拖入表格中，此时会出现约 5 列数据（X坐标、Y坐标、线条类型、线条宽度、颜色）。点击 Plot -> Line，选择 X 为 Col(A)，Y 为 Col(B)，点击 Add 添加图层，最后点击 OK 生成初始图片。

---

## 7. 在 Origin 中设置线条样式与颜色

双击图表打开 Plot Properties，在 Style 选项卡下进行设置：从 Col(C) "LinTp" 获取线条类型，从 Col(D) "LinWdt" 获取宽度。颜色设置需选择 By Points -> Direct RGB -> Col(E) "Color"，以便为每段线条应用对应的 RGB 颜色。设置完成后点击 Apply 生效。

---

## 8. 图表细节调整

生成图表后可进一步调整坐标轴范围、刻度、图片大小及坐标轴标签等格式。图表中包含的任意曲线均可通过 RGB 值进行颜色自定义。

---

## 9. 脚本更新标签绘制功能

2023-05-23 的脚本更新增加了对 scatter.txt 文件的支持，该文件用于在图表中绘制标签。

---
id: 320
title: 在Origin中绘制能量折线图的方法
url: http://sobereva.com/320
domain: 可视化与制图
topic: Origin绘制反应能量折线图
cards: 10
---

# Origin绘制反应能量折线图 — 知识卡片

## 1. 能量折线图的绘制工具选择

能量折线图用于描述反应过程中过渡态、中间体的能量及连接关系，纵坐标是能量，横坐标是反应坐标；使用ChemDraw绘制存在横杠位置靠肉眼估计、间距不均匀等缺陷，比较合理的做法是用Origin结合辅助小工具enepro作图。

---

## 2. 绘图示例数据

示例作图包含从左到右7个能量值，单位为KJ/mol，第一个值作为零点；数值依次为：0.0、100.2、29.5、60.3、-57.8、-9.7、-62.0。

---

## 3. enepro输入文件配置

下载enepro程序后，需在当前目录下编写input.txt文件；第一行输入1代表横杠宽度（Bar width），第二行输入2代表横杠之间的间隔（Spacing between bars），从第4行起依次输入能量值。

---

## 4. enepro生成绘图文件

双击启动enepro.exe，程序读取当前目录下的input.txt，会在当前目录下产生scatter.txt文件用于绘制横杠，以及line.txt文件用于绘制折线。

---

## 5. 在Origin中导入数据和添加图层

启动Origin，将scatter.txt和line.txt直接拖进窗口；点击绘制散点图按钮，先选中数据点击Add加入散点作图数据，再选中数据点击Add加入折线作图数据，使Plot List里包含两套数据。

---

## 6. 散点符号样式的设置

双击图中数据点符号，在Symbol标签页将符号改为横杠，加大Edge Thickness使之比较粗，并适当调节Size，使得数据点符号正好覆盖住折线的相应位置。

---

## 7. 数据点标签数值的显示

在数据点符号设置的Label标签页中勾选Enable以显示数值，可设定字体颜色、位置和偏移量；在Display Format框里输入.1代表保留一位小数。

---

## 8. 保存作图模板设置

在图的边框外侧点右键选择Save Format as Theme，设置名称如energy_profile并保存；以后按完全相同步骤作图后，按F7打开Theme Organizer选择该主题，即可套用以前设定的作图样式。

---

## 9. 在图中添加分子结构

在ChemDraw里画好结构按Ctrl+C复制，在Origin里按Ctrl+V即可粘贴；也可以通过右键选择Insert Images from Files导入图片文件，或利用左侧工具栏画直线、箭头、添加文字。

---

## 10. 在图中添加多条反应路径

将对应其他路径的scatter.txt、line.txt导入Origin当前项目；双击作图窗口左上角的灰色“1”字方框，点击plot setup，把对应另外路径的数据也加入到当前作图数据列表里即可。

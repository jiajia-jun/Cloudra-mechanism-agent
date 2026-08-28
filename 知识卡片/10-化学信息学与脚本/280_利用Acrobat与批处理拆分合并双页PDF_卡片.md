---
id: 280
title: 将双页扫描的pdf书籍转换为单页的方法
url: http://sobereva.com/280
domain: 化学信息学与脚本
topic: 利用Acrobat与批处理拆分合并双页PDF
cards: 6
---

# 利用Acrobat与批处理拆分合并双页PDF — 知识卡片

## 1. 切割双页PDF为左右两部分

使用Acrobat软件打开双页扫描的PDF文档，通过Document菜单下的Crop Pages功能将双页切割成左右两半并分别保存为两个PDF文件。在Page Range中输入页面范围（例如From 2 to 281），并在Margin Controls的Right或Left框中输入页面宽度的一半（例如5.88 in）来裁剪，完成后使用File-Save As分别保存为left.pdf和right.pdf。

---

## 2. 将PDF分割为单页独立文件

在Acrobat中打开left.pdf或right.pdf，选择Document-Split Document功能，将Number of pages设为1。点击Output Options，去掉Use label复选框的勾选，点击OK后文档会被分割为多个单页PDF文件（如book_1.pdf、book_2.pdf），原始book.pdf文件随后被删除。

---

## 3. 批处理重命名左侧页面文件

在存放左侧页面文件的文件夹中创建一个文本文件，输入命令`for /f %%i in ('dir *.pdf /b') do (rename %%i %%~nia.pdf)`并将后缀改为.bat。双击执行该批处理文件，会将当前目录下所有PDF文件的文件名末尾加上a后缀（如book_1a.pdf、book_2a.pdf）。

---

## 4. 批处理重命名右侧页面文件

将上述批处理文件中的代码修改为`for /f %%i in ('dir *.pdf /b') do (rename %%i %%~nib.pdf)`，并将其放入存放右侧页面文件的文件夹中执行。这会使右侧PDF文件的文件名末尾加上b后缀（如book_1b.pdf、book_2b.pdf），以便与左侧文件形成交错排列。

---

## 5. 分批合并重命名后的单页文件

将Left和Right文件夹中所有重命名后的PDF文件移入All文件夹，利用Acrobat的右键菜单Combine supported files分批合并。先选择编号<10的文件合并为1.pdf，再选择编号10~99的合并为10.pdf，最后选择编号100~999的合并为100.pdf，防止文件排序错乱。

---

## 6. 最终合并与清理

将分批合并生成的1.pdf、10.pdf、100.pdf再次合并成一个完整的PDF文件。检查合并后的文档，若有重复页面（如封面），在Acrobat中将其删除即可。

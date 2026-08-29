---
key: t10582
title: Windows��Multiwfn������������ɫͼ�Ľű�
url: http://bbs.keinsci.com/thread-10582-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2018
cards: 9
---

# Windows��Multiwfn������������ɫͼ�Ľű� — 知识卡片

## 1. Multiwfn LOL色图批量绘制原理

通过编写bat脚本调用Multiwfn程序，可以实现LOL色图的批量绘制。该方法适用于处理大量波函数文件，能显著提高绘图效率。利用脚本顺序执行命令，可自动完成多个文件的LOL图生成。

---

## 2. 准备输入文件与程序

需将所有后缀为“.wfn”的波函数文件放入Multiwfn程序所在目录下。输入文件格式需为Multiwfn支持的类型，具体格式说明及转换方法可参考相关文档。

---

## 3. 修改settings.ini配置文件

在Multiwfn目录下找到“settings.ini”文件并使用文本编辑器打开。定位到关键字“silent”，将“isilent= 0”中的数值从0修改为1。此步骤用于开启Multiwfn的silent模式，以消除运行过程中的交互提示。

---

## 4. 创建LOL.txt指令文件

在Multiwfn目录下新建一个名为“LOL.txt”的文资料件。该文件内容应包含绘制LOL图所需的按顺序执行的指令代码。指令序列由一系列数字和参数组成，具体内容如下：

===

4 

10 

1 

1000,1000 

1 

1.2 

2

3

5

0,0

3

0.5

11

5

12

1,0

8

1

0

===

---

## 5. 编写基础批处理脚本LOL_batch.bat

在Multiwfn目录下新建“LOL_batch.bat”文件，写入以下代码以实现批量处理。脚本会遍历当前目录下的wfn文件，调用Multiwfn执行LOL.txt中的指令，并将生成的图片重命名。

===

for /f %%i in ('dir *.wfn /b') do (

Multiwfn %%i < LOL.txt >

rename dislin.png %%~ni.png

)

===

---

## 6. 脚本执行效果

当Multiwfn目录下存在一系列如abc.wfn, bca.wfn, cba.wfn等文件时，双击运行LOL_batch.bat。程序将依次处理这些文件，最终生成对应的abc.png, bca.png, cba.png等LOL色图。

---

## 7. 异地文件批量处理方法

若所有“.wfn”文件存放在特定文件夹（如c:\LOL）中，需对批处理脚本进行修改。修改后的脚本如下，用于读取指定路径的文件并将输出图片移动至该路径：

===

for /f %%i in ('dir c:\LOL\*.wfn /b') do (

Multiwfn c:\LOL\%%i < LOL.txt >

move dislin.png c:\LOL\%%~ni.png

)

===

---

## 8. 脚本与程序分目录存放的处理

如果将bat脚本与wfn文件放在同一目录下，而Multiwfn程序位于其他路径，需使用绝对路径调用程序。脚本写法示例如下（需替换实际路径）：

===

for /f %%i in ('dir c:\LOL\*.wfn /b') do (

c:\multiwfn所在路径\Multiwfn c:\LOL\%%i < LOL.txt >

move dislin.png c:\LOL\%%~ni.png

)

===

---

## 9. 使用cd命令的脚本优化方案

另一种处理目录分隔的方案是使用cd命令切换到Multiwfn程序所在目录。此时bat脚本可以和wfn文件放在同一个文件夹下。优化后的脚本如下：

===

cd c:\multiwfn所在路径

for /f %%i in ('dir c:\LOL\*.wfn /b') do (

Multiwfn c:\LOL\%%i < LOL.txt >

move dislin.png c:\LOL\%%~ni.png

)

===

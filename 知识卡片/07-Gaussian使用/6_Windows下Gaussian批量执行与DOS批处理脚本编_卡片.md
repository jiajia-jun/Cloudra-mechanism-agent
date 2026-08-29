---
id: 6
title: 从高斯windows下的批量执行谈DOS批处理文件
domain: Gaussian使用
topic: Windows下Gaussian批量执行与DOS批处理脚本编
cards: 10
---

## 1. Windows下Gaussian批量执行方法一
Windows下高斯批量执行的第一种方法是创建.bcf批处理列表文件。每一行写入输入文件路径和输出文件路径，如C:\QCexperiment\exp3\b1.gjf, b1.out，没用的行开头写!注释掉。用gaussian打开该资料件后，先exit再点三角箭头开始运行，也可以用Utilities-edit batch list编辑并保存。

---

## 2. 批量任务出错处理设置
使用.bcf文件批量执行时，若其中一个任务出错整个批处理会断掉。解决方法是在G03W界面的File-Preference-Process中设定，将默认的"End Batch Run on Error"去掉，则出错后将继续执行后续任务。若去掉"Prompt Message"，运行中将不出现任何对话框，适合无人看管的批量执行。

---

## 3. Windows下Gaussian批量执行方法二
Windows下高斯批量执行的第二种方法是写一个输入文件，里面用--Link1--隔开多个任务。这种方式即addition step方法，适合多个任务有明显相关性，将它们合在一起计算。

---

## 4. DOS批处理运行单个任务
使用DOS批处理运行Gaussian任务前，需在系统环境变量PATH里添加g03路径，并新增GAUSS_EXEDIR变量设为g03所在路径。批处理文件中写入`g03 d:\study\2 e:\2p`，计算d:\study\2.gjf并将结果生成到e:\2p.out，命令中不写.gjf和.out后缀名。

---

## 5. DOS批处理运行单个任务注意事项
使用`g03 输入路径 输出路径`格式时，如果不写输出文件的路径，就默认生成和gjf同文件名的out文件在原gjf文件夹里。若使用E01版本，也可以在命令里写清楚输入和输出文件名的扩展名，例如`g03 1.gjf 1.out`。使用这种方法，若某个.gjf运行失败，将自动继续运行接下来的文件。

---

## 6. DOS批处理循环执行当前目录任务
编写批处理文件`for /f %%i in ('dir *.gjf /b') do g03 %%~ni %%~ni`可以执行当前目录下所有.gjf文件。`for /f... in... do`是循环，`dir /b`只显示文件名，`%%i`是循环变量，`%%~ni`是将`%%i`的.gjf后缀去掉的结果，输出文件名与.gjf相同。

---

## 7. DOS批处理记录运行状态和时间
在批处理中结合循环和条件判断可以记录每个文件的运行结果及结束时间。脚本内容为`@echo off`，`setlocal enabledelayedexpansion`，然后执行`for /f %%i in ('dir *.gjf /b') do (g03 %%~ni %%~ni&if!errorlevel!==0 (echo Calculation of %%i finished at!date!!time!) else (echo Calculation of %%i failed at!date!!time!))`。

---

## 8. DOS批处理基本命令含义
`echo off`用来屏蔽接下来运行的指令，`@`让echo off本身不显示。`&`用来连接前后语句，按顺序执行，因为DOS批处理do后面只能有一条语句，需用&连接多条指令。`if a==b (...) else (...)`是分支语句。`errorlevel`是程序返回代码，运行成功为0，错误为非0。

---

## 9. DOS批处理变量的延迟扩展问题
批处理文件中默认只有每运行完一条语句才更新一次变量的值。例如`set i=3 & echo %i%`显示的是5而不是3，因为设置i=3后并未立刻生效。为避免这种情况，需加上`setlocal enabledelayedexpansion`，之后用`!`括住的变量数值使用即时值，如`!errorlevel!`、`!date!`、`!time!`。

---

## 10. DOS批处理中的变量类型
批处理程序中的变量主要有4种：`%1 %2 %3`对应运行批处理文件时传入的参数；`%i%`是最普通的变量，用set设定；`%%i`用在随循环而变化的变量；用`!`括住的变量如`!errorlevel!`用于在延迟扩展模式下获取变量的实时值。

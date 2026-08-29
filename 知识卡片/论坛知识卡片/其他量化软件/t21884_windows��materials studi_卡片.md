---
key: t21884
title: windows��materials studio����������
url: http://bbs.keinsci.com/thread-21884-1-1.html
domain: 其他量化软件
source: keinsci
year: 2021
cards: 8
---

# windows��materials studio���������� — 知识卡片

## 1. 批量提交计算任务的优势

批量提交任务可在计算过程中节省大量时间与人力成本。设置好参数后，多个任务可连续自动运行，无需人工干预。这种方式允许用户在休息时段同时进行计算任务，从而提高工作效率。

---

## 2. 获取MS计算文件的具体路径

在Materials Studio中设置好计算参数后，不点击Run，而是点击Files菜单下的Save Files即可自动生成计算所需文件。在Project Explorer中右键点击生成的文件夹，选择Open Containing Folder可打开对应目录。在地址栏空白处右键选择“将地址复制为文本”，即可获取当前文件夹的绝对路径。

---

## 3. 获取RunDMol3.bat脚本路径

RunDMol3.bat文件位于Materials Studio的安装目录下。在系统资源管理器中按Ctrl+F搜索“RunDMol3.bat”可快速找到该文件。该文件的默认路径示例为 E:\Materials Studio 7.0\Materials Studio 17.1\etc\DMol3\bin。

---

## 4. Windows批处理脚本编写规范

编写Windows批处理脚本（.bat）时，第一行代码 %1 mshta vbscript:CreateObject("Shell.Application").ShellExecute("cmd.exe","/c %~s0 ::","","runas",1)(window.close)&&exit 用于设置每次打开脚本时自动请求管理员权限。第二行代码 @echo off 用于关闭命令回显，使运行界面更整洁。

---

## 5. 脚本编码与路径设置

在批处理脚本中添加 `chcp 65001` 可将命令提示窗口切换至UTF-8编码，以支持中文显示。`cd` 命令后需接上之前获取的计算文件绝对路径，用于定位计算任务的工作目录。若路径中包含空格，必须使用英文双引号将路径括起来。

---

## 6. RunDMol3命令参数解析

调用计算的核心命令格式为 `call [RunDMol3路径] -np [核数] [任务名]`。参数 `-np` 后跟数字表示指定使用的CPU核心数（如8表示8核）。命令末尾的任务名必须与文件夹名称中的主文件名一致，否则计算无法找到对应的输入文件。

---

## 7. 脚本结束与提示信息

脚本中 `echo.` 用于输出空行，以分隔不同的显示信息。`echo %date% %time%` 用于显示任务完成的具体日期和时间。脚本最后一行 `pause` 会使窗口在计算完成后暂停，等待用户按键才关闭，便于查看运行结果。

---

## 8. 结果文件更新与注意事项

计算完成后，右键点击Materials Studio的Project目录并选择Refresh，即可更新计算数据。对于原有的xsd结构文件，需通过Modules -> DMol3 -> Analysis -> Structure -> Update 将优化后的结构导入。此Windows批处理运行方式与Linux系统下的计算方法逻辑相近。

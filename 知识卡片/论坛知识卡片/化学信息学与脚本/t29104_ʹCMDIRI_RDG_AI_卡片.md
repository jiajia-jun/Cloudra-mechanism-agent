---
key: t29104
title: ʹ��CMD��������IRI/RDG/AIM������ļ�������������
url: http://bbs.keinsci.com/thread-29104-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2022
cards: 8
---

# ʹ��CMD��������IRI/RDG/AIM������ļ������������� — 知识卡片

## 1. IRI与AIM分析方法的应用

IRI和AIM分析方法可用于研究弱相互作用体系，如双π体系等。分析结果主要通过IRI-rho(r)、IRI-sign(lambda2)及IRI图进行可视化展示。计算过程会生成output.txt、func1.cub和func2.cub等关键文件。相关方法步骤可参考Multiwfn官方的拓扑分析与绘图方式介绍。

---

## 2. Multiwfn批量处理准备

使用Multiwfn进行批量计算前，需在setting.ini文件所在目录下准备输入文件（如*.wfn或*.fchk文件）。建议使用.fchk文件作为输入格式。可通过新建.txt文件并编写命令行代码，或使用notepad编辑后保存为.bat批处理文件来执行批量操作。

---

## 3. 批处理文件命令结构解析

批处理文件中 `for /f %%i in ('dir *.fchk /b') do (` 命令用于自动遍历当前目录下所有需要计算的.fchk文件并执行循环操作。此命令确保批量处理脚本能够逐个识别并处理目录中的每一个计算任务文件。

---

## 4. 调用Multiwfn执行计算

批处理命令 `Multiwfn %%i < IRI.txt > NUL` 用于调用Multiwfn程序读取当前文件，并按照IRI.txt文件中预设的指令执行计算。该步骤会利用输入文件生成IRI-sign(lambda2)数据。标准输出被重定向至NUL以抑制屏幕显示。

---

## 5. 输出文件的重命名与移动

命令 `move /Y output.txt %%~ni_s.txt` 用于将计算生成的output.txt文件重命名为与输入文件同名的.txt文件（后缀加_s）。随后的命令 `move /Y %%~ni_s.txt "C:\Users\Desktop\RDG\%%~ni"` 将重命名后的文资料件移动至目标文件夹。/Y参数表示覆盖已存在的同名文件时不提示。

---

## 6. 立方体文件的移动

命令 `move /Y func1.cub "C:\Users\Desktop\RDG\%%~ni"` 和 `move /Y func2.cub "C:\Users\Desktop\RDG\%%~ni"` 用于将计算生成的func1.cub和func2.cub文件直接移动至目标文件夹。这确保了所有可视化所需的立方体数据文件与文本结果归档在同一目录下。

---

## 7. IRI计算指令设置

IRI.txt文件中包含了控制Multiwfn计算IRI的具体指令序列。指令序列依次为：20（进入弱相互作用可视化及拓扑分析模块）、4（选择IRI计算）、3（选择计算梯度）、2（生成output.txt文件）、3（生成func1.cub和func2.cub文件）。这些数字对应Multiwfn交互界面中的功能选项。

---

## 8. 计算结果可视化

运行双击IRI.bat文件完成批量计算后，可使用VMD程序对生成的数据进行可视化分析。该方法不仅适用于IRI，也可通过修改指令文件用于RDG、AIM等其他需要可视化的相互作用分析。

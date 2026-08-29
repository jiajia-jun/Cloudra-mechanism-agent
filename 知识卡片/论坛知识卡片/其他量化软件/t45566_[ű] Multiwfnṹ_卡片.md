---
key: t45566
title: [�ű�] ��Multiwfn�������ṹ�Ż��������cp2k�����ļ�
url: http://bbs.keinsci.com/thread-45566-1-1.html
domain: 其他量化软件
source: keinsci
year: 2024
cards: 7
---

# [�ű�] ��Multiwfn�������ṹ�Ż��������cp2k�����ļ� — 知识卡片

## 1. CP2K 结构优化输入文件批量生成需求

CP2K 结构优化计算涉及大量的 *.pdb 文件，若使用 Multiwfn 手动将 *.pdb 文件转换为 CP2K 输入文件，过程繁琐且效率较低。

---

## 2. Multiwfn 调用参数文件内容 (pdb2inp.txt)

使用 Multiwfn 生成 CP2K 输入文件时，需调用包含以下指令的文资料件（如 pdb2inp.txt）：
- 100 // Other functions (Part 1)
- 2 // Export input file
- 25 // CP2k
- -1 // Choose task
- 1 // Energy
- 0 // Gernerate
- 0 // Return
- q //quit

---

## 3. Windows 批处理脚本内容 (pdb2inp.bat)

Windows 系统下可使用批处理脚本自动化处理文件转换、移动及任务提交脚本生成，脚本内容如下：
```batch
@echo off

for %%i in (*.pdb) do ( 
D:\Multiwfn\Multiwfn.exe %%i < pdb2inp.txt
)

if not exist ".\task" mkdir ".\task"

for %%f in (*.inp) do ( 
move %%f ".\task\" > nul
)

set "inplist=.\task\inplist.sh"
if exist "%inplist%" del "%inplist%"

for %%f in (.\task\*.inp) do (
echo mpirun -np 4 cp2k.popt %%~nxf ^|tee %%~nf.out >> "%inplist%"
)

echo All done!
```

---

## 4. 脚本使用环境配置要求

运行脚本前需将所有待处理的 *.pdb 文件放置在同一目录下，并将脚本中的 `D:\Multiwfn\Multiwfn.exe` 路径修改为 Multiwfn.exe 程序的实际存放地址。

---

## 5. 脚本自动化流程说明

该脚本执行以下操作：自动调用 Multiwfn 将当前目录下所有 *.pdb 文件转换为 *.inp 文件，将生成的 *.inp 文件移动至名为 "task" 的子目录中，并在 "task" 目录内生成用于批量提交计算的 inplist.sh 文件。

---

## 6. 批量提交脚本命令配置

生成的 `inplist.sh` 文件中默认包含的提交命令为 `mpirun -np 4 cp2k.popt [文件名] |tee [输出文件名]`，用户可根据实际计算需求修改脚本中的并行核数或 CP2K 可执行文件名称。

---

## 7. 脚本参数自定义修改项

用户可根据实际情况修改脚本中的参数，包括待转换的文件类型（如 *.pdb）、Multiwfn 的参数指令文件（pdb2inp.txt）、生成的 .inp 文件存放目录名称（task）以及提交计算的具体命令内容。

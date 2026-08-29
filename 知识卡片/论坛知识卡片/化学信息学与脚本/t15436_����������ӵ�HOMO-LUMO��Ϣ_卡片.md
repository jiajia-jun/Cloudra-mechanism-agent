---
key: t15436
title: ����������ӵ�HOMO-LUMO��Ϣ��txt������
url: http://bbs.keinsci.com/thread-15436-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2019
cards: 5
---

# ����������ӵ�HOMO-LUMO��Ϣ��txt������ — 知识卡片

## 1. Multiwfn 批量提取 HOMO/LUMO 能级与 Gap

Multiwfn 支持通过脚本批量化处理计算文件，自动输出包含 HOMO、LUMO 能级及 HOMO-LUMO Gap 的文资料件。此方法适用于需要对比大量体系电子结构的场景，能够避免重复手动输入指令。
- 批处理脚本可调用 Multiwfn 针对目录下所有 .fchk 或 .gbw 文件执行任务，并将结果重定向保存。

---

## 2. 批处理指令脚本 1.bat 内容

Windows 批处理脚本 1.bat 用于遍历当前目录下的 .fchk 文件，调用 Multiwfn 执行预设控制文件，并将标准输出保存为 txt 文件。
- 脚本代码如下：
```
for /f %%i in ('dir *.fchk /b') do (
Multiwfn %%i < HOMOLUMOGAP.mf > 1.txt
rename 1.txt %%~ni_GAP.txt
)
```

---

## 3. Multiwfn 控制文件 HOMOLUMOGAP.mf

HOMOLUMOGAP.mf 是 Multiwfn 的输入控制文件，用于指定程序功能选项。
- 输入内容仅为数字 `0`，代表选择主功能 0（基本信息输出）。

---

## 4. 批处理指令脚本 2.bat 内容

Windows 批处理脚本 2.bat 利用 PowerShell 正则表达式提取各个 txt 文件中的特定信息，并合并汇总到 IAMfACkINGAWESOME.txt 文件中。
- 脚本代码如下：
```
@echo off
pushd "%~dp0"
Powershell -NoProfile -Command "Get-Item -Path .\*.txt | ForEach-Object { if ([System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::Default) -match 'Note:(?:.*\n){2}.*') { $_.BaseName; $Matches[0]; ''; } } | Set-Content -Path .\IAMfACkINGAWESOME.txt -Encoding oem "
popd
pause
exit /b
```

---

## 5. HOMO/LUMO 信息输出格式

汇总文件 IAMfACkINGAWESOME.txt 中包含各体系的 HOMO 轨道序号、能量、LUMO 轨道序号、能量以及 Gap 值，能量单位包含 a.u.、eV 和 kJ/mol。
- 输出示例如下（数值为原文占位符）：
```
PGRE_YDD_GAP
Note: Orbital 105 is HOMO, energy: -1111111 a.u. -1111111 eV
 Orbital 106 is LUMO, energy: -0.1111111 a.u. -0.1111111 eV
 HOMO-LUMO gap: 0.1111111 a.u. 11111119 eV 11111117 kJ/mol
```

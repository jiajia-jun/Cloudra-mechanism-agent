---
id: 21
title: VMD的APBS插件提示...unreadable的解决方法
url: http://sobereva.com/21
domain: 其他量化软件
topic: VMD的APBS插件报错unreadable修复
cards: 4
---

# VMD的APBS插件报错unreadable修复 — 知识卡片

## 1. VMD APBS插件报错...unreadable的原因

VMD的APBS插件提示...unreadable是一个已知bug，mailing list已有报告但未给出解决方法。该问题的实质原因是APBS插件写入apbs.in文件里面的pqr文件路径有误。虽然偶尔通过修改临时文件路径能解决，但大多数情况下并不奏效。

---

## 2. 修改apbs.in文件修正路径的方法

照常操作，点击Run之后出现...unreadable提示，进入生成的临时文件夹（例如c:\apbs.27460）。修改apbs.in里面mol pqr后面的pqr路径成为正确路径，然后进入dos提示符并进入此目录。

---

## 3. 手动运行APBS生成.dx文件的命令

在修正apbs.in文件后，需在dos提示符下进入该目录，手动运行命令apbs apbs.in。执行此命令前，需先把apbs.exe路径加入系统-高级-环境变量-PATH环境变量中。运行后在此目录下得到.dx文件，根据任务不同文件名会不同。

---

## 4. 在VMD中手动加载结果文件的步骤

进入VMD先载入pqr文件，再把生成的.dx文件加载进此分子ID中即可，之后可进行后续操作。此外也可以修改apbsrun.tcl文件解决问题，但过程相对麻烦。

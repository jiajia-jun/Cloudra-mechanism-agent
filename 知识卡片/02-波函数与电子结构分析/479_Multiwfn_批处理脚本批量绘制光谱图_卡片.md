---
id: 479
title: 使用Multiwfn一键批量产生各类光谱图（含演示视频）
url: http://sobereva.com/479
domain: 波函数与电子结构分析
topic: Multiwfn_批处理脚本批量绘制光谱图
cards: 7
---

# Multiwfn_批处理脚本批量绘制光谱图 — 知识卡片

## 1. 批量绘制光谱的前置条件

使用Multiwfn一键批量产生光谱图需要2019-Apr-28及之后更新的程序包，且必须预先阅读《使用Multiwfn绘制红外、拉曼、UV-Vis、ECD、VCD和ROA光谱图》一文以了解支持的输入文件类型（如Gaussian、ORCA等程序的电子激发计算、振动分析任务输出文件）。
- 程序下载地址：http://sobereva.com/multiwfn
- 参考文档：http://sobereva.com/224

---

## 2. Windows下批量绘制光谱的文件准备

在Windows下运行批量绘图需将输入文件（如.out文件）、examples\spectra目录下的UV-Vis.txt和batchspec.bat文件拷贝到Multiwfn目录下，并修改settings.ini文件将isilent设为1以启用安静模式。
- 安静模式作用：防止处理文件时弹出图像窗口需手动关闭

---

## 3. Windows批处理脚本batchspec.bat内容

batchspec.bat通过循环调用Multiwfn处理当前目录下所有.out文件，并将输出重定向到NUL，最后将生成的DISLIN.png重命名为与输入文件同名的.png文件。
- 脚本内容：
```batch
for /f %%i in ('dir *.out /b') do (
 Multiwfn %%i < UV-Vis.txt > NUL
 rename DISLIN.png %%~ni.png
)
```

---

## 4. Multiwfn光谱绘制指令文件UV-Vis.txt

UV-Vis.txt记录了在Multiwfn界面中输入的指令序列，用于定义绘制UV-Vis光谱的各项参数，包括功能选择、坐标轴设定及图像输出。
- 文件内容示例：
```
11 //光谱绘制功能
3 //绘制UV-Vis
0 //显示一次光谱
3 //修改横坐标设定
150,850,100 //初值，终值，步长
4 //修改左侧坐标轴（对应摩尔吸收系数）
0,45000,5000 //初值，终值，步长
y //对右侧纵坐标做相应的缩放/平移
5 //修改右侧坐标轴（对应振子强度）
0,1.0,0.1 //初值，终值，步长
n //不对左侧坐标轴做相应的缩放/平移
1 //产生图像文件
```

---

## 5. 切换光谱类型的操作方法

若需批量绘制红外光谱等其他类型光谱，可将examples\spectra目录下的IR.txt拷贝至Multiwfn目录，并将batchspec.bat中的UV-Vis.txt替换为IR.txt，双击运行即可。
- 其他支持类型：ROA、Raman、VCD、ECD、光电子谱

---

## 6. Linux下批量绘制光谱的脚本操作

在Linux下使用需将batchspec.sh、UV-Vis.txt及输入文件拷至当前目录，运行chmod +x ./batchspec.sh赋予权限后执行./batchspec.sh。
- 脚本内容：
```bash
#!/bin/bash
  for inf in *.out
  do
  Multiwfn ${inf} < UV-Vis.txt > /dev/null
  mv -f dislin.png ${inf//out/png}
  done
```

---

## 7. Linux下配置批量绘图快捷命令

为了方便使用，可将batchspec.sh和UV-Vis.txt固定目录（如/sob），修改脚本中的路径，并在~/.bashrc中设置alias，实现在任意包含输出文件的目录下运行UV命令生成图片，或运行gUV命令编辑参数文件。
- 配置示例：
```bash
alias UV='/sob/batchspec.sh'
alias gUV='gedit /sob/UV-Vis.txt'
```

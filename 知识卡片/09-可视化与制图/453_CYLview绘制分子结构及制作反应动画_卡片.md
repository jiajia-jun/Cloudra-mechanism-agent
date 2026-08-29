---
id: 453
title: 使用CYLview绘制高质量分子结构图和制作化学反应演示动画（视频演示）
domain: 可视化与制图
topic: CYLview绘制分子结构及制作反应动画
cards: 12
---

## 1. CYLview软件简介与演示视频
CYLview功能不算强大，但在作图特性方面没有其它程序能很好取代。录制了长为11分钟的使用CYLview绘制分子结构图和制作各种类型动画的演示视频。此内容是对视频内容进行一些补充说明，着重讲解新用户容易犯懵、不是显而易见的操作。

---

## 3. 安装OpenBabel扩展文件支持
如果机子里没装化学文件格式转换程序Openbabel的话，CYLview只能载入Gaussian输出文件，因此很不方便。所以强烈建议在机子里装上Openbabel，是个免费程序。

---

## 4. 解决Gaussian 16输出文件载入问题
有些人发现目前的CYLview载入不了G16的输出文件，是因为没有按照视频里提及的方式去点击更新程序按钮，更新过之后就没问题了。

---

## 5. 使用Houkmol显示风格
视频里使用了Houkmol的style，这是CYLview里内置的一种显示风格的组合，是搞有机体系计算知名的Houk文章里常见的显示风格。

---

## 6. 使用renderall.bat批量渲染POVRAY文件
批处理文件内容如下
for /f %%i in ('dir *.pov /b') do (
povray +W640 +H480 +A %%i
将这些内容复制到一个文该资料件里，改名成renderall.bat即可使用。此脚本会调用当前目录下的povray.exe对当前目录下的所有povray渲染器文件（.pov）进行渲染，产生出同名图像文件。

---

## 7. FFmpeg工具简介与基本格式
程序为免费、小巧、功能强大的视频编码、解码、转换程序，支持格式众多，可在各操作系统使用，Windows 版解压即用。基本使用格式为 ffmpeg [选项] [输入选项] -i [输入文件] [输出选项] [输出文件]。

---

## 8. 使用FFmpeg制作MP4动画
制作 mp4 动画时用到的命令
ffmpeg -r 15 -i FRAME%04d.png -crf 22 video.mp4
其中%04d代表通配0001、0002、0003...。-r后面是每秒的帧数，视频实际长度就是图像数目除以r值，因此r越大动画播放越快，r越小播放越慢。-crf是ffmpeg调用的名为x264的编码器里的参数，数值越小动画越清晰，但是文件越大，一般-crf 22就比较合适。

---

## 9. 使用FFmpeg制作高质量GIF动画
制作 gif 动画时用到的命令
ffmpeg -i FRAME0001.png -vf palettegen palette.png
ffmpeg -r 15 -i FRAME%04d.png -i palette.png -lavfi paletteuse video.gif
虽然ffmpeg也可以一步就产生gif动画，即把前述命令的mp4后缀改成gif，但是动画里的某些颜色比较诡异，远不如上面这样先根据实际图像文件生成调色板文件，再产生gif动画来得好。

---

## 10. GIF与MP4格式对比
gif文件比mp4大得多，而且只能包含256色，但好处是可以直接嵌入到网页和ppt里。

---

## 11. CYL_mergeTXT.exe工具介绍与下载
用于合并带 _txt 后缀和不带该后缀的.pov 文件的工具如下。带 _txt 后缀的文件仅包含标签内容，而不带该后缀的包含分子结构信息。

---

## 12. GauIRC2xyz工具下载地址
工具《将Gaussian的IRC任务输出转换为.xyz轨迹文件的工具》下载地址如下

---

## 13. 相关动画制作工具文章推荐
制作计算化学相关视频用到的 imagemagick 工具可改用 ffmpeg 工具，速度更快且 Windows 版可直接使用。制作动画分析电子结构特征，通过键级曲线和 ELF/LOL/RDG 等值面动画研究化学反应过程。

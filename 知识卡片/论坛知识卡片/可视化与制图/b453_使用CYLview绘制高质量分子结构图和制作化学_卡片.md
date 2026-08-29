---
key: b453
title: 使用CYLview绘制高质量分子结构图和制作化学反应演示动画（视频演示）
url: http://sobereva.com/453
domain: 可视化与制图
source: blog
year: 2018
cards: 13
---

# 使用CYLview绘制高质量分子结构图和制作化学反应演示动画（视频演示） — 知识卡片

## 1. CYLview 软件特点与适用场景

CYLview 在绘图特性方面具有其它程序难以替代的优势，适合用于绘制高质量分子结构图。尽管其整体功能数量不算极其强大，但在特定领域的表现无可替代。该软件常用于有机体系计算相关的分子展示。

---

## 2. CYLview 视频教程版本信息

针对新用户容易困惑的非直观操作，演示视频重点讲解了使用 CYLview 绘制分子结构图及制作动画的方法。视频演示使用的软件版本为 CYLview 1.0b Build 561。视频时长为 11 分钟。

---

## 3. CYLview 官方下载地址

CYLview 的官方下载地址为 http://www.cylview.org。用户可从该网站获取软件安装包或程序文件。

---

## 4. OpenBabel 对 CYLview 文件兼容性的影响

若未安装化学文件格式转换程序 OpenBabel，CYLview 仅能载入 Gaussian 输出文件，使用便捷性会受到限制。建议安装 OpenBabel 以扩展文件格式的支持范围。OpenBabel 是一款免费程序。

---

## 5. Gaussian 16 输出文件载入问题的解决

CYLview 可能出现无法载入 Gaussian 16 (G16) 输出文件的情况。通过点击视频中提及的更新程序按钮进行更新，即可解决此兼容性问题。

---

## 6. CYLview 内置的 Houkmol 显示风格

CYLview 内置了一种名为 Houkmol 的显示风格组合。该风格常见于知名有机体系计算专家 Houk 的文章中。

---

## 7. renderall.bat 批处理渲染脚本

视频中使用的 renderall.bat 是一个 DOS 批处理文件，用于批量渲染图像。脚本内容如下：
```batch
for /f %%i in ('dir *.pov /b') do (
povray +W640 +H480 +A %%i
)
```
将上述内容复制到文资料件并重命名为 renderall.bat 即可使用。该脚本会调用当前目录下的 povray.exe，对所有 .pov 文件进行渲染并生成同名图像文件。

---

## 8. FFmpeg 视频处理工具简介

FFmpeg 是业界知名的视频编码、解码及转换程序，具有免费、小巧、功能极强且支持格式众多的特点。该工具支持各个操作系统，Windows 版本解压后无需安装即可直接使用。其基本使用格式为 `ffmpeg [选项] [输入选项] -i [输入文件] [输出选项] [输出文件]`。

---

## 9. 使用 FFmpeg 制作 MP4 动画

制作 MP4 动画使用的 FFmpeg 命令为：
```bash
ffmpeg -r 15 -i FRAME%04d.png -crf 22 video.mp4
```
其中 `%04d` 代表通配符 0001、0002、0003...。`-r` 参数后的数值为每秒帧数，视频长度等于图像总数除以该数值，数值越大播放越快。`-crf` 参数对应 x264 编码器，数值越小动画越清晰但文件越大，一般建议设置为 22。

---

## 10. 使用 FFmpeg 制作高质量 GIF 动画

制作 GIF 动画推荐使用两步命令以获得更佳的视觉效果：
```bash
ffmpeg -i FRAME0001.png -vf palettegen palette.png
ffmpeg -r 15 -i FRAME%04d.png -i palette.png -lavfi paletteuse video.gif
```
虽然 FFmpeg 支持直接生成 GIF，但直接生成的颜色效果较差。上述方法先根据实际图像生成调色板文件，再生成 GIF，颜色表现更优。

---

## 11. GIF 与 MP4 格式的特性对比

GIF 文件体积通常比 MP4 大得多，且只能包含 256 种颜色。GIF 格式的优势在于可以直接嵌入到网页和 PPT 演示文稿中。

---

## 12. CYL_mergeTXT.exe 工具功能

CYL_mergeTXT.exe 是一个用于合并 POV 文件的工具。它将带 `_txt` 后缀的文件（仅包含标签内容）与不带该后缀的文件（包含分子结构信息）进行合并。

---

## 13. GauIRC2xyz 工具简介

GauIRC2xyz 是一个用于将 Gaussian 的 IRC 任务输出转换为 .xyz 轨迹文件的工具。该工具可用于辅助处理化学反应路径的几何结构数据。

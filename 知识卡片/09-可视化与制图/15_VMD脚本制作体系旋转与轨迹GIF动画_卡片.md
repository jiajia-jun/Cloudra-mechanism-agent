---
id: 15
title: VMD制作体系旋转和轨迹播放的gif动画的简单方法
url: http://sobereva.com/15
domain: 可视化与制图
topic: VMD脚本制作体系旋转与轨迹GIF动画
cards: 13
---

# VMD脚本制作体系旋转与轨迹GIF动画 — 知识卡片

## 1. VMD制作GIF动画的优势

使用此方法制作体系旋转演示的gif图，适合嵌入网页或幻灯片，比压成视频文件更清楚也往往更小，无须调用videomach之类的软件。Gif文件可以保存进ppt保证演示时能够播放，不像视频文件嵌入ppt实际上只能作个视频文件的链接，而且很多视频还播放不了。

---

## 2. VMD制作GIF的环境要求

读者必须用Linux版VMD，且需要在Linux下安装ImageMagick，这样脚本中调用的convert命令才能用。对于CentOS系统，运行yum install ImageMagick即可安装。

---

## 3. 体系旋转GIF制作脚本

将以下内容保存为makegif.tcl文件：proc makegif {dir} { set frame 0; for {set i 0} {$i < 360} {incr i 15} { set filename snap.[format "%04d" $frame].rgb; render snapshot $filename; incr frame; rotate $dir by 15; }; exec convert -delay 10 -loop 4 snap.*.rgb movie.gif; foreach k [ls snap.*.rgb] { file delete $k} }

---

## 4. 体系旋转GIF制作操作步骤

启动VMD后在tk console运行诸如source /sob/makegif.tcl加载脚本，然后运行makegif y，这样体系就不断绕着y轴旋转并且截图。脚本会自动调用convert命令将图片合成为gif，储存在当前文件夹（即tkconsole输入pwd显示的文件夹)。

---

## 5. 体系旋转GIF的轴向选择

运行makegif命令时，如果绕x轴旋转就是makegif x，也可以是z，或者使用其他支持的轴向参数。

---

## 6. Windows用户生成GIF的方法

对于Windows用户，也可以使用脚本产生一批图像文件后，手动用ffmpeg、atani之类的软件合成gif。

---

## 7. 减小GIF体积的方法

如果想减小gif体积，有三种方法：缩小3D显示窗口；减少帧数，将makegif.tcl里面旋转角度和i变量的增量改大；减少颜色，把makegif.tcl的convert命令后面加上-colors 16即可（默认是256色）。

---

## 8. 减少GIF颜色的注意事项

将GIF颜色数减到16色体积可减小约一半，但16色有点太狠了，尤其是颜色比较丰富的时候，32色才算勉强。

---

## 9. 轨迹演示GIF制作脚本

制作轨迹演示的gif动画脚本内容如下：proc maketragif {start end {step 5} {color 32} {delay 5}} { for {set fn $start} {$fn < $end} {incr fn $step} { set filename snap.[format "%05d" $fn].rgb; render snapshot $filename; animate goto $fn; }; exec convert -delay $delay -loop 999 -colors $color snap.*.rgb movie.gif; foreach k [ls snap.*.rgb] { file delete $k} }

---

## 10. 轨迹演示GIF制作命令用法

加载脚本后可以用maketragif命令，用法为：maketragif 起始帧数 结束帧数 [步长] [颜色数] [动画中每帧间隔时间]。方括号内代表非必需的参数。

---

## 11. 轨迹演示GIF的默认参数

maketragif命令的默认步长为5帧，颜色数32，每帧间隔5。

---

## 12. 轨迹演示GIF制作示例

例如maketragif 350 650 5 64 10，代表350帧至650帧每5帧截一幅图，连结成gif，64种颜色，动画中每帧间隔为5。也可以只输入maketragif 350 650，步长、颜色数、动画中每帧间隔时间都用默认的。

---

## 13. 轨迹GIF输出位置

轨迹的动画生成在同目录下的movie.gif文件中。

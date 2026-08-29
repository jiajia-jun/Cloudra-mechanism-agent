---
id: 285
title: 将Gaussian的IRC任务输出转换为.xyz轨迹文件的工具：GauIRC2xyz
domain: Gaussian使用
topic: Gaussian_IRC输出转xyz轨迹工具GauIRC2x
cards: 4
---

## 1. GauIRC2xyz工具功能与版本信息
GauIRC2xyz是将Gaussian的IRC任务输出文件转换为.xyz轨迹文件的专用工具，用于解决获取IRC每个点结构及几何变量变化的问题。该工具首次发布于2015年3月，最后更新于2023年8月17日。程序可将Gaussian的IRC输出文件转换为同目录下同名的.xyz轨迹文件，启动后只需输入文件名即可完成转换。

---

## 2. GauIRC2xyz工具下载与使用说明
GauIRC2xyz最新版包含带.exe后缀的Windows版可执行文件和无后缀的Linux版可执行文件。程序中包含示例输入文件trimerization.out，转换后会生成对应的trimerization.xyz轨迹文件。

---

## 3. xyz轨迹文件格式与支持程序
.xyz轨迹文件格式简单，可参考《谈谈记录化学体系结构的xyz文件》一文。许多程序如VMD都支持.xyz轨迹文件，这使得分析IRC过程中各个变量的变化非常方便。

---

## 4. 利用VMD分析IRC轨迹中键长变化的操作步骤
若需查看IRC中某个键长度的变化，可将.xyz轨迹文件载入VMD，按键盘上的2键，点击相应的两个原子，然后进入Graphics - Labels菜单。在下拉框中选择Bonds，选中相应的项，选Graph标签页，点击Save即可将轨迹中这两个原子间距离保存到指定的文该资料件中。

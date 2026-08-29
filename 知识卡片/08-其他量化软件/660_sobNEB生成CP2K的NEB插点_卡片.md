---
id: 660
title: sobNEB：产生CP2K的NEB的插点的方便的工具
url: http://sobereva.com/660
domain: 其他量化软件
topic: sobNEB生成CP2K的NEB插点
cards: 6
---
## 1. sobNEB工具功能与优势

sobNEB是产生CP2K的NEB插点的工具，解决了CP2K自带NEB自动线性插点时存在偶发性bug（初始间距不均匀）且无法人为控制中间结构对应点号的问题。sobNEB允许用户直接控制提供的结构对应的初始点号，其余点在相邻提供的结构间线性插入；它能直接输出对应CP2K &BAND部分的信息以方便写输入文件；它还会将用户提供的点和插值点写入traj.xyz文件以便在VMD中预览轨迹。注意sobNEB不会对输入的结构自动消除平动转动。

---

## 2. sobNEB下载地址与版本

sobNEB工具的下载地址为 http://原作者.com/soft/sobNEB_1.0.zip；压缩包中后缀为.exe的是Windows版，无后缀的是Linux版。

---



---

## 3. sobNEB输入文件配置格式

用户需编辑sobNEB目录下的sobNEB.ini文件，指定xyz文件的路径及其对应的点号，两者之间以冒号分隔。只有始、末端的结构必须提供，中间结构可以提供零个或多个。配置示例如下：
conf1.xyz : 1
TS_guess.xyz : 11
conf2.xyz : 21

---

## 4. sobNEB插点生成规则与输出

sobNEB依据sobNEB.ini中定义的点号在相邻已知结构间进行线性插值。程序会在当前目录生成每个插点结构的xyz文件，并输出包含所有点的traj.xyz预览文件，以及可直接用于CP2K输入文件的BAND.txt。例如在点号1和11之间，以及11和21之间，程序会自动生成并输出点号2-10以及12-20的xyz文件。

---

## 5. CP2K &BAND输入段输出格式

sobNEB运行后会生成BAND.txt文件，其中包含按照点号顺序排列的CP2K &BAND输入段，格式如下，用户可将其直接粘贴到CP2K输入文件中：
&REPLICA
COORD_FILE_NAME [文件名]
&END REPLICA
该文件依次列举了初始结构、插值结构和最终结构的COORD_FILE_NAME。

---

## 6. 轨迹预览文件traj.xyz用途

sobNEB生成的traj.xyz文件包含了用户提供的点和所有插值点的结构，可以使用VMD软件打开该资料件来叠加显示所有帧。通过观察VMD中的显示效果，可以判断初始点的分布是否合理，确认其是否适合用于NEB计算。

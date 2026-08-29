---
key: b534
title: 谈谈VMD可视化程序的成键方式判断和设置问题
url: http://sobereva.com/534
domain: 可视化与制图
source: blog
year: 2020
cards: 17
---

# 谈谈VMD可视化程序的成键方式判断和设置问题 — 知识卡片

## 1. VMD连接关系的自动判断规则

VMD载入pdb、xyz、gro等格式结构文件时会自动判断原子间的连接关系，判断依据基于原子间距离与原子半径之和的对比。若两个原子间距离小于两个原子半径之和的0.6倍，VMD会将其视为成键。VMD内置的原子半径大多基于Bondi范德华半径，且元素的默认半径无法在图形界面或配置文件中直接修改。

---

## 2. VMD修改单个键连接关系的操作方法

若两个原子未被判定为成键但需要显示键，可选择Mouse - Add/Remove Bonds，然后点击这两个原子的正中心进行连接。若点击两个已成键的原子，它们之间的键会被移除。

---

## 3. VMD标签的隐藏与删除操作

点击原子时会自动显示标签，按键盘上的1键再点击有标签的原子可将该标签隐藏。进入Graphics - Labels界面，按住鼠标左键选中多个标签后，可点击Hide按钮隐藏或点击Delete按钮删除。

---

## 4. Windows版VMD批量删除标签的配置方法

在Windows版VMD目录下的vmd.rc文件中添加特定proc da命令定义，启动VMD后在文本窗口输入da命令，即可删除所有原子标签。

---

## 5. VMD的DynamicBonds显示模式

当需要批量修正连接关系时，可在Graphics - Representation界面将Drawing Method设为DynamicBonds，该模式基于当前结构实时判断成键并显示。判断阈值可通过Distance Cutoff控件修改以满足显示要求。

---

## 6. 结合DynamicBonds与VDW显示原子球

DynamicBonds模式不显示原子球且键为空心，为同时显示原子球，可增加一个Representation，将Drawing Method设为VDW并调小Sphere Scale。

---

## 7. 通过多Representation叠加解决键连显示冲突

使用DynamicBonds调节距离阈值导致部分键连显示不符合预期时，可设置多个Representation。每个Representation利用不同的选择语句选定绘制区域，并配置恰当的Drawing Method和参数，使叠加效果满足要求。

---

## 8. 载入含连接信息的文件格式

AMBER、NAMD的拓扑文件包含连接关系信息，载入后VMD会据此显示后续结构或轨迹。安装tpr插件后，VMD载入GROMACS的tpr文件时也能读取正确的连接关系。

---

## 9. mol2格式文件的连接关系识别

mol2格式文件包含@<TRIPOS>BOND字段记录键的形式（如双键），VMD载入mol2文件时会直接使用文件内记录的连接关系而非自动判断。

---

## 10. pdb文件CONECT字段的处理

pdb格式的CONECT字段记录了连接关系，但VMD默认不会采用该信息。若需利用此字段设定原子连接关系，需参照特定方法进行处理。

---

## 11. 利用GaussView辅助生成正确连接关系的mol2文件

在GaussView中编辑好连接关系并保存为mol2文件，VMD读取该文件后显示的连接关系将与GaussView中一致。此方法适用于利用GaussView 6自定义成键判断阈值并批量修正特定元素间成键方式的场景。

---

## 12. VMD对多重键形式的显示限制

VMD的Line、CPK、Licorice显示风格无法区分双键、三键等成键形式，均显示为单键样式。Bonds显示风格虽能通过套筒数量区分键级，但显示效果较差，缺乏实际意义。

---

## 13. 保存修改后的连接关系

在VMD中通过Add/Remove bonds修改连接关系后，可通过File - Save coordinate功能将结构保存为mol2文件，以便后续直接读取正确的连接关系。

---

## 14. 动力学轨迹播放中的连接关系问题

播放动力学轨迹时出现成键混乱或跨越盒子的情况，是因为连接关系仅在初始载入时判断（基于拓扑文件、结构文件或第一帧）。后续播放过程中内存中的连接关系列表不会自动更新，可能因分子解离、异构化或周期边界条件而不适用于某些帧。

---

## 15. 轨迹播放中实时更新连接关系的显示方法

针对轨迹播放中连接关系失效的问题，可使用DynamicBonds显示方式按当前帧坐标实时判断成键。若需使用其它显示方式并更新内存中的连接关系列表，需在文本窗口输入命令 `mol bondsrecalc all; topo retypebonds`。

---

## 16. VMD查看当前连接关系的命令

在VMD文本窗口输入 `[atomselect top all] getbonds`，可以列表形式输出当前内存中所有原子的连接关系信息，列表中的成员顺序与原子索引对应。

---

## 17. VMD设置自定义连接关系的命令

通过运行 `[atomselect top all] setbonds {{列表内容}}` 命令，可以将当前体系的连接关系修改为用户指定的列表所定义的形式。

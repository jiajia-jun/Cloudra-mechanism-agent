---
id: 134
title: 使用Multiwfn绘制NBO及相关轨道
domain: 波函数与电子结构分析
topic: Multiwfn绘制NBO及相关轨道等值面与等值线
cards: 13
---

## 1. NBO相关轨道及绘图工具推荐
NBO程序输出的轨道包括NBO（自然键轨道）、NHO（自然杂化轨道）、NAO（自然原子轨道）、NLMO（自然定域化分子轨道）及前头带P的类型。可视化这些轨道可使用GaussView（仅限NBO/NLMO）、ChemCraft（收费且基组含高角动量时可能有错）、NBOView（收费且界面落伍）或Molden。Multiwfn支持读入NBO plot文件绘制上述所有轨道，显示速度快，可同时显示两条轨道分析重叠，且免费灵活，是最佳选择。

---

## 2. fch文件绘制NBO轨道的限制
不建议使用fch文件查看NBO轨道，因为轨道序号需与NBO输出信息对应查找，且fch文件此时无法用于看分子轨道或进行许多波函数分析。若必须使用，Gaussian用户需在route section写入pop=saveNBO或pop=saveNLMO将轨道写入chk文件，再用formchk转化为fch文件。fch中的轨道已按能量排序，编号与NBO输出不一致，需参考“Reordering of NBOs for storage”信息。

---

## 3. fch文件绘制平面图或格点数据的修改
若使用fch文件让Multiwfn绘制平面图或生成轨道波函数格点数据，HF或DFT计算需在fch文件第一行开头写上saveNBOene；后HF计算且写了density关键词需写上saveNBOocc。否则部分编号靠后的轨道会被自动删掉而无法选择。若仅通过主功能0直接观看轨道，则无需修改fch文件。

---

## 4. 生成NBO plot文件的方法
查看NBO和NLMO以外的轨道必须使用NBO plot文件。Gaussian输入文件需加pop=nboread，末尾空一行写$NBO plot file=路径 $END。运行后将生成.31（基函数）到.41（密度矩阵）等文件，其中.32~.40分别储存PNAO/NAO/PNHO/NHO/PNBO/NBO/PNLMO/NLMO/MO的展开系数。独立版NBO程序GENNBO需在.47文件开头的$NBO和$END间写plot file=路径。

---

## 5. NBO plot文件的轨道编号优势
NBO plot文件内的轨道编号和实际的NBO（或NLMO、NAO等轨道）的编号是完全一致的。选择轨道时不必像使用fch文件那样麻烦地去查编号转换表。

---

## 6. Multiwfn绘制轨道等值面图基本操作
启动Multiwfn，输入.fch或.31文件路径。若输入.31，需再输入目标轨道对应的文件（如.37为NBO）。输入0进入主界面查看分子结构和轨道等值面。右下角轨道列表点击可显示对应等值面。若用.fch文件，轨道序号已被重排，列表中的第X号未必对应NBO输出中的第X号。

---

## 7. Multiwfn同时显示两条轨道等值面
在轨道列表中先选一条轨道作为Isosurface #1，勾选“Show+Sel. isosur#2”复选框后选第二条轨道作为Isosurface #2。#1正负值用绿蓝表示，#2正负值用黄绿紫表示。可通过Isosur#1 style和Isosur#2 style设定风格（不透明面、网、点、不透明面+网）及RGB颜色。两条轨道显示便于分析相位交叠和超共轭。

---

## 8. 调整轨道等值面格点质量
Multiwfn生成等值面前先计算格点数据，默认格点数较少，大体系等值面可能不够光滑。选择窗口上方Isosur. quality，点击按钮输入期望的格点数可提高显示精度。重新设定后当前等值面消除，之后生成的等值面套用新设定。

---

## 9. 使用Multiwfn生成轨道波函数格点文件
启动Multiwfn输入文件名，依次输入：5（生成格点数据）-> 4（轨道波函数）-> 输入轨道编号 -> 2（中等质量）-> 2（保存为MOvalue.cub）。将生成的文件重命名（如NBO12.cub）。重复此过程生成其他轨道的.cub文件。该资料件可用于VMD等软件绘图。

---

## 10. 使用VMD绘制轨道等值面图
将生成的.cub文件拖入VMD，在Graphics-representations中切换Selected Molecule。建立两个显示方式：Drawing Method选Isosurface，Draw选Wireframe，Isovalue设为0.05和-0.05，Coloring Method选ColorID并对应颜色（如正值为Green，负值为Blue）。可设置Material为GlassBubble并开启GLSL或Tachyon渲染以获得透明效果。

---

## 11. Multiwfn生成轨道波函数等值线图
启动Multiwfn载入文件，依次输入：4（绘制平面图）-> 4（轨道波函数）-> 输入轨道编号（可两个，逗号分隔）-> 回车（默认格点）-> 5（通过三个点定义平面）-> 输入三个坐标点。实线虚线代表正负值。可通过3（设定等值线）-> 5（删除一批等值线）去除数值较小的等值线，并选2显示数值。

---

## 12. 定义绘图平面的坐标点设置
在Multiwfn中通过三个坐标点定义绘图平面。前两个点设为关键原子坐标，第三个点在其中一点基础上沿垂直方向（如Z轴）移动一定距离（如1 bohr）。坐标需用bohr单位，可从主功能0显示的原子坐标中拷贝。移动距离需尝试以使感兴趣区域居中。

---

## 13. 结合Photoshop叠加多条轨道等值线图
分别生成单个或双个轨道的等值线图（需使用完全一致的绘图平面坐标）。在Photoshop中将图片作为不同图层打开，复制叠加。利用Select-Color Range选中白色背景按Del删除以透明背景。利用Color Range和Fill修改线条颜色，反选删除多余坐标轴。此法可绘制任意数量轨道的叠加图。

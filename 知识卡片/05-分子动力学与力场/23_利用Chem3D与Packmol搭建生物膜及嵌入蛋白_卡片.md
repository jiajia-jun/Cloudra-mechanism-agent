---
id: 23
title: Sob谈生物膜体系的搭建
url: http://sobereva.com/23
domain: 分子动力学与力场
topic: 利用Chem3D与Packmol搭建生物膜及嵌入蛋白
cards: 16
---
## 1. 推荐使用genmixmem和membed工具

所述的磷脂膜搭建和蛋白嵌入方法已不再推荐，建议使用genmixmem工具构建磷脂膜，以及GROMACS直接支持的membed方法将蛋白嵌入膜。相关内容见http://原作者.com/245及分子动力学与GROMACS培训班。

## 2. 磷脂缩写命名规则

磷脂通常用四个字母表示，后两个字母由磷酸酯的酯部分决定，例如PS代表磷脂酰丝氨酸（phosphatidyl serine），PE代表磷脂酰乙醇胺（phosphatidyl ethanolamine）。前两个字母与脂肪酸链有关，完整的缩写与写法对照表可参考提供的PDF文件。

---

## 3. 利用ChemBio3D构建DPPC分子

启动ChemBio3D，点击文本输入工具（A按钮），在空白处输入DPPC的完整名称1,2-Dipalmitoyl-sn-Glycero-3-phosphocholine并回车即可得到初始结构。由于CCDC中磷脂分子较少，需自行通过名称输入构建。

---

## 4. 调整DPPC脂肪链间距

初始构建的DPPC分子两条脂肪链相距较远，需使用ChemBio3D的Single Bond工具，将两条脂肪链的碳原子每隔两个碳连接一次。随后点击MM2优化按钮进行力场优化，使两条链并拢。

---

## 5. 断开脂肪链间的临时连接键

优化后选中两条链间连接键两端的原子（呈黄色），按Ctrl+B断开键。若断开失败且自动加氢，需在File-Model setting-Mode building中将rectify选项去掉，之后再次进行MM2优化。

---

## 6. 调整DPPC磷酸胆碱部分二面角

为摆正磷酸胆碱部分，需选中关键的四个原子定义二面角，右键选择Display Dihedral Measurement，将左侧显示的二面角数值改为50。最后再次进行MM2优化，并将结果保存为mol2格式（避免保存为pdb以防出错）。

---

## 7. 使用PRODRG处理分子结构

将mol2文件内容复制到PRODRG 2.5 beta网页工具中，注意将EM选项设为NO以防止脂肪酸链重新分开。运行后下载压缩包，提取DRGFIN.PDB（全氢）、DRGGMX.PDB（极化氢）和DRGGMX.ITP（拓扑文件）。

---

## 8. Packmol程序编译与准备

从指定网址下载packmol，解压后在目录下输入make进行编译（若需并行版输入make parallel）。将准备好的DPPC.pdb、DPPS.pdb及示例中的water.pdb放入可执行文件所在目录。

---

## 9. Packmol输入文件基本设置

Packmol输入文件需设置tolerance 2.0限制原子间最近距离，定义filetype为pdb，并指定output文件名。结构体设置包括指定结构文件、数量及空间范围（inside box x/y/z-min x/y/z-max）。

---

## 10. Packmol控制分子取向的约束

在Packmol中可通过atoms和below/over plane指令控制分子取向，例如限制某原子在特定平面之下或之上。两个平面间的距离应小于分子两端对应原子的实际距离（如DPPC为25.84埃），以保留一定的任意旋转余地。

---

## 11. 利用Packmol搭建混合磷脂双层

通过定义多个structure块，可以分别设置上下两层的水分子、DPPC和DPPS分子的数量与空间范围。DPPS和DPPC可定义相同的范围，packmol会自动处理冲突使其均匀混合，水分子则分布在膜的两侧。

---

## 12. 提高Packmol构建效率的策略

体系分子越多收敛越慢，建议先单独构建磷脂部分验证结果，再使用gmx genbox添加水分子，最后用grostat的反选功能去除疏水区的水。若对混合均匀度不满意，可多次运行packmol或使用FIXED关键字。

---

## 13. VMD可视化剔除重叠磷脂分子

在VMD中同时打开膜蛋白和磷脂层，调整膜蛋白位置后合并PDB并重置残基号。使用选择语句“all not same resid as (within 1.5 of protein)”不显示与蛋白距离小于1.5埃的残基，通过平移模式嵌入蛋白。

---

## 14. 保存剔除重叠磷脂后的体系

完成蛋白嵌入后，使用VMD的save coordinate功能，选择范围设为“all not same resid as (exwithin 1.5 of protein)”进行保存。该选择范围保留了蛋白质自身以及距离蛋白质1.5埃以外的DPPC，剔除了距离较近的DPPC。

---

## 15. 使用Packmol直接构建蛋白嵌入体系

使用packmol可在构建时直接混合膜蛋白与磷脂，效果通常比后期嵌入更好。输入文件中需设置tolerance 2.0，并使用center和fixed参数将膜蛋白几何中心固定在指定位置（如50. 50. 60.）。

---

## 16. Packmol构建蛋白膜体系的参数设定

在利用packmol构建含蛋白的膜体系时，应先用VMD将膜蛋白跨膜轴调整为垂直于Z轴，然后在fixed参数中将旋转角度设为0 0 0。磷脂分子同样使用plane约束限定在膜蛋白周围形成双层结构。

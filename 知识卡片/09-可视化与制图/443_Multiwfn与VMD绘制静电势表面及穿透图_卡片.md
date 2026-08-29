---
id: 443
title: 使用Multiwfn+VMD快速地绘制静电势着色的分子范德华表面图和分子间穿透图（含视频演示）
url: http://sobereva.com/443
domain: 可视化与制图
topic: Multiwfn与VMD绘制静电势表面及穿透图
cards: 25
---
## 1. 必读引用规范

使用该方法绘制表面静电势图发表文章时，必须引用Multiwfn程序原文及Multiwfn静电势算法在PCCP发表的原文；若图中显示分子表面静电势极值点位置，还需引用J. Mol. Graph. Model., 38, 314 (2012) DOI: 10.1016/j.jmgm.2012.07.004。

---

## 2. 范德华表面的Bader定义

此处所说的范德华表面是指Bader的定义，即把电子密度0.001 a.u.等值面作为范德华表面。

---

## 3. 必备文件与目录放置规则

绘图前需将ESPiso.bat、ESPpt.bat、ESPext.bat及对应的.txt文件放到Multiwfn所在目录；将ESPiso.vmd、ESPpt.vmd、ESPext.vmd等绘图脚本拷到VMD目录下；将被计算分子的fch文件改名为1.fch（及2.fch、3.fch等）放到Multiwfn当前目录下。

---

## 4. VMD路径配置与文件自动拷贝

用户必须编辑.bat文件，将默认的VMD目录路径改为自己机子的实际路径，若路径含空格必须用双引号扩住（如"D:\study\VMD 193"）；双击批处理文件时会自动计算并将结果文件拷到VMD目录下。

---

## 5. VMD快捷命令配置

为了简化绘图命令，应在VMD目录下的vmd.rc文件末尾添加`proc iso {} {source ESPiso.vmd}`、`proc pt {} {source ESPpt.vmd}`等语句，随后在VMD文本窗口输入如pt、iso等命令即可执行对应绘图脚本。

---

## 6. 批处理文件功能区分

ESPiso.bat用于产生电子密度和静电势的cube文件；ESPpt.bat用于产生分子结构和表面顶点的pdb文件；ESPext.bat在ESPpt.bat基础上额外产生记录分子表面静电势极值点的surfanalysis.pdb文件。

---

## 7. 绘制单个分子的表面顶点静电势图

将1.fch放入目录，双击ESPpt.bat，启动VMD并输入pt命令；ESPpt.vmd脚本默认色彩刻度是-50kcal/mol ~ 50 kcal/mol，颜色按“蓝-白-红”过渡。

---

## 8. 绘制单个分子的等值面静电势图

将1.fch放入目录，双击ESPiso.bat，重启VMD并输入iso命令；此方法通过将静电势数据映射到电子密度等值面（0.001 a.u.）进行着色，可用Tachyon渲染器增强光泽感。

---

## 9. 显示分子表面静电势极值点

双击ESPext.bat计算，在显示静电势图（通过pt或iso命令）后，在VMD文本窗口输入ext命令；黄球对应静电势极大点，青球对应极小点，极值点信息记录在surfanalysis.pdb中。

---

## 10. 查询表面极值点静电势数值

方法一：在VMD中按0进入查询模式点击极值点球体中心，根据显示的index值（从0开始），在surfanalysis.pdb文件中找到对应行（行号=index+2），其倒数第2列即为静电势数值（单位见文件头注释）；方法二：在VMD窗口输入`[atomselect top "index 3"] get beta`。

---

## 11. 绘制分子间范德华表面穿透图的文件准备

只需对复合物进行优化，单体坐标必须直接从优化后的复合物坐标中提取；对于Gaussian计算单体时必须加nosymm关键词以防坐标被重定向。

---

## 12. 绘制分子间穿透图的文件命名与操作

将复合物中各单体对应的fch文件分别命名为1.fch、2.fch等放入目录；运行批处理文件后，在VMD中使用pt2命令绘制表面顶点穿透图，或使用iso2命令绘制等值面穿透图。

---

## 13. 穿透图中的距离测量

在VMD中按键盘上的2键，点击两个表面顶点可测量距离；若白色文字难以观察，可在ESPpt2.vmd中删除`color Display Background white`或输入`color Display Background black`切换背景。

---

## 14. 调节材质透明度解决视觉混乱

对于复杂体系，若EdgyGlass材质下透明度过高导致画面混乱，应进入Graphics - Materials调节EdgyGlass的Opacity滑条，降低透明度以清晰显示表面特征。

---

## 15. 修改VMD色彩变化方式与Turbo模式

若不喜欢默认的蓝-白-红模式，可在Graphics - Colors - Color Scale中修改Method（如RWB）；VMD 1.9.4+支持turbo模式，可通过`color scale method turbo`等命令设置彩虹色渐变及调整刻度范围。

---

## 16. 在VMD中显示色彩刻度轴

方法一：在Graphics - Colors中截图Color Scale标签页并PS标注；方法二：使用Extensions - Visualization - Color Scale Bar，设置Use Molecule为density1.cub，启用Draw Color Scale Bar并移动到合适位置。

---

## 17. 静电势图的单位设置

默认单位可能是kcal/mol或eV（离子体系）；若需让iso/iso2命令产生的图以eV为单位，应使用ESPiso_eV.bat和ESPiso_eV.txt代替原文件，并在ESPiso.vmd/ESPiso2.vmd中取消注释set colorlow -0.8和set colorhigh 0.8。

---

## 18. 离子体系的色彩刻度范围设置

对于离子体系，必须修改默认色彩刻度范围；应在Multiwfn中载入文件进入主功能12做定量分析，将输出中带星号的表面静电势最小值和最大值设为色彩刻度的下限和上限。

---

## 19. 修改格点密度与质量设置

ESPpt.txt里的0.15是格点间距，改大则顶点变稀疏且耗时降低；ESPiso.txt默认密度用high quality grid，静电势用low quality grid，对于400原子以上的大体系应将ESPiso.txt内容改为高质量格点设置（含0.4等参数）。

---

## 20. 扩展脚本以支持更多聚体绘制

若需绘制四聚体以上的体系（如八聚体），需修改ESPiso.bat和ESPpt.bat中的计算序号上限至8，并将ESPiso2.vmd和ESPpt2.vmd里的nsystem参数从4改为8。

---

## 21. 巨大体系的快速绘制建议

对于1000原子以上的特大体系，基于波函数计算难以进行，应使用基于原子坐标和原子电荷快速计算的方法（如参考相关资料），虽准确性略低但耗时极低。

---

## 22. 极值点数目不一致的原因解释

ESPext.bat脚本使用的格点间距为0.15 Bohr，而Multiwfn主功能12默认为0.25 Bohr；若两者给出的极值点数目不符，以间距更小的ESPext.bat结果为准，或在主功能12中将间距改为0.15 Bohr以保持一致。

---

## 23. 高电荷体系的特殊处理

若体系带电荷特别多导致静电势数值超出pdb格式B因子字段记录范围，应使用examples\drawESP目录下带_pqr后缀的脚该资料件（如ESPpt_pqr.bat），利用.pqr文件的charge列记录数值（单位恒为a.u.）。

## 24. 常见报错：VMD无法加载文件

若VMD提示找不到mol1.pdb或density1.cub，通常是因为ESPiso.bat等文件中的VMD路径设置错误（未使用双引号括起含空格路径）或.vmd脚本未放置在VMD默认目录（pwd命令显示的目录）下。

---

## 25. 常见问题：分子表面显示为白色

若分子表面图全是白色而非彩色，可能是体系各处静电势接近0导致需缩小色彩刻度范围，或者静电势cube文件未正常载入（如32位VMD无法加载大文件，应换用64位VMD）。

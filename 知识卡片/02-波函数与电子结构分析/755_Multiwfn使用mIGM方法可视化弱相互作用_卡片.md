---
id: 755
title: 使用mIGM方法基于几何结构快速图形化展现弱相互作用
domain: 波函数与电子结构分析
topic: Multiwfn使用mIGM方法可视化弱相互作用
cards: 9
---

## 1. mIGM方法的原理与优势
mIGM（modified independent gradient model）是IGMH的变体，将基于波函数的实际电子密度替换为准分子密度，仅需元素和原子坐标信息即可计算。该方法不依赖波函数文件，计算速度远快于IGMH且图像效果优于IGM，使得IGM方法可被淘汰。mIGM适合快速预览、大体系分析或无法获得波函数文件的情况，但对于片段带显著净电荷的情况精度可能略低。

---

## 2. mIGM与IGMH及NCI方法的图像对比
IGMH图像等值面光滑且形状优雅，能很好展现范德华和氢键区域；NCI方法无法区分分子内和分子间相互作用，等值面零散且有锯齿；IGM图像等值面过于肥大且易出现不合理着色。mIGM的图像效果与IGMH十分接近，可通过调整δg_inter等值面数值（如0.006、0.01、0.03 a.u.）来着重展现不同强度的相互作用区域。
Struct. Bond., 190, 297 (2026)

---

## 3. 使用Multiwfn进行mIGM分析的实例操作（苯基丙氨酸三聚体）
启动Multiwfn并载入结构文件后，依次选择主功能20（弱相互作用可视化分析）、-10（mIGM分析），定义片段数及原子序号，选择自定义格点间距（推荐0.2 Bohr，若追求更好效果可用0.15 Bohr）。计算完成后在后处理菜单选3导出cube文件，保留sl2r.cub（对应sign(λ2)ρ）和dg_inter.cub（对应δg_inter）用于可视化。
- 参考文件: examples\phenylalanineresiduestrimer.xyz

---

## 4. 使用VMD绘制mIGM相互作用等值面
将Multiwfn生成的sl2r.cub和dg_inter.cub以及Multiwfn自带的IGM_inter.vmd脚本放入VMD目录，启动VMD并在文本窗口输入source IGM_inter.vmd加载脚本。默认δg_inter等值面数值为0.01，若需修改可在VMD Main窗口的Graphics - Representation中输入新数值；可通过修改Drawing Method为Licorice及Material为AOShiny来优化图像效果。
- 脚该资料件: IGM_inter.vmd

---

## 5. 计算原子和原子对相互作用贡献指数（δG_atom和δG_pair）
在Multiwfn的mIGM分析后处理菜单中选择6计算δG_atom和δG_pair指数，输入目标片段序号并选择Ultrafine格点，结果将导出至atmdg.txt和atmdg.pdb。atmdg.pdb中Beta因子对应δG_atom指数，可在VMD中通过Coloring Method设为Beta及BWR色阶直观显示原子对相互作用的重要性。

---

## 6. mIGM分析周期性体系的操作步骤（以碲晶体为例）
对于周期性体系如碲晶体，需先在Multiwfn中利用主功能300-7-19将原胞扩成足够大的超胞（如4x4x3），使用Tools - Select fragment获取目标片段原子序号。随后进入主功能20选-10进行mIGM分析，定义片段后选择中等质量格点（格点间距约0.25 Bohr）以平衡速度与质量，计算完成后导出cube文件进行可视化。
- 结构文件: Te.cif

---

## 7. mIGM分析周期性体系的可视化与参数设置
在VMD中载入周期性体系的cube文件后，可利用IGM_inter.vmd脚本绘图，通过设置不同的Representation（如CPK和DynamicBonds）及选择语句区分不同片段。可在文本窗口输入pbc box显示晶胞边框，调整等值面数值（如从0.01降至0.003）可展现更全面的相互作用，偏蓝色区域暗示可能有共价作用成分。
- 辅助功能: Mayer键级分析可论证共价作用

---

## 8. mIGM方法的局限性及适用范围
mIGM基于准分子密度近似，适用于电子密度较低的分子间弱相互作用区域，但不适用于描述化学键，因为化学键形成会导致实际密度显著偏离准分子密度。若体系巨大或格点间距很小导致计算耗时，可使用格点屏蔽方法来大幅降低计算时间。

---

## 9. amIGM方法对动态过程的扩展应用
基于mIGM的高效性，可将其扩展用于可视化研究动态环境中的平均弱相互作用，称为amIGM方法。amIGM方法比aNCI方法更好用，适用于分析分子动力学过程中产生的几百、几千帧结构，详细介绍及计算示例见专门文章。

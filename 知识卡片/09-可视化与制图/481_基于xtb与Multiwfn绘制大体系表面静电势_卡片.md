---
id: 481
title: 巨大体系的范德华表面静电势图的快速绘制方法
url: http://sobereva.com/481
domain: 可视化与制图
topic: 基于xtb与Multiwfn绘制大体系表面静电势
cards: 13
---

# 基于xtb与Multiwfn绘制大体系表面静电势 — 知识卡片

## 1. 当前最佳实践：绘制静电势着色的范德华表面图

如今绘制分子范德华表面静电势图的最佳做法是使用Multiwfn官网最新版本，结合xtb产生的molden文件作为输入，利用《使用Multiwfn+VMD快速地绘制静电势着色的分子范德华表面图和分子间穿透图》（http://sobereva.com/443）介绍的ESPiso脚本。这种方法得益于Multiwfn在PCCP期刊发表的高效静电势算法（http://sobereva.com/614）以及巨幅降低耗时的关键技巧（http://sobereva.com/602），比旧方法更省事省时且无需调用收费的Gaussian cubegen。

---

## 2. 超大体系静电势图的绘制方法

如果要绘制1000原子以上的特大体系的表面静电势图，应当使用《基于原子电荷极快速绘制超大体系的分子表面静电势图》（http://sobereva.com/639）里的做法。该方法用Multiwfn基于原子坐标和原子电荷来计算，耗时超级低。

---

## 3. 巨大体系波函数计算推荐方案

对于300多个原子的大体系，在普通四核机子上使用Gaussian算DFT或ORCA算RI都很困难，且一般程序不支持基于半经验方法（如PM6）的波函数计算静电势。最佳方案是使用Grimme的xtb程序，其安装和基本用法详见《将Gaussian与Grimme的xtb程序联用搜索过渡态、产生IRC、做振动分析》（http://sobereva.com/421）。

---

## 4. 使用xtb生成Molden输入文件

将大分子的结构文件载入Multiwfn，进入主功能100的子功能2导出为xyz文件（如336.xyz）。在包含该文件的目录下运行命令`xtb 336.xyz --molden`（若结构未优化可加`--opt`），计算完成后会在当前目录生成可被Multiwfn读取的Molden输入文件molden.input。

---

## 5. Multiwfn计算电子密度格点数据

启动Multiwfn载入molden.input，依次输入命令：5（计算格点数据） -> 1（计算电子密度） -> 3（高质量格点）。计算完成后选2导出格点数据，当前目录下会出现density.cub，将其改名为density1.cub备用。

---

## 6. 导出fch文件以支持cubegen

在Multiwfn中依次输入：0（返回主菜单） -> 100（其它功能part 1） -> 2（导出文件） -> 7（导出fch文件） -> 输入文件名如336.fch。当前目录下会生成336.fch文件，用于后续通过Gaussian的cubegen计算静电势。

---

## 7. 设置cubegen路径

修改Multiwfn目录下的settings.ini，将其中的cubegenpath路径设为机子里实际的Gaussian目录下的cubegen可执行文件的路径，例如`D:\study\G16W\cubegen.exe`。更多说明参见http://sobereva.com/435。

---

## 8. 增加cubegen可用内存上限

处理大体系时需增加cubegen的默认内存上限。Windows用户在环境变量中新建用户变量，变量名为GAUSS_MEMDEF，变量值设为1400MB（64位Gaussian可设更大如4GB，32位通常最多1400MB）。Linux用户应运行`export GAUSS_MEMDEF=4GB`命令（建议加入~/.bashrc）。

---

## 9. Multiwfn调用cubegen计算静电势

启动Multiwfn载入336.fch，依次输入：5（计算格点数据） -> 12（计算静电势） -> 3（高质量格点）。Multiwfn将调用cubegen进行计算，这是最耗时的一步（4核机约50分钟）。计算完成后选2导出格点数据，将生成的totesp.cub改名为ESP1.cub。

---

## 10. 使用VMD绘制静电势图

将density1.cub、ESP1.cub以及Multiwfn目录下examples\drawESP目录下的ESPiso.vmd拷贝到VMD目录。启动VMD，在文本窗口输入`source ESPiso.vmd`并回车，即可看到静电势着色的分子表面图。

---

## 11. 优化VMD图像显示效果

在VMD中进入Graphics - Materials，选择EdgyGlass材质并调节参数。进入Graphics - Representation，将分子结构的显示方式从CPK切换为Licorice，键粗细从0.3改为0.2。对于Isosurface显示方式，在Trajectory标签页将Color Scale Data Range从默认-0.03~0.03调整为-0.04~0.04，使颜色变化更柔和。

---

## 12. xtb波函数定性分析的适用性

xtb程序做的GFN-xTB计算只相当于半经验层面的DFT方法，使用极小基，精度算不上很理想。但对于几百个原子的静电势图绘制，只要定性正确即可满足需要，此时xtb+Multiwfn是黄金组合。

---

## 13. xtb波函数定量分析的局限性

若需基于xtb波函数进行定量分子表面分析（如预测反应位点）或计算拟合静电势电荷（如CHELPG），其精度不足以达到准确标准。与B3LYP/def2-TZVP结果相比，分子表面静电势极值点数值差异可达20 kcal/mol，原子电荷差异最大可达0.23。

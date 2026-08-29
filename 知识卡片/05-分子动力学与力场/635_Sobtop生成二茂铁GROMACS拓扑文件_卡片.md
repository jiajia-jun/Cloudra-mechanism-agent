---
id: 635
title: 使用Sobtop超级方便地创建二茂铁的GROMACS的拓扑文件
url: http://sobereva.com/635
domain: 分子动力学与力场
topic: Sobtop生成二茂铁GROMACS拓扑文件
cards: 15
---
## 1. Sobtop程序简介与适用场景

Sobtop是主要用于产生各种类型体系GROMACS拓扑文件的程序，可以解决主流有机分子力场（如GAFF、OPLS-AA、GROMOS）不支持的过渡金属元素及相应键/键角/二面角参数缺失的问题。该程序对于多核金属配合物、带有可旋转键的柔性部分的配合物等复杂情况也能容易地产生拓扑文件。Sobtop程序可在主页http://原作者.com/soft/Sobtop免费下载，示例使用的是2022-Feb-16发布的预览版1.0(dev)。

---



---

## 2. 二茂铁的结构特点与初始构型

二茂铁的两个茂环间仅在低温晶体中是交错式的，而在真空中极小点结构是重叠式（D5h点群），因此计算初始结构应选用重叠式。参考资料包括Materials, 8, 7723 (2015)和https://en.wikipedia.org/wiki/Ferrocene#Determining_the_structure。进行Gaussian计算前，建议用GaussView对结构做对称化，以获得更精准且速度更快的优化结果。

---

## 3. 二茂铁量子化学计算级别设置

二茂铁的优化和振动分析推荐使用TPSSh/def2-TZVP级别，这对过渡金属配合物体系通常是理想的选择。关于泛函的详细选择可参考《简谈量子化学计算中DFT泛函的选择》（http://原作者.com/272）。如果希望计算成本明显更低，Fe中心可以使用SDD基组，配体可以使用6-311G*基组。

---



---

## 4. Gaussian输入文件内容示例

计算二茂铁优化和振动的Gaussian输入文件应包含%chk、#p tpssh/def2tzvp opt freq等关键字，以及电荷自旋多重度0 1。初始结构坐标需包含Fe原子和两个茂环上的C、H原子，如Fe 0.00000000 0.00000000 -0.00000000等。计算完成后，需使用formchk将Ferrocene.chk转换为Ferrocene.fchk，相关用法见http://原作者.com/379。

---



---

## 5. 二茂铁mol2文件的键连关系处理

Sobtop生成拓扑文件时依赖mol2文件中记录的键连关系来确定力场项。使用GaussView打开Ferrocene.fchk文件，必须检查Fe和各个C之间是否显示了键，如果没有则需手动连上（设置几重键均可，Sobtop只判断有无键）。最后将结构保存为Ferrocene.mol2文件。

---

## 6. 二茂铁RESP电荷计算的等价性约束

二茂铁具有D5h对称性，直接计算RESP电荷会因拟合点分布不完全满足对称性而导致等价原子电荷有微小偏差，因此必须在Multiwfn中设置等价性约束。启动Multiwfn后，通过输入Ferrocene.fchk -> 7 -> 18 -> 5 -> 11 -> a -> y路径，利用点群自动判断等价性并生成eqvcons_PG.txt文件。

---

## 7. Multiwfn计算RESP电荷的操作步骤

生成等价性文件后，在Multiwfn RESP界面中选择1读取eqvcons_PG.txt文件，然后选择2进行一步式RESP电荷拟合。当程序提示Fe缺半径时，按回车键使用推荐半径。计算完成后屏幕会显示满足等价性的原子电荷，输入y将结果导出为当前目录下的Ferrocene.chg文件。RESP电荷计算原理详见http://原作者.com/441。

---



---

## 8. Sobtop生成GROMACS坐标文件操作

启动Sobtop并载入Ferrocene.mol2文件后，选择7指定原子电荷，再选择10从Multiwfn的chg文件中读取Ferrocene.chg。返回主菜单后选择2产生GROMACS的.gro文件，程序将在当前目录下生成Ferrocene.gro。

---

## 9. Sobtop生成拓扑文件的力场与参数设置

在Sobtop中选择1产生GROMACS拓扑文件，力场类型选择2（优先用GAFF原子类型，缺失的自动使用UFF力场）。成键相关参数选择2（基于振动分析产生的fchk文件里的Hessian矩阵生成），并载入Ferrocene.fchk文件。确认后程序将在当前目录下产生Ferrocene.top和Ferrocene.itp文件，当前版本Sobtop默认使用modified Seminario方法，其产生的键角力常数优于Seminario方法。

---

## 10. 拓扑文件合理性的真空动力学测试

生成拓扑文件后，建议在真空下进行动力学模拟以测试合理性。使用GROMACS 2018.8，配合md.mdp（控温298.15K，模拟100ps，步长1fs，每100fs写一帧，无PBC），运行gmx grompp -f md.mdp -c Ferrocene.gro -p Ferrocene.top -o md.tpr和gmx mdrun -v -deffnm md。对于较新版本GROMACS，需在足够大的空盒子里考虑PBC跑NVT模拟。

---

## 11. 拓扑文件合理性的轨迹分析

使用VMD载入生成的轨迹，利用Extensions - Analysis - RMSD Trajectory Tool工具对system选区做align以消除平动转动，并设置每10帧叠加显示一次。如果模拟过程中二茂铁能很好地维持刚性结构，说明产生的拓扑文件是合理的。

---

## 12. 含柔性基团配合物的Sobtop参数生成策略

对于既有刚性配位区域也有柔性基团的配合物，在Sobtop询问如何产生成键相关参数时，建议选择相应选项。该策略让键和键角参数基于Hessian产生，而其他参数（如描述柔性部分二面角旋转特征）使用预置力场（如GAFF）的参数。

---

## 13. 使用ORCA进行振动分析的替代方案

除了Gaussian，也可以使用免费的ORCA程序进行优化和振动分析。在使用Sobtop生成拓扑文件时，将载入的文件由Gaussian的.fchk文件改为ORCA振动分析产生的.hess文件即可，其余操作步骤保持不变。

---

## 14. 无对称性体系的RESP电荷计算差异

对于没有对称性的体系，计算RESP电荷时不需要像二茂铁那样设置对称等价性。直接在Multiwfn的RESP界面里选择1，使用常规的两步式拟合即可。具体细节参考《RESP拟合静电势电荷的原理以及在Multiwfn中的计算》（http://原作者.com/441）。

---

## 15. 手动修改原子电荷的方法

除了在Sobtop生成拓扑文件时直接载入RESP电荷外，也可以在Sobtop中先不设置电荷。待.itp文件产生出来之后，用户可以手动打开文件，将所需的原子电荷写入到[ atoms ]部分。

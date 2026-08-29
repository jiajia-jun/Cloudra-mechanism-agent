---
id: 379
title: 详谈Multiwfn支持的输入文件类型、产生方法以及相互转换
url: http://sobereva.com/379
domain: 波函数与电子结构分析
topic: Multiwfn输入文件类型选择与格式转换
cards: 28
---
## 1. Multiwfn功能所需的信息类型

Multiwfn的绝大多数功能需要的信息可归为四大类：(1)原子坐标，用于基于promolecular的RDG/aRDG分析、计算HOMA/Bird芳香性指标等；(2)GTF信息（原始高斯型函数定义、轨道系数等），用于绘制实空间函数图、拓扑分析、计算ADCH/CHELPG/Hirshfeld电荷等；(3)基函数信息（收缩基函数定义、轨道系数等），用于计算Mayer/Lowdin/Mulliken键级、绘制PDOS/OPDOS、轨道成份分析、CDA分析等；(4)格点数据，用于主功能13的格点数据处理。某些功能如光谱图绘制需要跃迁能量和强度，AdNDP分析需要NBO输出信息，ICSS计算需要磁屏蔽张量。

---

## 2. 输入文件选择的基本规则

选择输入文件应根据功能所需的信息类型：凡是需要基函数信息的分析，不能用wfn文件，需用fch、mwfn、molden等；凡是只需要GTF信息的分析，用wfn和fch等均可。含有基函数信息的文件在Multiwfn载入时会自动转化出GTF信息，因此Multiwfn博文或手册中使用wfn文件的地方，都可以用fch、mwfn、molden等代替（前提是轨道一致）。具体功能所需信息可查阅手册第三章对应小节末尾的"Information needed"字段，或参考手册第四章的例子。

---

## 3. 特殊输入文件格式的说明

手册2.5节表中提到的"plain text file"指文该资料件（如量化程序输出文件），Multiwfn默认不从中读取基函数/GTF/坐标/格点数据。若将settings.ini里的iloadGaugeom设为1，Multiwfn会尝试从中读取最后一次输出的几何结构（优先输入朝向，其次标准朝向），从而进行只依赖原子坐标的任务。

---



---

## 4. mwfn文件的特征与来源

mwfn文件是包含几乎所有波函数分析所需信息的理想格式，具有简约、紧凑、可扩展的优点，自Multiwfn 3.7版开始支持载入和导出。此格式的详细说明见文献：https://doi.org/10.26434/chemrxiv.11872524。

---

## 5. wfn文件的特征与Gaussian产生方法

wfn文件是广泛支持的记录GTF信息的格式，但不包含空轨道，无法用于考察空轨道或涉及空轨道的分析（如计算局部电子亲和能）。在Gaussian中，使用`out=wfn`关键词并在末尾空一行写上输出路径即可产生，例如`# B3LYP/6-31g(d) out=wfn`，最后写`/sob/poi.wfn`。

---

## 6. wfn文件在Gaussian后HF/激发态计算中的注意点

对于目前的Gaussian版本，后HF或CIS/TDDFT计算时默认产生自然轨道并输出到wfn文件。对于G09 C.01以前版本，若要在wfn中输出后HF自然轨道或激发态自然轨道，必须写`density`关键词（等价于`density=current`）；若基于非限制性HF波函数做后HF计算且想输出自然自旋轨道，还需写`pop=NOAB`。

---

## 7. wfn文件在Gaussian不同任务类型中的适用性

Gaussian的单点、opt、freq、NMR、polar等任务均可同时产生当前计算级别的波函数文件（wfn或wfx或fch），只要波函数是分析所需的，即可直接使用，无需必须是单点任务产生。对于scan、IRC任务，若想产生每个点的wfn文件，可参考工具文章http://原作者.com/199。

---



---

## 8. GAMESS-US和ORCA产生wfn文件的方法

GAMESS-US需在$CONTRL段落中加入`AIMPAC=.TRUE.`，任务完成后在$SCR路径下的dat文件中，将"----- TOP OF INPUT FILE FOR BADER'S AIMPAC PROGRAM -----"到"----- END OF INPUT FILE FOR BADER'S AIMPAC PROGRAM -----"之间的内容拷出并保存为.wfn文件。ORCA需在输入文件中加入`aim`关键词，计算后产生同名wfn文件，或使用`orca_2aim FFFFF`命令将FFFFF.gbw转化为FFFFF.wfn。

---

## 9. wfx文件的特征与产生方法

wfx文件是wfn的改进格式，带有EDF字段描述被赝势代替的内核电子密度。由于Multiwfn自3.4版起自带了EDF数据库，使用wfx文件相比wfn文件无明显优势。在Gaussian中产生wfx文件只需将`out=wfn`改为`out=wfx`，其余完全一致。wfn和wfx能提供的信息对Multiwfn来说完全一样。

---

## 10. fch文件的特征与产生方法

fch文件是Gaussian chk文件的文本形式，包含基函数信息和空轨道信息，比wfn/wfx支持更多功能。产生chk文件需在输入文件开头指定`%chk=path/to/file.chk`。Windows下通过Gaussian界面的Utilities - FormChk将chk转为fch；Linux下使用`formchk`工具，命令如`formchk MADLAX.chk`。若chk过大导致转换失败，需设置环境变量如`export GAUSS_MEMDEF=4GB`。

---

## 11. chk转换为fch的常见错误与处理

chk转换为fch时出错通常有三种可能：(1)chk文件损坏，需删除重算；(2)产生chk的任务未正常结束，需修改关键词；(3)产生chk的Gaussian版本/平台与formchk不一致，应使用配套的formchk。若不想手动转换，可将settings.ini里的formchkpath设为formchk路径，Multiwfn载入chk时会自动转换并清理。

---

## 12. 基于fch文件进行后HF或TDDFT自然轨道分析

默认情况下fch文件记录HF或基态DFT轨道。若想基于后HF或TDDFT自然轨道分析，推荐使用方法1：见《在Multiwfn中基于fch产生自然轨道的方法与激发态波函数、自旋自然轨道分析实例》（http://原作者.com/403）。方法2（不推荐）需：(1)带`density`关键词计算；(2)用`# guess(save,only,naturalorbitals) chkbasis`计算；(3)在fch文件第一行插入`saveNO`。

---



---

## 13. molden文件的特征与兼容性

molden文件提供基函数信息，可记录轨道不可约表示，明确注明轨道占据数和自旋类型。其缺点是没有核电荷数段落（只记录原子序数），在赝势下计算需手动将[atoms]字段第三列原子序数改为实际核电荷数（ORCA 6.0+的[Pseudo]字段会被Multiwfn自动读取）。Multiwfn完美支持Molpro、ORCA、MRCC、NWChem、deMon2k、Dalton、xtb、BDF产生的molden文件，其他程序产生的需用Molden2AIM标准化。

---

## 14. 常用程序产生molden文件的方法

ORCA使用`orca_2mkl MIO -molden`将MIO.gbw转化为MIO.molden.input；Molpro在输入文件末尾写`put,molden,ltwd.molden`；MRCC默认产生MOLDEN文件，改后缀为.molden；xtb运行时加`--molden`选项生成molden.input；Dalton在输出.tar.gz包里有molden.inp；NWChem需在输入文件末尾加入`property ... moldenfile ... end`和`task scf property`，且必须用`GEOMETRY noautosym`和`BASIS spherical`。

---

## 15. gms文件的特征与注意事项

gms文件是GAMESS-US或Firefly的输出文件，需手动改后缀为.gms。目前仅保证能正确载入默认NPRINT参数下的HF/DFT任务输出文件，对于几何优化载入的是初始结构波函数。gms文件提供的信息与fch、molden完全一致。

---

## 16. cub、grd、vti、dx文件的特征

cub文件是Gaussian定义的记录格点数据的流行格式，Multiwfn只支持三个平移矢量分别对应X,Y,Z轴的情况。grd文件（DMol3）与cub类似但不记录原子坐标，Multiwfn无法显示结构。vti文件（GIMIC 2.0、ParaView）和dx文件（VMD Volmap插件）也是格点数据格式，不含原子坐标。

---

## 17. NBO plot文件的特征

NBO plot文件指后缀为31~40的文件，31记录基函数定义，32~40分别记录PNAO/NAO/PNHO/NHO/PNBO/NBO/PNLMO/NLMO/MO向基函数的展开系数。载入31后再载入32~40中的一种可观看相应轨道。若考察实空间函数，只能用NBO（37）或NLMO（39），否则结果无意义。

---

## 18. 坐标文件格式（pdb、xyz、mol等）的特征

pdb、xyz、mol、mol2、gro、cif等文件用于提供原子坐标。pdb优先根据元素名指认，若无元素名则根据原子名猜测，易出错；xyz文件原子名应为元素名；.mol和.mol2记录原子间连接关系，对EEM电荷计算等必须；chg文件是Multiwfn自定义格式，记录坐标和电荷；gro文件靠原子名猜元素；cif文件用于晶体结构，不支持原子占据数不为1。

---

## 19. Gaussian和ORCA输入输出文件的使用

Gaussian和ORCA的输入、输出文件可提供坐标信息（ORCA输出文件还提供alpha和beta电子数）。原子必须以笛卡尔坐标记录。若任务包含多个结构（如opt freq），Multiwfn读取最后一次输出的结构。对于Gaussian输出文件，可通过settings.ini里的iloadGaugeom选择读取输入朝向或标准朝向的结构。

---

## 20. CP2K、Quantum ESPRESSO和VASP文件的使用

Multiwfn可从CP2K和Quantum ESPRESSO的输入文件载入原子坐标和晶胞信息（CP2K的restart文件也可直接载入）。支持VASP的POSCAR（坐标、晶胞）、CHGCAR/CHG（电子密度、自旋密度）、ELFCAR（ELF）、LOCPOT（外势）文件。文件名需包含格式名（如nozomi.CHGCAR），载入LOCPOT时会根据LVHAR设置询问是否反转符号。

---

## 21. Multiwfn主功能100子功能2的文件转换能力

主功能100子功能2可将载入文件转换为mwfn、pdb、xyz、chg、wfn、wfx、molden、fch、47文件（GENNBO输入）以及多种主流/第一性原理程序的输入文件。若载入文件包含基函数信息，生成的GAMESS-US、Dalton和Gaussian输入文件可包含初猜波函数信息。

---

## 22. 文件转换用途：molden/gms转fch

将molden或gms转换为fch，使得Gaussian以外的用户可以使用GaussView查看结构/轨道，或用Gaussian自带的cubegen产生格点数据，或使用必须依赖fch的程序（如GDMA）。转换出的fch可用Gaussian的unfchk工具转回chk，用于guess=read。

---

## 23. 文件转换用途：Gaussian输入文件转换与NBO分析

将Gaussian输入文件转化为其它程序输入文件，方便Gaussian用户使用其它程序。将gms、fch等转换为47文件，使得GAMESS-US、MOLPRO等不支持直接输出NBO输入的程序用户也能做NBO分析。

---

## 24. 文件转换用途：优化载入效率与生成特定格式

将大体系的molden文件转换为wfx/wfn，可减少再次载入时的耗时和内存占用（仅适用于仅需研究实空间函数的情况）。将波函数文件转换为Gaussian输入文件，可基于现有结构快速生成计算任务。

---

## 25. 文件转换用途：可视化与跨程序协作

将波函数文件转换为pdb或xyz格式，便于使用VMD、Avogadro、xtb等通用可视化或计算程序。转换为mkl格式可用于ORCA的初猜波函数（见http://原作者.com/517）。将VASP、Dmol3、VMD的格点数据转换为cub格式，便于利用支持cub的程序查看。

---



---

## 26. 文件转换用途：辅助程序收敛与ParaView可视化

将Multiwfn载入的波函数转换为带初猜（$VEC或**MOLORB字段）的GAMESS-US或Dalton输入文件，可解决这些程序SCF难收敛的问题。将格点数据导出为vti格式，可利用ParaView强大的体数据可视化功能（如流线场图）。

---

## 27. Gaussian输出文件转化为gjf格式

利用Multiwfn将Gaussian输出文件转化为gjf格式，可将优化任务的最后一帧结构保存为新的单点任务输入文件，此功能有批量转换脚本可用（见http://原作者.com/530）。

---

## 28. 波函数修改与导出的注意事项

利用主功能6修改波函数（如去掉原子/轨道贡献）后，需用主功能100子功能2导出mwfn/molden/fch等格式，再重新载入，才能在载入时产生正确的GTF信息（修改基函数信息后GTF信息不会自动更新）。

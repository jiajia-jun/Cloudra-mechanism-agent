---
id: 552
title: 使用Shermo结合量子化学程序方便地计算分子的各种热力学数据
url: http://sobereva.com/552
domain: 量子化学方法
topic: Shermo程序计算分子热力学数据
cards: 18
---

# Shermo程序计算分子热力学数据 — 知识卡片

## 1. Shermo程序简介及文献引用

Shermo是一个免费的独立运行的程序，用于基于理想气体假设和量子化学程序振动分析的输出文件计算分子热力学数据。使用Shermo程序计算热力学数据发表文章时请务必引用：Tian Lu, Qinxue Chen, Shermo: A general code for calculating molecular thermochemistry properties, *Comput. Theor. Chem.*, **12** **00**, 113249 (2021) DOI: 10.1016/j.comptc.2021.113249。Shermo的前身1.0版功能较少，本文介绍的是功能更强大的后续版本。

---

## 2. Shermo支持输入的量子化学程序格式

Shermo可以读入Gaussian、ORCA、GAMESS-US、NWChem、xtb这五种最流行的量子化学程序的输出文件（可以是振动分析，也可以是优化+振动分析）。此外，Shermo还可以读入CP2K第一性原理程序的振动分析的输出文件。

---

## 3. Shermo支持计算的热力学量与模型特点

Shermo可以计算内能、焓、熵、自由能、等压和等容热容、配分函数等所有常见的热力学量。程序支持对ZPE、熵、升温对焓/内能的增加量、热容分别设置不同的频率校正因子，支持对温度和压力进行扫描，并默认使用谐振近似模型。Shermo还支持Truhlar、Grimme和Minenkov提出的准RRHO方法来考虑低频振动的贡献，对柔性分子、弱相互作用团簇等含有低频的体系可以得到明显更合理的结果。

---

## 4. Shermo的高级功能与优势

Shermo可以给出一批构型/构象的Boltzmann分布比例和构象权重的热力学数据，并可以考虑浓度变化导致的自由能改变。程序既可以通过双击图标执行，也可以通过纯命令行方式运行从而嵌入批处理脚本，且无需安装配置运行环境。相比Gaussian等主流量子化学程序自带的热力学计算功能，Shermo支持准RRHO模型、能更稳健地判断点群和转动对称数，并且能弥补ORCA、GAMESS-US等程序缺乏类似freqchk工具的空白。

---

## 5. Shermo的基本运行方式与Linux环境配置

在Windows下运行Shermo通常是双击Shermo.exe图标启动，程序会从当前目录下的settings.ini中读取运行参数，输入文件路径后即可计算。在Linux下运行时，若想在任意目录下启动Shermo并从程序目录下载入settings.ini，需在~/.bashrc文件里加入`export PATH=$PATH:/sob/Shermo_2.0`和`export Shermopath=/sob/Shermo_2.0`（假设路径为/sob/Shermo_2.0），然后重新进入终端。

---

## 6. Shermo的命令行参数指定与在线使用

在Linux下运行时可以直接指定参数，例如`Shermo example/G16_H2CO_freq.out -T 350 -sclZPE 0.9806`，代表处理指定文件、温度设为350 K、ZPE校正因子设为0.9806，未指定的参数使用settings.ini里的设置。Shermo也可以通过https://atomistica-online-shermo.anvil.app网站在线使用，使用在线平台时除了引用Shermo原文外，还应同时引用平台作者的文章DOI: 10.1080/08927022.2022.2126865。

---

## 7. 计算气相甲醛热力学数据的参数设置示例

计算甲醛在350 K下的热力学数据时，若使用B3LYP/6-31G*进行优化和振动分析，用CCSD(T)/cc-pVTZ计算电子能量(-114.3338033 a.u.)，需在settings.ini中设置E=-114.3338033，T=350，sclZPE=0.9806。使用RRHO模型（与Gaussian 16相同）时需设置ilowfreq=0，若考察各振动模式贡献需设置prtvib=-1。

---

## 8. Shermo输出文件中的热力学量加和含义

Shermo输出的总热力学量中，配分函数是平动、转动、振动、电子激发四部分贡献的乘积，各种热力学校正量和熵是这四部分贡献的加和。电子能量与热力学校正量的加和即为常用的热力学量，例如“Sum of electronic energy and thermal correction to G”代表当前温度下的自由能，而“Sum of electronic energy and ZPE”代表0 K下的内能/焓/自由能。

---

## 9. 振动模式对热力学量贡献的输出内容

设置prtvib=-1生成的vibcontri.txt文件包含各振动模式的波数、频率、振动温度，以及对配分函数、ZPE、内能增加量U(T)-U(0)、内能、等压热容和熵的贡献。数据显示频率越低的振动模式对U(T)-U(0)、CV(T)、S(T)的贡献越大，而频率越高的振动模式对ZPE和U(T)的贡献越大。

---

## 10. Shermo的温度和压力扫描功能

在settings.ini中设置T=50,1000,10（代表下限50 K，上限1000 K，步长10 K），Shermo运行后会生成scan_UHG.txt（含U、H、G及与电子能量加和）和scan_SCq.txt（含S、热容、配分函数）。对压力也可以进行扫描，若对温度和压力都设了上下限和步长，则Shermo会进行二维扫描。

---

## 11. 柔性分子热力学计算的准RRHO模型选择

对于瑞德西韦等柔性大分子，必须使用准RRHO模型代替RRHO模型，因为RRHO对低频模式（<100 cm-1）计算熵的误差很大。Shermo支持Truhlar（ilowfreq=1）、Grimme（ilowfreq=2）和Minenkov（ilowfreq=3）三种准RRHO方法，其中Grimme的做法明显优于Truhlar，Minenkov的做法可能进一步提升精度。

---

## 12. 溶液标准态自由能的校正方法

要得到严格的溶液标准态（298.15K, 1 M）下的自由能，需要将气相标准态（298.15K, 1 atm）下计算的自由能加上1.89 kcal/mol（0.003012 a.u.）的转换项。Shermo提供了直接计算该自由能变的功能，只需在settings.ini中设置conc=1M，输出的“Gibbs free energy at specified concentration”即为液相标准态自由能。

---

## 13. 使用Shermo计算构象分布与权重平均热力学数据

创建一个文本文件（如list.txt），每行写入振动分析输出文件路径，并在分号后写上更高级别计算的电子能量（如`example\ensemble\gau00001.out;-2321.367718855799`）。Shermo载入该文件后会计算各构象的相对自由能、Boltzmann权重（分布比例），并输出考虑了构象平均的电子能量、内能、焓、自由能、熵（包含构象熵）等热力学数据。

---

## 14. 使用Shell脚本调用Shermo进行批量处理

在Linux下可以编写Shell脚本调用Shermo进行批处理，例如计算当前目录下所有.log文件的自由能：设置sclZPE为0.975，使用Grimme准RRHO方式，并提取Sum of electronic energy and thermal correction to G的结果存入getGall.txt。示例脚本命令为：`./Shermo ${inf} -sclZPE 0.975 -ilowfreq 2 | grep "Sum of electronic energy and thermal correction to G:" | cut -d: -f 2 >> getGall.txt`。

---

## 15. 固体体系热力学量计算的设置

计算晶体或固体表面（包括表面吸附）的热力学量时，一般使用CP2K程序进行优化和振动分析，然后将输出文件提供给Shermo。必须将Shermo的settings.ini里的imode参数设为1，这样平动和转动对热力学量的贡献会被忽略，以适应固体体系无法自由平动和转动的情况。

---

## 16. Shermo与Gaussian热力学计算结果不一致的原因

若Shermo输出的热力学校正量和Gaussian直接输出的不一致，首先需检查T、P、频率校正因子及计算模型（ilowfreq=0对应RRHO）是否一致。若以上均满足，不一致通常是因为Gaussian对体系点群判断有误导致转动对称数识别错误，而Shermo判断点群的功能更稳健，此时应以Shermo结果为准。

---

## 17. Shermo计算单个原子热力学量的方法

对于单个原子体系，不需要做优化（既无意义也会导致程序报错），直接进行振动分析，然后将输出文件给Shermo使用即可计算热力学量。

---

## 18. 频率校正因子sclfreq与焓校正因子的关系

Shermo的sclfreq参数设置的是计算U(T)-U(0)的频率校正因子，这与很多文献中给出的H(T)-H(0)频率校正因子是一回事。因为H(0)和U(0)相同，H(T)和U(T)在理想气体近似下仅相差一个与振动无关的RT项，所以两者使用相同的频率校正因子。

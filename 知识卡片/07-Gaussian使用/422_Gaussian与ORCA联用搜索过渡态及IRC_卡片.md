---
id: 422
title: 将Gaussian与ORCA联用搜索过渡态、产生IRC、做振动分析
url: http://sobereva.com/422
domain: Gaussian使用
topic: Gaussian与ORCA联用搜索过渡态及IRC
cards: 11
---
## 1. Gaussian与ORCA联用的引用方式

如果实际研究中使用了Gaussian与ORCA联用的接口，请按照以下格式引用：Tian Lu, gau_orca: A Gaussian interface for ORCA program, http://原作者.com/422 (accessed month day, year)。
- 原文明确要求在研究中使用该接口时需进行文献引用，引用格式包含了作者、接口名称、描述、网址及访问日期。

---

## 2. 联用优势：扩展理论方法

通过Gaussian的external功能与ORCA联用，可以令Gaussian进行过渡态搜索、IRC及振动分析时支持ORCA特有的理论方法，例如PBEh-3c、B97-3c、PWPB95-D3、NEVPT2、MRCI、DLPNO-CCSD(T)等；对于没有解析梯度的理论方法，可通过自写脚本以有限差分方式得到Gaussian所需的梯度信息。
- 原文列举了具体的理论方法名称，并说明了对于缺乏解析梯度的方法可以通过有限差分获取梯度。

---

## 3. 联用优势：计算效率与算法成熟度

联用方案利用ORCA出色的RI加速技术，能在使用大基组进行大体系计算时显著降低耗时；同时利用Gaussian在几何优化和过渡态搜索算法上更成熟、稳健且选项丰富的特点；此外还能解决ORCA目前缺乏IRC功能的问题，并使ORCA产生的Hessian振动模式能通过GaussView观看。
- 原文对比了两者的优势，指出了ORCA在RI加速方面的特长以及Gaussian在优化算法和IRC功能上的优势。

---

## 4. orca.sh脚本的参数设置

在使用接口脚本orca.sh时，用户必须在脚本开头自行设置ORCA的并行核数、单核内存（MB）、计算级别（如BLYP def2-svp def2/J）、数值精度参数（如默认开启tightscf）以及ORCA可执行文件的路径；这些变量包括nprocs、maxcore、level、numset和orcapath。
- 原文展示了脚本中需要用户修改的具体变量名称及其示例数值。

---

## 5. orca.sh脚本的输入读取

orca.sh脚本使用read命令从Gaussian自动生成的InputFile中读取原子数、导数阶数、净电荷和自旋多重度到相应变量，具体命令为：read atoms derivs charge spin < $2。
- 原文提供了读取输入文件信息的具体代码行。

---

## 6. ORCA计算任务的关键词选择

脚本根据导数阶数变量$derivs决定ORCA的执行任务：当导数为2时任务设为"engrad freq"（计算能量、梯度和Hessian），当导数为1时任务设为"engrad"（仅计算能量和梯度）；输出结果分别保存为当前目录下与输入文件同名的.engrad和.hess文件。
- 原文解释了判断逻辑及对应的ORCA关键词和输出文件格式。

---

## 7. ORCA输入文件的生成与单位

脚本生成名为mol.inp的ORCA输入文件，使用BOHRS关键词指明坐标单位为Bohr，并包含计算级别、精度设置、并行参数及电荷自旋多重度，坐标内容通过sed命令从Gaussian输入文件中截取。
- 原文说明了生成输入文件的命令细节，特别是单位转换关键词BOHRS的使用。

---

## 8. 波函数初猜的连续性保持

ORCA计算会在当前目录生成mol.gbw波函数文件；由于ORCA默认开启autostart，在后续几何优化步骤中会自动读取已存在的.gbw文件作为初猜，这不仅节约计算时间，还有助于保持电子态的连续性；脚本通过重命名操作确保mol.gbw在任务期间不被删除。
- 原文描述了利用.gbw文件维持波函数连续性的机制及脚本中的保留操作。

---

## 9. 数据提取与文件清理

脚本调用自编的Fortran程序extorca从ORCA输出的.engrad和.hess文件中提取能量及导数信息写入Gaussian的OutputFile；任务结束后，脚本会删除mol和mol_开头的临时文件，但通过mv命令保留mol.gbw文件以备后续使用。
- 原文说明了数据提取的程序名称以及清理临时文件但保留波函数文件的逻辑。

---

## 10. 过渡态搜索的Gaussian输入设置

进行HCN->CNH异构化过渡态搜索时，Gaussian输入文件需包含%chk、%nproc=1以及#P opt(nomicro,calcfc,ts,noeigen) external='./orca.sh'；运行命令示例为g09 < TS.gjf |tee TS.out；使用external功能时必须确保Gaussian串行计算以避免Link401的高CPU占用。
- 原文提供了具体的输入文件关键字、运行命令及关于串行运行的注意事项。

---

## 11. 振动分析与IRC的输入设置

振动分析输入文件需包含%chk、%nproc=1及# freq geom=allcheck external='./orca.sh'；IRC计算输入文件需包含%oldchk、%nproc=1及# IRC=calcfc geom=allcheck external='./orca.sh'，其中使用%oldchk可避免过渡态文件TS.chk被改写。
- 原文列出了振动分析和IRC任务的具体输入文件内容。

---
id: 476
title: 计算RESP原子电荷的超级懒人脚本（一行命令就算出结果）
url: http://sobereva.com/476
domain: 波函数与电子结构分析
topic: Gaussian与Multiwfn计算RESP电荷脚本
cards: 1
---

# Gaussian与Multiwfn计算RESP电荷脚本 — 知识卡片

## 1. RESP电荷在分子动力学模拟中的适用性

RESP电荷特别适合对柔性分子做分子动力学计算。作者撰写的《RESP拟合静电势电荷的原理以及在Multiwfn中的计算》（http://sobereva.com/441）一文详细介绍了RESP电荷，并展示了Multiwfn在计算RESP电荷上的便利性和灵活性。

## RESP2电荷作为分子动力学模拟的推荐选项
如果计算RESP电荷的目的是用于分子动力学模拟，作者更建议使用RESP2电荷，因为有较大可能结果更好。作者在《RESP2原子电荷的思想以及在Multiwfn中的计算》（http://sobereva.com/531）中介绍了RESP2电荷，并提供了专门的RESP2.sh脚本。

## 免费ORCA程序结合Multiwfn计算电荷
如果没有购买Gaussian，可以使用免费的ORCA量子化学程序结合Multiwfn计算各种原子电荷。作者提供了相应的傻瓜式脚本，详见《ORCA结合Multiwfn计算RESP、RESP2和1.2*CM5原子电荷的懒人脚本》（http://sobereva.com/637）。

## 脚本运行前的Gaussian与Multiwfn环境配置
使用脚本前需在机器上安装Gaussian（参考http://sobereva.com/439）并下载安装Multiwfn最新版本（参考http://sobereva.com/688），确保能通过输入Multiwfn命令启动程序。如果安装的是noGUI版，需要将脚本里的Multiwfn改为Multiwfn_noGUI。

## 脚本针对不同Gaussian版本的修改方法
Multiwfn目录下的examples\RESP\目录下的RESP.sh脚本默认调用g09，Gaussian16用户应当将其中的g09替换为g16。

## 脚本默认的计算级别与流程
脚本默认在B3LYP-D3(BJ)/def2-SVP级别下对结构进行优化，然后在B3LYP-D3(BJ)/def2-TZVP级别下计算单点能并产生分子表面静电势数据，之后调用formchk转化文件，最后调用Multiwfn产生RESP电荷。用户可根据需要修改关键词。

## 降低计算耗时可选的半经验方法
如果B3LYP-D3(BJ)/def2-SVP级别的几何优化耗时太高，可将关键词改为# PM6D3 opt，即使用PM6-D3半经验方法在真空中优化。此方法主要适合普通有机体系且体系无局部显著离子特征，结构精度虽低于DFT但对算RESP电荷目的影响不大。

## 降低单点计算耗时的基组选择
如果单点任务计算困难，可将def2-TZVP基组降为6-311G**，如果是阴离子建议改为6-311+G**。

## 旧版本Gaussian对DFT-D3校正的限制
Gaussian09 D.01版本之前不支持DFT-D3校正，使用老版本的用户应当把脚本里的em=GD3BJ关键词取消，相关信息见《DFT-D色散校正的使用》（http://sobereva.com/210）。

## 脚本的使用命令与参数格式
将RESP.sh拷贝到当前目录并赋予可执行权限，运行命令格式为：./RESP.sh [文件名] [净电荷] [自旋多重度] [溶剂名]。输入文件格式必须是Multiwfn支持的格式（如xyz/mol/mol2/pdb/fch/wfn/molden/gjf等）。

## 脚本参数的默认值与溶剂设置
如果不写净电荷和自旋多重度，默认值分别为0和1。如果不写溶剂名，默认为water；如果写gas，则在真空下计算；支持的溶剂名列表见http://sobereva.com/g09/k_scrf.htm末尾。

## 脚本计算输出结果与文件
计算完毕后，当前目录下会生成与输入文件同名的.chg文件。该文件前四列是元素名和优化后的坐标，最后一列是RESP电荷。

## 脚本运行错误的排查方法
如果调用Gaussian运行失败，脚本会自动停止，用户需检查当前目录下的gau.out文件来判断出错原因。

## 脚本使用的CPU核数设置
计算时使用的CPU核数取决于Gaussian的Default.Route文件里的-P-设置，详见《Gaussian的安装方法及运行时的相关问题》（http://sobereva.com/439）。

## 高级RESP拟合设置的操作方法
本文脚本仅以最一般的方式计算RESP电荷，若需更灵活的拟合方式（如设置电荷等价性、设置片段总电荷），需在Multiwfn的RESP模块界面中设置，详见http://sobereva.com/441。

## 跳过几何优化的脚本版本
如果输入的结构文件已经足够好且不想浪费时间进行优化，可以使用examples\RESP\目录下的RESP_noopt.sh代替RESP.sh，二者用法完全一致，但前者不做优化步骤。

## 含重元素体系的RESP电荷计算限制
如果体系含有18号及以后的元素，由于Gaussian没有内置拟合静电势用的原子半径，无法通过脚本自动得到RESP电荷。必须手动做Gaussian计算得到fch文件后，利用Multiwfn按照http://sobereva.com/441所述操作计算，并根据屏幕提示使用Multiwfn自动推荐的半径。

## 使用脚本计算的文献引用要求
如果以本文方式计算了RESP电荷，必须引用Multiwfn原文，具体引用方式见《Multiwfn FAQ》（http://sobereva.com/452）。

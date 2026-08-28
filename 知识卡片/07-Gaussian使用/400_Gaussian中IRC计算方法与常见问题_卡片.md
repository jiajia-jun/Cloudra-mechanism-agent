---
id: 400
title: 在Gaussian中计算IRC的方法和常见问题
url: http://sobereva.com/400
domain: Gaussian使用
topic: Gaussian中IRC计算方法与常见问题
cards: 1
---

# Gaussian中IRC计算方法与常见问题 — 知识卡片

## 1. IRC的定义与作用

IRC是质权坐标下连接势能面相邻两个极小点的能量最低路径，描述了化学过程在不考虑热运动因素下最理想的结构变化轨迹。IRC对于讨论微观化学过程至关重要，也是验证过渡态找没找对的最决定性的方法。
## 计算IRC前的准备步骤
在产生IRC之前，必须先进行过渡态(TS)优化，且必须以过渡态的结构为初始结构。既可以将优化出的TS结构直接写在IRC输入文件里，也可以用geom=check关键词从优化TS任务的.chk文件里读取最后一帧结构。
## IRC与过渡态计算的级别一致性要求
IRC任务特别需要注意的一点是，产生IRC和找过渡态用的计算级别必须严格一样。确切来说，任何影响势能面的设定必须严格相同（如果你不知道哪些会产生影响，比较修改前后单点能是否有差异便知）。
## Gaussian支持的IRC算法LQA
Gaussian09/16支持多种产生IRC的算法，其中LQA(Local quadratic approximation)是非常传统的一种IRC产生算法，1988年提出了，每一步都需要利用Hessian矩阵。
## Gaussian支持的IRC算法HPC
HPC(Hessian-based Predictor-Corrector)是2004年由Gaussian作者之一Schlegel提出，这是G09/16默认的算法。这个方法产生IRC每一个点的时候，是将LQA方法作为预测步(predictor)，再用修改的Bulrisch-Stoer方法做为校正步(corrector)。此方法校正步的计算过程是一个迭代过程，HPC方法的一个最大问题正是做校正步的时候经常不收敛。
## Gaussian支持的IRC算法GS2
GS2是1989年提出的方法，GS是Gonzalez-Schlegel的缩写，是G03默认的算法。此方法之所以不再是如今版本默认的，是因为此方法耗时比HPC高很多，每一步都相当于做一次限制性优化。
## IRC计算中Hessian矩阵的生成策略
走IRC时，对初始结构需通过calcfc关键词来产生精确的Hessian矩阵。如果在IRC里用calcall关键词代替calcfc，则每一步的Hessian矩阵都会精确生成，IRC走得也会更准确，但是耗时会暴增一个数量级甚至更多。也可以在写calcfc的同时用recalc=n关键词，此时每n步才会精确重算一次Hessian矩阵。
## IRC的反应坐标定义与单位
在Gaussian中IRC任务的初始结构（过渡态结构）被作为反应坐标的零点，往反应物一侧反应坐标为负，往产物一侧反应坐标为正。Gaussian给出的反应坐标单位是amu^1/2 Bohr，这里amu是指atomic mass unit。
## 同位素质量对IRC结果的影响
由于IRC是在质权坐标下定义的，因此结果受同位素质量设定的影响。如果在IRC里写上Cartesian关键词，代表在笛卡尔坐标下执行IRC任务，此时结果确切来说叫做MEP（minimal energy path，极小能量路径）。
## IRC计算方向的控制关键词
在IRC里可以用Reverse或Forward关键词让程序只往逆方向或者正方向一侧走IRC。如果你想让Gaussian知道指定哪边是正方向哪边是逆方向，需要在IRC里利用Phase关键词定义。
## IRC结果的查看与可视化
走完IRC后，可以用gview打开输出文件，在窗口左上角切换帧号可观看IRC每一帧结构，或者点绿色圆点播放IRC轨迹。IRC的“能量vs反应坐标”图可以用Results - IRC/Path来观看，点击图的左上角的Plots - Plot Molecular Property还可以把几何参数等信息随反应坐标的图绘制出来。
## IRC参数Maxpoints的作用与设定
Maxpoints设定的是每个方向走的步数，默认为10。注意maxpoints设的是步数上限，因为走IRC时，如果已经走到了被程序自动判断是离极小点很近的位置了，则IRC就认为这个方向的IRC已经产生完毕了。
## IRC参数Stepsize的作用与设定
Stepsize设的是IRC步长，默认为10。如果设的是正值，则单位是0.01 Bohr，如果设的是负值，则单位是0.01 amu^1/2 Bohr。stepsize设得越小，IRC越准确、曲线越光滑；stepsize设得越大，则IRC越不准确，曲线越可能出现褶皱。
## 验证过渡态的IRC参数建议
对于验证过渡态找没找对这一目的，IRC只要跑一小段就足够看出趋势了。maxpoints用默认即可，stepsize可以设大到15或20，从而在不增加计算量的前提下能比默认时稍微跑长一些，建议加上LQA关键词避免HPC方法因校正步不收敛而中断。
## 获取近似反应物/产物结构的IRC参数建议
为了获得近似的反应物和产物结构，maxpoints应设50甚至更大从而使IRC尽可能跑完整。其它参数设定同验证过渡态的情况。
## 获取高质量IRC曲线的参数建议
为了获得高质量、完整的IRC曲线用于发文章，可以把stepsize设小到5。由于设小了步长，又想要IRC完整，maxpoints必须设很大，比如200。如果此时跑出来的IRC还是不平滑，或者因HPC方法的校正步不收敛而中途报错中断，应再加上calcall重新跑。
## 解决IRC报错“Maximum number of corrector steps exceded”
此报错是HPC方法校正步不收敛导致的。解决办法包括：(1)用LQA关键词；(2)减小步长（如stepsize=5）或加上calcall/recalc=x；(3)改用GS2算法；(4)加上ReCorrect=never（但不建议）；(5)加上maxcyc=N（不建议）。
## IRC刚开始就结束或两侧曲线相同的原因
IRC刚走几步就正常结束，或两侧曲线相同，都是因为优化过渡态时定位准确度不够，结构稍微偏离了IRC的极大点。往一边产生IRC能正常产生，但从偏离点往另一边产生IRC时，程序发现能量升高就停止，或者转到了另一边。
## 解决IRC刚开始就结束或两侧曲线相同的方法
解决IRC异常结束的方法包括：(1)确保初始结构是优化TS得到的结构，且级别严格相同；(2)提高过渡态定位精度（如用tight、int=ultrafine、calcall）；(3)增大IRC步长（如20或30）越过偏差；(4)使用guess=read读取过渡态的波函数。
## 溶剂模型导致IRC停止的解决方法
用SMD溶剂模型时，可能由于数值噪音问题出现IRC走几步就停了的现象。可将优化和走IRC用的溶剂模型都改为IEFPCM再试。
## IRC输出文件中点突然掉下去的现象
当IRC还没有走完的时候就打开输出文件，或者看的是IRC失败的任务的输出文件，往往就会看到中间有一个点突然掉下去的现象。任务正常结束后再看就不会有这个现象。
## IRC端点不是反应物/产物结构
走出来的IRC最两端的点不是反应物和产物结构。IRC的步长是固定的，注定不可能恰好有一个IRC点正好落在与反应物或产物对应的极小点的位置。必须对IRC两端的点进一步做几何优化才能得到准确的反应物或产物结构。
## IRC端点优化得不到预期极小点的原因
对IRC两边的点优化却得不到想要的极小点结构，可能原因有：(1)与TS连通的极小点本来就是那样，且IRC跑得太短；(2)优化时步子太大或Hessian矩阵不准，优化到了其它邻近极小点。
## 柔性扫描与IRC的区别
柔性扫描和IRC概念完全不同，不能代替。IRC是从TS开始顺着虚频方向，沿着梯度负方向移动结构走出来的轨迹，所有坐标是同步变化的。柔性扫描是令某些坐标以特定方式改变并优化其余变量，变量间变化不是协同的。
## IRC曲线在过渡态位置不平滑的解决方法
如果IRC曲线在过渡态位置特别尖或不平滑，应确认计算级别严格相同，并尝试增加过渡态定位精度（tight、calcall/recalc=x、增加积分格点）。若问题依旧，走IRC时用GS2算法或加上calcall，并确保波函数一致。
## IRC任务的续算方法
IRC任务续算只需在IRC里添加restart关键词，例如IRC(restart,maxpoint=15)。此时%chk应当和之前中断的IRC任务相同。
## 在原有IRC基础上增加点数的方法
如果之前IRC跑得不够长，想在不完全重算的前提下增加点数，可执行IRC(restart,maxpoint=20)，%chk应当和之前的IRC任务相同。注意gview观看restart得到的IRC轨迹要打开chk/fch文件。
## 解决IRC任务出现L502错误
IRC任务出现L502错误是走IRC过程中出现了SCF不收敛所导致。可添加guess=read读取之前收敛的波函数作为初猜，或减小IRC步长。常规SCF不收敛解决方法见相关文献。
## IRC曲线出现凸起或肩峰的原因
IRC看起来边上凸起来一块很正常，只要确信计算流程合理且轨迹无异常，出现肩峰往往暗示反应涉及的电子结构变化复杂，应结合波函数分析手段考察。
## 无解析Hessian方法的IRC计算
如果理论方法（如CCSD）支持解析梯度但不支持解析Hessian，可以使用关键词生成IRC：IRC(gradientonly,euler)。gradientonly代表使用只依赖于梯度的IRC算法，默认是DVV方法，建议改成相对好点的Euler方法。
## 从chk文件读取Hessian矩阵进行IRC计算
对过渡态已经做过振动分析后，chk里已经有了过渡态结构下的Hessian矩阵，在IRC计算时可以直接读取以节约时间。在IRC里加上rcfc关键词即可，此时就不需要写calcfc了，程序会从%chk文件中直接读取Hessian矩阵。

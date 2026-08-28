---
id: 286
title: 使用sobMECP程序结合Gaussian程序搜索极小能量交叉点
url: http://sobereva.com/286
domain: 激发态与光谱
topic: sobMECP结合Gaussian搜索极小能量交叉点
cards: 16
---

# sobMECP结合Gaussian搜索极小能量交叉点 — 知识卡片

## 1. 势能面交叉条件

两个态波函数分别为|1>和|2>，构成2*2哈密顿矩阵，矩阵元包括对角元H11=<1|H|1>、H22=<2|H|2>和耦合矩阵元H12=<1|H|2>=H21。两态能量E1、E2相同需同时满足两个条件：(1) H11=H22 (2) H12=0。对于自旋多重度不同的态，不考虑旋轨耦合时H12总为0，只需满足H11=H22。

---

## 2. 极小能量交叉点定义

不考虑旋轨耦合下，两个自旋多重度不同的态的交叉在3N-7维超曲面中进行。极小能量交叉点(MECP)是指两个态能量相同的3N-7维超曲面中能量最低的那个结构。两个态之间可以存在多个MECP，搜索到的具体结果取决于初猜结构。

---

## 3. 系间窜越与MECP

系间窜越是重要的光化学过程，指电子激发后，由于不同自旋多重度的态的势能面之间存在交叉，导致体系经历这样的结构时以非辐射方式改变自旋多重度。寻找MECP的结构对光化学研究十分重要。

---

## 4. MECP理论方法选择

搜索MECP可用的理论方法有两类：一类是做态平均CASSCF（或MS-CASPT2、MRCI）计算；另一类是用普通方法如DFT、MP2、CCSD分别对两个态做单点计算。基于DFT搜索MECP是首选，便宜、方便且可用于大体系，如果对精度要求高可考虑CCSD或CASSCF。

---

## 5. Robb的MECP搜索算法

Robb提出的MECP搜索算法定义两个有效梯度f和g。f是(E1-E2)^2对核坐标求导，即E1-E2乘以两个态的梯度矢量之差，沿f移动减小能量差。g是E1对核坐标求导并投影掉f方向的分量，沿g移动降低第一个态能量。按f+g作为有效受力进行优化，最后得到MECP结构。

---

## 6. MECP搜索收敛标准与算法应用

MECP搜索一般同时使用位移、受力、两个态能量差作为收敛判断标准。若去掉能量差必须接近0的收敛标准，该算法也可直接用于搜索避免交叉极小点。搜索MECP用的初猜取平衡结构或过渡态结构即可，该算法基于牛顿法或赝牛顿法。

---

## 7. sobMECP程序引用与下载

sobMECP是Harvey的MECP程序的修改版，使用更方便，下载地址：http://sobereva.com/soft/sobMECP.zip。如果使用了sobMECP发表文章，请引用：Tian Lu, sobMECP program, http://sobereva.com/286 (accessed month day, year)。

---

## 8. sobMECP的Input_Header文件设置

设定Input_Header_A和Input_Header_B文件，内容分别是两个态的分子坐标之前的部分。%chk必须写，force和guess(read)关键词必须写，其它关键词根据实际情况填写，必须用#n。如果需要用gen或genECP从坐标末尾读取基组，需在Input_Tail文件中写明定义，否则留空。

---

## 9. sobMECP的geom文件格式

在geom文件中填好体系初始结构，末尾必须空一行，原子名必须用元素的序号代替。运行./prepare.sh会编译产生MECP.x、运行进度文件ProgFile和主脚本runMECP.sh。

---

## 10. sobMECP运行步骤与监控

运行流程为：./prepare.sh -> ./runfirst.sh (计算初始结构) -> ./runMECP.sh (开始搜索)。收敛信息输出到屏幕，细节信息输出到ReportFile，每一步结构记录到traj.xyz。若中断，应重新依次执行上述三个脚本基于geom文件中的最后一步结构继续。

---

## 11. sobMECP的收敛阈值与步数设置

默认收敛阈值在temp/MECP.f的第300行，包括TDE、TDXMax、TDXRMS、TGMax、TGRMS五个标准。搜索步数上限在temp/runMECP.sh第30行设置，默认100步。修改后需再次运行./prepare.sh生效。

---

## 12. sobMECP的extract_energy脚本

extract_energy脚本用于从Gaussian输出文件提取能量，不同理论方法需用不同脚本（extract_energy_SCF、extract_energy_MP2、extract_energy_CIS、extract_energy_TD）。如果两个态用不同理论方法，需分别准备extract_energy和extract_energy2。

---

## 13. CH2卡宾MECP搜索实例

寻找CH2单-三重态MECP，Input_Header_A设为单重态，Input_Header_B设为三重态，使用B3LYP/6-311G**。运行后收敛仅需5步，ab_initio文件显示两态能量分别为-39.1443410840和-39.1443771072 a.u.，结构上H-C-H角度从119.9度变为100.1度。

---

## 14. FeO+阳离子MECP搜索实例

寻找FeO+四-六重态MECP，O用6-311G*，Fe用SDD赝势，Input_Tail需定义基组。初始Fe-O长度0.67埃，收敛后变为1.322埃。若在2.0埃附近存在势能曲线平行的交叉点，MECP搜索算法会失效。

---

## 15. 激发态单重态与三重态的交叉搜索

搜索S1-T1等激发态交叉时，计算第一单重态激发态用TDDFT，算三重态用UKS。需将extract_energy (用于TDDFT) 和extract_energy2 (用于UKS) 拷到sobMECP目录。TDDFT计算时S1电子态的不可约表示可能改变，而UKS跟踪的是初始结构下的T1态。

---

## 16. MECP处的自由能计算问题

计算MECP自由能应计算两个态能量简并的3N-7维空间里的3N-7个振动模式频率，但无简单工具。使用Gaussian的freq=projected关键词计算自由能不具备普适性，因为垂直于downhill路径的子空间不等同于能量简并的3N-7维空间，结果依赖于自旋多重度选取且不唯一。

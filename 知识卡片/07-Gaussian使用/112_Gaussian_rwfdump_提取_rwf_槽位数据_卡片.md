---
id: 112
title: 提取Gaussian的rwf文件信息的工具rwfdump简介
domain: Gaussian使用
topic: Gaussian_rwfdump_提取_rwf_槽位数据
cards: 9
---

## 1. Gaussian程序的Link结构与rwf文件机制
Gaussian程序由独立的Link子程序按指定顺序和选项调用组成，Link间传递临时数据主要依靠读写文件即rwf文件。rwf文件在任务开始时初始化并随计算不断填充信息，若未通过%rwf=xxx指定位置，任务正常结束后会被自动删除。由于rwf文件储存信息极为丰富且体积庞大不便保存，其中最重要的信息会在checkpoint文件（chk文件）中留有副本，且chk文件体积较小可转换为文本格式用于分析或任务重启。

---

## 2. rwf文件槽位编号与存储属性
rwf文件包含多个存放不同类别信息的“子文件”即槽位，每个槽位有对应编号，具体内容可参考链接中的RWF Numbers部分。槽位编号前的标识代表信息的存储属性：P代表该信息同时也储存在chk文件中；T代表该信息在任务执行过程中储存在chk文件中以备重启，但任务结束后会从chk文件中删除；空格代表该信息只存在于rwf文件中而在chk文件中没有副本。

---

## 3. rwfdump工具的功能与本质
rwfdump是Gaussian自带的一个位于安装目录下的小程序，专门用来将rwf文件中指定槽位中的信息提取出来并转化为可读文件。该工具未在Gaussian用户手册或程序员手册中提及，本质上是通过给Gaussian代码中负责读写rwf文件指定槽位信息的FileIO子程序加个壳，使之成为能够独立运行的程序。

---

## 4. rwfdump的命令行调用语法
rwfdump通过命令行调用，语法是：rwfdump a.rwf a.txt iiix。其中a.rwf是被提取信息的rwf文件；a.txt是提取出的信息储存的地方，如果输出文件名只写为一个横杠-，则直接输出到屏幕上；iii是rwf信息的槽位编号；x控制输出数据的数据类型，I代表十进制整数，H代表十六进制数，R代表浮点数，A代表ASCII文本。

---

## 5. 提取非限制性计算alpha-beta重叠积分示例
从官方表格中查到540号槽位储存的是Molecular alpha-beta overlap (U), real，即非限制性计算中alpha轨道和beta轨道间的重叠积分，提取命令如rwfdump c:\idol-master\a.rwf d:\sob\BLOOD-C.txt 540R。该示例基于uhf/sto-3g下计算的三重态乙酸，打开输出文件会看到包含Number、Base、End、Length等字段的槽位汇总信息，随后是指定长度的数据。

---

## 6. rwf文件槽位汇总信息含义
rwfdump输出文件开头的汇总信息列出了各个槽位的Number、Base（起始偏移量）、End（终止偏移量）、Length（长度，即End与Base之差）、Wr Pntr（写指针位置）、Rd Pntr（读指针位置）。这些数值的单位都是word，即8字节（一个双精度浮点数的大小），例如540号槽位长度为576，对应体系中总共24个alpha轨道与24个beta轨道间的重叠积分。

---

## 7. rwfdump输出数据的格式解读
rwfdump提取的数据以D格式表示法（如0.99999749D+00）输出，这是Fortran双精度浮点数表示法，D代表10的多少次方。在自旋极化体系的非限制性计算中，alpha与alpha轨道、beta与beta轨道间正交归一，但alpha与beta轨道间没有正交归一限制，因此数据接近0表明相应轨道重叠积分很小（接近正交），接近1则意味着轨道几乎配对、相互重合。

---

## 8. rwfdump从chk文件提取数据
rwfdump也能用来从chk文件中直接提取指定槽位的数据，条件是该槽位信息在chk文件中有副本（即RWF Numbers表中以P开头的项）。例如，501号槽位储存的是Gen数组且以P开头，因此可以通过命令rwfdump c:\ltwd\a.chk h:\K-ON\touhou.txt 501R直接从chk文件提取包含各种标量数据的Gen数组。

---

## 9. Gen数组中的SCF能量位置
从chk文件提取的Gen数组包含各种标量数据，查阅Gaussian程序员手册可知Gen数组第32个数是SCF能量。例如提取数据显示第32个数为-0.22469385D+03，这与Gaussian输出文件中显示的E(UHF) = -224.693847643完全对应。

---
id: 758
title: Multiwfn结合ORCA的TDDFT计算做空穴-电子等分析的方法
url: http://sobereva.com/758
domain: 波函数与电子结构分析
topic: Multiwfn结合ORCA进行空穴电子分析
cards: 1
---

# Multiwfn结合ORCA进行空穴电子分析 — 知识卡片

## 1. 软件版本与前提要求

读者请务必使用2025-Dec-7及以后更新的Multiwfn版本，务必使用ORCA 6.1.1及以后的版本。读者需已了解空穴-电子分析的原理、用法以及ORCA的各种常识和做TDDFT的方法。

## TDA-DFT计算输出组态系数的设置
在ORCA的%tddft模块中设置tprint 1E-8非常重要，代表对电子激发贡献大于1E-8的组态都输出系数。这相当于Gaussian的IOp(9/40=4)，若设得更小输出文件尺寸会增大、Multiwfn分析耗时增加。

## ORCA生成Molden输入文件
运行orca_2mkl TDA -molden命令，会基于TDA.gbw转换出TDA.molden.input文件，其中记录了参考态轨道波函数，类似于Gaussian的fch文件。

## TDA-DFT下Multiwfn进行空穴-电子分析
启动Multiwfn载入TDA.molden.input，依次选择主功能18（电子激发分析）和子功能1（空穴-电子分析），输入ORCA输出文件路径（默认同路径同名out文件）和激发态序号，即可加载组态系数进行后续分析。

## TDDFT情况下的限制说明
截至ORCA 6.1.1版本，ORCA对于参考态为开壳层的情况无法在json文件中以正确格式输出组态系数，因此利用json文件进行空穴-电子分析的做法目前只适用于参考态为闭壳层的情况。

## TDDFT生成包含组态系数的JSON文件
创建文本文件TDDFT.json.conf并写入{"CIS": true, "CISNRoots": true}，然后运行orca_2json TDDFT.gbw，这将在当前目录下产生包含所有激发组态系数的TDDFT.json文件。

## TDDFT下Multiwfn自动读取JSON组态系数
在Multiwfn中载入TDDFT.molden.input并进行空穴-电子分析时，若发现同目录下存在同名json文件，Multiwfn会自动从中载入组态系数。默认只载入绝对值大于1E-4的组态系数以节约时间，该阈值可通过settings.ini中的ORCAloadcoeff修改。

## ORCA计算的主要轨道跃迁贡献查看
启动Multiwfn后直接载入ORCA的TDDFT输出文件TDDFT.out，进入主功能18的子功能15，即可查看所有激发态中的主要轨道跃迁贡献，其组态系数也是从json文件中读取的。

## 自动调用orca_2mkl转换文件
如果把Multiwfn的settings.ini里的orca_2mklpath设为了orca_2mkl的实际路径，则可以直接载入gbw文件。Multiwfn会自动将之转换为.molden.input文件并载入，然后再删掉molden.input。

---
id: 758
title: Multiwfn结合ORCA的TDDFT计算做空穴-电子等分析的方法
domain: 波函数与电子结构分析
topic: Multiwfn结合ORCA进行空穴电子分析
cards: 5
---

## 1. TDA-DFT空穴-电子分析的数据准备流程
ORCA进行TDA-DFT计算时必须在输入文件中设置`tprint 1E-8`以输出贡献大于1E-8的组态系数。计算完成后保留输出文件（如TDA.out）和波函数文件（.gbw），并运行`orca_2mkl TDA -molden`命令将.gbw文件转换为记录参考态轨道波函数的.molden.input文件。
- Multiwfn载入.molden.input文件后，在电子激发分析功能中会自动读取同路径下的.out文件以获取组态系数。

---

## 2. ORCA输出TDDFT组态系数的JSON配置方法
ORCA在TDDFT计算下无法直接分别输出激发和去激发组态系数，需通过生成JSON文件供Multiwfn读取。需创建文该资料件（如TDDFT.json.conf）写入`{"CIS": true, "CISNRoots": true}`，然后运行`orca_2json TDDFT.gbw`命令生成包含所有组态系数的TDDFT.json文件。
- 此方法目前仅适用于参考态为闭壳层的情况，开壳层情况因ORCA格式输出Bug暂不支持。

---

## 3. TDDFT空穴-电子分析的数据读取操作
使用Multiwfn进行ORCA的TDDFT空穴-电子分析时，需载入.molden.input文件并进入电子激发分析功能。Multiwfn会自动检测并载入同目录下的.json文件（如TDDFT.json）读取组态系数，默认只读取绝对值大于1E-4的系数，该阈值可通过settings.ini中的ORCAloadcoeff修改。
- ORCA的TDDFT计算需要`%tddft`块中设置`tda false`。

---

## 4. 简化molden文件转换的设置技巧
若在Multiwfn的settings.ini文件中将orca_2mklpath设置为orca_2mkl程序的实际路径，则可直接载入ORCA生成的.gbw文件。Multiwfn会自动调用orca_2mkl将.gbw转换为.molden.input文件并载入，分析结束后自动删除转换生成的临时文件。

---

## 5. 软件版本与兼容性要求
进行所述分析需使用2025-Dec-7及以后版本的Multiwfn，以及6.1.1及以后版本的ORCA。可参考《Multiwfn支持的电子激发分析方法一览》、《使用Multiwfn做空穴-电子分析全面考察电子激发特征》及《量子化学程序ORCA的安装方法》。

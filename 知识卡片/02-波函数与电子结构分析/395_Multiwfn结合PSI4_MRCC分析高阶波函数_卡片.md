---
id: 395
title: 在Multiwfn中分析比CCSD更高级别波函数的方法
url: http://sobereva.com/395
domain: 波函数与电子结构分析
topic: Multiwfn结合PSI4_MRCC分析高阶波函数
cards: 8
---

# Multiwfn结合PSI4_MRCC分析高阶波函数 — 知识卡片

## 1. PSI4安装与环境变量配置

Linux下下载PSI4安装包（如psi4conda-1.2.1-py36-Linux-x86_6.sh）并运行安装，需在用户目录下的.bashrc里添加环境变量。添加的环境变量示例如下：
 export PATH=/sob/psi4/bin:$PATH
  export PSI_SCRATCH=/sob/psi4scr

---

## 2. PSI4输出CCSD(T)密度矩阵的输入文件

在PSI4中通过gradient函数和FCHKWriter生成CCSD(T)级别的.fchk文件，PSI4默认不冻核。输入文件示例如下：
 molecule HF {
  H 0.0 0.0 -0.831975
  F 0.0 0.0 0.092442
 }

  set basis cc-pVTZ
  grad, wfn = gradient('CCSD(T)', return_wfn=True)
  fchk_writer = psi4.FCHKWriter(wfn)
  fchk_writer.write('HF_CCSDpT.fchk')
注：若PSI4版本>=1.4，最后两行应替换为fchk(wfn,'HF_CCSDpT.fchk')。

---

## 3. Multiwfn分析PSI4产生的CCSD(T)波函数的步骤

PSI4输出的.fchk文件中轨道是HF参考态的，密度矩阵是CCSD(T)的，需通过Multiwfn主功能200的子功能16载入密度矩阵生成自然轨道。操作步骤为：(1)将.fchk载入Multiwfn；(2)进入主功能200的子功能16；(3)输入CCSD载入Total CCSD Density字段矩阵；(4)输入y导出并自动载入包含CCSD(T)自然轨道的new.mwfn文件，后续分析即为CCSD(T)级别。

---

## 4. 开壳层体系在Multiwfn中的自然轨道类型选择

若.fchk文件对应开壳层体系，Multiwfn在生成自然轨道时会询问产生哪种类型的自然轨道。可选择的类型包括：总密度对应的自然轨道、自旋密度对应的自然轨道、alpha/beta各自的自然轨道。

---

## 5. MRCC运行与输入文件基础

MRCC下载预编译包解压并将目录添加到PATH环境变量后使用，输入文件名必须为MINP，运行命令为dmrcc |tee out.txt。生成密度矩阵需在输入文件中设置dens=1，例如CCSDT/cc-pVTZ计算氟化氢的输入文件如下：
 basis=cc-pvtz
  calc=CCSDT
  mem=2500MB
  dens=1

  geom=xyz
  2

  H 0.0 0.0 -0.831975
  F 0.0 0.0 0.092442

---

## 6. MRCC输出的密度矩阵文件格式

MRCC计算后输出MOLDEN文件（记录HF轨道）和CCDENSITIES文件（记录密度矩阵）。CCDENSITIES文件第一部分记录二阶约化密度矩阵(2RDM)有四个标号，之后记录一阶约化密度矩阵(1RDM)有两个标号，矩阵以MO为基，标号从第一个考虑电子相关的MO开始计。

---

## 7. MRCC密度矩阵在Multiwfn中的处理流程

启动Multiwfn输入MRCC产生的MOLDEN文件路径，进入主功能1000的子功能97，输入CCDENSITIES文件路径及被冻结的轨道数。MRCC默认冻核，冻结轨道数根据输出文件中的Number of core electrons除以2（闭壳层）确定，之后Multiwfn计算自然轨道并输出到.mwfn文件，载入该文件即可进行对应级别的波函数分析。

---

## 8. MRCC进行FCI计算的输入文件设置

MRCC进行FCI计算需将calc设为fci，并通过core=0设置不做冻核近似。FCI/aug-cc-pVDZ下计算拉长LiH的输入文件示例如下：
 basis=aug-cc-pvdz
  calc=fci
  mem=2500MB
  dens=1
  core=0

  geom=xyz
  2

  H 0.0 0.0 0.0
  Li 0.0 0.0 3.0

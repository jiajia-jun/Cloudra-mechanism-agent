---
key: t35859
title: ��cp2k�����pdb�켣�Ӳл������Լ���pdb�켣ת��Ϊtrr�Ľű�
url: http://bbs.keinsci.com/thread-35859-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2023
cards: 8
---

# ��cp2k�����pdb�켣�Ӳл������Լ���pdb�켣ת��Ϊtrr�Ľű� — 知识卡片

## 1. CP2K输出PDB轨迹的残基信息缺失

CP2K输出的PDB轨迹文件默认不包含残基名（Residue name）、残基序号以及链（Chain）信息，这导致后续处理（如VMD可视化或特定格式转换）不便。
- CP2K输出的轨迹文件缺少残基相关信息，需通过脚本补充。
- 为解决此问题，可利用包含完整信息的参考结构文件将残基信息映射到轨迹文件中。

---

## 2. 参考结构文件REF.pdb的准备要求

参考结构文件 REF.pdb 需包含完整的残基名、残基序号及链信息，且其原子顺序必须与CP2K输出的轨迹文件中的原子顺序保持一致。
- 用户需准备一个包含完整残基信息（位于PDB文件第18-26列）的PDB文件作为参考。
- 原子顺序的一致性是成功映射残基信息的关键前提。

---

## 3. 使用setres.sh脚本补充残基信息

运行 setres.sh 脚本，以包含残基信息的 REF.pdb 和缺失信息的 CP2K轨迹文件 sys-pos-1.pdb 为输入，可生成带有残基名的轨迹文件。
- 执行命令：`sh setres.sh REF.pdb sys-pos-1.pdb > sys-with-resname.pdb`
- 该脚本将参考文件中的残基信息复制并添加到轨迹文件的对应原子上。
- XYZ格式的轨迹文件不支持此残基信息的添加操作。

---

## 4. VMD读取CP2K PDB轨迹的方法

对于包含残基信息的CP2K PDB轨迹文件，可直接使用VMD读取和可视化，无需进行格式转换。
- VMD能够识别并显示带有resname的PDB轨迹文件。
- 此方式适用于不需要转换为TRR格式的简单可视化需求。

---

## 5. 使用Gromacs工具处理PDB轨迹的思路

若需使用Gromacs工具进行分析，需先将PDB轨迹转换为TRR格式，通常以包含残基信息的PDB文件作为拓扑结构（top），TRR文件作为轨迹。
- 推荐使用Gromacs自带工具或Python库MDAnalysis进行格式转换。
- 转换后可使用命令如 `gmx_mpi rdf -f sys-pos-1.trr -s REF.pdb -n index.idx` 进行后续分析。

---

## 6. 使用pdb2trr脚本转换格式

运行 pdb2trr 脚本可以将补充了残基信息的PDB轨迹文件转换为Gromacs兼容的TRR格式文件。
- 执行命令：`sh pdb2trr sys-pos-1.pdb`
- 执行后将生成输出文件 sys-pos-1.trr。
- 使用此脚本需要预先安装VMD。

---

## 7. MDAnalysis读取转换后的TRR文件

MDAnalysis 库可以直接读取转换后的TRR文件和参考PDB文件进行分子动力学分析。
- 使用命令：`u=mda.Universe("REF.pdb","sys-pos-1.trr")`
- REF.pdb 作为拓扑结构文件，sys-pos-1.trr 作为轨迹文件。

---

## 8. MDAnalysis直接读取CP2K原始PDB轨迹的预处理

若要直接使用MDAnalysis读取CP2K输出的原始PDB轨迹文件（如 cp2k_traj.pdb），需通过awk命令将REMARK行转换为标准的MODEL行，并保留必要的原子及晶胞信息。
- 执行命令：`awk '{if ($0 ~ /^CRYST1/ || $0 ~/^END/ || $0 ~/^ATOM/) print $0; else if ($0 ~ /REMARK/) print "MODEL " sub(",","",$3)}' cp2k_traj.pdb > mda_traj.pdb`
- 该处理步骤会将轨迹步数信息标准化为MDAnalysis可识别的MODEL关键字。
- 生成的 mda_traj.pdb 文件即可被MDAnalysis正确读取。

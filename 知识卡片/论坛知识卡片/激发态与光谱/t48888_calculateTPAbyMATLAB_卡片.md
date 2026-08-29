---
key: t48888
title: calculateTPAbyMATLAB�����ڼ���̬ż���ؼ���˫�������ս����matlab�ű�
url: http://bbs.keinsci.com/thread-48888-1-1.html
domain: 激发态与光谱
source: keinsci
year: 2024
cards: 4
---

# calculateTPAbyMATLAB�����ڼ���̬ż���ؼ���˫�������ս����matlab�ű� — 知识卡片

## 1. MATLAB计算TPA工作流程

使用Gaussian进行激发态计算并结合Multiwfn获取偶极矩信息，随后通过MATLAB处理数据以计算双光子吸收（TPA）截面，该流程主要包含三个步骤。首先利用Gaussian进行激发态计算生成格式检查文件，其次使用Multiwfn从格式检查文件中提取偶极矩信息，最后使用MATLAB读取Multiwfn生成的文资料件提取偶极矩信息并计算TPA。

---

## 2. Gaussian激发态计算输入文件设置

进行激发态计算时需准备Gaussian输入文件（.com格式），计算route section应设置为`#P TD(nstates=20) IOp(9/40=4) [泛函和基组]`。关键词`TD(nstates=20)`指定计算20个激发态，`IOp(9/40=4)`确保将详细的激发态信息写入输出文件。泛函和基组可根据需求自定义，文件准备完成后需提交Gaussian计算并生成.fchk格式文件。

---

## 3. Multiwfn提取偶极矩数据操作步骤

Gaussian计算完成后使用Multiwfn加载.fchk文件以提取偶极矩数据，操作步骤包括：启动Multiwfn.exe并打开.fchk文件；选择主功能18（激发态分析）；选择子功能5（跃迁偶极矩分析）；输入空格键将信息输出到日志文件；输入2将偶极矩信息写入到详细.txt文件中。执行完上述步骤后，Multiwfn会在当前目录下生成包含偶极矩信息的.txt文件。

---

## 4. MATLAB脚本处理数据要求

Multiwfn生成.txt文件后，需使用提供的MATLAB脚本读取当前文件夹下的所有.txt文件以提取偶极矩信息并计算双光子吸收（TPA）数值。确保.txt文件与MATLAB脚本`calculateTPAinbatchpar.m`位于同一文件夹内，脚本运行后将自动读取每个文件并完成计算。

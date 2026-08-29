---
key: t21005
title: ��ȡorca�����ļ���SOC���ݵ�python�ű�
url: http://bbs.keinsci.com/thread-21005-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 4
---

# ��ȡorca�����ļ���SOC���ݵ�python�ű� — 知识卡片

## 1. ORCA计算重金属UV-Vis光谱

ORCA软件可用于含重金属体系的TDDFT计算以获取UV-Vis吸收光谱，此类计算需考虑激发态与基态间的自旋轨道耦合（SOC）效应。
- ORCA计算设置包含x、y、z三个方向的SOC矩阵元计算。

---

## 2. SOC矩阵元计算脚本

Python脚本 `orca-soc2.py` 可用于计算单重态激发态与基态、三重态激发态与三重态基态之间的SOC，并获取总的SOC值。
- 该脚本解决了传统使用Excel手动复制数据和计算繁琐的问题，能够自动处理计算文件中的SOC相关数据。

---

## 3. 脚本使用方法

将Python脚本放置在目标文件夹中运行，脚本会自动读取当前目录下所有后缀为 `.out` 的文件。
- 脚本运行后生成两个文件，第一个文件包含计算得到的SOC值，第二个文件包含对应的激发态与基态编号。

---

## 4. 脚本输出内容

脚本生成的第二个文件直接提取了ORCA输出文件中的原始数据部分，即 `CALCULATED SOCME BETWEEN TRIPLETS AND SINGLETS`。
- 使用者无需手动编写或修改数据提取代码。

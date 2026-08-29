---
key: t15455
title: Multiwfn��SOS�������ѿ��ԶԶ�̬��������beta(w1,w2)��Ƶ������άɨ��
url: http://bbs.keinsci.com/thread-15455-1-1.html
domain: 波函数与电子结构分析
source: keinsci
year: 2019
cards: 8
---

# Multiwfn��SOS�������ѿ��ԶԶ�̬��������beta(w1,w2)��Ƶ������άɨ�� — 知识卡片

## 1. Multiwfn SOS模型与beta频谱扫描

Multiwfn程序支持利用态求和(SOS)模型计算超极化率，并可对beta(-(w1+w2);w1,w2)进行双频率维度扫描。该功能可用于重现《ACS Appl. Nano Mater. 2019, 2, 1648−1654》文献中的螺旋石墨烯纳米带相关计算图表。
- 参考:http://原作者.com/232

---

## 2. beta频谱扫描图的原点含义

在beta(-(w1+w2);w1,w2)的二维频谱扫描图中，X=0与Y=0的位置对应输入光场频率w1与w2为0的情况。当w1与w2为0时，计算结果代表静态极化率。
- 参考:ACS Appl. Nano Mater. 2019, 2, 1648−1654

---

## 3. beta频谱扫描的非原点区域特征

在频谱扫描图中，若w1与w2不为0，且w2相对于w1取特定值时会出现共振峰。若w1与w2符号相同，对应于和频产生过程；若w1与w2符号相反，则对应于差频产生过程。
- 参考:ACS Appl. Nano Mater. 2019, 2, 1648−1654

---

## 4. 特定非线性光学效应在频谱图中的位置

当w1=w2为某非零频率时出现的共振峰，对应于该频率下的SHG（二次谐波产生）效应。当w1=-w2为某非零频率时出现的共振峰，对应于optical rectification（光学整流）效应。当固定w2并扫描w1出现的共振峰，对应于electro-optical Pockels效应。
- 参考:ACS Appl. Nano Mater. 2019, 2, 1648−1654

---

## 5. Multiwfn SOS模型功能入口

在Multiwfn程序中，进入SOS计算模块后选择功能“19 Scanning w1 and w2 of beta(-(w1+w2);w1,w2)”即可执行双频率扫描。
- 参考:Multiwfn手册

---

## 6. 频率扫描参数设置与输出

在扫描功能中，需分别设置w1和w2的起始值、终止值以及扫描点数。参数设置完成后，程序会在当前目录下生成beta_w.txt和beta_w_comp.txt文件，并实时在屏幕上显示进度。
- 参数建议:w1和w2可取100个点

---

## 7. 频谱扫描结果文件内容

beta_w.txt和beta_w_comp.txt文件记录了beta总量及其各分量随w1和w2变化的详细数据。这些数据可用于后续绘图。
- 输出文件:beta_w.txt, beta_w_comp.txt

---

## 8. beta频谱扫描图的绘制方法

利用Sigmaplot或Origin等绘图软件，将beta_w.txt中的w1设为X轴，w2设为Y轴，将对应的beta值设为Z轴，即可绘制出beta频谱扫描图。
- 工具:Sigmaplot, Origin

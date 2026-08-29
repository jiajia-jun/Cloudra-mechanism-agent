---
key: t31476
title: ����python���ɵ�����-�����ģ�͸���ɨ���gaussian�����ļ�[����Ū��]
url: http://bbs.keinsci.com/thread-31476-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2022
cards: 7
---

# ����python���ɵ�����-�����ģ�͸���ɨ���gaussian�����ļ�[����Ū��] — 知识卡片

## 1. 计算背景与方法选择

该研究基于大分子模型研究转环酶催化底物反应的机理。反应体系包含金属原子及非碳原子，部分非碳原子在优化时需要进行固定以保持值构架。几何优化使用的计算方法和基组为 `B3LYP/6-31G(d,p)`，优化完初始结构后，需要根据反应路径寻找中间体和过渡态。

---

## 2. 坐标扫描限制与替代方案

Gaussian 自带的 `scan` 功能无法实现两个相对独立分子或分子片段间的扫描。在反应物片段间距拉长的过程中，需要提供一种简易的方法。通过编写 Python 程序，可以基于两个初始结构的坐标线性插值生成扫描轨迹，从而绕过 Gaussian 扫描功能的限制。

---

## 3. 脚本依赖库与输入参数

该脚本使用 Python 的标准库及第三方库处理数据，主要依赖 `numpy`、`pandas` 和 `math`。核心输入参数包括：两个后缀为 xyz 的轨迹文件名 (`fn1`, `fn2`)、两个移动原子的索引 (`atomidx1`, `atomidx2`，注意索引从1开始)、步长 (`stepsize`)、步数 (`step`)，以及 Gaussian 计算所需的电荷 (`charge`)、自旋多重度 (`spin`)、核数 (`nproc`)、内存 (`mem`)、方法 (`method`) 和基组 (`basis`) 等。

---

## 4. 线性插值生成轨迹原理

脚本首先读取两个 xyz 文件中的原子坐标并转换为 DataFrame，计算两个指定原子之间的向量 `vec`。通过循环，将第二个结构的坐标沿着该向量方向按照设定的步长 `stepsize` 进行线性平移，生成一系列中间构型。利用 `numpy.append` 和 `pandas` 处理，将所有步数的坐标数据合并，并保留原子类型信息。

---

## 5. 轨迹文件 (traj.xyz) 输出格式

脚本生成名为 `traj.xyz` 的轨迹文件，包含所有扫描步骤的构型。每一步的帧包含原子的总数、当前步长的累计距离，以及固定部分（来自 `fn1`）和移动部分（插值生成的 `fn2` 变体）的原子坐标。坐标输出保留 8 位小数。

---

## 6. Gaussian 输入文件 (traj.gjf) 生成逻辑

脚本生成名为 `traj.gjf` 的 Gaussian 输入文件，利用 `--link1--` 机制将所有步骤串联在一个文件中。每个计算任务的 Checkpoint 文件名按步骤索引自动命名为 `traj_0.chk`, `traj_1.chk` 等。文件头包含 `%nproc`、`%mem` 和计算方法路径（如 `#p b3lyp/6-31g(d,p)`），标题栏显示 `traj_X Structure`，电荷与自旋多重度根据输入参数设定。

---

## 7. 脚本代码块

```python
import numpy as np
import pandas as pd
import math

# 初始设置参数
fn1="1.xyz"
fn2="2.xyz"
atomidx1=163
atomidx2=1
stepsize=0.05
step=50
charge=0
spin=1
nproc=32
mem="12GB"
method="b3lyp"
basis="6-31g(d,p)"
#fixatoms="1,2,16,17,33,34,52,71,78,86,97,111,113,129,130,156,145"
other=""

#------------------------------------------------------------------------------#
with open(fn1) as f1:
    m1=f1.readlines()
    xyz1=list(filter(None,[ l.split() for l in m1[2:] if not l.startswith('\n') ]))
with open(fn2) as f2:
    m2=f2.readlines()
    xyz2=list(filter(None,[ l.split() for l in m2[2:] if not l.startswith('\n') ]))

df1=pd.DataFrame(xyz1,columns=["atom","x","y","z"])
df2=pd.DataFrame(xyz2,columns=["atom","x","y","z"])

data1=df1[["x","y","z"]].values.astype(np.float64)
data2=df2[["x","y","z"]].values.astype(np.float64)

vec=data1[atomidx1-1]-data2[atomidx2-1]
proc_data=data2

for i in range(1,step+1):
    proc_data=np.append(proc_data,data2+vec*stepsize*i/math.sqrt(np.square(vec).sum()),axis=0) 

mm=pd.DataFrame(proc_data,columns=["x","y","z"])
mm.insert(0,"atom",np.tile(df2["atom"].values,step+1))

# -------------------------------------------------------------------------------- #
# 输出轨迹
fp=open("traj.xyz","w")
for m in range(step+1):
    print("{}".format(data1.shape[0]+data2.shape[0]),file=fp)
    print("{}".format(m*stepsize),file=fp)
    for i in range(data1.shape[0]):
        print ("{} {} {} {}".format(df1.iloc[i]["atom"],df1.iloc[i]["x"],df1.iloc[i]["y"],df1.iloc[i]["z"]),file=fp)
    for j in range(data2.shape[0]):
        print ("{} {:.8f} {:.8f} {:.8f}".format(mm.iloc[(m*(data2.shape[0])+j)]["atom"],mm.iloc[(m*(data2.shape[0])+j)]["x"],mm.iloc[(m*(data2.shape[0])+j)]["y"],mm.iloc[(m*(data2.shape[0])+j)]["z"]),file=fp)
fp.close()

#-------------------------------------------------------------------------------#
# 生成gaussian文件
fg=open("traj.gjf","w")
for m in range(step+1):
    chkname="%chk="+"traj_"+str(m)+".chk"
    print("{}".format(chkname),file=fg)
    print("{}".format("%nproc="+str(nproc)),file=fg)
    print("{}".format("%mem="+str(mem)),file=fg)
    print("{}".format("#p "+method+"/"+basis+" "+other),file=fg)
    print("{}".format(" "),file=fg)
    print("{}".format("traj_"+str(m)+" Structure"),file=fg)
    print("{}".format(" "),file=fg)
    print("{}".format(str(charge)+" "+str(spin)),file=fg)
    for i in range(data1.shape[0]):
        print ("{} {} {} {}".format(df1.iloc[i]["atom"],df1.iloc[i]["x"],df1.iloc[i]["y"],df1.iloc[i]["z"]),file=fg)
    for j in range(data2.shape[0]):
        print ("{} {:.8f} {:.8f} {:.8f}".format(mm.iloc[(m*(data2.shape[0])+j)]["atom"],mm.iloc[(m*(data2.shape[0])+j)]["x"],mm.iloc[(m*(data2.shape[0])+j)]["y"],mm.iloc[(m*(data2.shape[0])+j)]["z"]),file=fg)
    print("{}".format(" "),file=fg)
    #print("{}".format("{}".format("notatoms="+fixatoms)),file=fg)
    print("{}".format(" "),file=fg)
    if m!=step:
        print("{}".format("--link1--"),file=fg)
    else:
        continue
fg.close()
```

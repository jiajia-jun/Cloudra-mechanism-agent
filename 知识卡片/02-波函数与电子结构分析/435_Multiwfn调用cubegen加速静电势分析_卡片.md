---
id: 435
title: Multiwfn现已可以调用cubegen使静电势分析耗时有飞跃式的下降！
domain: 波函数与电子结构分析
topic: Multiwfn调用cubegen加速静电势分析
cards: 11
---

## 1. Multiwfn调用cubegen计算静电势的适用性与速度优势
2020-Jul-4及以后版本的Multiwfn的自身静电势代码计算速度有极大提升，直接使用内部代码计算拟合静电势电荷、分子表面静电势定量分析比调用cubegen更快；只有在使用主功能5计算静电势格点数据、主功能17做静电势盆分析等需要计算整个空间均匀分布静电势格点数据的情况时，调用cubegen的耗时才会更低。

---

## 2. ORCA用户使用cubegen的替代方案
如果波函数由ORCA计算且没有Gaussian，对于适合调用cubegen的情况，可采用《对ORCA用户大幅节约Multiwfn做分子表面静电势分析耗时的方法》中的做法来节约耗时。

---

## 3. cubegenpath参数设置与自动调用机制
在Multiwfn 3.6(dev)及以上版本的settings.ini文件中，将cubegen参数设为本机cubegen的实际路径（Windows下如"D:\study\G16W\cubegen.exe"，Linux下如"/sob/g16/cubegen"），且输入文件为fch或fchk格式时，Multiwfn在做静电势分析时会自动调用cubegen代替内部代码。

---

## 4. 自动调用cubegen的功能列表
Multiwfn在执行以下涉及静电势的功能时会自动调用cubegen：(1)绘制静电势曲线（主功能3）；(2)绘制静电势平面图（主功能4）；(3)各种需要计算静电势格点数据的功能（如主功能5、主功能17、主功能200的子功能14）；(4)计算拟合静电势电荷（主功能7的MK、CHELPG和RESP）；(5)计算TrEsp原子跃迁电荷（手册4.A.9）；(6)定量分子表面分析（主功能12）。

---

## 5. cubegen的版本兼容性与并行策略
经测试G09和G16的cubegen均可被直接调用，计算结果与Multiwfn内部代码完全相同；G09的cubegen因并行模式存在bug，Multiwfn调用时采用串行方式，而G16的cubegen则采用并行方式（核数由settings.ini里的nthreads决定），Multiwfn通过判断cubegenpath路径中是否包含g16或G16字样来区分版本。

---

## 6. 非Gaussian用户使用cubegen的方法
非Gaussian用户若想利用cubegen节约静电势计算时间，需先利用Multiwfn将.molden文件、GAMESS-US或firefly输出文件（.gms）等含有基函数信息的文件转换为.fch格式，再以此fch文件作为输入。

---

## 7. cubegen计算不同函数的速度差异
cubegen支持的各种实空间函数中，仅静电势计算速度快于Multiwfn，电子密度、电子密度拉普拉斯函数、分子轨道波函数等其它函数的计算速度远慢于Multiwfn且无法并行，故Multiwfn计算这些函数时不利用cubegen。

---

## 8. 大体系计算崩溃的内存解决方法
若Multiwfn借用cubegen计算小体系正常但计算大体系时崩溃，可能是cubegen可用内存不足，需通过设置GAUSS_MEMDEF环境变量来增加可用内存量。

---

## 9. cubegendenstype参数与密度矩阵选择
cubegen计算静电势基于.fch文件里的密度矩阵，默认使用SCF密度矩阵；对于后HF或TDDFT等计算，需修改settings.ini里的cubegendenstype参数为对应的密度矩阵标识（如MP2），以计算相应级别的静电势。

---

## 10. 修改波函数后调用cubegen的处理步骤
若在Multiwfn中修改了波函数（如修改轨道占据数），.fch文件内容不会自动更新，直接调用cubegen算出的静电势仍对应原始波函数；若需基于修改后的波函数利用cubegen计算，应在修改波函数后使用主功能100的子功能2将当前波函数导出为新的.fch文件作为输入。

---

## 11. Multiwfn调用cubegen相对于直接调用的优势
Multiwfn调用cubegen计算静电势.cub文件优于直接命令行调用cubegen，原因包括：(1)Multiwfn全交互式操作，提示清晰；(2)Multiwfn设定格点选项丰富灵活，而cubegen死板笨拙；(3)Multiwfn算完后可直接绘制等值面或计算变形密度的静电势。

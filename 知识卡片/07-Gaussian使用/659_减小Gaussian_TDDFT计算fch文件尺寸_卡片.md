---
id: 659
title: 巨幅减小Gaussian的TDDFT计算产生的fch文件的尺寸的方法
url: http://sobereva.com/659
domain: Gaussian使用
topic: 减小Gaussian_TDDFT计算fch文件尺寸
cards: 7
---

# 减小Gaussian_TDDFT计算fch文件尺寸 — 知识卡片

## 1. Gaussian 16 C.01起TDDFT的fch文件尺寸巨大

Gaussian 16从C.01版开始，对大体系做TDDFT计算得到的chk转换成的fch文件尺寸颇大，尤其是算的激发态数目多的时候。例如用Gaussian 16 C.02对C60富勒烯在6-31G*下做TDDFT计算50个激发态，产生的chk文件是1356 MB，formchk转换出来的fch文件达到1915MB。相比之下，G16 B.01版生成的fch文件仅38MB，差异巨大。

---

## 2. fch文件尺寸巨大的原因

从G16 C.01版开始fch文件里额外保存了Excited state densities和G to E trans densities字段，分别记录激发态密度矩阵和基态到激发态的跃迁密度矩阵，导致文件体积显著增加。这两个信息对绝大多数用户没用，需要时可用Multiwfn计算，详见《使用Multiwfn绘制跃迁密度矩阵和电荷转移矩阵考察电子激发特征》（http://sobereva.com/436）。

---

## 3. 使用fchred程序减小fch文件尺寸

fchred程序用于去除fch中占空间极大的Excited state densities和G to E trans densities字段以减小体积，可在http://sobereva.com/soft/fchred.zip免费下载。对于G16 C.02计算C60富勒烯TDDFT的例子，原fch文件经fchred处理后，尺寸从1915MB减小到了38MB。

---

## 4. fchred程序的使用方法

启动fchred后，输入原fch文件的路径，再输入新产生的fch文件的路径，就会开始转换。fchred也可以通过命令行使用，比如输入fchred Liella.fch，就会直接产生转换完的Liella_new.fch文件到当前目录下。

---

## 5. 使用Multiwfn主功能100子功能2导出fch

如果保留fch文件是为了做空穴-电子分析、IFCT分析、看轨道图像或依赖基态波函数的分析，可以用Multiwfn载入fch文件后选择主功能100的子功能2再选择导出fch文件。处理后的fch文件仅保留有用信息，前述G16 C.02算富勒烯TDDFT的fch文件经处理后尺寸仅有19MB。

---

## 6. 使用Multiwfn导出mwfn格式文件

建议用Multiwfn载入原fch文件，进入主功能100的子功能2，选择导出mwfn格式文件，在导出信息时选择Only export wavefunction。mwfn格式更紧凑，前例产生的mwfn文件尺寸只有不到13MB，用winrar或7zip压缩后只有不到2MB，原fch文件则有1915MB。

---

## 7. fchred相比Multiwfn处理的优势

用fchred减小fch文件的优点是保留其它信息，而Multiwfn处理会导致Hessian矩阵等信息丢失。对于做激发态振动分析得到的fch文件，若用Multiwfn处理，之后将无法用sobtop计算激发态的力场参数，也无法用GaussView观看振动模式。

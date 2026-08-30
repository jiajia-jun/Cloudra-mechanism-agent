---
key: b659
title: 巨幅减小Gaussian的TDDFT计算产生的fch文件的尺寸的方法
url: http://sobereva.com/659
domain: Gaussian使用
source: blog
year: 2023
cards: 5
---

# 巨幅减小Gaussian的TDDFT计算产生的fch文件的尺寸的方法 — 知识卡片

## 1. Gaussian 16 C.01版本TDDFT计算fch文件尺寸剧增的原因

Gaussian 16从C.01版本开始，将TDDFT计算产生的fch文件中额外保存了Excited state densities和G to E trans densities字段，分别记录激发态密度矩阵和基态到激发态的跃迁密度矩阵。这两个字段导致fch文件尺寸显著增大，特别是在计算大量激发态时，例如在C60富勒烯的TDDFT计算中，fch文件大小从B.01版的38MB增加到C.02版的1915MB。这些额外信息对大多数用户并非必需，且可通过Multiwfn程序重新计算。

---

## 2. 使用fchred程序减小fch文件尺寸

fchred程序通过删除fch文件中占用空间极大的Excited state densities和G to E trans densities字段来减小文件体积。程序下载后包含Windows版（带.exe后缀）和Linux版，使用时需输入原fch文件路径和新文件路径。对于前述C60富勒烯TDDFT计算生成的1915MB fch文件，经fchred处理后尺寸可减小至38MB。程序也支持命令行操作，输入`fchred Liella.fch`将直接在当前目录生成转换后的`Liella_new.fch`文件。

---

## 3. 利用Multiwfn功能100子功能2精简fch文件

Multiwfn程序的主功能100子功能2可用于导出fch文件，并过滤掉对空穴-电子分析、IFCT分析、轨道图像绘制及基态波函数分析无用的信息。经过此处理，G16 C.02生成的C60富勒烯TDDFT fch文件尺寸可缩减至19MB，比G16 B.01版本生成的原始fch文件还要小一倍。

---

## 4. Multiwfn导出mwfn格式文件以进一步压缩

Multiwfn支持将fch文件导出为mwfn格式，该格式更为紧凑且能支持与fch同等的分析功能。操作步骤为载入原fch文件，进入主功能100子功能2，选择导出mwfn文件并选定Only export wavefunction选项。对于C60富勒烯的例子，生成的mwfn文件尺寸小于13MB，经winrar或7zip压缩后仅为不到2MB，相比原始1915MB的fch文件大幅节省存储空间。

---

## 5. Multiwfn与fchred处理fch文件的区别

使用fchred程序减小fch文件的优势在于能够保留除Excited state densities和G to E trans densities以外的所有信息，如Hessian矩阵等。若使用Multiwfn精简fch文件，Hessian矩阵等信息会丢失，导致后续无法使用sobtop计算激发态力场参数，也无法用GaussView查看振动模式。因此，若需保留这些额外信息，应选用fchred而非Multiwfn。

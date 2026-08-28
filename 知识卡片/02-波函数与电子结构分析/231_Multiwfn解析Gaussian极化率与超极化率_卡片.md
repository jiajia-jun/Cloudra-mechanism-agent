---
id: 231
title: 使用Multiwfn分析Gaussian的极化率、超极化率的输出
url: http://sobereva.com/231
domain: 波函数与电子结构分析
topic: Multiwfn解析Gaussian极化率与超极化率
cards: 1
---

# Multiwfn解析Gaussian极化率与超极化率 — 知识卡片

## 1. Gaussian中（超）极化率的计算关键词与原理

Gaussian中polar关键词专门用来计算极化率α和第一超极化率β，从Gaussian09 D.01开始支持polar=gamma计算第二超极化率γ。将能量E对均匀外电场F进行Taylor展开，求极化率需对能量做两次导数，求第一超极化率做三次导数。Gaussian通过解析导数、数值导数或解析+数值混合导数来计算这些量，外场频率为0时称为静态（超）极化率，不为0时称为动态（超）极化率。

## HF/DFT/半经验方法的（超）极化率计算
对于HF、DFT、半经验方法，Gaussian支持三阶解析导数，使用polar关键词可直接给出静态和含频的α和β。若写上CPHF=RdFreq并在输入文件末尾空一行写上外场频率w，可计算含频极化率α(-ω;ω)和含频第一超极化率β(-ω;ω,0)。若要计算SHG形式的第一超极化率β(-2ω;ω,ω)，应写polar=DCSHG，此时CPHF=RdFreq可忽略。

## MP2及双杂化泛函等方法的（超）极化率计算
对于MP2、双杂化DFT、TDDFT、CIS等Gaussian只能支持到二阶解析导数的方法，直接写polar只计算α；若想得到β，需写polar=Cubic，Gaussian会自动基于解析二阶导数做有限差分来得到三阶导数。对于这类方法，Gaussian无法给出含频（超）极化率。

## CISD、CCSD等仅支持一阶解析导数方法的（超）极化率计算
对于CISD、QCISD、CCSD、MP3、MP4(SDQ)等Gaussian只支持一阶解析导数的方法，直接写polar关键词会基于解析一阶导数做一次有限差分得到α。若想得到β，需写polar=DoubleNumer（等价于polar=enonly），基于解析一阶导数做两次有限差分得到三阶导数。对于这些方法，Gaussian没法给出含频（超）极化率。

## CCSD(T)等仅支持单点能方法的极化率计算
对于CCSD(T)、QCISD(T)、MP4(SDTQ)、MP5等Gaussian只支持计算单点能的方法，写polar关键词会对能量做两次有限差分并由此得到α。在Gaussian里对于这些方法没有办法直接给出β。

## 使用polar=gamma计算第二超极化率
从G09 D.01开始，对于支持三阶解析导数的方法（如HF、DFT、半经验）可以用polar=gamma来算静态γ和动态的γ(-2ω;ω,ω,0)、γ(-ω;ω,0,0)。该关键词基于解析三阶导数自动做有限差分来得到所需的四阶导数，输入文件末尾应空一行写上外场频率。

## 使用Multiwfn解析Gaussian极化率输出的基本操作
启动Multiwfn后输入Gaussian的polar任务输出文件路径，进入主功能24选1，根据Gaussian计算时使用的方法和关键词选择对应的选项1~7。Gaussian的route section必须写上#P，否则输出文件无法被正确解析。选项1~7对应不同的导数计算情况，只有1、3、5会给出β，只有7会给出γ。

## Multiwfn解析动态（超）极化率的设置
如果在HF/DFT/半经验计算时用了polar CPHF=rdfreq或polar=DCSHG做了含频（超）极化率计算，或用了polar=gamma，默认情况下Multiwfn只解析静态值。若想分析含频值，应先选-1将Toggle loading frequency-dependent result状态切换为Yes。当Gaussian输入文件定义了多个频率时，用户可以选择分析哪个频率下的结果，对于β还可选择β(-ω;ω,0)或β(-2ω;ω,ω)。

## Multiwfn对极化率α输出的解读
Multiwfn输出的极化率张量是对称的3*3矩阵，包含6个独立矩阵元。各向同性平均极化率<α>是对XX、YY、ZZ取平均得到的，极化率体积也一并给出。Multiwfn还输出极化率的各向异性值Δα，定义有三种，其中定义2最常用，数值越大各向异性越强，球对称体系该值为0。

## Multiwfn对第一超极化率β输出的符号修正
Gaussian输出的β元素符号是反的，每个β元素的数值都应乘以-1，Multiwfn已考虑此问题并输出正确的符号。静态β满足Kleinman对称性，三个标号可随意置换，只有10个元素唯一。Beta_X、Beta_Y、Beta_Z衡量β在X、Y、Z方向上的分量，Magnitude of first hyperpolarizability体现β的整体大小。

## Multiwfn输出的β相关实验可比拟量
只有β在偶极矩方向上的投影值（Projection of beta on dipole moment，即β_prj）可通过EFISH实验测量。文献中常见的Beta ||正比于β_prj。Beta ||(z)和Beta _|_(z)分别衡量平行和垂直于Z方向上的β值，当偶极矩方向和Z方向一致时，Beta_Z=β_prj，Beta ||(z)=Beta ||。

## 动态第一超极化率β(-ω;ω,0)的对称性与解析
对于动态β(-ω;ω,0)，只有标号中的i,j可以互换，如xyy=yxy≠yyx，有18个独立元素。当外场频率不是很大时，Kleinman对称性可近似满足。使用polar CPHF=RdFreq计算并配合Multiwfn解析时，通过选择对应频率和β(-ω;ω,0)选项可得到结果，含频外场下β值通常增大。

## 使用polar=DCSHG计算β(-2ω;ω,ω)
若要计算动态β(-2ω;ω,ω)形式，应在Gaussian输入文件中使用polar=DCSHG关键词，此时CPHF=RdFreq可忽略。使用Multiwfn解析时，进入功能后选择分析β(-2ω;ω,ω)情况的数据。如果只写了CPHF=RdFreq而未写DCSHG，则无法在Multiwfn中选择解析β(-2ω;ω,ω)。

## 第二超极化率γ的输出与精度要求
使用polar=gamma可计算静态和动态的γ，高精度计算小体系的γ要求基组必须带非常充足的弥散函数（如d-aug-cc-pVTZ），且计算本身非常昂贵。Multiwfn解析γ时，Magnitude of gamma体现其整体大小，同时给出X/Y/Z分量、Average of gamma（定义1即gamma ||、定义2）以及gamma _|_等常用量。

## Multiwfn解析γ时的坐标系朝向注意事项
在Multiwfn中使用polar=gamma功能解析γ时，屏幕提示给出的gamma信息对应的是输入朝向下的。而在解析alpha和beta时，Multiwfn给出的是标准朝向下的结果（Gaussian默认会将坐标调整到标准朝向）。若想避免Gaussian自动调整到标准朝向，应在输入文件中使用nosymm关键词。

## 提取freq任务中的极化率数据
如果使用DFT或MP2对体系做振动分析（freq）和极化率（polar）计算，没必要分别运行任务，只需运行一次freq即可。用Multiwfn载入freq任务的输出文件，在（超）极化率分析界面选择2 "Polar" + analytic 2-order deriv.即可提取极化率数据。

---

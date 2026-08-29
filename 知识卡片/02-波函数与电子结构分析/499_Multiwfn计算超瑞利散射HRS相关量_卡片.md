---
id: 499
title: 使用Multiwfn计算与超瑞利散射(HRS)实验相关的量
domain: 波函数与电子结构分析
topic: Multiwfn计算超瑞利散射HRS相关量
cards: 11
---

## 1. HRS实验基础与定义
超瑞利散射(HRS)是测定分子第一超极化率beta(-2w;w,w)的实验手段。HRS测得的beta_HRS值是各向平均属性，不受分子朝向影响。退偏比(DR)的理论最小值为1.5，对应Td点群的分子。相关细节可参考Acc. Chem. Res., 31, 675 (1998)及PCCP,10,6223(2008)。

---

## 2. beta_HRS与DR的计算公式
根据入射光强度和测定的垂直散射出的倍频光强度计算beta_HRS值。<beta^2 ZZZ>和<beta^2 XZZ>是基于beta(-2w;w,w)张量的各个分量计算的。公式定义见Multiwfn手册3.200.7节或PCCP,10,6223(2008)。

---

## 3. beta张量分量的分解与贡献
<beta^2 ZZZ>和<beta^2 XZZ>可分解为偶极(J=1)和八极(J=3)成份的加和。由此可定义各向异性参数ρ，以及偶极和八极对beta的相对贡献φ(beta J=1)和φ(beta J=3)。

---

## 4. 散射光强度与极化角的关系
当入射光以X方向射入、相位延迟量δ=π/2时，顺着Y方向散射出的沿Z方向极化的光的强度与入射光极化角Ψ存在特定关系。这种关系被JCP,136,024506(2012)、JPCA,116,10249(2012)等文章考察。

---

## 5. Multiwfn版本要求与功能来源
计算HRS相关量必须使用2019年7月30日更新的3.7(dev)或更新版本。Multiwfn可在其主页。

---

## 6. Gaussian输入文件设置要点
计算HRS需要Gaussian的polar=DCSHG任务输出文件。输入文件中必须包含#P关键词以供Multiwfn解析。必须使用polar=DCSHG关键词来计算beta(-2w;w,w)形式。

---

## 7. 频率相关计算的Gaussian设置
结合CPHF=rdfreq和末行的波长值（如1064nm）可计算指定频率下的数据。polar=DCSHG关键词默认包含CPHF=rdfreq。可使用scrf=solvent关键词（如scrf=solvent=CH2Cl2）描述隐式溶剂环境。

---

## 8. Multiwfn计算HRS数据的操作步骤
启动Multiwfn载入输出文件，依次输入200、7、-1、1、2、2。输入200进入主功能，7解析polar任务信息，-1切换含频模式，1选择有解析三阶导数的级别，2载入特定波长数据，2选择beta(-2w;w,w)形式。

---

## 10. 计算结果与文献数据对比
在HF/daug-cc-pVTZ/IEFPCM(CH2Cl2)级别和1064nm波长下，Multiwfn计算的beta_HRS值为20.911，DR值为3.16。这与J. Chem. Phys., 136, 024506 (2012)表5中的文献值(20.90, 3.12)高度相符。

---

## 11. 散射光强度随极化角变化的计算
在Multiwfn输出界面输入y并输入起始角度（如-180），程序会生成HRS_angle.txt文件。文件包含从起始角度到r+360度范围内每隔1度对应的散射光强度值。

---

## 12. 散射光强度数据的可视化
将HRS_angle.txt文件导入Origin，选择Plot - Polar theta(X)r(Y)可绘制极坐标图。图中角度对应Ψ值，红线距离原点的距离代表散射强度值。

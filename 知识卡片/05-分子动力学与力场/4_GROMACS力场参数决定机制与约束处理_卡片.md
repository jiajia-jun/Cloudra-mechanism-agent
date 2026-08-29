---
id: 4
title: gromacs决定力场参数的方式
domain: 分子动力学与力场
topic: GROMACS力场参数决定机制与约束处理
cards: 13
---

## 1. Constraint设置对键参数的影响
GROMACS在mdp文件中设置constraint=all-bonds时，[bonds]里列出的所有键都会被约束，无论是否填写了力场参数。此时即便写了力场参数也会被视为无效，键不再按成键项(如G96BONDS)处理，而是按约束项(CONSTR)处理，使用gmxdump -s查看.tpr文件可以验证这一点。Constraint的优先级最高，约束的依据是[bonds]里定义的连接关系而非原子间距离。

---

## 2. GROMOS96力场键参数的读取规则
GROMOS96力场在constraint=none的情况下，其键参数完全取决于grompp读入的.top或.itp文件中直接写入的内容。如果[bonds]里定义了连接关系但没写力场参数，则该参数被视为0（即不存在），模拟时原子可能逐渐远离。这是因为GROMOS96力场的ffG43a1bon.itp中[bondtypes]内容极少，参数必须由pdb2gmx从.rtp文件搬运至.top中。

---

## 3. OPLSAA力场键参数的读取机制
OPLSAA力场在grompp时根据原子类型自动决定成键参数，而非像GROMOS96那样直接在.top中定义。程序根据[ atoms ]将原子序号转化为原子类型(如opls_136)，再由ffoplsaanb.itp转化为bond_type(如CT)，最后从ffoplsabon.itp的[bondtypes]中查找参数。因此.top文件中只需列出键结项(如`1 2 1`)，不需要直接写出具体参数。

---

## 4. GROMACS决定键参数的通用机制
GROMACS决定键参数时，如果[bonds]中已直接写入参数（或宏如ga_1并经cpp还原），则直接使用该参数；若只写了原子序号和函数类型未写参数，程序会去力场文件(如ff????bon.itp)的[bondtypes]中根据原子类型查找。如果查找失败，grompp会提示Warning并将该参数设为0；若同时存在直接写入参数和[bondtypes]参数，优先使用直接写入的参数。

---

## 5. GROMOS96与OPLSAA力场参数定义的差异
GROMOS96力场比较特殊，它在.rtp中预先定义了所有键结项和参数，.top文件包含全部参数，grompp直接从.top读取。OPLSAA力场则较为通用，.rtp只定义连接关系，.top列出键结项，参数由grompp时去力场库搜索。这种差异源于参数文件内容不同，而非程序处理机制的差异。

---

## 6. 特殊键（如二硫键）的处理方式
pdb2gmx通过读取specbond.dat文件来处理二硫键等特殊键，例如发现同链上两个CYS残基的SG原子距离在0.2nm附近时，将其视为成键并将残基名改为CYS2。生成的.top文件会包含这两个硫原子间的键、角、二面角项，但通常不写参数，程序会去[ bondtypes ]中查找对应参数（如`S S 2 gb_33`）。用户可通过修改specbond.dat来自定义处理规则。

---

## 7. 非键作用中VDW参数的确定
GROMOS96力场通过ffG43a1nb.itp中的[ nonbond_params ]提供原子类型对的C6和C12参数，若无对应组合，则根据comb-rule=1利用公式(C(i)*C(j))^1/2组合[ atomtypes ]中的参数。OPLSAA力场没有[ nonbond_params ]段，所有VDW参数均由组合规则得出（comb-rule=3）。静电作用仅依赖于原子电荷。

---

## 8. nrexcl对非键相互作用范围的影响
拓扑文件[ moleculetype ]段中的nrexcl参数决定了相隔多少个键以内的原子间不计算非键相互作用。例如nrexcl=3时，相隔3个键及以内的原子（包括直接成键、构成角度两端、构成二面角两端的原子）都不计算非键作用。nrexcl仅对常规非键作用有效，对1-4作用无效。

---

## 9. 1-4相互作用的定义与nrexcl的关系
1-4相互作用（包括库仑和VDW）在GROMACS中由.top文件[ pairs ]段明确定义，未在[ pairs ]中列出的原子即便符合1-4拓扑关系也不计算1-4作用。nrexcl参数仅控制常规非键作用的排除，不排除1-4作用；即使根据nrexcl设定不计算非键作用，若原子存在于[ pairs ]中，仍会计算1-4作用。

---

## 10. 1-4库仑作用与GROMOS96的1-4VDW参数
1-4库仑作用通过原子电荷计算静电能并乘以FudgeQQ因子（在[ defaults ]中定义）。GROMOS96力场的1-4VDW参数明确定义在ffG43a1nb.itp的[ pairtypes ]中，程序根据原子类型自动提取。GROMOS96的gen-pairs设为no，若找不到对应参数则报Warning并设为0。

---

## 11. OPLSAA力场的1-4VDW参数生成
OPLSAA力场通过将普通VDW参数乘以FudgeLJ因子(0.5)来计算1-4VDW参数，从而达到削弱效果。ffoplsaa.itp中gen-pairs设为yes，且ffoplsaanb.itp中没有[ pairtypes ]，因此所有1-4VDW参数均由组合规则乘以因子生成。若在[ pairs ]中直接给出参数，则优先使用给定参数。

---

## 12. 导致1-4作用为0或失效的设定
不计算1-4作用有两种情况：一是根本不写[ pairs ]项；二是写了[ pairs ]但参数为0或无法获取（gen-pairs=no且无对应pairtypes），导致计算结果为0（但1-4静电力仍会计算，除非FudgeQQ设为0）。后一种情况仍会消耗计算时间。若直接在[ pairs ]中给定参数为0，或导致参数获取失败，1-4VDW作用即为0。

---

## 13. ffgmx力场参数规则
基于GROMOS87的ffgmx力场，其VDW参数的决定方式与GROMOS96力场相同（即查阅[ nonbond_params ]或组合），但其键结参数的决定方式与OPLSAA力场相同（即由grompp根据原子类型查找）。

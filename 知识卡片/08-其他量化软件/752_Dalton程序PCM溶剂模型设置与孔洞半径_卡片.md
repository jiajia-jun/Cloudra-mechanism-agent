---
id: 752
title: 谈谈Dalton中的PCM溶剂模型的使用
domain: 其他量化软件
topic: Dalton程序PCM溶剂模型设置与孔洞半径
cards: 12
---

## 1. Dalton支持的隐式溶剂模型
Dalton程序仅支持PCM（极化连续介质模型）作为隐式溶剂模型，不支持SMD等其他溶剂模型。在使用时，需在.dal输入文件的*PCM模块下通过.SOLVNT关键字指定内置溶剂名或化学式。Dalton自带18种常用溶剂，包括水（H2O/WATER）、甲醇（CH3OH/METHANOL）、乙醇（C2H5OH/ETHANOL）、二氯甲烷（CH2CL2/METHYLCL）、苯（C6H6/BENZENE）、乙腈（CH3CN/ACETONIT）等。

---

## 2. Dalton内置溶剂的光学与物理常数
Dalton为内置溶剂储存了光学和物理常数，输出文件会显示当前溶剂的介电常数（EPS）、光学介电常数（EPSINF）、溶剂半径（RSOLV）以及摩尔体积（VMOL）。例如，以水为溶剂时，输出文件会显示：** LOOKING UP INTERNALLY STORED DATA FOR SOLVENT = WATER **，以及具体的参数值：EPS= 78.390; EPSINF= 1.776; RSOLV= 1.385 A; VMOL= 18.070 ML/MOL。

---

## 3. Dalton中溶质孔洞的定义与默认构造方式
在Dalton中使用PCM模型时，必须包含*PCMCAV模块以定义溶质孔洞。若不在*PCMCAV下进行额外设置，程序将以默认方式通过原子范德华球叠加来构造溶质孔洞。计算吸收光谱等电子激发问题时，需在*PCM模块中加入.NEQRSP关键字以使用非平衡溶剂。

---

## 4. Dalton中自定义溶剂介电常数的方法
若需使用Dalton未内置的溶剂，可通过在PCM模块下分别设置.EPS（静态介电常数）和.EPSINF（动态介电常数）来自定义。例如，要定义一个静态介电常数为23.0、动态介电常数为1.84的溶剂，在PCM模块下写.SOLVNT WATER（作为模板）后，接.EPS 23和.EPSINF 1.84即可。

---

## 5. Dalton PCM计算输出中的原子孔洞信息
Dalton在进行PCM计算时，输出文件中会列出构造溶质孔洞所用的原子信息，包括原子序号（INDEX）、以Bohr为单位的直角坐标（X, Y, Z）以及以埃为单位的原子半径（R）。这些信息位于标记为**SPHERES IN PCMSPHGEN**的段落中，格式示例为：1 2.1499166192D+00 -1.9894550417D+00 1.6741801837D+00 1.2000000000D+00。

---

## 6. Dalton构造溶质孔洞的默认原子半径来源
Dalton构造溶质孔洞所用的原子半径基于Bondi原子半径（出处：A.Bondi, J.Phys.Chem. 68: 441-451(1964)），其中C、N、O的半径被U. Pisa修改为更适于单键的数值。源代码`sirius/sircav.F`中设定的具体数值为：H 1.20，He 1.22，Li 0.00，Be 0.00，B 2.08，C 1.70（修改值），N 1.60（修改值），O 1.50（修改值），F 1.60，Ne 2.31等；未定义半径的元素默认为0。

---

## 7. Dalton中自定义原子半径的输入设置
要在Dalton中自定义原子半径，需在*PCM模块下设置.ICESPH为2（代表自定义半径），并设置.NESFP为需要自定义半径的原子总数。在*PCMCAV模块下，使用.INA列出原子序号，.RIN列出对应的半径值（单位埃），并可用.ALPHA设定Alpha值。原子序号需与.mol文件中的顺序一致，例如：.ICESPH 2，.NESFP 9，随后在*PCMCAV中列出9个原子的序号和半径。

---

## 8. Dalton与Gaussian偶极矩计算的对比验证（UFF半径）
通过将Dalton的原子半径和Alpha系数设置为与Gaussian 16默认IEFPCM（UFF力场半径）一致，可以验证两个程序的计算结果。例如对乙醇分子的B3LYP/def2-SVP计算，Dalton使用自定义半径（C 1.9255, H 1.4430, O 1.7500，Alpha均为1.1）计算出的偶极矩为1.8599 D，与Gaussian 16计算出的1.8592 D完美吻合。Dalton中需使用B3LYPg关键词以对应Gaussian的B3LYP定义。

---

## 9. Dalton与Gaussian偶极矩计算的对比验证（默认半径）
若要让Gaussian模拟Dalton默认孔洞设置的结果，需在Gaussian输入文件中通过scrf=read自定义半径和Alpha系数。Dalton默认半径为H 1.2、C 1.7、O 1.5，默认Alpha为1.2；对应Gaussian输入需包含`alpha=1.2`、`modifysph`以及具体的原子半径定义（如H 1.2, C 1.7, O 1.5）。对比结果显示，Gaussian计算出的偶极矩1.9136 D与Dalton默认孔洞下的1.9139 D吻合极好。

---

## 10. Dalton PCM计算中的SI矩阵警告及消除方法
在PCM计算时，输出文件常会出现“Warning, element... of SI too big: set to zero”之类的警告。这些警告源于矩阵校正，实际上可以直接忽略；若要消除警告，需在*PCM模块下加入“.NPCMMT 0”，即不进行DI、SI和C矩阵的校正。

---

## 11. NPCMMT参数对计算结果的影响
NPCMMT参数控制矩阵校正行为，0代表不校正，1代表校正DI和SI（默认），2代表校正DI、SI和C。虽然NPCMMT为1或2时会产生警告，但其计算结果与为0时的差异微乎其微。例如乙醇分子的计算中，NPCMMT为1时偶极矩为1.913867，单点能为-154.9289657907 Ha；而为0时分别为1.913182和-154.9289638876 Ha。

---

## 12. Dalton PCM计算中的Poor Tesselation警告
在Dalton的PCM计算中，可能会出现“** WARNING ** A VERY POOR TESSELATION HAS BEEN CHOSEN”警告，该警告无法通过设置NPCMMT为0来消除。根据测试，此警告通常是无害的，计算结果依然正常；若不放心，可以通过将Gaussian的半径设置成与Dalton一致来验证结果，或者将Dalton的半径设成与Gaussian默认一致以测试能否消除警告。

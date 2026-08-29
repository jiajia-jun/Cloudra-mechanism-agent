---
id: 266
title: 几种生成有机分子GROMACS拓扑文件的工具
domain: 分子动力学与力场
topic: GROMACS有机分子拓扑文件生成工具汇总
cards: 25
---

## 1. 原子电荷推荐与Multiwfn计算RESP/RESP2电荷
RESP电荷是最适合分子动力学模拟使用的电荷之一，AMBER、GAFF、GLYCAM等力场将之作为御用的原子电荷，将RESP电荷与UFF力场结合使用也是得当的。Multiwfn是计算RESP电荷最简单、最好、最灵活而且完全免费的工具，原理、用法和实例见《RESP拟合静电势电荷的原理以及在Multiwfn中的计算》、《计算RESP原子电荷的超级懒人脚本（一行命令就算出结果）》、《RESP2原子电荷的思想以及在Multiwfn中的计算》。

---

## 2. OPLS-AA力场推荐电荷与Multiwfn计算CM5电荷
OPLS-AA力场很适合结合1.2*CM5电荷使用，用Multiwfn的主功能7的子功能16直接就能计算出CM5电荷，将之手动乘以1.2即是1.2*CM5电荷。可用Gaussian、ORCA等程序产生的fch/wfn/wfx/molden等格式作为Multiwfn的输入文件，可参考《详谈Multiwfn支持的输入文件类型、产生方法以及相互转换》。《计算适用于OPLS-AA力场做模拟的1.2*CM5原子电荷的懒人脚本》可直接用一行命令算出结果，《ORCA结合Multiwfn计算RESP、RESP2和1.2*CM5原子电荷的懒人脚本》是专门结合ORCA用的傻瓜式脚本。

---

## 3. Sobtop工具简介与特点
Sobtop是GROMACS拓扑文件产生工具，主要产生GAFF/GAFF2、AMBER力场的拓扑文件，但由于其力场库可以自行非常方便地修改和扩充，因此Sobtop本质上是完全普适、通用的。Sobtop可谓是最理想、最灵活、最易用的产生GROMACS拓扑文件的工具，此程序用起来超级简单，什么额外的程序以及特殊的运行环境都不需要装，解压即用。

---

## 4. Sobtop的适用体系与参数来源
Sobtop可以产生任意体系的拓扑文件，有机和无机小分子、过渡金属配合物、聚合物、共价团簇、晶体、二维材料等等全都可以产生，孤立体系和周期性体系都支持。Sobtop可以用于包含任意元素的体系，那些GAFF/GAFF2/AMBER不支持的元素可以自动让Sobtop用UFF的，或者自己定义额外原子类型。对于GAFF/GAFF2/AMBER力场里缺失的成键相关参数，可以直接让Sobtop基于量子化学程序产生的Hessian矩阵通过不同方法自动算出来，也可以自己把其它方式得到的（如自己单独拟合、文献中找的）添到力场库文件里让Sobtop直接用。

---

## 5. Sobtop的原子类型指认与电荷计算功能
Sobtop极度灵活，提供许多不同的指认原子类型的方式，可以自动指认GAFF/GAFF2/AMBER原子类型，也可以手动指认，也可以自定义判断规则让Sobtop结合实际化学环境和成键关系判断。Sobtop还可以调用Multiwfn或OpenBabel自动指认EEM、Gasteiger、MMFF94原子电荷，还可以载入Multiwfn计算RESP/RESP2等电荷产生的chg文件来获得原子电荷。

---

## 6. acpype工具简介与依赖
acpype是一个Python脚本，使用前必须在机子里安装AmberTools（免费）。acpype会调用AmberTools中的Antechamber先产生Amber格式的拓扑文件然后再转成GROMACS的，默认情况下产生的拓扑文件是基于GAFF力场的，另外也会输出_OPLS后缀的基于OPLS力场的文件，但属于实验性质不建议用。

---

## 7. acpype的使用方法与输入文件
acpype用法很简单，要处理xxx.mol2就执行./acpype.py -i xxx.mol2，算完后会新产生一个xxx目录，里头有_GMX后缀的.gro、.itp、.top，直接在GROMACS里用即可。.mol2文件用常用的GaussView就可以产生（但必须确保在gview里看到的分子结构中没有诡异的成键方式），也可以通过OpenBabel或Antechamber将其它格式转成.mol2。

---

## 8. acpype的原子电荷处理建议
默认情况下acpype分配的原子电荷是Antechamber产生的AM1-BCC，虽然能用，但明显不如RESP/RESP2电荷理想，建议使用Multiwfn计算出RESP或RESP2电荷，自行写入分子拓扑信息的[atoms]的原子电荷那一列。如果不想安装AmberTools，可以使用在线版，但可能需要排队很久。

---

## 9. acpype处理大体系的参数建议
对于稍大的体系，用独立的acpype时强烈建议加上-c user选项以避免acpype自动算AM1-BCC原子电荷，否则在处理期间acpype所调用的Antechamber会先调用SQM程序用半经验方法进行优化然后再算这个电荷。然而SQM不仅慢，做优化还容易不收敛，导致半天也无法成功产生拓扑文件，更何况最后也是要替换为Multiwfn算的RESP/RESP2电荷，故计算AM1-BCC电荷没实际意义。同理，用在线版acpype也是建议把charge method设为user。

---

## 10. ATB工具简介与特点
Automated Topology Builder（ATB，）是生成GROMACS拓扑文件的在线工具，可以生成基于GROMOS96 G54A7力场（扩充了原子类型）的GROMACS或GROMOS程序的拓扑文件。ATB比PRODRG2更先进更可靠，解决了PRODRG2没法自动确定质子化态和charge group指认不准的问题以保证原子电荷可靠，并且能利用对称性保证电荷等价，另外没有PRODRG2那样对于每日提交的数目有限制。

---

## 11. ATB的使用建议与分子库
ATB虽然设计得不错，可以作为产生小分子GROMOS力场的GROMACS拓扑文件的首选，但它生成的原子电荷、确定的参数的可靠性也只是一般，不能保证总是很理想。如果要做很严谨的模拟研究，还是建议自行计算RESP电荷并且手动检查ATB给出的拓扑文件的合理性，有必要时适当调节。ATB网站上也有个分子库，包含巨量事先搞好的小分子的参数和拓扑文件，其中有的是别人之前提交过的分子，有的是经过专人手工处理过的分子，显然后者可靠程度更高，对于比较常见的分子，提交到ATB之前建议先搜索一下分子库，如果已经有的话就直接用。

---

## 12. LigParGen工具简介与电荷模型
LigParGen是生成GROMACS, NAMD, CHARMM, LAMMPS等程序OPLS-AA力场的拓扑文件的工具，支持SMILES字符串、.mol、.pdb文件作为输入，原子上限200个，可以顺带着让服务器对分子在OPLS-AA力场下做几何优化。分配的原子电荷是1.14*CM1A或1.14*CM1A-LBCC，前者是把CM1A电荷数值乘上1.14得到的，后者是在1.14*CM1A基础上再引入LBCC校正得到的，在J. Phys. Chem. B, 121, 3864 (2017)中已证明这两种原子电荷结合OPLS-AA模拟有机体系凝聚相可以得到不错结果。

---

## 13. LigParGen的电荷替换建议
该资料开头所述的Multiwfn可以计算的1.2*CM5电荷比LigParGen直接给出的电荷在多数情况下更适合做动力学模拟，特别是对于密度、蒸发焓的精度方面而言，这点在J. Phys. Chem. B, 121, 3864 (2017)的测试中充分体现了。而且对于一些分子，LigParGen给出的原子电荷加和不精确为0，而是比如0.0001，这导致此类分子数目较多时体系总电荷对整数有不可忽视的偏离，对模拟造成不良影响。因此建议将LigParGen给出的itp文件里的原子电荷部分替换为Multiwfn得到的1.2*CM5电荷。

---

## 14. MKTOP工具的使用方法
MKTOP是个Perl脚本，支持OPLS-AA和AMBER03力场，电荷无法自动生成而必须自己提供。使用之前需要确保已经安装了Perl运行环境，并且要把mktop.pl脚本开头的GROMACS拓扑文件目录改成当前机子里实际的，例如$gromacs_dir="/gmx/share/gromacs/top";。之后可以运行./mktop.pl -i new.pdb -o new.top -ff opls -conect no。这代表处理当前目录下的new.pdb，产生名为new.top的拓扑文件，使用OPLS-AA力场，并且不使用.pdb里的CONECT字段记录的连接关系而是根据原子之间距离猜测连接关系。之后需要自行把原子电荷填到new.top的[atoms]字段里。

---

## 15. MKTOP的注意事项
MKTOP有时候指认的OPLS-AA原子类型是错误的，所以建议按照力场目录下的atomtypes.atp仔细看看指认的原子类型到底是否合理。MKTOP在线服务如今已失效。

---

## 16. OBGMX工具简介与局限性
OBGMX是生成UFF力场的gromacs拓扑文件的在线工具，由于UFF几乎涵盖整个周期表，因此不光有机分子，也可以使Gromacs能够处理无机物、周期性体系，比如MOF。由于UFF的力场形式和Gromacs所支持的不完全兼容，此程序给出的参数实际上是对原UFF力场的近似，个别原子类型识别可能有误，电荷必须自己提供。2020-Dec-26注：此在线服务器目前已无法使用，但可以下载离线程序使用。

---

## 17. SwissParam工具简介
SwissParam输入有机小分子mol2文件，生成用于CHARMM/NAMD和GROMACS模拟的拓扑、参数文件。力场参数基于MMFF，但只保留谐振项部分，因此只是MMFF的近似，原子电荷通过MMFF方法获得，范德华参数采用CHARMM22中最接近的原子类型。这样的参数比较粗糙，有优化的余地。

---

## 18. CGenFF工具注册与使用前提
CGenFF是能够生成CGenFF力场的GROMACS拓扑文件的在线工具，学术用户必须用edu邮箱才能注册。

---

## 19. PRODRG2工具的缺陷与现状
PRODRG2是生成Gromacs拓扑文件的在线工具，只支持GROMOS87/96力场。原子电荷是根据基团指认的，如果基团识别不对那么电荷也不可靠，此工具在J. Chem. Inf. Model., 50, 2221 (2010)被指出往往不能正确指认charge group，导致原子电荷分配也很不合理。而且由于有了更好的ATB，因此如今强烈不推荐使用。

---

## 20. 旧版CGenFF在线服务器的操作步骤
旧版CGenFF先注册，上传有机小分子的mol2文件，如果mol2是gview建的，一定要事先把里面的Ar替换成ar。上传文件的时候不要选Guess bond orders from connectivity和Include parameters that are already in CGenFF。如果文件处理正常，会立刻产生str文件，点击其链接之后把里面内容拷到比如Actos.str里面。

---

## 21. 旧版CGenFF的文件转换与运行命令
进入旧版CGenFF网页里的More Info & Tools - Utilities，点击GROMACS conversion program，可下载把str文件转换为GROMACS格式的Python脚本cgenff_charmm2gmx.py。对于CentOS 7.2，应运行yum install numpy和yum install python-networkx把这个脚本所需的包装上。下载力场文件解压得到比如charmm36-nov2016.ff文件夹，将它和Actos.str、cgenff_charmm2gmx.py都放到当前目录，另外也把该资料件夹拷到gromacs的top目录下。假设Actos.str里RESI后面的词是Molecu，最初上传的是Actos.mol2，则运行./cgenff_charmm2gmx.py Molecu Actos.mol2 Actos.str charmm36-nov2016.ff。

---

## 22. 旧版CGenFF的输出文件与参数可靠性
旧版CGenFF运行后在当前目录会产生molecu.top、molecu.prm、molecu.itp、molecu.pdb（从mol2转换过来的），适当调整itp和top里的分子名，调整itp里的残基名和结构文件相对应后，即可用于模拟。str文件里的力场参数有penalty指标，数值越大说明此参数可靠性越低，详见网页里的说明。

---

## 23. TPPmktop工具简介与问题
TPPmktop是在线工具，提供pdb文件，能产生OPLS-AA力场参数的GROMACS拓扑文件，速度比较快。但是得到的拓扑文件里有时候会缺参数，或者出现额外的原子类型，需要再手工处理（需要引入额外的力场文件，但是在网上下载不到）。此服务器有时候有其它任务在跑，此时无法提交任务，只能等过一阵服务器没任务时再提交。

---

## 24. YASARA AutoSMILES Server简介
YASARA AutoSMILES Server是在线版程序，离线的话得买YASARA（建模+可视化+动力学模拟工具）。它可以计算AM1-BCC电荷、指认amber94/96/99力场参数，但是产生的文件只能用YASARA View打开，也就是说，拓扑文件相当于YASARA专用的。

---

## 25. RED工具简介
RED（RESP ESP charge Derive，）专门生成RESP电荷的工具，也能搞力场参数。由于Multiwfn已经完美支持RESP电荷计算了，RED已没有必要使用。

---
id: 421
title: 将Gaussian与Grimme的xtb程序联用搜索过渡态、产生IRC、做振动分析
url: http://sobereva.com/421
domain: 反应机理与过渡态
topic: Gaussian与xtb联用搜索过渡态及IRC分析
cards: 10
---

# Gaussian与xtb联用搜索过渡态及IRC分析 — 知识卡片

## 1. gau_xtb接口与引用方式

gau_xtb是将Gaussian与Grimme的xtb程序联用的接口脚本，支持利用Gaussian的external功能调用xtb进行极小点/过渡态优化、IRC及振动分析等任务。此接口利用Gaussian作为优化器，读取由xtb产生的能量、受力和Hessian信息，弥补了xtb无法搜索过渡态和产生IRC的缺陷。实际研究中若使用此接口，必须按如下格式引用：Tian Lu, gau_xtb: A Gaussian interface for xtb code, http://sobereva.com/soft/gau_xtb (accessed month day, year)。该脚本始终兼容最新版xtb，若出现调用失败应首先更新xtb和gau_xtb，并避免使用稀奇古怪的运行环境。

---

## 2. xtb程序的安装与环境配置

xtb程序可从GitHub下载预编译版本（如xtb-191025.tar.xz），解压后将bin目录路径加入PATH环境变量，并将share/xtb路径加入XTBPATH环境变量。需在~/.bashrc中配置如下环境变量：export PATH=$PATH:/sob/xtb/bin、export XTBPATH=/sob/xtb/share/xtb、export OMP_NUM_THREADS=N、export MKL_NUM_THREADS=N、export OMP_STACKSIZE=1000M、ulimit -s unlimited，其中N为并行核心数。根据测试，xtb做优化和动力学时在约12核速度封顶，建议多核机箱设N为12并跑多任务，而做振动分析时使用更多核心（如36核）仍有显著加速效果。

---

## 3. xtb程序的常用命令行选项

xtb输入文件为xyz格式，常用选项包括：-c或--chrg设定体系净电荷，-u或--uhf设定alpha与beta电子数之差，--gbsa和--alpb分别使用GBSA和ALPB隐式溶剂模型，--molden生成molden.input文件，--gfn选择GFN-xTB版本（0、1、2）。常用任务类型有：--sp（单点，默认）、--grad（梯度）、--opt（几何优化）、--hess（数值Hessian和振动分析）、--ohess（优化后自动振动分析）、--md（分子动力学）。GFN2-xTB精度最佳但SCF收敛难，GFN1-xTB易收敛且适合金属团簇，GFN0-xTB速度快但精度低不适合找过渡态。

---

## 4. xtb程序的控制文件(xcontrol)使用

xtb可通过-I选项载入控制文件来对运行细节进行控制，控制文件中字段以$开头。例如，设定alpha电子比beta电子多2且冻结原子3、19至22号位置的控制文件内容为：$spin=2、$fix、atoms:3,19-22。控制文件中的设置优先级低于直接通过命令行选项指定的设置（如电荷）。更多控制字段和高级用法需参考xtb在线手册或相关培训资料。

---

## 5. Gaussian的external功能与文件传递

Gaussian的external功能通过在输入文件中写入external='./xtb.sh'来调用外部脚本，调用命令格式为：xtb.sh layer InputFile OutputFile MsgFile FChkFile MatElFile。Gaussian会生成InputFile文件，包含原子数、所需导数层级（0能量、1受力、2Hessian）、电荷、自旋多重度及原子坐标（单位Bohr）。外部脚本需生成OutputFile文件，按指定格式填入能量、梯度、Hessian等信息供Gaussian读取。InputFile示例格式为：原子数 导数 电荷 自旋多重度，随后每行包含元素序号、XYZ坐标、MM电荷和MM原子类型。

---

## 6. xtb.sh接口脚本的工作原理

xtb.sh接口脚本首先读取Gaussian传递的InputFile，提取原子数、导数要求、电荷和自旋多重度，并构建临时xyz文件供xtb调用。脚本根据导数要求决定xtb运行参数：若derivs为2则调用xtb --hess --grad，若为1则调用--grad，同时将自旋多重度减1作为uhf参数传递给xtb。脚本调用自编译的genxyz程序将Gaussian格式转换为xyz，调用xtb计算后，再使用extderi程序从xtb输出文件中提取能量、梯度和Hessian，并按Gaussian格式写入OutputFile。脚本默认使用GFN1-xTB，可添加--gfn 2切换至GFN2-xTB。

---

## 7. Gaussian与xtb联用搜索过渡态的输入设置

利用Gaussian与xtb联用搜索过渡态时，Gaussian输入文件应使用#P opt(ts,calcfc,noeigen,nomicro) external='./xtb.sh'，其中nomicro必须写上以阻止Gaussian调用分子力学优化器。输入文件中无需写理论方法和基组，但必须提供与过渡态结构相近的初猜结构，并建议使用%chk保存chk文件以便后续任务使用。注意不能将opt和freq写在一起做，必须分步执行，且若Gaussian默认并行计算需在输入文件中设%nproc=1改为串行以避免资源浪费。

---

## 8. 环丙基卡宾异构化过渡态搜索实例与精度对比

对环丙基卡宾异构化过程，使用Gaussian+xtb联用（opt=TS）搜索过渡态，13步收敛，所得结构（GFN-xTB）与B3LYP/TZVP结果对比RMSD较小，定性正确。虚频计算结果显示Gaussian+xtb为732cm-1，B3LYP/TZVP为686.7cm-1，PM7为843.1cm-1，说明GFN-xTB误差比PM7更小。IRC计算曲线光滑且结构正常，证明联用方法可行，对于普通有机体系虽优势不显著，但优于半经验方法。

---

## 9. 过渡金属体系过渡态搜索的性能对比

在Sc金属引发的C-H活化反应中，以PBE0-D3(BJ)优化的过渡态为基准，Gaussian+xtb联用能维持住过渡态结构，虚频和键长合理且IRC顺利。相比之下，PM7半经验方法优化过渡态时结构严重变形，震荡一百多步不收敛，且Sc配位环境完全错误（如Sc与碳配位而非茂环）。这表明对于涉及过渡金属等复杂体系，当预感半经验方法无法给出定性正确结果时，应改用Gaussian+xtb进行预优化。

---

## 10. GFN-xTB方法的局限性

虽然GFN-xTB普适性和精度较好，但并不能完全抗衡一般DFT计算，例如优化Li2分子时，M06-2X/def2-TZVP结果为2.7064埃（实验值2.6729埃），GFN-xTB结果为2.2991埃，误差较大（尽管优于PM7的1.8106埃）。对于含重元素（如Pt）的体系，Gaussian与xtb联用虽不进行量化计算，但Gaussian内部默认基组STO-3G可能不含重元素定义从而导致报错，解决方法是在关键词中加入UGBS基组以覆盖整个周期表元素。

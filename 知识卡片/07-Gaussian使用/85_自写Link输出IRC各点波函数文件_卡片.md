---
id: 85
title: 自写Link生成Gaussian的IRC任务中每个点的波函数文件
domain: Gaussian使用
topic: 自写Link输出IRC各点波函数文件
cards: 10
---

## 1. Gaussian Link基本代码结构模板
Gaussian的Link由dummy程序（壳）和本体子程序组成，模板中InitSCM用于分配内存，ltwd是本体，Drum用于初始化，ChainX用于扫尾工作。程序通过Common块（如/IO/、/IOp/、/PHYCON/）和rwf文件（如Gen数组）交换数据，其中nbasis为基函数数，phycon(5)为阿伏伽德罗常数，Gen(1)和Gen(32)分别为维里值和能量。
- Call FileIO(2,-501,1000,Gen,0)代表从rwf文件中编号501的子文件读取长度为1000的信息到Gen数组里
- ChainX必须用在link的末尾，参数0代表对执行顺序不进行修改
- /IO/中In=5用于读取输入，IOut=6用于屏幕输出，IPunch=7用于punch文件输出

---

## 2. 编译自己写的Gaussian Link步骤
编译自定义Link需先设置环境变量$g09root并进入csh，执行source /sob/g09/bsd/g09.login。将/sob/g09/bsd/link.make拷至当前目录并改名为Makefile，删除MAIN502内容，将OBJ502设为源文件编译生成的.o文件（如666lite.o），运行mk脚本即可生成l502.exe，可重命名为自定义名称（如l666.exe）。
- 源代码文件名假设为666lite.F
- 若提示World accessible，需用chmod修改文件权限为700

---

## 3. 修改现有Gaussian Link子程序步骤
修改现有Link（如l601）需使用gau-get命令提取子程序（如gau-get DQ l601生成dq.F），修改代码后，拷贝link.make为Makefile并替换其中的编号（如502改为601）。设置MAIN601为ml601.o（使用Main.F中的壳），OBJ601为修改后的.o文件（如dq.o），运行mk脚本连接原l601.a中的其他子程序。
- 示例中将l601中DQ子程序的2002号format从F20.4改为F20.8

---

## 4. 自写Link输出每一步波函数的原理
为实现IRC、Scan等任务每步输出波函数文件，需在l502（SCF）之后插入一个新Link（如l555）。该Link核心是调用l9999中的DoWfn子程序，需将AllDun内容拷贝并保留与DoWfn相关的铺垫代码（如计算IEnd变量），删除读取IOp(6)百位数的判断条件，使其无条件调用DoWfn。
- l502做完之后SCF波函数信息就有了，所以只需要写一个link插在l502之后
- 需保留计算IEnd变量的过程，避免引起麻烦

---

## 5. 波函数文件名自动编号的代码实现
为防止每步波函数文件覆盖，需修改WrtWfn代码，在Read(In,'(A)') FilNam后插入backspace(In)，并增加循环逻辑检测文件名是否存在。代码会从0000开始检查，若文件存在则递增编号，直到找到不存在的文件名，最终生成如H2_0000.wfn, H2_0001.wfn的文件。
- inamelen=LenFil-4为不含扩展名的文件名长度
- namedigit是character*4型新增的变量，通过write(namedigit,"i4.4") itestname赋值
- 代码需将ISt:LenFil替换为1:inamefullen以适应新文件名长度

---

## 6. 编译调用l9999子程序的自定义Link
编译包含l9999子程序（如AllDun, WrtWfn）的自定义Link（555.F）时，需将Makefile中的编号改为9999，清空MAIN9999，将OBJ9999设为555.o。运行mk后，生成的l9999.exe会替换掉原l9999中的外壳和指定子程序，其余子程序沿用原版，最后将生成的exe改名为l555.exe。
- 这种方法相当于把原本l9999里的外壳、AllDun、WrtWfn都用555.F里所定义的替换

---

## 7. 在Gaussian输入文件中插入自定义Link
在非标准路径中插入自定义Link有两种写法：直接写一行如`5//55;`仅调用l555，或在现有Link路径末尾添加如`5/5=2,38=5/2,55;`。若l555.exe不在g09目录，需在输入文件开头写`%subst l555.`；使用`ExtraLinks=l555`可在每次调用完overlay 5的所有link后自动调用l555。
- 示例路径：`5/5=2,38=5/2,55;` 与 `5//55;` 效果一致
- ExtraLinks=l555免得列出冗长的执行路径

---

## 8. IRC任务输出波函数文件的过剩问题
IRC任务中每一步实际执行限制性优化，包含多次SCF循环，导致在每步优化后都插入输出Link会产生大量波函数文件，其中仅包含优化收敛点的文件有用。若IRC有20步且平均每步3次优化，会输出约60个文件，但实际只有21个（含TS）是有用的。
- 必须想办法只让每次限制性优化收敛的步才输出波函数文件

---

## 9. 筛选IRC收敛步波函数文件的Shell脚本
通过分析Gaussian输出文件中的"Delta-x Convergence Met/NOT Met"信息，可编写Shell脚本筛选波函数文件。脚本会删除标记为"NOT"的未收敛步文件，保留标记为"Met"的收敛步文件，并将它们重命名为连续编号（0000.wfn~0020.wfn），其中0对应过渡态。
- 脚本关键行：`res=(pass `grep -E "Delta-x Convergence NOT Met|Delta-x Convergence Met" $outname|awk '{print $3}'`)`
- 如果"${res[$i]}" == "NOT"且i不为0，则rm -f $filnam

---

## 10. 利用l123实现仅输出收敛步波函数的思路
第二种方法是修改l123.F中的PreDWI子程序，利用cordon变量判断限制性优化是否收敛。当收敛时（cordon为true），通过/Gen/空余位置或system命令（如touch conv）传递信息给WrtWfn，使其仅在检测到收敛信息时才输出波函数文件，需注意波函数对应的步数偏移问题。
- PreDWI子程序与这个问题相关，当cordon变量为true时说明限制性优化已收敛
- 可通过Inquire(file="conv",exist=ircconv)判断是否收敛

---
id: 509
title: 给def2以ma-方式加弥散函数的Gaussian格式的基组定义文件（含所有def2支持的元素）
url: http://sobereva.com/509
domain: Gaussian使用
topic: def2基组ma-方式加弥散函数定义文件
cards: 10
---
## 1. def2基组ma-方式加弥散的定义文件

def2系列基组没有官方标配的带弥散函数版本，Truhlar课题组网站提供的ma-基组定义文件关键缺点是元素不全。基于BSE上的def2系列基组支持的所有元素的定义文件，自动批量按照ma-方式添加弥散函数，生成的文件包包含ma-QZVPP.txt等文件和共用的赝势文件def2-ECP.txt。这些文件可以在这里下载：http://原作者.com/attach/509/file.zip。

---

## 2. Gaussian中引用外部基组文件的Windows用法

在Gaussian中使用ma-系列基组时，只需将定义文件（如ma-TZVP.txt）放到某个目录，输入文件中使用@符号include该文件路径即可。例如`@C:\ma-TZVP.txt`会在计算前自动展开文件内容。由于.txt文件里所有元素前头都有个负号，只有当前体系里存在的元素才会自动取文件里的基组定义。

---

## 3. Windows下B3LYP-D3(BJ)/ma-TZVP计算单点示例

这是一个Windows下计算水-氟代甲烷单点的例子，计算前先把ma-TZVP.txt放到C:\下。输入文件中使用`#p B3LYP/gen em=gd3BJ int=fine`，在分子坐标后空一行输入`@C:\ma-TZVP.txt`。@代表把后面的文件在计算Gaussian之前会被自动展开。

---

## 4. def2基组对重元素使用赝势

def2系列基组对第五周期开始的元素是赝势基组，因此使用时需要配合赝势文件。文件包里的def2-ECP.txt是所有def2基组共用的赝势文件，包含def2系列支持的从第五周期开始的所有元素的赝势定义。

---

## 5. Windows下genecp配合外部基组文件计算顺铂

这是一个BP86计算顺铂的例子，对所有元素用ma-SVP，对Pt还加了赝势。计算前先把ma-SVP.txt和def2-ECP.txt放到C:\下。输入文件使用`#P BP86/genecp int=fine`，在分子坐标后先空一行输入`@C:\ma-SVP.txt`，再空一行输入`@C:\def2-ECP.txt`。C:\ma-SVP.txt对体系涉及的所有元素定义了基组，C:\def2-ECP.txt定义了Pt的赝势。

---

## 6. 负号在基组定义文件中的作用

在ma-SVP.txt和def2-ECP.txt文件中，各个元素定义前头都有负号。这种写法意味着只有当该元素在当前体系（分子坐标）中出现时，才会调用文件中对应的基组或赝势定义，而文件里定义的其它元素不会影响当前计算。

---

## 7. Linux下引用外部基组文件的用法

在Linux下也可以用@引用的方式使用基组文件，但需要在路径后加/N参数以避免运行时自动把文件里的内容完整输出一遍。例如使用`@/sob/ma-SVP.txt/N`和`@/sob/def2-ECP.txt/N`。两个文件引用指令之间不能有空行，否则会导致Pt的赝势信息没法被载入。

---

## 8. ma-TZVP(-f)基组的特点与用途

文件包里的ma-TZVP(-f).txt是对def2-TZVP(-f)以ma-方式加弥散函数的版本。def2-TZVP(-f)比def2-TZVP便宜得多，差异在于前者把后者的f极化函数去掉了（对镧系元素保留了f函数，去掉了g极化函数）。ma-TZVP(-f)比6-311+G(2d,p)略大，强烈鼓励将其代替6-311+G(2d,p)使用。

---

## 9. def2-TZVP与def-TZVP的基组大小比较

def2-TZVP(-f)比def-TZVP更大，例如对于碳，前者有两层d极化而后者只有一层。因此ma-TZVP（基于def2-TZVP）比起将def-TZVP用ma-方式加弥散函数的版本计算成本更贵一些。

---

## 10. 自动构建ma-基组定义的工具ma-diffuse

构建ma-基组定义的程序ma-diffuse可在此下载：http://原作者.com/soft/ma-diffuse.rar。这是一个Windows版可执行文件，使用Def2-SVP.gbs等原始定义文件作为输入。程序运行时可以设定最小的s和p指数要除的因子，如果设成3，对应的就是以标准的ma-方式加弥散函数的情况。新产生的基组会输出到当前目录下的new.txt。

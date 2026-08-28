---
id: 258
title: 使用Gaussian时的几个实用脚本和命令
url: http://sobereva.com/258
domain: Gaussian使用
topic: Gaussian批量运行与文件处理脚本
cards: 10
---

# Gaussian批量运行与文件处理脚本 — 知识卡片

## 1. 依次执行多个Gaussian任务

在命令行中可以使用分号分隔指令来依次执行多个Gaussian计算任务，例如`g09 < 1.gjf > 1.out;g09 < 2.gjf > 2.out;g09 < 3.gjf > 3.out`。也可以将这些指令写入文本文件（如t.sh），使用`chmod +x *`赋予可执行权限后通过`./t.sh`运行。若希望指令同时执行而非依次执行，需要在每行命令末尾加上`&`。

---

## 2. 批量执行当前目录下所有Gaussian输入文件

将脚本保存为runall.sh并执行，可以自动运行当前目录下所有的.gjf文件，生成对应的.out文件并显示进度和耗时。脚本内容为：`icc=0`，`nfile='ls ./*.gjf|wc -l'`，循环执行`time g09 < ${inf} > ${inf//gjf/out}`。Windows用户可参考《从高斯windows下的批量执行谈DOS批处理文件》编写DOS批处理脚本。

---

## 3. 批量转换chk文件为fchk文件

将脚本保存为chk2fch.sh并执行，可以调用formchk程序将当前目录下的所有.chk文件转换为同名的.fchk文件。脚本核心是循环`for inf in *.chk do formchk ${inf} done`。

---

## 4. 执行当前目录下所有子目录里的Gaussian输入文件

将脚本保存为folder_runall.sh并执行，可以进入当前目录的下一级子目录，依次执行其中的.gjf文件。脚本使用`for i in 'ls -F |grep /' do cd $i`进入子目录，执行完计算后通过`cd ..`返回。

---

## 5. 递归执行所有子目录里的Gaussian输入文件

将脚本保存为allfolder_runall.sh并执行，可以递归进入当前目录及所有深层子目录，执行其中的.gjf文件。脚本利用`ls -R |grep :|tr : " "`获取所有目录路径，通过`cd $i`和`cd -`在各目录间切换，并在屏幕上显示进入的目录。

---

## 6. 批量替换Gaussian输入文件中的字符

使用sed和grep命令可以批量替换当前目录及子目录下.gjf文件中的计算级别或关键词，例如将M062X替换为B3LYP：`sed -i "s/M062X/B3LYP/g" 'grep M062X -rl *|grep .gjf'`。若替换字符包含`*`、`/`等符号需加`\`转义（如6-31G\*\*），若包含括号或空格，grep后的内容需用双引号括住。

---

## 7. 批量删除指定类型文件

使用find和xargs命令可以删除当前目录及任意级子目录下的所有.out文件：`find ./ -name "*.out"|xargs rm -f`。

---

## 8. 显示几何优化收敛情况

使用grep命令可以查看几何优化输出文件的收敛情况，例如`grep Converged C4H8.out -A4`会输出收敛信息及后4行。执行`grep Converged C4H8.out -c`会输出匹配次数（即优化步数），或者使用`grep -E "out of|Converged" C4H8.out -A4`同时显示步数和收敛情况。

---

## 9. 计算Counterpoise任务的一半BSSE校正能

根据J. Chem. Theory Comput., 10, 49 (2014)的建议，对于<= aug-cc-pVTZ基组的Counterpoise计算，可使用脚本计算只含一半BSSE校正能的结果。脚本读取.log文件中的`Counterpoise corrected energy`、`BSSE energy`和`sum of fragments`，通过公式`($Edimer-$EBSSE*0.5-$Esum)*627.51`计算并以kcal/mol为单位输出。

---

## 10. 批量提取输出文件最后一次SCF Done能量

使用脚本可以提取当前目录下所有.out文件中最后一次出现的`SCF Done`行及其对应的能量。脚本利用`tac $inf | grep -m 1 "SCF Done"`倒序读取文件并只匹配第一次出现的结果，将能量值与文件名一同输出。

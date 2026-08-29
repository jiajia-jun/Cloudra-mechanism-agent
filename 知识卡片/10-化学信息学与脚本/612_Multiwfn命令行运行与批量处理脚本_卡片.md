---
id: 612
title: 详谈Multiwfn的命令行方式运行和批量运行的方法
domain: 化学信息学与脚本
topic: Multiwfn命令行运行与批量处理脚本
cards: 15
---

## 1. Multiwfn命令行启动与参数设置
Multiwfn可通过命令行启动，格式为Multiwfn [输入文件路径] [选项/参数]。支持-nt设置线程数、-uf指定用户自定义函数序号、-silent开启静默模式避免图形窗口弹出、-set指定settings.ini路径。例如：Multiwfn /nico/COCl2.fch -nt 36 -set /sob/tmp/settings.ini -silent。

---

## 2. 重定向输入运行Multiwfn
可将记录指令的文该资料件通过重定向传递给Multiwfn执行。例如创建LBO.txt包含"9\n8\ny"，运行Multiwfn /sob/Rio.molden < LBO.txt，即可计算拉普拉斯键级并导出矩阵文件bndmat.txt。输出信息可重定向到文件：Multiwfn /sob/Rio.molden < LBO.txt > out.txt。

---

## 3. Bash脚本传递指令与输出控制
在Bash中可用Here Document将指令直接传递给Multiwfn。例如：Multiwfn /sob/Rio.molden << EOF > out.txt（指令内容）EOF。管道方式如echo -e "9\n8\ny" | Multiwfn /sob/Rio.molden > out.txt也可实现相同目的。可使用2> /dev/null或2> NUL屏蔽报错信息，或加入"0\nq"实现优雅退出。

---

## 4. 一键预测晶体密度的脚本逻辑
脚本preddens.sh通过Multiwfn调用主功能12计算分子表面静电势，提取M/Vm和νσ2tot值，代入公式0.9183*(M/Vm)+0.0028*(νσ2tot)+0.0443预测晶体密度。利用grep和awk从输出文件中提取Estimated density和Product of sigma^2_tot and nu数值。

---

## 5. ESPiso.bat批量绘制静电势图的原理
ESPiso.bat脚本依次调用Multiwfn处理多个fch文件，使用-ESPrhoiso 0.001参数加速计算，并将生成的density.cub和totesp.cub通过move命令重命名。最后将所有cub文件移动到VMD目录。指令文件ESPiso.txt通过主功能5输出电子密度和静电势格点数据。

---

## 6. ESPiso_eV.txt实现静电势单位转换
ESPiso_eV.txt在ESPiso.txt基础上增加了格式转换步骤：在导出静电势后，使用r命令重新载入totesp.cub，进入主功能13的子功能11乘以27.2114（Hartree到eV的转换系数），覆盖原文件实现单位转换。

---

## 7. 批量空穴-电子分析脚本结构
脚本通过循环生成指令文件calcall.txt，依次对激发态执行主功能18的子功能1进行分析。利用grep和nl命令提取输出中的Sr index、D index、RMSD等指标，并追加行号后写入result.txt。循环变量控制分析激发态的序号范围。

---

## 8. RESP电荷自动化计算脚本流程
RESP.sh脚本自动完成Gaussian优化、单点计算和Multiwfn电荷拟合。它首先提取输入文件坐标生成gjf文件，调用Gaussian计算，使用formchk转换chk文件，最后通过Multiwfn主功能7子功能18读取gau.out中的静电势计算RESP电荷，并导出为chg文件。

---

## 9. Bash循环批量处理wfn文件
使用for循环遍历当前目录下所有.wfn文件，调用Multiwfn执行指令文件genELFcub.txt，并将输出结果ELF.cub重命名。语法示例：for inf in *.wfn; do Multiwfn $inf < genELFcub.txt; mv ELF.cub ${inf//.wfn}_ELF.cub; done。

---

## 10. Windows批处理循环批量处理文件
Windows batch脚本利用for /f命令遍历文件。语法示例：for /f %%i in ('dir *.wfn /b') do (Multiwfn %%i < genELFcub.txt > NUL; rename ELF.cub %%~ni_ELF.cub)。%%~ni表示去掉扩展名的文件名。

---

## 11. 批量格式转换脚本outgjf.sh
脚本遍历所有.out文件，调用Multiwfn主功能100子功能2将其转换为Gaussian输入文件.gjf。利用${inf//out/gjf}修改输出文件名，并计算处理进度。指令包括输入输出文件设置及退出选项。

---

## 12. 批量提取HOMO-LUMO gap并统计
脚本getgap.sh遍历.fch文件，在静默模式下运行主功能0，利用grep提取HOMO-LUMO gap的eV值。累加计算平均值，并通过条件判断记录最小gap对应的文件名。最终使用awk格式化输出平均值和最小值到gap.txt。

---

## 13. AIMD轨迹自旋布居提取
针对AIMD产生的轨迹文件，脚本调用Multiwfn主功能7子功能5计算Mulliken自旋布居。利用grep -A 100定位Population of atoms区块，提取特定原子（如4(H)）的自旋布居数值，并追加到文该资料件中用于绘图。

---

## 14. AIMD轨迹键级变化分析
脚本遍历轨迹文件，通过Multiwfn主功能9子功能1计算Mayer键级。利用grep和cut命令提取特定原子对（如1(C ) 3(C )）的Total键级值，分别保存到不同文件中，从而分析C1-C3、C3-O6、O5-O6键级随时间的变化。

---

## 15. AIMD自旋密度动画制作流程
首先通过脚本批量计算每一帧的自旋密度格点数据（主功能5子功能5），导出cub文件并按序号命名。然后使用VMD的tcl脚本批量渲染等值面图保存为bmp。最后使用ffmpeg生成调色板并将bmp合并为gif动画，命令如ffmpeg -r 5 -i %05d.bmp -i palette.png -lavfi paletteuse video.gif。

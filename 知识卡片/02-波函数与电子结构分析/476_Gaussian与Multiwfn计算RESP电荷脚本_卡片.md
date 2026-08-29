---
id: 476
title: 计算RESP原子电荷的超级懒人脚本（一行命令就算出结果）
domain: 波函数与电子结构分析
topic: Gaussian与Multiwfn计算RESP电荷脚本
cards: 19
---

## 1. RESP电荷的特点
RESP电荷特别适合对柔性分子做分子动力学计算，结合Multiwfn使用明显比Antechamber等其它程序更便利灵活。
可参考《RESP拟合静电势电荷的原理以及在Multiwfn中的计算》一文

---

## 2. RESP2电荷的适用性
如果计算RESP电荷的目的是用于分子动力学模拟，更建议使用RESP2电荷，有较大可能结果更好。
可参考《RESP2原子电荷的思想以及在Multiwfn中的计算》一文

---

## 3. 使用ORCA计算原子电荷
若未购买Gaussian，可使用免费的ORCA量子化学程序结合Multiwfn计算RESP、RESP2和1.2*CM5原子电荷。
可参考《ORCA结合Multiwfn计算RESP、RESP2和1.2*CM5原子电荷的懒人脚本》一文

---

## 4. 脚本原理的参考文献
若想了解基于Gaussian和Multiwfn的懒人脚本原理，应阅读《详谈Multiwfn的命令行方式运行和批量运行的方法》。
- 见

---

## 5. RESP.sh脚本的安装准备
需安装Gaussian并下载Multiwfn最新版本到Linux环境，确保能通过输入Multiwfn命令启动程序。
- 可参考《Gaussian的安装方法及运行时的相关问题》
- 可参考《Multiwfn在Linux下安装的中文说明》

---

## 6. RESP.sh脚本的版本配置
脚本RESP.sh默认调用g09，Gaussian16用户应将其中的g09替换为g16；若安装的是noGUI版，需把脚本里的Multiwfn改为Multiwfn_noGUI。

---

## 7. RESP.sh的默认计算级别
脚本默认在B3LYP-D3(BJ)/def2-SVP级别下优化结构，然后在B3LYP-D3(BJ)/def2-TZVP级别下计算单点能并产生分子表面静电势数据。

---

## 8. 降低几何优化耗时的方法
若B3LYP-D3(BJ)/def2-SVP优化耗时过高，可将关键词改为# PM6D3 opt，使用PM6-D3半经验方法在真空中优化。
- PM6-D3主要适合普通有机体系且体系无局部显著离子特征的情况

---

## 9. 降低单点计算耗时的方法
若单点任务计算困难，可将def2-TZVP基组降为6-311G**，如果是阴离子建议改为6-311+G**。

---

## 10. 旧版Gaussian的D3校正限制
Gaussian09 D.01版本之前不支持DFT-D3校正，使用老版本者应取消脚本里的em=GD3BJ关键词。
- 可参考《DFT-D色散校正的使用》

---

## 11. RESP.sh脚本的运行命令
使用命令`./RESP.sh [文件名] [净电荷] [自旋多重度] [溶剂名]`进行计算。
- 输入文件格式必须是Multiwfn支持的格式（如xyz/mol/mol2/pdb/fch/wfn/molden/gjf）

---

## 12. 脚本命令的参数默认值
若不写净电荷和自旋多重度，默认值分别为0和1；若不写溶剂名，默认为water；若写gas，则在真空下计算。

---

## 13. 计算结果的输出文件
计算完毕后，当前目录下会生成与输入文件同名的.chg文件，包含元素名、优化后坐标及最后一列的RESP电荷。

---

## 14. 计算出错的检查方法
如果调用Gaussian运行失败，脚本会自动停止，需检查当前目录下的gau.out文件判断出错原因。

---

## 15. 计算使用的CPU核数设置
计算时使用的CPU核数取决于Gaussian的Default.Route文件里的-P-设置。
- 可参考《Gaussian的安装方法及运行时的相关问题》

---

## 16. 高级拟合设置的操作
若需设置电荷等价性或特定片段总电荷等灵活拟合方式，需在Multiwfn的RESP模块界面中进行设置。
- 可参考《RESP拟合静电势电荷的原理以及在Multiwfn中的计算》

---

## 17. 跳过几何优化的脚本
若输入结构已足够好且不需自动优化，可使用RESP_noopt.sh代替RESP.sh，二者用法完全相同。

---

## 18. 含重元素体系的限制
若体系含有18号及以后的元素，因Gaussian无内置静电势拟合原子半径，无法通过脚本自动计算，需手动计算后用Multiwfn处理。

---

## 19. 文献引用要求
使用该方法计算RESP电荷时，请引用Multiwfn原文，引用方式见《Multiwfn FAQ》。
- 见

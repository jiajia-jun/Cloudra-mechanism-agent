---
key: t18782
title: ������һ��ORCA����scfÿһ������Ķ����ű�����sob��ʦ��gau_orca���Ӷ���Ĺ���
url: http://bbs.keinsci.com/thread-18782-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 17
---

# ������һ��ORCA����scfÿһ������Ķ����ű�����sob��ʦ��gau_orca���Ӷ���Ĺ��� — 知识卡片

## 1. ORCA EF值梯度计算与Gaussian对接

ORCA自带的EF值梯度计算功能非常完善，Gaussian可以通过external关键字调用ORCA进行EF值梯度计算和优化。beefly老师的博客和sob老师的gau_orca脚本提供了此类功能的相关介绍和实现方法。
- 相关链接：http://bbs.keinsci.com/thread-6860-1-1.html
- 相关链接：http://bbs.keinsci.com/thread-10141-1-1.html

---

## 2. Gaussian调用ORCA进行DLPNO-CCSD(T)小基组优化

Gaussian结合ORCA进行DLPNO-CCSD(T)小基组优化的流程在gau_orca项目中表现良好。通过设置特定的IOP参数，可以实现Gaussian调用外部ORCA程序执行高级别计算。
- 适用场景：需要利用DLPNO-CCSD(T)方法进行几何优化的情况
- 注意事项：需正确配置external脚本和IOP参数

---

## 3. DLPNO-CCSD(T)优化的IOP参数配置

使用Gaussian调用ORCA进行DLPNO-CCSD(T)优化时，需要在Route Section之后输入特定的IOP参数。这些参数控制了外部调用的各个细节，包括计算步骤、内存分配和收敛标准。
- 参数示例：
  - `1/18=40,29=20000,38=1,172=1/1,14;`
  - `2/12=2,17=6,18=5,29=3,40=1/2;`
  - `99/9=10/99;`
- 注意：需按顺序完整输入，不得随意更改数值

---

## 4. Gaussian启用EF梯度优化的IOP设置

Gaussian的EF梯度优化通常通过`opt=z-matrix`关键词结合特定IOP参数启用。若直接写关键词无效，需修改IOP（如`1/18=40/14(2)`）来调用数值微分功能。
- 关键IOP：`1/18=40/14(2)` 用于启用解析梯度
- 关键IOP：`1/18=40/14(-4)` 用于数值微分
- 限制：使用`opt=z-matrix`时，坐标需为内坐标或直角坐标，不建议使用冗余内坐标

---

## 5. EF梯度优化中的Onion模型参数

在EF梯度优化的IOP配置中，可以通过特定参数启用Onion模型（ONIOM类型的Embedding）。设置`4/113=1`和`4/114=1`分别代表使用file 747中的第1项作为嵌入项和激活ONIOM模型系统。
- IOP `4/113=1`：指定嵌入源
- IOP `4/114=1`：启用ONIOM/ECP
- IOP `4/22=1`：要求外部程序提供一阶导数

---

## 6. 自定义extorca程序调用Shell脚本

为了避免复杂的Fortran编程，可以将Gaussian的external接口改为调用Shell脚本来读取ORCA的输出。Shell脚本通过grep或awk提取能量并写入文件，供Fortran程序读取，这种做法开发效率高且易于调试。
- 替代方案：将extorca.f90改为调用Shell脚本
- 优势：代码修改简单，逻辑直观
- 参考链接：http://bbs.keinsci.com/thread-14848-1-1.html

---

## 7. external脚本调用中的nonstd关键词

在Gaussian中使用external功能时，必须在Route Section中显式添加`nonstd`关键词。如果只写`#p external='orca.sh'`而不加`nonstd`，L402步骤可能无法正确调用orca.sh，导致任务失败。
- 正确写法：`#p external='orca.sh' nonstd`
- 错误后果：外部调用被忽略或失败

---

## 8. 避免L114错误的IOP配置

Gaussian的L114步骤在处理EF优化时可能存在兼容性问题，导致archive文件为空。可以通过在Route Section添加`iop(99/5=0,99/9=10) skip=ov9 extraoverlays`来规避L114步骤，直接进入L999。
- 关键词：`skip=ov9 extraoverlays`
- IOP `99/5=0` 和 `99/9=10`：用于跳过特定链接
- 注意：此方法不适用于需要L114数据的情况

---

## 9. SCF迭代过程中的.gbw文件备份脚本

ORCA计算过程中，可以使用Shell脚本自动备份每一圈SCF迭代生成的.gbw文件（如`gbwsave.sh`）。脚本通过检测文件变化或迭代次数，将`mol.gbw`复制为带编号的文件名，以便在计算中断或出错时恢复。
- 核心逻辑：监控SCF迭代输出，复制并重命名.gbw文件
- 注意：需预留足够的磁盘空间

---

## 10. 检测SCF收敛的字符串匹配方法

在监控ORCA的SCF计算时，可以通过解析.out文件中的特定字符串（如"SCF CONVERGED"）来判断迭代是否完成。若文件内容较长，简单的grep或tail命令可能会消耗较多时间，建议优化读取方式。
- 关键字符串："SCF CONVERGED", "ORCA TERMINATED NORMALLY"
- 性能提示：避免频繁读取大文件

---

## 11. gbwsave脚本的并发写入Bug

gbwsave.sh脚本在执行时可能遇到并发写入导致的Bug，表现为`.gbw`文件被覆盖或备份编号混乱。这是因为脚本在读取和写入文件时存在竞争条件，且ORCA的输出文件中包含进度信息（如"Restarting incremental Fock matrix"）可能干扰判断。
- 现象：迭代编号跳跃，文件内容异常
- 原因：Shell脚本未处理文件锁和并发冲突

---

## 12. ORCA输出文件中的增量Fock矩阵干扰

ORCA在SCF计算过程中会输出"Restarting incremental Fock matrix formation"等信息。如果Shell脚本直接使用`tail -1`或简单的正则匹配读取文件末尾，可能会误匹配到这些包含星号的行，导致判断SCF状态出错。
- 干扰行特征：以`***`开头或包含特定英文字符
- 解决方案：优化正则表达式，精确匹配数值行或特定状态词

---

## 13. CCSD(T)与MP2联合能量计算策略

为节省计算资源，可采用"CCSD(T)/小基组 - MP2/小基组 + MP2/大基组"的方案近似CCSD(T)/大基组的能量。该方法假设高级别相关能对基组的依赖较小。
- 适用场景：需要高精度单点能但大基组CCSD(T)计算成本过高时
- 原理：利用基组误差的抵消效应

---

## 14. CCSD梯度优化与解析梯度的使用

在CCSD计算中，如果解析梯度可用（如Gaussian的L1110），应优先使用解析梯度进行优化。仅在解析梯度不可用时，才考虑使用数值梯度（EF值优化），因为数值梯度耗时极长。
- 解析梯度：L1110链接自动支持
- 数值梯度：计算量随原子数三次方增长

---

## 15. 高精度单点能计算工具enecalc

sob老师提供的`enecalc`工具支持Gaussian输出文件，可自动进行不同等级计算结果间的相互加减运算（如CBS外推或同构反应能计算）。该工具简化了复合能量方法的后续处理流程。
- 功能：自动能量组合与校正
- 链接：http://原作者.com/308

---

## 16. 检测ORCA进程状态的系统命令

在脚本中判断ORCA是否正在运行时，可以使用`ps aux | grep orca_scf`命令。通过统计进程数量，可以确定计算是否已开始或已结束。
- 命令：`ps aux | grep orca_scf | grep -v grep`
- 用途：防止在未运行时尝试读取输出文件

---

## 17. ORCA输入文件中的nofinalgrid关键词

在需要频繁读取中间.gbw文件的ORCA计算中，建议在输入文件中添加`nofinalgrid`关键词。这可以跳过最后耗时的精细积分网格计算，加快备份速度，虽然可能略微降低最终属性的精度。
- 位置：ORCA输入文件%scf块或Method行
- 效果：显著减少SCF结束前的等待时间

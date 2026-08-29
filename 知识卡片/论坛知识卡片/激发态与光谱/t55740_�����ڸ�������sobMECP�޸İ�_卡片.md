---
key: t55740
title: �����ڸ�������sobMECP�޸İ�(9.23����MECI֧��)
url: http://bbs.keinsci.com/thread-55740-1-1.html
domain: 激发态与光谱
source: keinsci
year: 2025
cards: 12
---

# �����ڸ�������sobMECP�޸İ�(9.23����MECI֧��) — 知识卡片

## 1. baneMECP 程序概述

baneMECP 是基于 Harvey 算法逻辑的程序，用于寻找最小能量交叉点（MECP）。该程序通过优化寻找两个态势能面交叉处的几何结构，对计算化学软件接口进行解析以获取能量和梯度。程序主体为 baneMECP.f，提供静态编译版本 banemecp_static 供使用。

---

## 2. MECP 优化的输入输出文件逻辑

MECP 优化过程会读取特定格式的文件，包括几何结构文件 astep1.xyz 以及对应的梯度文件 astep1.grad1 和 astep1.grad2。梯度文件格式需与 xyz 一致，且内部包含梯度数值，程序依据这些文件进行迭代优化。

---

## 3. 运行 MECP 优化所需的文件列表

执行 MECP 优化需要在当前目录下准备以下文件：程序文件 banemecp_static 或 baneMECP.f；初始结构文件 init.xyz；配置文件 xxx.conf；输入文件 xxx.inp；如果使用 external 模式，还需要自备能量和梯度计算的脚本。

---

## 4. 配置文件 [main] 段落设置

配置文件 [main] 段落用于设置计算环境，包括环境变量初始化（如 source ~/.bashrc）、加载计算软件模块（如 module load g16）。此外需定义输入输出文件后缀（如 INPUT_SUFFIX=gjf, OUTPUT_SUFFIX=log），并指定执行计算的具体命令（RUN_CMD）。

---

## 5. 配置文件 [scf] 段落与数据提取规则

[scf] 段落通过正则表达式定义如何从输出文件中提取能量和梯度。E 参数用于匹配能量值（如 SCF Done），GARD.Loacte 指定梯度数据起始位置，GARD.TargetColumns 指定梯度所在的列数，GARD.EndBy 设定读取结束标志。若文件中包含多个匹配项，可使用 LocateCount 参数指定第几次匹配时开始提取。

---

## 6. 输入文件头部参数定义

输入文件头部包含 %Prog 指定使用的配置文件，%Geom 指定初始几何结构文件（如 init.xyz，无需 end 结尾）。%Control 段落用于控制优化参数，包括最大循环次数（maxcyc）、临时文件目录（tmpdir）、是否保留临时文件（keeptmp）以及是否重启（restart）。

---

## 7. 输入模板 %InpTmplt 与占位符

%InpTmplt1 和 %InpTmplt2 分别定义了两个态的输入文件模板，其中使用方括号作为占位符。常用占位符包括 [geom] 表示插入几何坐标，[nstep] 表示步数，[xyzfile] 表示 xyz 文件路径。这些占位符在运行时会被实际内容替换，以生成具体的计算任务输入文件。

---

## 8. Gaussian 软件的输入模板示例

在针对 Gaussian 16 的配置中，%InpTmplt 设置了 checkpoint 文件、计算方法和电荷自旋多重度（如 0 1 和 0 3）。模板通过 [geom] 占位符引入坐标，并使用 guess(read) 读取猜测波函数，以计算基态和激发态的力。

---

## 9. 梯度计算类型指定 %GrpTmplt

%GrpTmplt 段落用于指定各态的梯度计算类型，例如 state1=scf 表示第一态使用 SCF 计算梯度。若第二态为 TD-DFT 激发态，则设置 state2=td，此时程序会采用解析导数计算精确梯度。

---

## 10. GAMESS 软件的 external 模式配置

对于 GAMESS 软件，特别是使用 MRSF-TDDFT 方法时，可采用 external 模式执行自定义脚本。此模式下 %InpTmplt 中的内容会被复制为 bash 脚本执行，脚本需将输出重定向到特定文件（如 mrsfout.tmp），并最终生成以 astep[nstep]_state1.${OUT_SUFFIX} 命名的输出文件供解析。

---

## 11. 程序执行命令与成果

准备完所有必要文件后，通过命令 ./banemecp_static xxx.inp > xxx.out 运行 MECP 优化。该程序已成功用于 GAMESS 的 MRSF-TDDFT 计算，能够找到 MECP 位置，并对原有的 Harvey 算法进行了修改和改进。

---

## 12. BPUPD 算法支持与调用

程序更新后新增了对 BPUPD 算法的支持，用于寻找 MECI（最小能量交叉点）。用户可以在输入文件的 %Control 字段中通过 algorithm=bpupd 参数指定使用该算法，若不指定则默认使用 Harvey 算法。

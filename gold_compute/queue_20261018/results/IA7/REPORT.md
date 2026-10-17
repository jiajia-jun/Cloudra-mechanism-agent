# IA7：Bergman 成环真实计算尝试

## 模型、假说与范围
气相热单分子 C6H4，q0/m1；无溶剂、水、酸碱、对离子。温度/压力未指定，本模型不含碰撞、热动力学或态交叉。假说为Z烯二炔C1–C6成键，耦合两炔弯曲及π键重排至p-benzyne；不是氢迁移。仅GFN2-xTB计算；未换Hamiltonian，未扩PM7桥接。

## 已完成的科学计算
- [R输入](R_opt.inp)、[原生日志](.cloudra/calc-771.out.log)、[原生末结构](R_opt.xyz)：ORCA GFN2-xTB Opt/NumFreq正常、收敛、0虚频，E=-14.708256716240 Eh，最低振动91.17 cm^-1。C1–C6=4.259 Å，C1–C2/C5–C6=1.202 Å，C3=C4=1.342 Å。原始Z种子的C2–C3–C4–C5二面角0.01°见[R内坐标](R.zmat)；[R末内坐标](R_opt.zmat)中C2–C3–C4–C5二面角-0.00°证实Z几何；工具立体感知未直接给E/Z。
- [P输入](P_opt.inp)、[原生日志](.cloudra/calc-772.out.log)、[原生末结构](P_opt.xyz)：同方法Opt/NumFreq正常、收敛、0虚频，E=-14.709098112370 Eh，最低431.16 cm^-1。平面六碳环、H仅连P行2/3/5/6，P行1/4无H且相距2.697 Å，符合p-benzyne骨架。XYZ键级感知失败（全部按单键回退），因此不以感知失败认定物种不存在，也不称其苯。
- 两个独立结构纯数值差为-0.52798 kcal/mol，仅GFN2-xTB m1端点模型诊断；**不交付为目标开壳单重态reaction_energy**。尚非IRC外端闭合；也没有势垒。

## 电子态及durable路径
目标P是开壳单重态。[P声明图](P.mol)保留两个自由基标记，构建器跳过力场。普通ORCA输入的electronic_character声明没有初始化反铁磁耦合、自旋纯态或提供自然占据；m1/--uhf0及分数占据不证明目标开壳单重态。因此以上P仅几何极小候选。
正式durable run [ts_0006](../../../../ts/ts_0006/process.json) 已准备（ts_prepare call_id tc_275a1a210b0e489a），初次停在映射；核候选0 P→R全原子[2,1,6,5,4,3,7,10,9,8]，H附着保持、新增1–6，无非目标断骨架。ts_resume call_id **tc_226d941588154d73**显式选择候选0后map完成，停guess，failure_class=**electronic_state_backend_unsupported**：当前GFN-xTB接口不能经--uhf0表示开壳单重态。没有实际TS/Freq/IRC作业。这是具体电子态接口能力阻塞，非本反应物理不可能，亦非共同waiting/refine故障。未用闭壳改标签规避，也未手动TS/IRC。

## 未完成与下一步
唯一边未完成：缺目标态可用初猜/电子设置、正式TS、目标重原子一虚频、双向IRC及各外端无约束Opt/Freq。没有可声明barrier或目标reaction_energy；不写accessible=false、不写零垒。原始输入、日志、hess/engrad/末几何均保留本目录。PM7/PySCF桥接由IA8唯一owner推进；本题未重复安装/桥接，未来需证实其开壳单重态能力及durable支持才可用于正式链。

工具诊断：format_converter无法读取两条external-xTB ORCA日志最后帧；改直接用计算产生的R_opt.xyz/P_opt.xyz，经internal_coordinates核几何，无改日志。log_parser使用external-MLIP文本回退提取正常结束、收敛和频率，未返回HOMO/占据或自旋诊断。

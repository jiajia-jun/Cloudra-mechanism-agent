# NR1 回填提案（BACKFILL_PROPOSAL）

生成者：Coordinator（NR1 lane）｜时间：2026-10-18 05:37 CST
目标题源：`ideapool/tasks/normal/NR1.json`（`gold.mechanism_graph` 目前只有 NR1_R 一个节点、edges 为空）

## 一、建议回填的三条边（均 verified=true，实测值）

| 边 id | from → to | via | 虚频 / cm-1 | barrier_kcal_mol | bond_changes（atom-map 1 基） |
|---|---|---|---|---|---|
| e1 | R（NC=O，甲酰胺） → INT-1a（N=CO） | TS1（ts_0032） | -1897.6514 | **46.32** | break [[1,5]]（N1–H5）；form [[3,5]]（O3–H5） |
| e2 | INT-1a → INT-1b | TS2（ts_0033） | -991.8673 | **22.80** | 空（构象边） |
| e3 | INT-1b → INT-1c | TS3（ts_0034） | -508.3050 | **7.25** | 空（构象边） |

能量依据（同程序同方法纯电子能，B3LYP/def2SVP+GD3BJ+UltraFine+SCF=Tight，气相）：
- R = -169.772982663（job 1121；重算 1210 同值）
- INT-1a = -169.751090026（job 1123；端点复算 1196 / 1215 同值）
- INT-1b = -169.745424789（job 1124；端点复算 1187 -169.745424733、1200 -169.745424119）
- INT-1c = -169.744844814（job 1125；端点复算 1192 同值）
- TS1 = -169.699169421（freq job 1206）→ 46.32 = (-169.699169421 + 169.772982663)×627.509474
- TS2 = -169.714755466（freq job 1148）→ 22.80 = -0.036334560×627.509474
- TS3 = -169.733877738（freq job 1149）→ 7.25 = -0.011546995×627.509474

## 二、(c) 采用替代方案，回填时必须原样写清

本交付的端点验证**不是**「双向 IRC 跑到端点」，而是：
> 短 IRC 方向区间（10 FORWARD + 10 REVERSE 点）+ 两端各自 Opt+Freq（0 虚频）+ interval proof

原因（平台限制，已实测）：durable 工作流目前无法把 IRC 的 MaxPoints/StepSize 传进 route——写进 `keywords` 会被 admission 判 keywords mismatch，写进 `end_setting` 能过校验但不进 route，Gaussian 因此用默认 10 点上限，IRC 在离极小值尚有距离处停止。端点能量一律取各自 Opt+Freq 的收敛值，IRC 过程帧只作方向证据、不作能量。

端点 Opt+Freq 作业：
- ts_0032：reactant opt 1210 / freq 1214；product opt 1215 / freq 1216
- ts_0033：reactant opt 1196 / freq 1198；product opt 1200 / freq 1202
- ts_0034：reactant opt 1187 / freq 1190；product opt 1192 / freq 1194

## 三、暂不回填的部分（缺口，保持 null）

- **e4 = INT-1c → HCN + H2O（via TS4 / ts_0035）**：本轮未定位一阶鞍点，E / 虚频 / barrier 一律 null。四次尝试：
  1) xTB path（refinement_runs=400）的 guess 落在化学错误区（末帧 C–O 2.3209、N–H4 1.0279、O3–H4 2.4004，H4 未迁移），ts_opt 停在第 24 步；
  2) 一维 O3···H4 约束扫描（job 1212）在 O···H 1.275 Å 处出现极大（E = -169.650950084，+58.9 kcal/mol），但该几何 Hessian（job 1222）在迁移方向为正曲率（最低实频 85.17 cm-1、唯一虚频 -137.9 属 H6 转子）⇒ 该极大是约束伪极大，不是鞍点；
  3) 二维 C2–O3 × N1–H4 网格（job 1223；收敛 18/36 点后因单点超步 l9999 中止）窗口内未见一阶鞍点结构：C2–O3 冻结 1.758 时 N1–H4 1.228/1.429/1.629 对应 O3–H4 2.554/2.496/2.424（H4 远离 O），而下一列 N1–H4 1.830 已出现 O3–H4 0.991 与 C2–N1 1.177（N≡C 形成）⇒ 质子转移发生在 1.63→1.83 Å 之间，该分辨率下没有「H4 同时桥接 N 与 O」的帧；
  4) 用峰区帧作 provided guess 的 OptTS 收敛到 -169.733877583、ν = -508.3812，与 ts_0034 构象鞍点数值/模态同构（H6 份额 0.933、逐键投影 ≤0.0005 Å）⇒ 滑回 O–H 转子；
  补充：job 1232（只约束 O3···H4、C–O 自由）12 点后因 `Step number 25 out of a maximum of 25` 中止，起点两点能量即回到 INT-1c 附近（+0.71 / +0.02 kcal/mol）⇒ 分子会把 C–O 闭回、H 退回 N，一维约束在该方向不可能给出鞍点；
  口径：扫描剖面与网格点永不写成势垒；SI 的 59.1 kcal/mol 只作背景对照，不参与回填。
- 第 4 个甲亚胺酸构象（job 1126，E = -169.741299945，0 虚频）不在本路径上，仅登记备查。
- HCN···H2O 松散复合物（job 1213，E = -169.720742486，0 虚频，结合能 ≈5.2 kcal/mol）可作为产物节点的可选证据，但 e4 未成立前不加边。

## 四、证据文件（原生日志，未改动）

- `gold_compute/queue_20261018/results/NR1/jobs/R_formamide_optfreq.log`（3398 行，sha256 前缀 5351eb3a）
- `gold_compute/queue_20261018/results/NR1/jobs/imidic_dNH180_dOH0_optfreq.log`（INT-1a）
- `gold_compute/queue_20261018/results/NR1/jobs/imidic_dNH0_dOH0_optfreq.log`（INT-1b）
- `gold_compute/queue_20261018/results/NR1/jobs/imidic_dNH0_dOH180_optfreq.log`（INT-1c）
- `ts/ts_0032/jobs/declaration_0011/frequency/frequency.log`（TS1，1206）
- `ts/ts_0033/jobs/declaration_0001/frequency/frequency.log`（TS2，1148）
- `ts/ts_0034/jobs/declaration_0001/frequency/frequency.log`（TS3，1149）

## 五、与文献的对照（仅背景，不参与回填数值）

SI（Nguyen et al., JPCA 2011, 115, 841-851；CCSD(T)/CBS）给 tsH-1,3 = 43.9、tsR-1a1b = 23.0、tsR-1b1c = 5.4、INT-1c-tsH2O = 59.1（相对各自起点）。本水平实测 46.32 / 22.80 / 7.25，偏差 +2.42 / -0.20 / +1.85 kcal/mol（0.9%–5.5%）。文献值**不得**回填为 gold。

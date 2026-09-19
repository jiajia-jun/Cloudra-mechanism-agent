# gold 逐边能垒战役 —— 剩余缺口盘点 + 批次二选择

生成：Coordinator（2026-09-17）

## 已完成（图上批次一 + 昨天算过的）
F1、NU6、NY3、NU3、HA1 —— 5 题 / 10 条边，已回填 gold、tests 绿。
（runs/ 下仅有 _smoke、F1、HA1、NU3、NU6、NY3）

## 全库剩余缺口边（gold.barrier_kcal_mol 仍为 null）

| 题 | 档 | 重原子 | 含H原子 | 缺口边 | 体系/说明 |
|---|---|---|---|---|---|
| **HA6** | hard | 6 | 16 | E1, EM1 | trans-3,4-二甲基环丁烯 4π 顺旋开环（成对 TS） |
| **HL1** | hard | 7 | 19 | E1, E4 | 丁酮肟 Beckmann（两处质子转移） |
| **NU5** | normal | 8 | 15 | E1 | Passerini（HCOOH→HCHO 质子转移） |
| **NA5** | normal | 8 | 22 | E1, E2, E3, E5 | Mannich（酸催化，4 步） |
| **HG2** | hard | 8 | 20 | E1, EM1 | 巴豆基丙烯基醚 Claisen（chair/boat 成对 TS） |
| NA2 | normal | 9 | 22 | E1, E3, E4, E5 | 丙酮自缩合 aldol |
| NO3 | normal | 9 | 20 | E1, E4 | 过酸/Criegee（两处质子转移） |
| NR1 | normal | 9 | 26 | E1, E3 | 频哪醇重排（两处质子转移） |
| NQ1 | normal | 10 | 20 | E2 | 芳基烯丙基醚 Claisen 再芳构化 |
| HE3 | hard | 16 | 35 | E1, EM1 | CBS 还原（大体系） |

合计剩余 22 条边 / 10 题。

## 批次二选择：原子数最小的一簇（重原子 ≤ 8）
**HA6, HL1, NU5, NA5, HG2**（5 题 / 11 条边）。
（9 重原子的 NA2/NO3/NR1、10 原子的 NQ1、16 原子的 HE3 留待后续批次）

| 题 | 电荷 | 溶剂（按题面） | 缺口边数 |
|---|---|---|---|
| HA6 | 0 | 气相 | 2 |
| HL1 | +1 | 气相（H2SO4 不显式建模，酸催化以 [OH3+] 体现） | 2 |
| NU5 | 0 | CPCM(DCM)（与已有 E2/E3/E4 的 DCM 口径一致） | 1 |
| NA5 | +1 | CPCM(water)（弱酸性水/醇） | 4 |
| HG2 | 0 | 气相 | 2 |

统一口径：B3LYP-D3(BJ)/def2-SVP（ORCA 6.1.1），ΔE‡ 纯电子能、逐边相对该步起点极小值；
Ts 恰 1 虚频 + IRC 双向 + 端点 0 虚频；fail-loud。nproc=1（本机 MPI 坑）。

## 批次二派发（2026-09-17）
swarm group_id = `grp_9a09b48995ea41b7ad968509b205bcae`，agent a-4，max_concurrency=3，5 题并发。
每题一个 small_mol；逐边值写 gold_compute/edge_barriers/computed/<TASK>.json；证据日志 gold_compute/campaign/runs/<TASK>/<EDGE>/。
完成后 AgentHub 回报 → 汇总 → 回填 gold 边（经生成器重跑，禁手改 JSON）→ tests/test_benchmark.py 守卫绿。
下一批候选（未派）：NA2 / NO3 / NR1（9 重原子）→ NQ1（10）→ HE3（16）。

## 计划变更（2026-09-17，用户）：改为“全部算完”
本战役从“补齐缺口边”升级为**全量自算**：
- 对每一题，把 gold 机理图的**每个物种极小值（起始反应物复合物 / 全部中间体 / 产物）+ 每条基元步的过渡态**都用统一口径算出来并给值；
- 原先带文献值的边也**按本战役口径重算，不保留文献值**（文献 anchor 与强制口径不一致，本战役即为其替代）。
- 批次二已就地位扩展：HA6/HG2 本就覆盖全部边；**HL1 扩到 E1–E5（5 步）、NU5 扩到 E1–E4（4 步）、NA5 扩到 E1–E5（5 步）**。已分别 notify 3 个在跑会话并广播（evt_6b4806682e5e4237）；NA5/HG2 尚在排队，待其启动后补发同指令。
- 后续批次（NA2/NO3/NR1/NQ1/HE3 及 easy 20 题）一律按“全量自算”口径执行。
- 验收不变：极小值 0 虚频、TS 恰 1 虚频、IRC 双向、fail-loud；<TASK>.json 覆盖全部边。

### 待确认口径
- “全部”是否含 **easy 档 20 题**（各 1 条边，现有文献值）：按“全部算完”字面应含，待用户确认后单独安排批次。

## 批次二交付（滚动）
- **HA6 ✅ 交付并独立复核（2026-09-17）**：E1(双外向)=31.24（TS −520.96，IRC 外端帧→R 与 (E,E) 产物，strict pass）；EM1(双内向)=42.31（TS −631.01，外端帧→R 与 (Z,Z)，strict pass）；**ΔΔ=11.06 有利外向**（与文献 11.3 一致、证伪 gold 的 2.0）。产物 gold_compute/edge_barriers/computed/HA6.json。Coordinator 已用 log_parser 复算两条 ΔE‡ 与虚频，一致。

## 子代理进度（滚动）
- HA6（as_e597129e088c4622）：已确认范围=1 起点极小值 + 2 产物极小值 + 2 成对 TS，无额外物种；R opt+freq(job429)、C2–C5 松弛扫描(job430) 在跑；ts_prepare 在 guess 阶段 blocked（xTB 无路径，同 HA1），改扫回退。
- HL1（as_888225683b164e21）：已扩到 E1–E5 全 5 步，在跑。
- NU5（as_e00525c442e548cc）：已扩到 E1–E4 全 4 步；ts_prepare ts_0001(E1) 端点已建/映射 15 原子，但 xTB MTD 到 100 循环上限未收敛（无垒 PT 预期）；已提醒按 §4 记 ≈0 + 证据，勿烧机时。
- HL1（as_888225683b164e21）：已扩到 E1–E5 全 5 步；ts_prepare ts_0003(E1) 两端点+19 原子映射完成，但 guess 阶段 blocked（xTB 路径搜索无产出 xtbpath.xyz，incomplete_artifacts），转人工路线（ts_guess interpolate/scan → 无约束 OptTS）。
- NA5 / HG2：排队中，启动后补发同指令。

## 内存口径（用户指示 2026-09-17，长期有效）
- 所有 ORCA 作业内存上限 **4–8 GB 总量**（本机并行数不多，大 reservation 只占队列）。
- ORCA %maxcore 是**每核**值；submit_compute_job.memory_mb 填**总量**（例 nproc=1→6000；nproc=4→8000，即 maxcore 2000）。
- 已通知批次二 5 个会话（calls）+ AgentHub 广播 evt_a24a982f9c4543fa；后续批次派发时写入指令。

## 批次二交付（滚动）
### NU5（2026-09-17）— 交付但 E1/E4 打回复核
- 独立复核：E2 TS −351.3（1 虚频，复算 8.20 ✓，strict PASS）；E4 TS −153.44（1 虚频，复算 31.68 ✓）；E4 IRC 双向未收敛（fwd50/bwd50，端点 [−436.5101,−436.4635]）；E1 无孤立 TS，约束扫描上界 11.9。
- 裁决：E2=8.20、E3=0.0（无垒）、I1/I2/I3/P 接受；**E1 需耦合/弛豫判定后按上界或 ≈0 入库（禁写无垒/已验证）；E4 需核对鞍点是否为 Mumm 酰基转移鞍点并争取 IRC 双向连通，否则记 partial（31.68 标 low-med）**。已把裁决发回 a-4。
- 产物：gold_compute/edge_barriers/computed/NU5.json。

### HL1 ✅ 交付（2026-09-17，气相全链，含连通性 caveat）
- E2 = 23.13（TS −364.0453，恰1虚频 −304.17；IRC 前向→I2，后向→−364.055 比 I1 高 ~17 kcal、非 I1 ⇒ 连通性部分成立）
- E5 = 21.06（TS −364.1538，恰1虚频 −653.06；IRC 外端帧落向 ~P 而非 I4 ⇒ 连通性不确定）
- E1 = null（气相 O-配位复合物非极小值；OptTS 5 虚频）；E3/E4 = null + 诊断（O-质子化亚胺酸在气相/CPCM 均非极小值，合并边 OptTS 6 虚频）
- 产物 computed/HL1.json（final_model=gas phase + reason、CPCM 诊断附录、remaining_gaps）。Coordinator 已 log_parser 复算两条 TS，能量与虚频一致。
- 注：E2/E5 的 TS 干净但与声明端点连通性有 caveat；E1/E3/E4 属模型限制，非返工项。
## 裁决记录（滚动）
- **HA6**：E1(外向)=31.24、EM1(内向)=42.31，**ΔΔ=11.07 有利外向**，与文献 11.3 一致、证伪 gold 的 2.0。回填时按计算值更新 gold.selectivity（经生成器）。
- **HL1 建模**：气相把 O-质子化算成 +22~24 上坡，与质子亲和能（PA(H2O)=691 vs 肟 O≈810–830 kJ/mol，应放热）矛盾 → 先做参考碎片核对定位坏几何；**维持气相 (A)**（E1 两侧净电荷同为 +1，溶剂为二阶效应）；批准一次 CPCM(water) 单点（RC/I1，最好含 N-质子化肟）以钉死「O- vs N-质子化哪个是极小值」——若气相下 N-质子化为极小值，则 E1 气相不可表示，需改模型。

## HL1 模型裁决（2026-09-17）
气相模型无法表示 gold 机理要求的 O-质子化中间体（H3O+···肟 质子自发上 N；O-质子化亚胺酸 I3 断裂回腈鎓+2H2O），且 CPCM 不改变 O/N 质子化差（+21.8 kcal）。**裁决：改用 CPCM(water) 全链一致重算**（代理题面酸性水相）；先测 I3 在 CPCM 下是否为 0 虚频极小值——是则跑完 E1–E5，否则 E3/E4 记 null+diagnostic，E1/E2/E5 仍给值。不上显式 H2SO4/微水合。O/N 差属模型化学，写 caveat，不凑「近无垒」。

## HL1 补充裁决（2026-09-17）
509 结果：CPCM(water) 下 I3(O-质子化亚胺酸+水) 不是极小值（O-质子自发转给旁水→I4，2 虚频）；孤立阳离子(507)才是极小值→旁水夺质子所致。**补充裁决：E3/E4 按「合并边」处理**——直接求 I2→I4（腈鎓+2水→中性亚胺酸+H3O+）单步：有鞍点则其 ΔE‡(相对 I2) 记为 E3、E4 记 subsumed；无垒则 E3≈0；两者都不成立才 null。note 必须写明 I3 非极小值及其诊断。

## HL1 最终模型裁决（2026-09-17，修正版）
实测证伪了「CPCM 更忠实」的假设：CPCM 下起点极小值不成立（cI1 软虚模 -44.9、cI2 4 虚频、cP -89.8、cRC 塌成 N-质子化）→ CPCM 的 ΔE‡ 无参考起点；气相 I1/I2/I4/P 均为 0 虚频真极小值。裁决：采用气相 (A) 全链一致（4 条 TS 全气相、相对气相起点极小值；无混用），CPCM 结果作诊断附录。此前「改用 CPCM 全链」的裁决撤销。

## 工具修复（2026-09-17）
- 多组分 + sp2 立体标记（C=N/C=C）导致 conformer_search / 多片段组装崩溃的 bug 已修复（issue #37 已关闭）：复测 conformer_search('O.C/C=C/C')、('O.CC/C(=N/O)/C') 均成功，且 (E) 立体正确保留（C–C=N–O ≈178.6°）。
- 结论：**今后多组分复合物组建一律走 conformer_search（含 E/Z 组分也可）**，不再需要「单组分建 3D + 刚性平移合并」的手工绕过。
- smiles_to_mol(generate_3d=True) 对多组分输入仍 fail-loud，属既定设计（多组分组装是 conformer_search 的职责）。

## 复现性观察（本机）
- ts_prepare 的 guess 阶段（xTB metadynamics 路径初猜）在本机对本批题**系统性失败**：HA1/NU3/F1/NU5(路径 100 循环未收敛)/HL1(incomplete_artifacts) 全部在 guess 阶段 blocked → 一律转 SOP 回退（IDPP 插值 / 约束-松弛扫描 → 无约束 OptTS）。另有：ts_prepare 无法把 OptTS/Freq/IRC 设成 nproc=1（本机 MPI 析 Hessian 会 SEGFAULT），进一步支持人工路线。后续批次可直接预期该回退。


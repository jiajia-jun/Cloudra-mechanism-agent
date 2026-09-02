# 参考答案（能垒标定）计算分工计划

> 目标：为 benchmark 题集生成**自算标定的参考答案能垒**（`gold.reference_computation`），
> 依据 `paper/benchmark_construction_narrative.md` 的锁定约定 ——
> **全档统一以 MACE-OMol25 为唯一物理计算金标准**（单引擎，2026-08-25 决策），
> 参考值 = 我们自算标定，**不把文献二手数字当 ground truth**（narrative §55）。
> 产物：`reference_computation.computed_by_us = True`，`verification = computed_by_us`。

---

## 一、题集范围（谁需要算）

| tier | 总题数 | 有 barrier 锚点 | 需要算（能垒标定） | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| easy | 30 | 28 | **30** | 单基元步，R→TS→P，方法舒适区 |
| normal | 30 | 15 | **30** | 多步网络（2–5 个 TS），需算每条边 |
| hard | 20 | 1 (+12 selectivity) | **20** | 需算主/副通道 TS + ΔΔ 选择性 |
| impossible | 40 (20 拒答 + 20 兄弟) | 0 | **0** | **不走能垒计算**（拒答验证档） |

**需要算能垒的总题数 = 30 + 30 + 20 = 80 题。**
impossible 档 40 题是「强多参考/拒答」档，gold 里已用 `accessible=false` 标注不可达节点，
参考答案本质是**确认不可算**（cas evidence 而非能垒数值），本轮不派能垒计算。

> 注意：impossible 档的 20 个 **sibling（S<id>）兄弟题**是单参考可算的正常题，理想上也应补能垒，
> 但它们被归入 impossible 档的"对照"语义，其 gold 字段目前不含 barrier。
> 若本轮只做能垒标定，sibling 可暂缓；若要完整，需另行确认是否给 S 系列补能垒。

---

## 二、方法口径（每题必须统一，否则无法合并成一致参考答案）

1. **方法等级**：MACE-OMol25（唯一金标准）。
   - 需要：`mace` python 包 + OMol25 权重（`.model` 文件）+ 引擎可调用。
   - **本机现状（2026-09 检查）**：`import mace` 在 `.venv-trans` / `chemai` / 系统 python 均失败，
     **无 xtb 二进制，未找到 OMol25 权重文件**。→ **开工前必须先把 MACE-OMol25 引擎安装/配置到位**。
2. **能垒口径（barrier_reference）**：统一 **`central_complex`**（TS 相对离子-偶极/反应物络合物），
   不要用 `reactants`（TS 相对分离反应物渐近线）——否则同一体系两个口径会误判成 ~10 kcal/mol 偏差。
   - easy 档生成器已统一 CENTRAL；normal/hard 照此。
3. **能垒类型（barrier_type）**：按题目实际定义，`Ea`/`ΔE‡`/`ΔH‡`/`ΔG‡`。
   - 机械 TS 常用 `ΔE‡`（电子能垒）；若要热力学量（ΔG‡）需频率校正。
   - **诚实缺测**：源数据未显式注明类型/口径时保持 `None`，不默认贴 Ea 标签。
4. **TS 验证**：每条边对应一个 TS。TS 必须是**一阶鞍点**（n_imag==1），
   并做**双向 IRC** 确认它连接正确的两个端点（reactant ↔ product / intermediate）。
   仅"找到一个鞍点"不算完成；必须 IRC 端点连通性通过。
5. **每题的产物**（回填 `ideapool/tasks/<tier>/<task_id>.json` 的 `gold`）：
   - `reference_computation.barrier_kcal_mol` = 该题**决定步（速率决定步）能垒**（MACE-OMol25 值）。
     - easy：唯一 TS → 该 TS 能垒。
     - normal：多步网络 → 最高能垒的步（RDS），或逐边记录（见下）。
     - hard：主通道 TS 能垒 + `selectivity.spread_kcal_mol` = 副通道 TS − 主通道 TS。
   - `reference_computation.level_of_theory` = "MACE-OMol25"。
   - `reference_computation.computed_by_us = True`。
   - `reference_computation.verification` = `computed_by_us`。
   - 若题有 DOI 参考，`reference_doi` 保留（作交叉核对，但不作 ground truth）。

---

## 三、工作分工（两桶均衡，family 保持化学连贯）

> 工作量模型：`题分 = Σ(TS数 × 体系重原子数)`（体系用反应物最大分子重原子数近似）。
> 均衡目标 420.5 分/人。**family 作为不可分单元**，同一反应族机理相通、计算设置可复用、
> 有利于交叉校验。产出两桶最终工作分均 ~420。

### PERSON 0（工作分 420）
**normal 大族 + hard 小族 + easy 混合**

| tier | family | 题号 | 题数 | TS | 工作分 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| normal | H | NH1 NH2 NH3 NH5 | 4 | 14 | 107 |
| normal | R | NR1 NR2 NR3 | 3 | 9 | 55 |
| normal | O | NO2 NO3 NO4 NO5 | 4 | 9 | 33 |
| normal | I | NI1 NI3 | 2 | 7 | 29 |
| normal | Y | NY2 NY3 | 2 | 7 | 28 |
| normal | Q | NQ2 NQ3 | 2 | 4 | 22 |
| hard | L | HL1 HL4 | 2 | 7 | 44 |
| hard | A | HA1 HA2 HA6 | 3 | 6 | 34 |
| easy | P | P1 P2 P3 | 3 | 3 | 17 |
| easy | D | D1 D3 D4 | 3 | 3 | 14 |
| hard | F | HF1 | 1 | 2 | 14 |
| hard | D | HD2 | 1 | 1 | 7 |
| easy | G | G1 G2 G3 | 3 | 3 | 7 |
| easy | F | F1 F2 F3 | 3 | 3 | 6 |
| easy | E | E1 | 1 | 1 | 3 |

（normal H 族最重，normal R 次之；hard L/A 为核心；easy 三族为轻量补充）

### PERSON 1（工作分 421）
**hard 大族 + normal A 族 + easy M/T/C/L/X 族**

| tier | family | 题号 | 题数 | TS | 工作分 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| normal | A | NA1 NA2 NA4 NA5 NA7 | 5 | 21 | 91 |
| hard | E | HE1 HE2 HE3 | 3 | 6 | 62 |
| hard | I | HI1 HI4 | 2 | 6 | 50 |
| easy | M | M1 M10 M12 M14 M15 M16 M3 M6 M8 | 9 | 9 | 37 |
| hard | G | HG1 HG2 | 2 | 4 | 32 |
| normal | U | NU1 NU5 NU6 NU7 | 4 | 10 | 32 |
| hard | J | HJ1 HJ2 HJ4 | 3 | 4 | 26 |
| normal | X | NX1 NX2 NX3 NX4 | 4 | 4 | 21 |
| hard | H | HH1 | 1 | 1 | 20 |
| hard | B | HB7 | 1 | 2 | 14 |
| hard | K | HK1 | 1 | 2 | 10 |
| easy | L | L1 L2 | 2 | 2 | 10 |
| easy | C | C1 C2 C3 | 3 | 3 | 6 |
| easy | T | T1 T3 | 2 | 2 | 5 |
| easy | X | X1 | 1 | 1 | 5 |

（hard E/I/G 立体化学主力；normal A 族最重；easy M 族含 1 个大体系 M1 需留意）

---

## 四、执行顺序建议（利于尽早校验管线）

1. **先各自做 1 个"试点题"**：PERSON 0 做 NH1（normal H，最重族）、PERSON 1 做 NA1（normal A）。
   跑通「TS 搜索 → n_imag==1 → 双向 IRC → 提取能垒 → 回填 JSON」全流程，产出 1 个 `computed_by_us=True` 样例。
2. **交叉校验收口**：两人各挑 1 个对方族的题交叉验证方法一致性（同族可复用设置）。
3. **按 family 批量**推进，每完成一个 family 更新一个进度清单。
4. **hard 档 SPECIAL**：每题需算**主 + 副两条通道 TS**，并给出 `selectivity.spread_kcal_mol`
   （ΔΔ = 副 TS − 主 TS，同一反应物络合物基准），不要把 ΔΔ 塞进 `barrier_kcal_mol`。

---

## 五、风险与待确认

- [ ] **MACE-OMol25 引擎未安装**（本机实测无 mace 包 / 无 xtb / 无权重）。需先装好再开工。
- [ ] hard 档 `accuracy.enabled=false`（HA1 等）——**当前 hard 不做 accuracy 评分**，只作参考记录。
      需确认是否本轮要补出 hard 档能垒（若 accuracy 仍 disabled，则本轮只补 SELECTIVITY 记录即可）。
- [ ] impossible sibling（S 系列）是否补能垒：待确认。
- [ ] normal 多步网络是否逐边记录能垒（还是只记 RDS 能垒）：待确认（建议逐边，便于 graph/self-consistency 层校验）。

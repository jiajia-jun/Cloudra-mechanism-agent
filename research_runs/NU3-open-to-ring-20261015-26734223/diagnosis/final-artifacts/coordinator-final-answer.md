## 结论：开链 H₂P–CH₂–CH₂–OH 与 PH₃ 四元环之间是「一步协同」连接（Supervisor 终审 ACCEPTED）

**实际物种**（B3LYP-D3(BJ)/def2-SVP、ORCA 6.1.1、气相、电荷 0、单重态）：
- reactant = 开链 2-羟基乙基膦 H₂P–CH₂–CH₂–OH（SMILES `OCCP`）= 给定最低点 `inputs/open.xyz`；独立复核 Opt+Freq 收敛、6 个零模 + 27 个实模、0 虚频、E=−496.635840 Ha。
- product = 环状 1,2-λ⁵-氧杂磷杂环丁烷（SMILES `C1C[PH3]O1`，4 元环 P-C-C-O，五配位 P 带 3 H）= 给定最低点 `inputs/ring.xyz`；0 虚频、E=−496.585622 Ha。
- TS1 = 协同一阶鞍点：E=−496.546904 Ha，恰好一个虚频 −1022.18 cm⁻¹（几乎纯迁移氢运动，重原子位移占比 0.004）。

**连接证据**：IRC 双向正常结束（前后各 20 点）。前向端 E=−496.583882（P–O 1.804 Å、H 在 P）→ 环；反向端 E=−496.629813（O–H 0.971 Å、H 在 O）→ 给定开链 A（羟基二面角 56.4° 与 A 的 56.6° 一致，而非被弃用的 76.7° 转动异构体）。两端几何与能量都落在 TS 与相应最低点之间 → 几何方向证明成立。净变化 = 生成一根 P–O 键 + 羟基氢由 O 迁移到 P。

**每步电子能垒（相对该步自身起始最低点，气相、电子能）**：开链→TS **+55.8 kcal/mol**（= −496.546904 −(−496.635840) = 0.088936 Ha）；环→TS **+24.3 kcal/mol**（= 0.038717 Ha）；环高于开链 **+31.5 kcal/mol**。

**竞争路径**：经膦鎓-醇盐甜菜碱 [H₃P⁺]CC[O⁻] 的两步机理被证伪并删除（无甜菜碱驻点；IRC 两侧无中间体盆地）。

**交付物**：`mechanism_graph.json`（通过 harness GoldMechanismGraph 校验，3 节点 + 1 条经 TS 的边，bond_changes break [9,7]/form [2,9],[2,7]，声明均可追溯到未改动的原生日志）、原生日志 `ts/ts_0001/jobs/declaration_0008/{ts_opt,frequency,irc,reactant_opt,reactant_frequency,product_opt,product_frequency}/.cloudra/calc-{18..24}.out.log` 与 `runs/verify_A/.cloudra/calc-25.out.log`（快照 `.cloudra/evidence/`）、`PROCESS.md`。

**局限**：单一电子结构级别、仅电子能垒（无 ZPE/Gibbs）；盐自由气相；每物种单一构象；超价 P 对方法敏感（半经验数字不可当作能垒）；短 IRC 依赖区间证明。

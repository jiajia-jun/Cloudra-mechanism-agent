# Hard 档候选反应池（立体化学：微观 3D 选择性与构型映射，候选 51 条）

> **⚠ 存量题源（2026-09-21）**：本文件是历史策展入库的 hard 题池，**不是**本轮「边选边填 gold」的候选清单。新候选不从本文档抄题；现行策略见 `gold_compute/README.md`。
>
> 日期：2026-08-31；**v3 重配 2026-09-09（20 → 10，见文末"定稿圈定"）**。Hard 档 = **立体化学**，三类考点：(i) 立体专一性（底物构型/几何 → 产物的确定性映射：Woodward–Hoffmann 规则、syn/anti 加成与消除、SN2 构型翻转、几何 → 产物判定）；(ii) 立体选择性竞争（两个非对映过渡态的能垒差决定 dr/ee/endo:exo/面选择性）；(iii) 构型稳定阻垒（阻转异构消旋化）。单步多步皆可，只要有立体上的选择性。本文件为评审用候选池（51 条超采，已定稿正选 20 条见文末"定稿圈定"），表格列结构与 `easy.md`/`normal.md` 完全对齐（同一套解析正则 ROW_RE/SMILES_RE/VERIFY_RE/能垒格规则可读）。**池子只增不删：落选条目留档。**
>
> **本文件取代 2026-08-25 旧版 hard.md**（H-01~H-38 编号条目体例，git 历史可查）：升级为表格线缆格式并重新编号（A1…L4），旧→新编号映射见文末"使用注意"；旧池 38 条全部保留，新增 13 条（B9 + J 族 6 + K 族 2 + L 族 4）扩充反应多样性。**勘误两条旧池立体化学错误**：旧 H-19（现 D1）把 trans-2,3-二甲基环氧乙烷酸水解产物误写为 dl-2,3-丁二醇——anti 开环翻转一个中心，实际得 **meso**（(2R,3S)），dl 才是错误非对映体；旧 H-05（现 A5）产物 canonical SMILES 与 (2E,4Z) 名称的对应关系已程序化核对（RDKit 确认 `C/C=C/C=C\C` = 2E,4Z）。
>
> **与 easy/normal 档的边界**：easy 已定稿 30 体系一律不重复——parent DA（D1）、未取代环丁烯/己三烯电环化（L1/L2）、Claisen（P3）、Cope（P1）、二亚胺+乙烯（G2）、氢硼化乙烯（G1）、联苯阻转（M1）等无立体维度的原型不再出现于本档；hard 的周环/加成条目全部带立体化学维度（取代基 torquoselection、构型映射、面选择性）。J1（二亚胺+2-丁炔）与 easy G2（二亚胺+乙烯）、J2（氢硼化 1-甲基环己烯）与 easy G1（氢硼化乙烯）同试剂不同考点（syn 立体专一/区域+立体），特此说明。normal 的 O1/O2（环氧乙烷氧转移）、X 族（开链 SN2/E2 取向）、R2（对称丙酮肟 Beckmann）等同样不重复——hard 的 D/J/L 族均取带立体化学的底物（L1 丁酮肟 E/Z 是 normal R2 对称肟的立体化版本，L2 是 normal O3 的迁移保持版本）。
>
> **舒适区约束（MACE-OMol25）**：候选体系以 CHNO 小分子为主，反应物装配体（含写入 SMILES 的试剂/催化剂）重原子 ≤20 为宜；超出者（H2=24、H3=22、I2=21、I3=21）与恰在边界者（H1=20、I1=20、I4=20）显式标注，去留由打标裁决。含 B（E1–E3/J2/K1/K2）、Si（G3）、S（I4/L4）、Br（J3/J6）、F（J4）的条目均在 OMol25 元素覆盖内但训练密度低于 CHNO，"舒适区自查"格有 ⚠ 标注。
>
> **SMILES 约定**：立体化学一律写入 SMILES（`@`/`@@` 四面体、`/`/`\` 双键几何）；均为原子数配平的净反应式；试剂与催化剂一律写入 SMILES 两侧（同 normal 2026-08-30 规范化），条件列只记录实验经典条件供参考；产物相对/绝对构型归属未经 3D 核对的，在 SMILES 后括注"构型待 3D 核对"。全部闭壳层单重态；气相/微溶剂化模型可算。
>
> **能垒锚点标注约定**（沿用 easy/normal，并按 hard 特点补充）：
> - 核实状态标签同前：[已核实]/[已核实存在]/[部分核实]/[未核实]。
> - **hard 档锚点多为选择性差值**（竞争非对映 TS 的 ΔΔG‡/ΔΔE‡，kcal/mol）或绝对阻垒（H 族消旋 ΔG‡）；纯立体专一条目（选择性为 0/1 映射、无能垒差数值）能垒格不写数字（barrier=null）。评分绑定 agent 实际计算证据（两个竞争 TS + IRC + 频率），锚点只作容差参考，不作 pass/fail 硬线；选题判据优先级沿用 normal：**MACE 可算性 > 机理判别价值 > 锚点完整度**，锚点缺失/口径偏差不构成剔除理由，最终参考值可由计算试算标定。
> - 解析纪律同 normal：能垒格第一个括号之前的第一个阿拉伯数字即锚点数值（dr/ee/比值/年份等一律进括号）；范围值取下界；DOI 以 `DOI 10.xxxx` 形式给出且后随中文标点。
> - **ΔΔ 记号注意**：选择性差值（ΔΔG‡/ΔΔE‡）按选择性锚点（selectivity spread，非绝对能垒）登记，不塞进绝对能垒字段。
> - gold 机理概要列写竞争通道（"竞争：…"）；多步条目按 ①②③ 列基元步并标（决速）。
>
> **验证**：全部 51 条通过 RDKit 程序化校验（SMILES 合法、重原子/H/电荷配平、E/Z 与 CIP R/S 归属核对；环 cis/trans 与环氧 syn/anti 归属经 3D 嵌入核对；syn/anti 无环产物归属经 Fischer-CIP 推导核对）。标注"构型待 3D 核对"者（B2–B4、B6–B9、C2/C3、E1/E3、F2、G2/G3、I1–I4、K2、L3/L4 产物）在 gold 构建阶段以文献结构图/计算 3D 锚定。

---

## A. Torquoselectivity 与电环化立体专一性（旧 H-01~H-07，7 个）

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| A1 | 3-甲基环丁烯顺旋开环（3-methylcyclobutene，torquoselectivity 母体）| `CC1CC=C1>>C=C/C=C/C`（主产物 (E)-1,3-戊二烯；(Z) 副产物见机理格），0/1 | 气相或惰性溶剂，~150–200 °C | 协同顺旋开环；给电子甲基**外向**旋转占优（σ→σ* 超共轭+位阻）→ (E) 主产物。竞争：内向旋转 → (Z) `C=C/C=C\C` | ΔΔE‡ = 5.71 kcal/mol（外向 33.04 : 内向 38.75，本战役 ORCA 5.0.2 B3LYP-D3BJ/def2-SVP 气相自算；两条 TS 频率、双向 IRC 及端点 E/Z 构型验证；旧约 2 kcal/mol 估计不作为本模型参考） | C,H；5 重原子；✅ | torquoselectivity 奠基计算研究（Houk 组）；Bachrach 教科书收录 |
| A2 | 3-甲酰基环丁烯"反向"torquoselectivity（3-formylcyclobutene，受体内向）| `O=CC1CC=C1>>C=C/C=C\C=O`（主产物 (Z)-2,4-戊二烯醛），0/1 | 加热 ~120–180 °C | 强 π-受体 CHO **内向**旋转占优（与给体相反）→ (Z) 主产物。竞争：外向 → (E) `C=C/C=C/C=O` | ΔΔE‡ ≈ 2–3 kcal/mol（内向:外向；Kirmse, Rondan & Houk 1984 JACS 106, 7989；Rudolf 1987 JOC 52, 3708，DOI 10.1021/jo00392a047；综述 Dolbier 1996 ACR 29, 471）[已核实] | C,H,O；6 重原子；✅ | "理论预测先于实验证实"经典案例 |
| A3 | 3-甲氧基环丁烯（3-methoxycyclobutene，强给体外向）| `COC1CC=C1>>C=C/C=C/OC`（主产物 (E)），0/1 | 气相热解 | 给体 OMe 强烈外向（孤对供体效应叠加位阻）→ 几乎单一 (E)。竞争：内向 → (Z) | ΔΔE‡ ≈ 5–7 kcal/mol（外向:内向，给体序列上限量级；Niwayama 1996 JOC 61, 2813；具体数值回查原文）[部分核实] | C,H,O；6 重原子；✅ | 与 A1/A2 构成给体-受体对比组 |
| A4 | 3-(甲氧羰基)环丁烯（methyl cyclobut-3-ene-1-carboxylate，受体内向）| `COC(=O)C1CC=C1>>C=C/C=C\C(=O)OC`（主产物 (Z)-2,4-戊二烯酸甲酯），0/1 | 加热 | 受体 CO2Me **内向**旋转占优（与 A2 同族，略弱）。竞争：外向 → (E) | ΔΔE‡ ≈ 2–3 kcal/mol（内向:外向；Niwayama 1996；Dolbier 1996 ACR 29, 471）[部分核实] | C,H,O；8 重原子；✅ | 受体系列内梯度 |
| A5 | 顺-3,4-二甲基环丁烯立体专一开环（cis-3,4-dimethylcyclobutene，WH 规则）| `C[C@@H]1C=C[C@@H]1C>>C/C=C/C=C\C`（meso 底物 (3R,4S) → 唯一产物 (2E,4Z)-2,4-己二烯，RDKit 已核对），0/1 | 加热 ~175 °C | 4π 热顺旋立体专一：meso 底物只给 (E,Z) 二烯（顺时针/逆时针殊途同归）。竞争：对旋为对称禁阻路径 | 能垒数值未核（顺旋唯一允许；对旋禁阻垒差 ≫10 kcal/mol 量级；Woodward & Hoffmann 1965 JACS 87, 395，DOI 10.1021/ja01080a054；Winter 1965 TL 实验）[已核实] | C,H；6 重原子；✅ | 轨道对称性守恒教科书标准案例 |
| A6 | 反-3,4-二甲基环丁烯（trans-3,4-dimethylcyclobutene，顺旋方向×位阻双重选择）| `C[C@H]1C=C[C@@H]1C>>C/C=C/C=C/C`（(3R,4R) 底物 → 主产物 (E,E)，双甲基外向），0/1 | 加热 | WH 允许的两条顺旋路径分别给 (E,E) 与 (Z,Z) `C/C=C\C=C/C`（登记阶段勘误：池初稿误写 `C/C=C\C=C\C`，该串实为 (Z,E)）；位阻使双外向占优。竞争：双内向 → (Z,Z) | ΔΔE‡ = 11.00 kcal/mol（双外向 31.31 : 双内向 42.31，本战役 ORCA 5.0.2 B3LYP-D3BJ/def2-SVP 气相自算；两条 TS 频率、IRC 方向及端点构型验证；原估 2–4 被证伪） | C,H；6 重原子；✅ | 对称性约束×torquoselection 双重考点 |

| A7 | (2E,4Z,6E)-辛三烯对旋闭环（6π disrotatory stereospecificity）| `C/C=C/C=C\C=C\C>>C[C@@H]1C=CC=C[C@@H]1C`（主产物 cis，meso (5R,6S)），0/1 | 加热 | 6π 热对旋立体专一：(E,Z,E) → cis。竞争：顺旋对称禁阻 → trans 不出现 | 能垒数值未核（Woodward & Hoffmann 1965；Marvell 组取代己三烯电环化系列 1970 前后）[部分核实] | C,H；8 重原子；✅ | 6π 电环化立体专一定义性案例 |

A6 自算证据：`computed_by_us=True`；类型为纯电子 ΔE‡，两条通道均以相同的反应物极小值为参考。gold 上 `/public/home/yyywaa/cloudra_workspace/HA6_gold_20260928/REPORT.md` 记录方法、能量、IRC 与构型检查；原始 ORCA 日志在同目录的 `rc/.cloudra/calc-552.out.log`、`ts/.cloudra/calc-555.out.log`、`ts/.cloudra/calc-556.out.log`、`irc/.cloudra/calc-566.out.log`、`irc/.cloudra/calc-567.out.log` 及 `irc/endpoints/.cloudra/calc-570..573.out.log`。

A1 自算证据：`computed_by_us=True`；类型为纯电子 ΔE‡，两条通道均以相同的反应物极小值为参考。gold 上 `/public/home/yyywaa/cloudra_workspace/HA1_gold_20260928/REPORT.md` 记录方法、能量、双向 IRC 与端点构型检查；原始 ORCA 日志在同目录的 `rc/.cloudra/calc-557.out.log`、`ts_E/.cloudra/calc-558.out.log`、`ts_Z/.cloudra/calc-559.out.log`、`ts_E/.cloudra/calc-560.out.log`、`ts_Z/.cloudra/calc-561.out.log`、`rc/.cloudra/calc-574.out.log`、`prod_E/.cloudra/calc-575.out.log`、`rc/.cloudra/calc-576.out.log`、`prod_Z/.cloudra/calc-577.out.log`。

## B. Diels–Alder endo/exo、π-面与立体专一性（旧 H-08~H-15 + 新 B9，9 个）

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| B1 | 环戊二烯 + 顺丁烯二酸酐（cyclopentadiene + maleic anhydride，Alder endo 规则）| `C1=CCC=C1.O=C1OC(=O)C=C1>>C1[C@@H]2C=C[C@H]1[C@@H]3[C@H]2C(=O)OC3=O`（endo，PubChem CID 2723766），0/1 | 室温或温和加热，苯/醚类溶剂 | 协同 [4+2]，动力学 **endo** 近乎专一（次级轨道相互作用+位阻）。竞争：exo | 自算 ΔΔE‡ = 1.71 kcal/mol（endo 8.46、exo 10.17；ORCA 5.0.2 B3LYP-D3BJ/def2-SVP CPCM(benzene)，共同零虚频 RC 652 参考；TS 654/655 各一相关虚频，IRC 660/661 双向收敛并通过几何方向核验，产物 658/659 零虚频及 endo/exo 构型核对）[自算核实] | C,H,O；12 重原子；✅ | 有机化学最著名的选择性规则 |
| B2 | 环戊二烯 + 丙烯醛（cyclopentadiene + acrolein，弱 endo 偏好基线）| `C1=CCC=C1.C=CC=O>>O=C[C@H]1[C@@H]2C=C[C@H]1CC2`（endo，构型待 3D 核对），0/1 | 无催化室温（Lewis 酸 BF3 催化增强 endo，本基准不加入） | 协同 [4+2]，无催化 endo 略占优。竞争：exo——偏好强度随取代基变化的梯度题 | ΔΔG‡ ≈ 0.6 kcal/mol（无催化 endo:exo ≈ 3:1；BF3 催化增至 ≈ 2（endo:exo >95:5）；Houk & Strozier 1973 JACS 95, 4094，DOI 10.1021/ja00793a070；Birney & Houk 1990 JACS 112, 4127）[已核实] | C,H,O；9 重原子；✅ | Houk 组 DA 选择性物理有机奠基文献 |
| B3 | 环戊二烯 + 丙烯腈（cyclopentadiene + acrylonitrile，最弱 endo 偏好）| `C1=CCC=C1.C=CC#N>>N#C[C@H]1[C@@H]2C=C[C@H]1CC2`（endo，构型待 3D 核对），0/1 | 加热 ~80–110 °C | endo 偏好明显弱于丙烯醛/顺酐（次级轨道作用随亲双烯体电负性减弱）。竞争：exo | ΔΔG‡ ≈ 0.3–0.8 kcal/mol（endo:exo ≈ 1.3–2:1 量级；Hoffmann & Woodward 1965；Sauer & Sustmann 1980 Angew 19, 779）[部分核实] | C,H,N；9 重原子；✅ | endo 规则强度梯度对照 |
| B4 | 环戊二烯 + 对苯醌（cyclopentadiene + p-benzoquinone）| `C1=CCC=C1.O=C1C=CC(=O)C=C1>>O=C1C=CC(=O)[C@H]2[C@@H]1[C@H]1C=C[C@@H]2C1`（endo 单加成物，构型待 3D 核对），0/1 | 室温，苯/乙醇 | 醌亲双烯体 endo 加成（醌羰基指向双烯 π 面下方）。竞争：exo；二次加成副通道 | ΔΔG‡ ≈ 1.5–2 kcal/mol（量级类比 MA 体系；Alder & Stein 1937；教材 Clayden ch.34）[部分核实] | C,H,O；13 重原子；✅ | Alder 学派经典底物组合 |
| B5 | 环戊二烯自二聚（cyclopentadiene dimerization，动力学 endo vs 热力学 exo）| `C1=CCC=C1.C1=CCC=C1>>C1C=C[C@@H]2[C@H]1[C@H]3C[C@@H]2C=C3`（endo，PubChem CID 10176158），0/1 | 室温自发二聚；高温平衡 | 动力学 **endo** 主产物；可逆条件下 exo 更稳定（热力学产物）——动力学/热力学选择性分离。竞争：exo；retro-DA | ΔΔG‡ ≈ 2 kcal/mol（endo:exo 动力学偏好量级；Woodward & Katz 1959 Tetrahedron 5, 70；Hoffmann & Woodward 1965）[部分核实] | C,H；10 重原子；✅ | endo/exo 与可逆性结合的最佳教学案例 |
| B6 | 呋喃 + N-甲基马来酰亚胺（furan + N-methylmaleimide，可逆 DA 选择性漂移）| `c1ccoc1.CN1C(=O)C=CC1=O>>CN1C(=O)[C@H]2[C@H](C1=O)[C@H]1C=C[C@@H]2O1`（endo，构型待 3D 核对），0/1 | 室温（动力学控制）或加热长时间（平衡） | 呋喃 DA 高度可逆：低温短时 **endo** 主产物；高温长时 **exo**（热力学）累积——endo 规则"失效"经典反例 | 能垒数值未核（选择性随时间/温度漂移，无单一数值锚点；教材 Clayden ch.34、Carey & Sundberg Part B）[已核实] | C,H,N,O；13 重原子；✅ | 可逆反应选择性漂移判别题，Hard 区分点 |
| B7 | 5-甲基环戊二烯 + 顺丁烯二酸酐（5-methylcyclopentadiene + MA，π-面 syn/anti）| `CC1C=CC=C1.O=C1OC(=O)C=C1>>O=C1OC(=O)C2C1C1C=CC2C1C`（anti 主产物；连接性程序化核对，syn/anti 归属名称锚定、构型待 3D 核对；注意 5-取代 Cp 经 1,5-H 迁移快速异构化，题目锁定该异构体），0/1 | 低温快速捕获 | 亲双烯体从取代基**异面（anti）**进攻占优（位阻控制）；给氧取代基（5-OAc）出现"反位阻"syn 偏好——电子 vs 位阻竞争标杆 | 能垒数值未核（anti:syn 位阻控制高比例；Gleiter & Paquette 1983 ACR 16, 328；Fallis 组 5-取代 Cp 实验系列 Can. J. Chem. 1984 起）[部分核实] | C,H,O；13 重原子；✅ | π-面选择性概念发源地体系 |
| B8 | (E)-1-甲氧基丁二烯 + 丙烯醛（regioselectivity × endo）| `CO/C=C/C=C.C=CC=O>>COC1C=CCCC1C=O`（邻位加成物即 OMe 与 CHO 相邻，endo 主，构型待 3D 核对），0/1 | 加热或 Lewis 酸催化 | FMO 预测"邻位"区域异构体为主 + endo 取向。竞争："对位"区域异构体；exo | ΔΔG‡ ≈ 1–2 kcal/mol（区域选择性量级；Houk 1973 JACS 95, 4092，DOI 10.1021/ja00793a069；Houk 1975 ACR 8, 361，DOI 10.1021/ar50095a001）[已核实] | C,H,O；10 重原子；✅ | DA 区域选择性 FMO 解释原始文献 |
| B9 | 环戊二烯 + 富马酸二甲酯（Cp + dimethyl fumarate，亲双烯体立体专一 cis principle）| `C1=CCC=C1.COC(=O)/C=C/C(=O)OC>>COC(=O)[C@H]1[C@@H](C(=O)OC)[C@H]2C=C[C@@H]1C2`（trans-2,3 加成物，构型待 3D 核对），0/1 | 加热 | E 亲双烯体取代基相对构型保持 → trans-2,3；与 B1（cis 亲双烯体 → cis 稠合）构成亲双烯体立体专一对照。竞争：endo/exo 取向叠加 | 能垒数值未核（cis principle 教材锚点；Alder & Stein 规则）[已核实] | C,H,O；15 重原子；✅ | DA 立体专一性（cis principle）定义性对照 |

## C. Nitrone [3+2] 环加成（旧 H-16~H-18，3 个）

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| C1 | C,N-二甲基硝酮 + 乙烯（最小 [3+2] TS 基线）| `C/C=[N+](/C)[O-].C=C>>CC1CCN(C)O1`（2,3-二甲基异噁唑烷），0/1 | 加热（模型体系） | 协同、异步性小的 [3+2]；无立体中心的基线体系（标定 TS 搜索与 FMO 类型归属，供 C2/C3 对照；旧池产物 SMILES 漏写 C-甲基，已勘误配平） | 能垒数值未核（Houk 1973 双论文 JACS 95, 7287，DOI 10.1021/ja00803a017 与 JACS 95, 7301，DOI 10.1021/ja00803a018）[已核实] | C,H,N,O；7 重原子；✅ | 1,3-偶极环加成 FMO 理论奠基双论文 |
| C2 | (Z)-C-苯基-N-甲基硝酮 + 丙烯酸甲酯（regio/endo-exo）| `C/[N+]([O-])=C/c1ccccc1.C=CC(=O)OC>>COC(=O)[C@@H]1C[C@H](c2ccccc2)N(C)O1`（5-CO2Me 区域异构体，相对构型待 3D 核对），0/1 | 苯，回流或室温长时间 | Type-I FMO 环加成：5-取代异噁唑烷区域异构体为主；endo（CO2Me 指向硝酮 π 面下）略占优。竞争：4-取代区域异构体；exo | ΔΔG‡ ≈ 2–3 kcal/mol（5- vs 4-取代区域选择性量级；Houk 1973 双论文；Tufariello in Padwa《1,3-Dipolar Cycloaddition Chemistry》Wiley 1984）[部分核实] | C,H,N,O；16 重原子；✅ | 硝酮化学最经典底物组合 |
| C3 | (Z)-C-苯基-N-甲基硝酮 + (E)-巴豆酸甲酯（[3+2] 立体专一性）| `C/[N+]([O-])=C/c1ccccc1.C/C=C/C(=O)OC>>CN1O[C@H](C(=O)OC)[C@@H](C)[C@@H]1c1ccccc1`（trans-4,5，相对构型待 3D 核对），0/1 | 加热，苯 | 双超面协同加成 → E→trans 立体专一（dr 接近单一）；(Z)-巴豆酸酯对照应给 cis-4,5。竞争：分步双自由基路径（剪枝考点） | 能垒数值未核（Huisgen 立体专一性原理 Angew 1963, 2, 565/633；Tufariello 1984）[部分核实] | C,H,N,O；17 重原子；✅ | [3+2] 立体专一性的定义性案例 |

## D. 小环开环立体专属性（旧 H-19~H-23，5 个）

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| D1 | 反-2,3-二甲基环氧乙烷酸催化水解（trans-2,3-dimethyloxirane，anti 开环→meso）| `[OH3+].C[C@H]1[C@@H](O1)C.O>>[OH3+].C[C@H]([C@H](C)O)O`（meso-2,3-丁二醇 (2R,3S)），+1/1 | 稀酸水溶液，室温 | ① 环氧 O 质子化；② 水背面 SN2 型开环（决速），受进攻碳构型翻转。trans 环氧 → **meso** 二醇；dl（(2R,3R)/(2S,3S)）为错误非对映体（旧池 H-19 误写为 dl，已勘误）。竞争：cis-2-丁烯经环氧水解应给 dl（整体 anti 双羟化的立体化学对应） | 能垒数值未核（教材标准案例 Clayden ch.33、Carey & Sundberg Part A ch.5；Fürst & Plattner 1949 HCA 32, 275）[已核实] | C,H,O；7 重原子；✅ | 环氧开环立体专属性必修案例 |
| D2 | 环氧环己烷亲核开环（cyclohexene oxide，Fürst–Plattner trans-diaxial）| `C1CCC2OC2C1.[OH-]>>O[C@@H]1CCCC[C@H]1[O-]`（trans-1,2-环己二醇盐 (1R,2R) 对映对之一），−1/1 | NaOH 水溶液加热 | 反式双轴向开环唯一产物：椅式构象锁定下 SN2 进攻必须轴向进入；顺式/双赤道开环为高能路径。竞争：无（构象锁死） | ΔE‡ = 16.42 kcal/mol（本战役自算；ORCA 5.0.2 B3LYP-D3BJ/def2-SVP CPCM(Water)，相对 IRC 连通的反应物离子偶极络合物极小值；双向 IRC 与两端零虚频验证。松散络合物构象导致参考态有数 kcal/mol 不确定性） | C,H,O；8 重原子；✅ | 构象分析×立体电子效应经典交汇 |
| D3 | 氧化苯乙烯酸/碱条件区位翻转（styrene oxide，regioselectivity switch）| `c1ccccc1[C@@H]2CO2.C[O-]>>COC[C@@H](c1ccccc1)[O-]`（碱性：进攻末端碳，苄位中心不动 (R) 保持），−1/1 | NaOMe/MeOH（碱）；MeOH/H⁺（酸，走苄位进攻翻转，写入机理格） | 碱性 SN2 进攻末端碳（位阻控制），苄位立体中心不受触及；酸性条件下进攻苄位（部分 SN1 特征稳定化）并构型翻转——区位随条件翻转。竞争：两条区位通道互为竞争（条件依赖） | ΔΔG‡ ≈ 1.5–3 kcal/mol（区位选择性量级；教材 Clayden ch.33、March）[已核实] | C,H,O；11 重原子；✅ | 区域/立体选择性耦合经典 |
| D4 | 环氧丙烷碱性开环（propylene oxide，最小 SN2 位阻选择性）| `C[C@H]1CO1.[OH-]>>C[C@H]([O-])CO`（(S)→(S) 空间保持，末端进攻），−1/1 | NaOH 水溶液 | SN2 少取代碳进攻 ≫ 多取代碳；立体中心不被触及（区域选择性题+立体"不动点"对照）。竞争：多取代碳进攻 | ΔΔG‡ ≈ 2–3 kcal/mol（区位选择性量级；教材 Clayden ch.33）[已核实] | C,H,O；5 重原子；✅ | 最简位阻控制区位选择性模型 |
| D5 | 2-甲基氮杂环丙烷活化开环（2-methylaziridine，O/N 类比）| `[OH3+].C[C@H]1CN1.CO>>[OH3+].C[C@@H](OC)CN`（(S) 底物→进攻取代碳构型翻转为 (R)），+1/1 | 酸性醇溶液 | N 质子化活化后进攻**取代碳**占优（与未活化底物相反），背面进攻构型翻转；与 D3 环氧体系构成 O/N 类比对照。竞争：进攻末端碳 | 能垒数值未核（Dermer & Ham《Ethylenimine and Other Aziridines》Academic Press 1969；教材 Clayden ch.33）[部分核实] | C,H,N,O；7 重原子；✅ | 氮杂环化学标准专著覆盖体系 |

D2 自算证据：`computed_by_us=True`；类型为纯电子 ΔE‡，参考态为 IRC 反应物侧重新优化的离子偶极络合物极小值。gold 上 `/public/home/yyywaa/cloudra_workspace/HD2_gold_20260927/REPORT.md` 记录方法、几何及检查；原始 ORCA 日志为同目录 `ts/typ_05b/.cloudra/calc-545.out.log`（TS）、`ts/typ_05b/.cloudra/calc-546.out.log`（IRC）、`rc/.cloudra/calc-569.out.log`（反应物）、`product/.cloudra/calc-563.out.log`（产物）。

## E. 羰基 π-面选择性与手性还原（旧 H-24~H-26，3 个）

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| E1 | (S)-3-苯基-2-丁酮硼氢化（Felkin–Anh π-面选择）| `[BH4-].CC(=O)[C@@H](C)c1ccccc1>>C[C@@H]([O-])[C@@H](C)c1ccccc1.[BH3]`（Felkin–Anh 主非对映体 (2R,3S)：氢负转移不动 C3，(S)-底物 C3 保持——旧写 (2S,3R) 令 C3 反转、从 (S)-底物不可达，2026-08-31 登记阶段勘误；另一非对映体 (2S,3S) `C[C@H]([O-])[C@@H](C)c1ccccc1`），−1/1 | NaBH4/MeOH 或 LiAlH4/Et2O，0 °C–室温 | Felkin–Anh 构象（Ph 垂直羰基平面，亲核试剂沿 Bürgi–Dunitz 从最小取代基侧进入）预测主非对映体。考核：无环构象系综+σ* 立体电子效应 | ΔΔG‡ ≈ 0.7–0.9 kcal/mol（dr ≈ 3–5:1（LAH 量级）；Chérest, Felkin & Prudent 1968 TL 2199，DOI 10.1016/S0040-4039(00)89719-1；Paddon-Row, Rondan & Houk 1982 JACS 104, 7162）[已核实] | C,H,O,B；12 重原子；⚠ 含 B | 无环羰基面选择性最被引用模型体系 |
| E2 | 4-叔丁基环己酮还原（axial vs equatorial attack）| `[BH4-].CC(C)(C)C1CCC(=O)CC1>>CC(C)(C)[C@H]1CC[C@H]([O-])CC1.[BH3]`（trans：赤道 O⁻，轴向进攻主产物；cis 副产物 `CC(C)(C)[C@H]1CC[C@@H]([O-])CC1`），−1/1 | LiAlH4/Et2O 或 NaBH4/醇 | 构象锁定环己酮：小亲核试剂**轴向进攻**占优（扭转应变控制，Wu–Houk）→ 赤道醇为主；大位阻试剂反转为赤道进攻 | ΔΔG‡ ≈ 1.3–1.5 kcal/mol（LAH 约 8–9:1 量级；Chérest 1968；Wu, Tucker & Houk 1991 JACS 113, 5018，DOI 10.1021/ja00013a042）[已核实] | C,H,O,B；12 重原子；⚠ 含 B | 构象-选择性耦合教科书标杆 |
| E3 | CBS 还原苯乙酮简化模型（Corey–Bakshi–Shibata，手性催化剂诱导）| `[BH3].CC(=O)c1ccccc1.C[C@H]1COBN1>>C[C@@H](OB)c1ccccc1.C[C@H]1COBN1`（(S)-催化剂→(R)-产物烷氧基硼烷，归属待 gold 核对），0/1 | THF，−20 °C~室温，催化量 oxazaborolidine | 双配位六元环椅式 TS：酮氧配位催化剂 B、BH3 配位 N，B–H 从较小位阻面转移。考核：手性催化剂-底物装配体 3D 构想 | ΔΔG‡ ≈ 2 kcal/mol（对应 ≈95% ee 量级，实验 CBS 苯乙酮 96–97% ee；Corey, Bakshi & Shibata 1987 JACS 109, 5551，DOI 10.1021/ja00252a056；Quallich 1994 JACS 116, 8516；Alagona 2003 DOI 10.1021/ja034928d）[已核实] | C,H,O,N,B；16 重原子；⚠ 含 B | 诺贝尔级不对称催化，小模型 TS 反复复核 |

## F. 氢键导向环氧化（旧 H-27~H-28，2 个）

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| F1 | 环己-2-烯-1-醇过酸环氧化（Henbest directed epoxidation）| `OC1C=CCCC1.O=COO>>O[C@H]1[C@H]2O[C@H]2CCC1.O=CO`（cis：OH 与环氧同侧，3D 嵌入已核对 syn），0/1 | 过甲酸，CH2Cl2，0–25 °C | 烯丙位 OH 与过酸氢键缔合导向 **syn/cis** 环氧化（Henbest 规则），蝶形 TS。竞争：trans（非导向面） | 自算 ΔΔE‡ 3.87 kcal/mol（同一最低反应物络合物作参考：cis 16.82、trans 20.70 kcal/mol；ORCA 5.0.2 B3LYP-D3(BJ)/def2-SVP CPCM(CH2Cl2)，TS、IRC、端点验证；原实验 ΔΔG‡ ≈ 1.4 kcal/mol 属不同能量口径，不能直接当电子能真值）[自算核实] | C,H,O；11 重原子；✅ | 底物导向立体选择性开端文献 |
| F2 | 无环手性烯丙醇过酸环氧化（(S)-(E)-pent-3-en-2-ol，acyclic π-face）| `C/C=C/[C@H](C)O.O=COO>>C[C@H]1O[C@@H]1[C@H](C)O.O=CO`（主/次归属按 Houk 模型，构型待 3D 核对），0/1 | 过酸，非配位溶剂 | OH 导向+无环构象竞争（"inside alkoxy"效应）预测主非对映体；比环状体系弱，更考验构象搜索完备性 | ΔΔG‡ ≈ 0.5–0.8 kcal/mol（dr ≈ 2–3:1 量级；Houk 1986 Science 231, 1108；Chamberlin 1987 JACS 109, 672）[部分核实] | C,H,O；10 重原子；✅ | Houk"立体选择性反应的理论与建模"名文体系 |

## G. [3,3]-σ 迁移：椅式/船式竞争（旧 H-29~H-31，3 个）

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| G1 | meso-3,4-二甲基-1,5-己二烯 Cope 重排（chair TS 立体专一）| `C=C[C@H](C)[C@H](C)C=C>>C/C=C\CC/C=C/C`（meso (3S,4R) 底物 → (2E,6Z)-辛-2,6-二烯；对称分子 (E,Z)≡(Z,E)，RDKit 已核对），0/1 | 气相热解 ~200–250 °C | 椅式 TS ≫ 船式 → meso 底物立体专一给出 (E,Z) 二烯。竞争：船式 TS（给 (E,E)/(Z,Z) 组合） | ΔΔG‡ ≈ 5.8 kcal/mol（椅:船实验差；高级别计算椅-船差 11.4（CASPT2，Khaledy–Houk 2003 转引）；Doering & Roth 1962 Tetrahedron 18, 67；Khaledy 2003 JOC 68, 572，DOI 10.1021/jo020595b）[部分核实] | C,H；8 重原子；✅ | Cope 立体化学"罗塞塔石碑"实验 |
| G2 | (E,E)-巴豆基丙烯基醚 Claisen 重排（chair preference，syn/anti）| `C/C=C/CO/C=C/C>>C=C[C@H](C)[C@H](C)C=O`（syn-2,3-二甲基戊-4-烯醛 dl 对之一，(S,S) 经 Fischer-CIP 推导核对），0/1 | ~150–200 °C | (E,E)-巴豆基丙烯基醚 Claisen：[3,3]-σ 重排；chair TS（两甲基 pseudo-equatorial）→ anti(1,2-trans) 为优势通道（较低垒），boat TS → syn(1,2-cis) 为次通道；ΔΔE‡≈3.28 kcal/mol 有利 anti。 | ΔΔG‡ ≈ 3.28 kcal/mol（syn:anti 量级；椅:船 ≥ 95:5；Vance, Rondan, Houk 1988 JACS 110, 2314，DOI 10.1021/ja00215a059；Vittorelli 1968 HCA 51, 1457）[部分核实] | C,H,O；8 重原子；✅ | Claisen 立体化学实验（Schmid）+计算（Houk）双经典 |
| G3 | (E)-巴豆基丙酸酯 Ireland–Claisen（硅基烯酮缩醇几何×椅式）| `C/C=C/CO/C(=C/C)/O[Si](C)(C)C>>C=C[C@H](C)[C@H](C)C(=O)O[Si](C)(C)C`（(E)-巴豆基 + (Z(O))-烯酮缩醇，几何经 RDKit 核对；syn/anti 归属待 gold 核对），0/1 | LDA/THF/−78 °C → TMSCl → 室温重排（本题从烯酮缩醇出发，单步） | 烯酮缩醇几何决定相对构型：E(O)/Z(O) 分别经椅式 TS 给出相反非对映体；取代基假赤道排布。竞争：船式 TS | 能垒数值未核（dr 常 >95:5；E(O)/Z(O)→syn/anti 助记对应关系待 gold 核对；Ireland, Mueller & Willard 1976 JACS 98, 2868，DOI 10.1021/ja00426a033；Khaledy 2003 JOC 68, 572，DOI 10.1021/jo020595b）[已核实] | C,H,O,Si；13 重原子；⚠ 含 Si | 立体选择性烯醇化学教科书反应 |

## H. 阻转异构消旋阻垒（旧 H-32~H-34，3 个）

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| H1 | 1,1′-联萘消旋化（1,1′-binaphthyl atropisomerization）| `C1=CC=C2C(=C1)C=CC=C2C3=CC=CC4=CC=CC=C43>>C1=CC=C2C(=C1)C=CC=C2C3=CC=CC4=CC=CC=C43`（Ra↔Sa 消旋体表示；轴手性以 3D 锚定），0/1 | 热消旋 ~50 °C，DMF 隐式溶剂 | 两条 peri-H 对穿的消旋路径共用 P/M 端点：syn（扭转角约 0°）较低，anti（约 180°）较高；自算电子能垒差 9.35 kcal/mol，取代旧“约 1”估计 | 自算 ΔE‡ 23.01 kcal/mol（syn）与 32.36 kcal/mol（anti），相对 P 极小值；ORCA 5.0.2 B3LYP-D3(BJ)/def2-SVP CPCM(DMF)，TS 各一相关虚频，双向 IRC 及两侧零虚频端点对应 P/M；gold 工作区 `HH1_gold_20260928/REPORT.md`，作业 615–618、621、623–627；旧实验 ΔG‡ ≈ 23.5 kcal/mol（50 °C 半衰期约 14.5 min）不是本题电子能垒真值 [自算核实] | C,H；20 重原子（恰在边界）；✅ | 轴手性消旋动力学第一个定量经典体系 |
| H2 | 6,6′-二硝基联苯-2,2′-二甲酸消旋（6,6′-dinitrodiphenic acid，首例拆分阻转异构体）| `O=C(O)c1cccc([N+](=O)[O-])c1-c1c(C(=O)O)cccc1[N+](=O)[O-]>>O=C(O)c1cccc([N+](=O)[O-])c1-c1c(C(=O)O)cccc1[N+](=O)[O-]`（消旋体表示），0/1 | 加热消旋（溶液） | 邻位四取代（2,2′-COOH+6,6′-NO2）使室温可拆分；阻转阻垒测定对象 | ΔG‡ ≈ 28–32 kcal/mol（估计值，gold 构建需查原始动力学文献或 Eliel 教材表格；Christie & Kenner 1922 JCS 121, 614，DOI 10.1039/CT9222100614）[未核实] | C,H,N,O；**24 重原子，超预算标注**；闭壳层 ✓ | 阻转异构现象开天辟地文献（1922 首例拆分） |
| H3 | 1,1′-联萘-2,2′-二酚消旋（BINOL racemization barrier）| `Oc1ccc2ccccc2c1-c1c(O)ccc2ccccc12>>Oc1ccc2ccccc2c1-c1c(O)ccc2ccccc12`（消旋体表示），0/1 | 高温（>100 °C）溶液消旋；酸/碱催化加速 | 消旋阻垒高（中性条件 100 °C 长期稳定）；syn/anti 路径竞争 | ΔG‡ ≈ 35–37 kcal/mol（diglyme 150 °C 20 h 仅 ~10% 消旋实验锚点；Can. J. Chem. 1980, 58, 2134，DOI 10.1139/v80-021；DFT 阻垒 Meca, Řeha & Havlas 2003 JOC 68, 5677 页码待回查）[部分核实] | C,H,O；**22 重原子，略超预算标注**；闭壳层 ✓ | 不对称催化最著名轴手性骨架 |

## I. 手性小分子/氢键催化诱导（旧 H-35~H-38，4 个）

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| I1 | 脯氨酸催化直接 Aldol（List–Barbas aldol：acetone + benzaldehyde）| `CC(C)=O.O=Cc1ccccc1.O=C(O)[C@@H]1CCCN1>>CC(=O)C[C@H](O)c1ccccc1.O=C(O)[C@@H]1CCCN1`（(S)-脯氨酸催化，产物绝对构型归属待 gold 核对），0/1 | 20–30 mol% (S)-脯氨酸，DMSO，室温 | 烯胺机理+Houk–List 椅式 TS（羧基质子转移+氢键网络），单分子脯氨酸参与。① 烯胺生成；② C–C 加成（立体决定步）；③ 水解。竞争：另一对映面 TS | ΔΔG‡ ≈ 1.2 kcal/mol（苯甲醛 ee ≈ 60–76%（对硝基苯甲醛 76%，List 2000）；List, Lerner & Barbas 2000 JACS 122, 2395，DOI 10.1021/ja994280y；Bahmanyar & Houk 2001 JACS 123, 11273，DOI 10.1021/ja011403h；Hoang 2003 JACS 125, 16，DOI 10.1021/ja028634o）[已核实] | C,H,N,O；20 重原子（恰在边界）；✅ | 2021 诺贝尔化学奖核心反应+Houk–List TS 模型 |
| I2 | 脯氨酸催化 Mannich（丙醛供体，syn-β-氨基醛）| `CCC=O.C/N=C/c1ccccc1.O=C(O)[C@@H]1CCCN1>>C[C@H](C=O)[C@@H](NC)c1ccccc1.O=C(O)[C@@H]1CCCN1`（syn 主产物，归属待 gold 核对；旧池 H-36 为丙酮供体单中心版，本题换丙醛供体以考核 dr+ee 双维），0/1 | 脯氨酸催化，DMSO/DMF，室温 | 烯胺对亚胺 si/re 面进攻 → **syn** 非对映体高 dr+高 ee；TS 中羧基同时活化亚胺并定向烯胺。竞争：anti；另一对映面 | 能垒数值未核（实验 syn:anti >10:1、ee >90% 量级；List 2002 JACS 124, 8272（醛供体 syn Mannich，DOI 未核）；Bahmanyar, Houk, Martin & List 2003 JACS 125, 2475）[部分核实] | C,H,N,O；**21 重原子，略超预算标注**；闭壳层 ✓ | List 诺奖工作+Houk 组定量 TS 分析 |
| I3 | Hajos–Parrish 环化（proline-catalyzed intramolecular aldol 去对称化）| `CC(=O)CCC1(C)C(=O)CCC1=O.O=C(O)[C@@H]1CCCN1>>C[C@]12CCC(=O)C[C@]1(O)CCC2=O.O=C(O)[C@@H]1CCCN1`（双环酮醇；连接性经配平与环系程序化核对，立体归属待 gold 核对），0/1 | 1–3 mol% (S)-脯氨酸，DMF/DMSO，室温 | 去对称化分子内羟醛：① 烯胺生成；② 烯胺进攻两个前手性羰基之一（立体决定步）；③ 水解得双环酮醇（可再脱水成 Wieland–Miescher 型烯二酮，本题止于酮醇）。竞争：另一前手性羰基/另一面 | 能垒数值未核（ee ≈ 93%（原始 Hajos–Parrish，已优化至 >99%）；Hajos & Parrish 1974 JOC 39, 1615；Bahmanyar & Houk 2001 JACS 123, 12911，DOI 10.1021/ja011714s；Hoang 2003 DOI 10.1021/ja028634o）[已核实] | C,H,N,O；**21 重原子，略超预算标注**；闭壳层 ✓ | 有机催化"创世纪"反应（1971/1974） |
| I4 | 手性硫脲催化 Strecker 简化模型（thiourea-catalyzed Strecker）| `C#N.C/N=C/c1ccccc1.CC[C@H](C)NC(=S)NC>>CN[C@H](C#N)c1ccccc1.CC[C@H](C)NC(=S)NC`（(S)-催化剂模型，产物构型归属待 gold 核对），0/1 | 低温，甲苯（模型体系为计算对象） | 硫脲双氢键结合亚胺 N、定向 + 多重非共价作用稳定优势 TS（Zuend–Jacobsen 机理）。注意：催化剂为人工截短模型，gold 以"催化剂两个非对映 TS 竞争"形式出题，不直接对标实验 ee | ΔΔG‡ 预期 ≈ 1–2 kcal/mol（模型体系量级；Sigman & Jacobsen 1998 JACS 120, 4901，DOI 10.1021/ja980139y；Zuend & Jacobsen 2009 JACS 131, 15358）[已核实] | C,H,N,O,S；20 重原子（恰在边界）；⚠ 含 S | 氢键有机催化奠基工作（Jacobsen 组） |

## J. syn/anti 加成与消除立体化学（2026-08-31 新增，6 个）

> 与 easy G1/G2（乙烯，无立体维度）和 normal X 族（开链取向竞争）互补：本族全部是"几何/构象 → 产物构型"的立体专一映射——炔顺式还原（J1）、syn 氢硼化（J2）、溴鎓 anti 加成（J3/J6）、构象锁定 anti-E2（J4）、烯烃环氧化几何保持（J5）。

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| J1 | 二亚胺顺式还原 2-丁炔（diimide + 2-butyne，syn 加成立体专一）| `N=N.CC#CC>>N#N.C/C=C\C`（唯一产物 (Z)-2-丁烯，RDKit 已核对），0/1 | 气相/溶液温和加热 | 协同 [σ2s+σ2s+π2s] 双氢转移（cis-HN=NH 供体），syn 立体专一 → 唯一 cis 烯。竞争：分步/反式通道（对称禁阻，高垒背景） | 能垒数值未核（二亚胺还原立体专一性教材锚点；与 easy G2（乙烯，TST/机理判别）同试剂互补——本题考 syn 立体维度；具体垒值量级参 G2）[已核实] | C,H,N；6 重原子；✅ | 炔烃顺式还原教科书原型 |
| J2 | 1-甲基环己烯氢硼化（hydroboration，syn + anti-Markovnikov）| `[BH3].CC1=CCCCC1>>C[C@H]1[C@H](B)CCCC1`（trans-2-甲基环己基硼烷：B 与甲基 trans，3D 嵌入已核对），0/1 | BH3·THF，0 °C–室温 | 4 中心环状 TS，H 与 B 同面加成（syn 立体专一），B 至少取代碳（anti-Markovnikov 区域选择性）→ trans 关系唯一。竞争：Markovnikov 区域异构体；反面加成 | 能垒数值未核（区域与立体选择性教材锚点；与 easy G1（乙烯，气相近无能垒/TST 失效警示）同试剂带立体维度）[已核实] | C,H,B；8 重原子；⚠ 含 B | 氢硼化立体化学教科书原型（Brown 诺奖工作） |
| J3 | 环己烯 + Br2（bromonium anti 加成）| `C1=CCCCC1.BrBr>>Br[C@H]1CCCC[C@@H]1Br`（trans-1,2-二溴环己烷 (1R,2R)/(1S,2S) 对映对之一，RDKit+3D 已核对），0/1 | CCl4 或惰性溶剂，室温 | 溴鎓离子中间体，Br⁻ 背面进攻 → anti 加成唯一通道；cis（meso (1R,2S)）为错误非对映体。竞争：自由基/顺式通道（背景） | 能垒数值未核（溴鎓离子 anti 加成教材锚点；立体专一性实验证据经典）[已核实] | C,H,Br；8 重原子；⚠ Br 低密度但 OMol25 覆盖 | 烯烃卤化立体专一性定义性案例 |
| J4 | trans-2-甲基环己基氟 anti-E2（构象锁定消除，Hofmann 取向反转）| `[F-].C[C@@H]1CCCC[C@H]1F>>CC1C=CCCC1.F.[F-]`（trans 底物 (1R,2R) 型，3D 嵌入已核对；唯一产物 3-甲基环己烯），−1/1 | 气相（本基准模型）；溶液为经典条件 | 反式双轴向要求：F 必须轴向的椅式构象中 C2 位轴向被甲基占据 → 只能向 C6 消除 → Hofmann 产物 3-甲基环己烯唯一；cis 异构体对照给 Zaitsev 产物 1-甲基环己烯（写入竞争）。竞争：SN2 背景通道（二级碳） | 能垒数值未核（二级氟代物气相 PES 文献空白，量级参 normal 档 X 族二级碳体系；trans-diaxial 取向反转教材锚点 Eliel）[部分核实] | C,H,F；9 重原子；✅ | 构象分析×E2 立体专一性教科书案例 |
| J5 | (E)-2-丁烯过酸环氧化（Prilezhaev stereospecificity）| `C/C=C/C.O=COO>>C[C@H]1[C@H](C)O1.O=CO`（trans-2,3-二甲基环氧乙烷 (2R,3R)/(2S,3S) 对映对之一，RDKit 已核对），0/1 | 过酸，惰性溶剂，0–25 °C | 协同蝶形 TS syn 氧转移 → 烯烃几何保持：E → trans 环氧（dl 对）；cis-2-丁烯对照给 meso（写入竞争）。与 normal O1（乙烯，无立体维度）互补 | ΔE‡ ≈ 15.6 kcal/mol（过氧酸+乙烯蝶形 TS，UQCISD(T) 级（Bach/Schlegel 组，同 normal O1 锚点；底物为乙烯、按类似体系转录——口径登记见文末）[部分核实] | C,H,O；8 重原子；✅（O–O 过氧键注意） | 环氧化立体专一性原型 |
| J6 | 环己烯 + Br2/H2O 溴醇形成（bromohydrin，anti + 捕获竞争）| `C1=CCCCC1.BrBr.O>>O[C@H]1CCCC[C@@H]1Br.Br`（trans-2-溴环己醇对映对之一，3D 嵌入已核对；HBr 副产物），0/1 | 溴水，室温 | 溴鎓离子被水背面进攻 → anti 溴醇；与 J3（Br⁻ 捕获给二溴化物）构成亲核捕获化学选择性竞争。竞争：Br⁻ 捕获（→ J3 产物）；syn 通道（背景） | 能垒数值未核（溴醇 anti 立体专一性教材锚点；捕获竞争为判别考点）[已核实] | C,H,O,Br；9 重原子；⚠ Br 低密度 | 卤醇化学经典；与 J3 刻意的捕获竞争对偶 |

## K. Zimmerman–Traxler 椅式过渡态（2026-08-31 新增，2 个）

> 羰基加成立体化学的"椅式 TS"超族：硼烯醇盐 aldol（Z(O)→syn）与巴豆基硼化（E→anti）——与 E 族（构象系综π-面）和 G 族（[3,3] 椅/船）互补，考核椅式 TS 的 3D 构想与取代基假赤道排布。

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| K1 | (Z)-丙烯醛硼烯醇盐 + 乙醛 aldol（Zimmerman–Traxler：Z(O)→syn）| `C/C=C\OB.CC=O>>C[C@@H](OB)[C@@H](C)C=O`（syn-3-羟基-2-甲基丁醛硼酸酯，(2R,3R) 型经 Fischer-CIP 推导核对），0/1 | 硼烯醇盐模型（气相/惰性溶剂计算对象） | 六元环椅式 TS：(Z)-烯醇盐 → syn aldol（甲基假赤道排布）。竞争：船式/扭船式 TS → anti（副产物 SMILES `C[C@@H](OB)[C@H](C)C=O`）；另一对映面（外消旋底物→dl） | 能垒数值未核（硼 aldol 立体选择性实验 dr 常 >95:5；Zimmerman & Traxler 1957 JACS 79, 1920；教材 Clayden ch.26）[部分核实] | C,H,O,B；8 重原子；⚠ 含 B | Z–T 椅式模型定义性反应 |
| K2 | (E)-巴豆基硼烷 + 乙醛（crotylboration：E→anti）| `C/C=C/CB.CC=O>>C=C[C@H](C)[C@H](C)OB`（anti-3-甲基戊-1-烯-4-醇硼酸酯，(R,R)/(S,S) 对映对之一经 Fischer-CIP 推导核对），0/1 | 巴豆基硼烷模型（气相/惰性溶剂计算对象） | 椅式 TS 烯丙基转位：(E)-巴豆基 → anti 高烯丙醇（甲基与烷氧基 anti）；(Z)-巴豆基对照给 syn。竞争：另一椅式排布 → syn（副产物 SMILES `C=C[C@H](C)[C@@H](C)OB`） | 能垒数值未核（巴豆基硼烷立体专一性实验 dr 常 >95:5；Brown 组巴豆基硼化系列；Org. React. 综述锚点）[部分核实] | C,H,O,B；8 重原子；⚠ 含 B | 烯丙基硼化立体化学教科书原型 |

## L. 几何→产物映射与手性转移（2026-08-31 新增，4 个）

> 立体化学信息的"读取与搬运"：肟几何决定迁移基团（L1，normal R2 对称肟的立体化版）、迁移碳构型保持（L2，normal O3 的立体化版）、[3,3] 的 1,3-手性转移（L3）、[2,3] 的 S→C 手性转移（L4）。

| # | 反应（中/EN） | SMILES (reactant>>product)，q / mult | 典型条件 | gold 机理概要 | gold 能垒锚点 | 舒适区自查 | 经典性依据 |
|---|---|---|---|---|---|---|---|
| L1 | (E)-丁酮肟 Beckmann 重排（oxime geometry → 迁移基团映射）| `[OH3+].CC/C(=N/O)/C>>CCNC(C)=[OH+].O`（(E)-肟经 RDKit 核对，乙基 anti 迁移 → O-质子化 N-乙基乙酰胺＋水），+1/1 | 浓 H2SO4 或酸催化，加热 | ① 肟 OH 质子化；② N–O 断裂与 anti 乙基迁移协同生成腈鎓离子；③ 水加成生成稳定的 O-质子化亚胺酸＋水 I3′；④ O→N 质子转移生成 O-质子化 N-乙基乙酰胺＋水。新气相计算已验证 I3′ 极小值及两条下游一阶鞍点，故撤销先前的净水合边，拆为两步；采用 IRC 得到的较低 P 构象（比原 P 低 1.89 kcal/mol）。 | 自算电子 ΔE‡ 23.13 kcal/mol（E2）保留旧一阶 Beckmann 迁移鞍点值及部分 IRC 连通 caveat；E3 水加成 10.44（相对 I2 络合物），E4 O→N 质子转移 13.46（相对 I3′ 络合物）。E3/E4 为 ORCA 6.1.1 B3LYP-D3BJ/def2-SVP、RIJCOSX/def2-J、TightSCF、气相，同版能量、无 ZPE/热修正；相关一阶虚频、双向 IRC 方向及零虚频优化端点已验证，IRC 本身未均收敛。E1 保持 null；孤立中性亚胺酸 28.46 不回填。证据见 `gold_compute/hard_hl1_2026-10-01.md`。 | C,H,N,O；7 重原子；✅ | Beckmann 立体专属性的定义性考点 |
| L2 | (S)-3-甲基-2-戊酮 Baeyer–Villiger（迁移性排序 + 构型保持）| `[OH3+].CC[C@H](C)C(C)=O.O=COO>>[OH3+].CC[C@H](C)OC(C)=O.O=CO`（(S)→(S) 迁移碳构型保持，RDKit 已核对），+1/1 | 过酸，酸催化（以 `[OH3+]` 写入两侧） | ① 过酸加成 → Criegee 中间体；② 二级碳（3-甲基戊基侧）优先迁移（2°>1° 排序）伴 O–O 断裂（决速区），**迁移碳构型保持**。竞争：甲基迁移 → 另一酯（次要） | 能垒数值未核（迁移性排序与构型保持教材锚点（同位素/立体化学证明经典）；normal O3 锚点作量级参考）[已核实] | C,H,O；12 重原子；✅ | 1,2-迁移立体化学证明经典体系 |
| L3 | (R,E)-戊-3-烯-2-基乙烯基醚 Claisen（1,3-手性转移）| `C=CO[C@H](C)/C=C/C>>C/C=C/[C@H](C)CC=O`（(R,E) 底物经 RDKit 核对 → (E)-3-甲基-4-己烯醛；产物绝对构型待 gold 核对），0/1 | ~150–200 °C | [3,3]-σ 迁移经椅式 TS（甲基假赤道 → E 双键几何）；烯丙位立体中心消毁、新立体中心生成——自消毁式手性转移（chirality transfer 方向由椅式排布唯一决定）。竞争：船式/另一面椅式 → (Z) 或差向 | 能垒数值未核（Claisen 手性转移经典（Eschenmoser/Johnson-Claisen 系列）；综述 Ziegler 1988 Chem. Rev. 88, 1423）[部分核实] | C,H,O；8 重原子；✅ | 不对称 Claisen 手性转移教科书案例 |
| L4 | (S,E)-巴豆基甲基亚砜 Mislow–Evans 重排（[2,3] S→C 手性转移）| `C/C=C/C[S@@](=O)C>>C=C[C@@H](C)OSC`（(S,E) 底物经 RDKit 核对 → 磺酸酯新立体中心，构型归属待 gold 核对），0/1 | 室温–温和加热 | [2,3]-σ 迁移：烯丙基亚砜 → 烯丙基磺酸酯，硫立体中心的手性经内型/外型 TS 偏好转移到碳（S→C chirality transfer）。竞争：另一面 TS → 差向 | 能垒数值未核（Mislow–Evans 重排手性转移经典（Mislow 组 JACS 1968 前后）；教材锚点）[部分核实] | C,H,O,S；7 重原子；⚠ 含 S | [2,3] 手性转移定义性体系 |

---

## 汇总

### 数量与分布

- 候选总数：**51**（旧池 38 + 新增 13：B9、J1–J6、K1–K2、L1–L4；超采，目标圈定 20）。
- 族分布：A 电环化/torquoselection 7；B DA 9；C nitrone [3+2] 3；D 小环开环 5；E 羰基π-面/手性还原 3；F 导向环氧化 2；G [3,3] 椅/船 3；H 阻转消旋 3；I 有机催化诱导 4；J syn/anti 加成消除 6；K Z–T 椅式 2；L 几何映射/手性转移 4。
- 立体化学考点覆盖：立体专一映射（A5/A7/B9/C3/D1–D5/J1–J6/L1/L2）× 立体选择性竞争（A1–A4/A6/B1–B8/C2/E1–E3/F1/F2/G1–G3/K1/K2/L3/L4）× 构型稳定阻垒（H1–H3）；多步网络条目（I1–I3、L1、L2、D1、D5 等）自带中间体捕获考点。
- 重原子分布（反应物装配体）：≤9 个 29 条；10–13 个 10 条（B1/B4/B6/B7/D3/E1/E2/F1/G3/L2）；15–17 个 4 条（B9/C2/C3/E3）；20+ 8 条（H1/I1/I4=20 恰界、I2/I3=21、H3=22、H2=24）。
- 元素覆盖：纯 CHO/CHN/CHNO 为主 40 条；含 B 6 条（E1/E2/E3/J2/K1/K2）；含 Si 1 条（G3）；含 S 2 条（I4/L4）；含 Br 2 条（J3/J6）；含 F 1 条（J4）。
- 电荷态：0 为主；−1（D2–D4/E1/E2/J4/J6）；+1（D1/D5/L1/L2）。全部闭壳层单重态。
- 有数值锚点约 19/51；核实状态：已核实 ~24 / 部分核实 ~22 / 未核实 1（H2 阻垒估计值）；立体专一条目（能垒格无数字）由 MACE 试算标定。
- 刻意的对照/对偶设计：A1 vs A2（给体 vs 受体 torquoselection）、A5 vs A6（meso vs dl 底物）、B1 vs B9（cis vs trans 亲双烯体）、B5 vs B6（动力学/热力学分离两种机制）、D3 vs D5（O/N 类比）、J3 vs J6（Br⁻ vs H₂O 捕获）、G2 vs K1（[3,3] vs aldol 两种椅式）、L1/L2 分别与 normal R2/O3 的"对称→立体化"对照。打标时按"对偶保留 vs 单收"逐组决策，不机械裁。

### 打标带映射（供评审打标参考，不构成门禁）

- **带1 周环立体专一/选择性**（A/B/C/G 族，22 条）：A1 A2 A3 A4 A5 A6 A7 B1 B2 B3 B4 B5 B6 B7 B8 B9 C1 C2 C3 G1 G2 G3。
- **带2 极性开环/加成/消除立体化学**（D/J 族，11 条）：D1 D2 D3 D4 D5 J1 J2 J3 J4 J5 J6。
- **带3 π-面/椅式 TS 选择性**（E/F/K 族，7 条）：E1 E2 E3 F1 F2 K1 K2。
- **带4 几何映射与手性转移**（L 族，4 条）：L1 L2 L3 L4。
- **带5 阻转消旋阻垒**（H 族，3 条）：H1 H2 H3。
- **带6 不对称有机催化诱导**（I 族，4 条）：I1 I2 I3 I4。

### 定稿圈定（v3 缩减：10 条，2026-09-09 用户裁决）

> 2026-09-09 依用户口径重配：总量 ~120 → ~60，hard 保留 10 条。原 20 条定稿在 v3 中按
> "立体化学考点类型覆盖 + 尺寸 ≤20 重原子 + 开放 B3LYP-D3(BJ)/def2-SVP（不再被 xtb 噪声卡死）"
> 缩至 10：剔 A2（与 A1 同族冗余）、B7（DA π-面，无锚点数值）、E1（Felkin ΔΔ 0.7–0.9 过小）、
> G1（Cope 椅/船，TS 边缘 MR）、I4（硫脲 Strecker，与 I1 同为氢键催化，保留 I1）、
> J1/J2/J4（syn/anti 加成族，考点与电环化/开环族重叠）、K1（Z–T 硼 aldol，与椅式选择性族重叠）、
> L4（Mislow–Evans [2,3] 小 ΔΔ）。原 20 名单 + 原替补/剔除 14 条全部留档池内，只增不删。
>
> **收录规则不变**：1,3-偶极环加成不考虑（C 族整体剔除）；多参考体系划归 impossible 档。

- **正选 10（2026-09-30 更新）**：A1, A6, B1, D2, E3, F1, G2, H1, I1, L1。
- **2026-09-30 替换**：用户决定停算 E2（HE2，硼氢化物还原）。补入 B1（HB1，环戊二烯＋顺丁烯二酸酐 endo/exo 加成）；先按苯溶剂模型试算，两条电子能垒未得到自算值前均保持 null。E2 仍留在候选池，不生成正式题。
- **v2 定稿 20 期留档**：A2, B7, E1, G1, I4, J1, J2, J4, K1, L4（v3 剔出）+ A1, A6, D2, E2,
  E3, F1, G2, H1, I1, L1（v3 保留）。
- 未来生成器 `cloudra/benchmark/gen_hard_tasks.py` 只读上方更新的正选名单；task_id 统一加 "H" 前缀。

### 原建议名单（2026-08-31 打标前，已被定稿取代）

> 打标台初始默认值曾按"立体化学考点覆盖最大化 + MACE 舒适区优先"建议正选 20（A1, A2, A5, B1, B5, B7, C2, C3, D2, E1, E2, F1, G1, G2, H1, I1, J1, J4, K1, K2）、替补 10（A6, B9, D1, E3, I4, J2, J3, J5, L1, L3）。评审打标后已被上方定稿取代，留档备查。

### 口径核对登记（供未来 hard 生成器降级名单使用）

- **J5**：锚点（15.6）来自 normal O1 的过氧酸+**乙烯**体系，底物为 (E)-2-丁烯，按类似体系转录。
- 其余数值锚点均为选择性差值（ΔΔ）而非绝对能垒——**生成器需为 hard 新增"选择性锚点"字段语义**（如 `selectivity_anchor`），不要塞进 `barrier_kcal_mol`；H 族（H1–H3）为绝对阻垒 ΔG‡，可正常挂 barrier 字段。
- B5/B6（可逆体系）与 I4（截短模型催化剂）的锚点语义特殊，gold 构建时按机理格说明处理。

### 使用注意

- **旧→新编号映射**（2026-08-25 旧 hard.md，git 历史可查）：A1–A7 = H-01~H-07；B1–B8 = H-08~H-15；C1–C3 = H-16~H-18；D1–D5 = H-19~H-23；E1–E3 = H-24~H-26；F1–F2 = H-27~H-28；G1–G3 = H-29~H-31；H1–H3 = H-32~H-34；I1–I4 = H-35~H-38；B9/J/K/L 族为 2026-08-31 新增。
- **勘误记录**：旧 H-19（现 D1）产物 dl → meso 已勘误（anti 开环翻转一个中心）；旧 H-05（现 A5）产物 SMILES 与 (2E,4Z) 名称对应关系已程序化核对；旧 H-36（现 I2）丙酮供体改丙醛供体（单立体中心无法考核 dr）。
- 族前缀与 easy（D/P/L/X/C/E/F/T/G/M）/normal（A/I/Y/O/S/X/R/U/Q/H）在池文件层面有重叠（A–L 为 hard 池内部编号）；**生成 task JSON 时 task_id 统一加 "H" 前缀**（如 HA1、HJ4），同 normal 的 N 前缀纪律。
- 产物 SMILES 标注"构型待 3D 核对"者（B2–B4、B6–B9、C2/C3、E1/E3、F2、G2/G3、I1–I4、K2、L3/L4），gold 构建阶段以文献结构图/计算 3D 锚定后替换。
- 轴手性条目（H1–H3）SMILES 为消旋体表示（无 `@` 标记）——轴手性/Ra/Sa 由 query 文本与 gold 3D 锚定；RDKit 对联芳轴手性支持有限，生成器注意。
- **评审打标台**：`ideapool/reaction_candidates/hard_tagging.html`（浏览器直接打开；由 `scripts/gen_hard_tagging.py` 从本文件生成，条目变更后重跑脚本重建）。打标存浏览器 localStorage、不回写本文件，可导出/导入 JSON 与正选/替补名单文本。

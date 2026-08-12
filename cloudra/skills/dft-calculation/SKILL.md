---
name: dft-calculation
description: Provide domain expertise for DFT (Density Functional Theory) quantum chemistry calculations on molecules and clusters using Gaussian/ORCA. Use when selecting functionals/basis sets, planning transition state workflows, and troubleshooting input errors. For periodic solids, see first-principles-calculation.
---

# 1. 本地工具链映射 (Toolchain Mapping)
在执行分子/团簇 DFT 计算时，动作应与 `CLOUDRA` 本地工具链紧密绑定：
- **获取分子结构与建模**：SMILES 是分子结构的核心。当缺乏现成的三维坐标文件时，优先调用本地 SMILES 相关工具：
  - 若用户只给出了化合物名称（通用名/IUPAC/CAS 号），调用 `name_to_structure` 解析为 SMILES（可设 `generate_3d=True` 直接产出 xyz）；中文俗名命中率低，失败时引导用户改用英文名或 CAS 号。
  - 若用户只给出了一张化学结构图，优先调用 `image_to_smiles` 识别 SMILES。
  - 若需将 SMILES 转为 3D 坐标，调用 `smiles_to_mol` 并设置 `generate_3d=True`。
  - 若只需生成高斯输入文件，可直接在调用 `gjf_writer` 时设置 `source_type="smiles"`。
  - **严禁手写坐标**：不得凭空逐原子键入笛卡尔坐标，也不得凭记忆写键长/键角搭建分子——**没有例外**，哪怕只是"微调几个原子"或自觉比工具快。坐标只允许来自上述工具、数据库，或经 `format_converter`/`log_parser` 从既有日志中提取；手工干预仅限 `internal_coordinates` 的 Z-matrix 数值微调后转回笛卡尔。
- **多分子复合物/双分子体系建模**：把两个（或多个）分子组装成反应复合物时，**不要手摆相对取向**——手摆既慢又几乎必然不合理。正确路径：粗略放近（质心间距略大于成键距离即可）后，用 `conformer_search` 加 `distance_filters` 锁定反应原子对采样取向，或用 xtb/力场对复合物做预优化弛豫到合理构型，再交给 DFT 级别。预组织取向对双分子 TS 搜索的成功率影响极大，值得在这里花算力而不是在手摆坐标上花时间。
- **反应原子映射**：拿到反应物/产物两个 SMILES 后，先调用 `reaction_mapping`，再生成插值路径。未标号 SMILES 可能给出多个近似候选；`ambiguous` 时要结合机理选择，不能把排名第一当成原子身份真值。工具同时保留 SMILES 序号的 `graph_watch_pairs`，并在具体结构绑定成功后把顶层 `watch_pairs` 翻译成反应物坐标序号。已有 mol/sdf/xyz 要求 `binding_status=complete` 且 `binding_source=concrete` 才把全原子 `atom_map` 直接传给 `ts_guess interpolate`；`binding_source=internal_generated` 的映射只对应工具内部 RDKit `AddHs` 顺序，不能套到任意外部 XYZ。
- **生成输入文件**：推荐调用 `gjf_writer` 生成 `.gjf`，减少手写格式错误。尽量避免在输入文件正文中写注释，以减少解析风险。
- **结构洞察与微调**：调用 `internal_coordinates` 作为你的“眼睛”和“双手”。`mode=analyze` 返回键级感知的结构报告（异常键长/键角、可旋转二面角分类、立体化学 R/S 与 E/Z、环与 Cremer–Pople 褶皱、等价原子），用 `reactive_atoms`/`watch_pairs` 可聚焦反应中心（如成键距离与进攻角）；完整 Z-matrix 自动写入 `.zmat` 文件不进上下文。需要像 GaussView 中那样“手工拖拽”结构时，仍可修改 Z-matrix 文本后用 `mode=zmatrix_to_cartesian` 转回坐标。
- **构象搜索**：调用 `conformer_search` 生成构象系综（能量窗口 + RMSD 聚类 + Boltzmann 布居）。机理任务中用 `distance_filters` 锁定反应原子对，筛出预组织的 reactive conformer——不要默认取最低能量构象（Curtin-Hammett）。工具会额外保留能窗外最低能的 reactive conformer，并保留它相对全局最低点的构象罚分；它只是候选，不自动等于可行 TS 前体。
- **过渡态初猜与验证**：调用 `ts_guess`。`mode=interpolate` 对反应物/产物做 IDPP 插值直接产出候选坐标（也可作 NEB 初始路径）；`mode=scan_prepare` 生成 Gaussian modredundant / ORCA 扫描输入；`mode=scan_parse` 解析扫描剖面并提取 TS 初猜，但它是探索工具，输出不作为 SI 级验证材料。`mode=verify` 默认也只给出 `candidate/unlikely/inconclusive` 方向建议；只有在已有一个虚频、双向部分 IRC 和两侧外帧各自优化所得中间体时，才用 `strict=True` 检查每个外帧是否位于 TS 与对应中间体之间。strict 的 `pass` 只证明这段路径方向自洽，不代表 TS 绝对正确。日志解析与判据均交给工具，不要手写正则。
- **电子结构感知**：调用 `electronic_analysis` 做单点层面的电子结构验证——原子电荷（Mulliken/meta-Löwdin）、Mayer 键级（partial bond / incipient bond 识别）、IBO Lewis 图像；自由基体系设 `spin>1`（自动 UHF/UKS），用自旋布居定位自由基中心并检查 `<S^2>` 自旋污染。
- **任务投递**：统一调用 `submit_compute_job`。长耗时任务建议设置 `is_async=True` 异步执行。
- **结果解析与热化学**：优先调用 `log_parser` 等工具提取能量、频率、收敛状态；它会分开返回 thermal corrections 与 total H/G，不能混用。多物种 ΔE/ΔH/ΔG 用 `thermo_analysis` 按带符号化学计量系数汇总：`raw_rrho` 是日志原始 RRHO，`goodvibes` 才是显式准谐振/低频修正；温度、浓度、标准态和单点能来源必须随结果报告。避免直接用 `cat` 读取巨型日志。IRC/扫描曲线分析用 `format_converter` 将日志 log→csv 后程序化读取（pandas/csv），不要手写正则解析日志。

# 2. 限制与例外 (Constraints & Exceptions)
以下规则是常见最佳实践，但存在合理例外。遇到矛盾时，优先以**具体体系、目标性质和最新文献**为准。

1. **输入文件注释**：Gaussian 官方文档允许用 `!` 添加注释，但实践中 `.gjf` 文件中的注释/空行常因版本或解析差异导致任务异常。因此建议不在计算指令区写注释，必要时把说明放在文件外部或标题行，并务必先用小体系测试。[Gaussian Input Format](https://gaussian.com/input/)
2. **HF (Hartree-Fock)**：对大多数定量计算，普通 HF 因缺少电子相关而不被推荐。但在以下情况仍有价值：
   - 作为 DFT/后自洽方法的参照计算；
   - 需要 HF 轨道作为多参考、EOM 或强自旋污染开壳层体系的初猜（如 Q-Chem 中可用 DFT 轨道替代 HF 轨道，反之 HF 轨道也可作为参考）；
   - 使用色散校正 HF（HFLD）专门分析非共价相互作用能。[HFLD paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9009084/)
3. **MP2**：普通 MP2 对弱相互作用和过渡金属常表现不佳，原则上不建议盲目使用。但 MP2.5、SCS-MP2 等变体在部分弱相互作用基准中仍可作为对照方法。
4. **M06-2X 与过渡金属**：M06-2X 主要针对主族热化学、动力学和非共价相互作用参数化，对含过渡金属（尤其是开壳层/强相关）体系风险较高，建议优先选用 M06、PBE0-D3(BJ)、TPSSh-D3(BJ) 等。若体系以轻金属或主族配位为主，且性质对交换相关能敏感，可酌情使用 M06-2X 并加基准验证。[M06 Suite](https://comp.chem.umn.edu/truhlar/docs/773fin_plus_supp_info.pdf)
5. **QST2 / QST3（禁用）**：本项目不使用 Gaussian `Opt=QST2/QST3`。过渡态初猜统一走约束扫描（`ts_guess` scan_prepare 生成 modredundant 输入）或 IDPP 插值（`ts_guess` interpolate），再 `Opt=(TS,noeigen,calcfc)` 优化。
6. **基组一致性**：IRC 和振动分析原则上应使用与几何优化相同的基组，以保证势能面一致；单点能计算完全可以用更大基组进行外推或能量修正。
7. **弥散函数**：
   - 计算极化率、偶极矩、Rydberg 态或阴离子时，通常需要弥散函数（如 `def2-TZVPD`、`aug-cc-pVDZ`）。
   - 键级分析、布居分析、NMR 计算通常避免使用弥散函数，因为弥散基函数会离域化并稀释局部分析结果；但如果研究对象本身是弥散态（如弱配位阴离子），仍需带弥散并谨慎解释。

# 3. 科学知识库：泛函与基组选型 (Scientific Knowledge Base)
在调用 `gjf_writer` 设定 `method` 和 `basis_set` 时，以本节内容为一般性事实依据；最终选择应结合体系特点和最新基准。

## 3.1 泛函选择指南
*   **一般精度顺序**：CCSD(T) > 双杂化泛函 > 恰当选用的普通泛函 > MP2 > HF > 半经验方法。
*   **高低搭配策略**：用普通泛函做结构优化和振动分析（如大体系用 `B3LYP-D3(BJ)`），再用双杂化泛函（如 `wB97M(2)` 或 `PWPB95-D3(BJ)`）算单点能。

| 计算任务/体系 | 首选/推荐泛函 | 备选或特定条件泛函 |
| :--- | :--- | :--- |
| **主族结构优化与振动** | `B3LYP-D3(BJ)` | 显著共轭体系用 `wB97XD` |
| **有机体系热力学** (反应能等) | `wB97M-V` | `M06-2X` |
| **各类弱相互作用** | `wB97M-V`, `wB97X-V` | `PW6B95-D3(BJ)`, `M06-2X` |
| **局部激发与一般激发态** | `PBE0` (结合 TDDFT) | `CAM-B3LYP`, `wB97XD` (大共轭/CT) |
| **极化率 /偶极矩等电性** | `PBE0`, `wB97M-V` | `BHandHLYP` (大共轭), `LC-wPBE` |
| **多参考特征强 /团簇** | `r2SCAN`, `TPSS` | `PBE0`, `MN15L` |
| **过渡金属 (闭壳层反应)** | `wB97X-V`, `wB97M-V` | `PBE0-D3(BJ)`, `TPSSh-D3(BJ)` |
| **过渡金属 (开壳层反应)** | `TPSS0-D4` | `PBE0-D4` |
| **NMR 化学位移** | `B3LYP` (结合标度法) | `revTPSS` (结合 pcSseg-1 基组) |

### 3.1.1 多参考诊断与边界（保留 r2SCAN/TPSS，勿擅自换 CAS）
上表“多参考特征强 → `r2SCAN`/`TPSS`”是 **DFT 框架内的最佳缓解**，不是错误建议。agent 不擅自改走 CASSCF 全流程；要做的是**先诊断、再标注不确定度**。

*   **何时怀疑强多参考**：臭氧 / Criegee 中间体；双自由基边界（部分环加成 TS）；均裂中段；低自旋过渡金属多态 / 近简并。
*   **廉价诊断（可写进作业关键词）**：
    *   xTB FOD：`xtb --fod`（fractional occupation density，Grimme 2015）——局域 FOD 热点提示多参考区；
    *   UDFT 破缺对称 + ⟨S²⟩ + Yamaguchi 自旋投影校正；
    *   波函数稳定性：`stable=opt`（Gaussian）/ 等价 ORCA 稳定性检查；
    *   有 CCSD(T) 单点时看 T1 diagnostic（主族经验：T1 > 0.02 预警）。
*   **诊断阳性时的行动**：改用 / 复核 `r2SCAN` 或 `TPSS` 类泛函；结论中**显式标注方法不确定度**；能垒定量结论降级为定性排序；必要时**建议用户**用 NEVPT2/CASPT2 单点复核——agent **不得**自行宣称定量可靠。

## 3.2 基组选择指南
理论方法对基组的依赖性存在根本差异，切勿混用评判标准。Pople（6-31G* 族）与 Karlsruhe def2 族**并列可用**；同一研究内保持一族一致，勿混用后再比能垒。

*   **Pople 族（现有常用）**：优化/频率 `6-31G*` / `6-311G**`；阴离子与弱相互作用加 `+` / `++` 弥散。
*   **def2 族（推荐现代化默认）**：
    *   预优化 / 粗扫：`def2-SVP`
    *   精修几何与频率 / 日常单点：`def2-TZVP`（或 `def2-TZVPP`）
    *   阴离子、弱相互作用、氢键/离子对：加弥散 `def2-TZVPD` 或 `ma-def2-SVP` / `ma-def2-TZVP`
*   **pcseg 等**：高精度单点可选 `pcseg-2`。
*   **特定任务基组建议**：
    *   **弱相互作用能**：主导体系必须加弥散，建议加 BSSE 校正。
    *   **势垒计算**：有算力可加少量弥散（如 `ma-` / `def2-TZVPD`），或提升 zeta 数。
    *   **相对论计算**：全电子相对论必须用专用基组（如 `cc-pVnZ-DK`）；第四周期及以后重元素强烈推荐赝势基组（def2-ECP 与 def2 价基配套）。

## 3.3 溶剂化决策树
把溶剂模型写进条件假设，再选计算策略（与机理文件中的 SMD 提示对齐，此处为总决策入口）。

| 场景 | 推荐 | 关键词/动作 |
| :--- | :--- | :--- |
| 非极性、气相实验或对照 | 气相几何 + 气相能量 | 不设 scrf |
| 需要 ΔG_solv / 溶液自由能剖面 | **SMD**（优先） | `scrf=(smd,solvent=...)`；报告标准态 1 M |
| 几何受溶剂影响小、只要定性溶剂效应 | CPCM/PCM 优化或气相优化后溶剂单点 | `scrf=(cpcm/pcm,solvent=...)` |
| 质子转移、强氢键参与反应坐标、紧密离子对 | 隐式 + **1–3 个显式溶剂分子** | 显式分子进 `distance_filters`/反应坐标；勿只靠隐式 |
| 离子型机理（SN1/E1、鎓离子、裸电荷中间体） | **必须溶剂化**（至少 SMD） | 气相剖面严重失真，禁止只报气相 ΔG‡ 作溶液结论 |

*   **优化 vs 单点**：几何对溶剂敏感（离子、氢键网络、极性 TS）→ 在隐式溶剂下优化+频率；敏感度低时可用气相优化/频率，再对关键结构做 SMD 单点（须在报告中写明）。
*   溶液热化学用 `thermo_analysis` 的 `solution_1m` / `solution_custom`，与实验浓度对齐。

# 4. Agent 工作流：过渡态 (TS) 搜索 (Workflow State Machine)
当接收到“过渡态搜索”任务时，建议遵循以下程序化执行步骤。
**完整机理任务（假设→验证→能垒→报告）必读扩展资料**：`getskill("dft-calculation", other="mechanism-elucidation-sop.md")`（全流程 SOP、机理假设图管理、失败诊断决策表）；建模思路与反应归属查 `getskill("dft-calculation", other="reaction-class-geometry.md")`（五问题框架 + 反应结果分类索引），再按索引指引只取对应领域文件 `getskill("dft-calculation", other="mechanisms/<领域>.md")`（substitution/addition/carbonyl/elimination/pericyclic/radical/rearrangement/redox/coupling；各自含该领域的机理假设空间、几何谓词与陷阱），不要一口气加载全部领域文件。

如果当前会话是 `dag_record` 或 `dag_guided`，还必须按该 SOP 的“两张 DAG”契约工作：delivery DAG 就是带证据指针的机理图，由 Coordinator 设计（`dag_graph` mutate 提交假设）；process DAG 管待办与依赖，`dag_guided` 下由 Supervisor 维护（Coordinator 的机理图变更被接受后会自动唤醒它），`dag_record` 下只有 harness 的确定性记录。SOP 中 `C=COCC=C` → `C=CCCC=O` 的 Claisen 段是 DAG-guided 的 worked example，用来理解证据如何逐步进入图，不是通用反应脚本。`ts_guess`、扫描或 Supervisor 建议都不能替代 endpoint-supported 所需的独立 TS、短 IRC、优化端点、方向检查与端点身份匹配证据。

**Step 1: 建模与精准初猜 (Modeling & Initial Guess)**
- 过渡态搜索对初猜严格。优先从网络或数据库获取核心分子的 SMILES，使用系统工具转换为坐标。
- 若给定反应物/产物 SMILES，先用 `reaction_mapping` 确定或显式选择原子映射候选，再把具体结构绑定得到的全原子 `atom_map` 交给插值；映射歧义本身是需要保留的机理不确定性。
- **结构洞察与拖拽**：调用 `internal_coordinates`（mode=analyze）作为你的“眼睛”：结构报告中的异常键（elongated / forming_candidate / clash）、可旋转二面角与 Reactive Center 块直接指出断键/成键位点；也可用 `mode=zmatrix_to_cartesian` 编辑 Z-matrix 数值后转回坐标，手工拉长将断的键、缩短将成的键，捏出高质量 TS 初猜。
- 初猜的两条主路线（详见 mechanism-elucidation-sop.md）：① 端点已知时用 `ts_guess` interpolate 做 IDPP 插值取候选帧；② 用 `ts_guess` scan_prepare 生成约束扫描输入（坐标选择查 reaction-class-geometry.md），提交后用 scan_parse 读剖面判定并自动提取 TS 初猜。为节省算力可先用半经验方法（如 xtb）扫描。**请注意，xtb在较大分子的过渡态面前的精度可能比较差，扫出了奇异的结果建议再使用优化级别扫一遍**
- **扫描成本纪律**：扫描是探索工具，成本随维度爆炸——一维扫描 ~10–30 个单点，二维扫描是 N×M（轻易数百个单点）。默认只做一维，沿最关键的那条反应坐标；二维扫描只有在确证两个坐标强耦合、一维无法回答时才用，且先用 xtb 预扫再决定要不要上 DFT 级别，并在报告中写明理由与成本估计。
- 提取势能较高且梯度较小的点作为 TS 初猜。找到初猜后，建议先将结构展示给用户确认，再开启正式搜索。

**Step 2: 任务构建与投递 (Build & Submit)**
- 调用 `gjf_writer` 生成输入。
- 关于**计算资源设置**：dft本身内存要求不算太高，如果是小分子建议加大核数而不是加大内存，大分子要注意，hessian计算的内存占用量会急剧上升，此时内存成为计算瓶颈。
- **推荐关键词组合**：`opt=(ts,noeigen,calcfc)`。可视收敛情况调整，例如增加 `maxstep=10` 或 `int=ultrafine`。
- `opt` 和 `freq` 可连用，这是高斯标准做法；过渡态需要唯一虚频，建议带上 `freq` 验证。
- 调用 `submit_compute_job` 提交任务。无语法错误后，使用异步提交 (`is_async=True`)。
- 系统不负责任务调度功能，多个提交默认为异步计算，请注意这其中的风险，若串行提交需要一个一个提交任务。
- 在较大分子的情况下（>=30），建议采用串行提交，理想的配置是单个任务核数不大于32，内存需求几乎无上限。

**Step 3: 运行与验证 IRC (IRC Validation)**
- 计算级别建议与 TS 搜索一致。关键词示例：`irc=(lqa,calcfc,maxpoint=80)`。
- **点数门槛（与证据对齐）**：双向 IRC **每个方向至少 50 个有效点**；`maxpoint=80` 为常用起步。某一侧有效点不足 50 或过早卡住时，加大 `maxpoint`（或缩小步长）重跑该向，勿用过短 IRC 冒充 endpoint-supported。
- *逻辑验证*：作 IRC 曲线。如果曲线不平滑（有平台或噪声），说明过渡态精度不够或位置不对。不必执着于整条 IRC 曲线完整收敛到极小点：从两侧最外有效帧分别做无约束优化得到中间体，再调用 `ts_guess mode=verify strict=True`，证明两个部分端点各自处于 TS 与对应优化中间体之间即可。
- *端点身份*：再把两个优化中间体作为具体结构交给 `reaction_mapping`，与该基元步预期的端点 SMILES 分别核对分子图。`strict pass` 与端点图匹配是两件独立证据，任一项都不能代替另一项。
- *重搜策略*：此时不仅要加上 `maxstep=10`，还应该加上积分格点精度参数（如 `int=ultrafine` 或 `int=superfine`）重新计算 TS。

**Step 4: 计算单点能 (Single Point Energy)**
- **先完成 Step 3 的路径/端点验证，再上高价单点**（与 SOP 一致：避免对错误鞍点浪费高水平计算）。
- 保持几何优化时的基组一致或按 §3.2 升级，去掉 `opt` 和 `freq` 关键词，提高泛函级别计算单点能；热校正仍来自频率级日志，用 `thermo_analysis` 叠加。

过渡态搜索任务一般伴随着机理寻找的任务，一般策略是：**以过渡态为中心，跑出双向部分 IRC 后对两侧外帧分别优化得到中间体，再以这些结构拼出完整能垒**。工具不保存“已验证”等任务状态，只对本次传入的几何材料作判定。

# 5. 异常诊断与排障断路器 (Circuit Breakers)
如果 `submit_compute_job` 失败，或 `log_parser` 返回解析异常，请在重试前比对以下错误：

1. **色散冲突诊断**：检查当前泛函是否支持所选的色散校正（例如 M06-2X 不支持 GD3BJ）。
2. **结构奇异性排查**：如果报告 Hessian 矩阵无法计算，检查分子中是否存在明显的直线键角。如有，请改用笛卡尔坐标进行几何优化。
3. **IRC 步长发散**：若出现步长不收敛，直接将算法换用 `lqa`。
4. **IRC 异常终止**：若只跑了几步就 normal termination：
   - 过渡态不够平滑：需增加精度重算高精度 TS（见 Step 4 重搜策略）。
   - 反应能垒过平：尝试在 gjf_writer 中追加 `extra_keywords="IOp(1/108=-1)"` 取消收敛判断。
5. **freq数值崩溃**：有时freq突然崩溃并不是物理上的问题，在排查了无不合理距离等问题后，可以考虑读取已经算过的几何优化文件中的频率数据：geom=allcheck guess=read freq
6. **疑似强多参考**：见 §3.1.1；勿静默把单参考 DFT 能垒写成定量结论。

# 6. 热化学细节与可检验预言
频率级结果进 `thermo_analysis` 前，先对齐下列约定（可写进报告 assumptions）。

*   **频率标度因子**：谐振频率按泛函/基组查表标度后再算热校正。常见量级（仅作起步，最终以表为准）：B3LYP/6-31G* ≈ 0.960；M06-2X 常用 ≈ 0.97。查 [NIST CCCBDB](https://cccbdb.nist.gov/vibscalejust.asp) 或 Truhlar harm_fac；GoodVibes 可用 `-v` / 自动检测（见 `thermo_analysis` 的 `frequency_scale_factor`）。
*   **多构象 Boltzmann 加权**：ΔG‡ 存在多个可及 TS 构象时，对自由能做 Boltzmann 加权，或至少报告最低与次低及 ΔΔG。勿只报 conf0。
*   **Eyring 速率常数**（过渡态理论）：`k = (k_B T / h) * exp(-ΔG‡ / RT)`。标准态须与 ΔG‡ 一致（1 atm vs 1 M）；双分子步骤写清浓度单位；此式为经典 TST，**不含隧穿**。
*   **隧穿**：氢（氘）转移、显著虚频的 HAT/质子转移，应提示存在 Wigner / Eckart 校正；定量 k 或一级 KIE 需要时再启用，并在结论中标注。
*   **KIE 一句话协议**：预测动力学同位素效应可用频率数据 + Bigeleisen–Mayer 方程（工具如 Kinisot）；把计算 KIE 当作可检验的机理预言，与实验对照，而非事后解释词。
*   **ΔΔG‡ → 选择性**：见 `reaction-class-geometry.md` §3.3（如 298 K 下 ≈1.4 / 2.7 kcal/mol 对应约 10:1 / 100:1）。

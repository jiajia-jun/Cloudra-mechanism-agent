# 有机反应机理计算 SOP（无视觉闭环）

适用场景：从反应 SMILES / 三维结构出发，自主完成机理假设生成 → 过渡态定位 → 验证 → 能量学报告的全流程。
所有坐标与图像文件一律落盘；上下文只保留数值表、判定与文件路径。开始前先记录真实反应条件：温度、溶剂/标准态、浓度、催化剂/添加剂、质子化态、电荷/自旋以及是否有光照；缺失项是显式假设，不从两个 SMILES 中臆造。**每个 TS 必须三证齐全**：恰好 1 个虚频、双向 IRC 外帧处于 TS 与两侧优化中间体之间、电子结构与机理假设自洽。IRC 可以不走到极小点，但外帧必须另行优化并用分子图与预期中间体核对。

若会话启用了 DAG，系统只维护一张持久图。**delivery DAG** 就是化学机理图：节点是中间体 occurrence，边是 elementary step；节点和边只保存指向 species、完整工具结果、作业与 artifact 的不可变指针，不把坐标、日志或大段结果塞进图内。催化循环用指向同一 species 的多个 occurrence 展开，不能为了画成环而破坏 DAG。不存在 process DAG——"下一步做什么"不再落图，由 Coordinator 按自己的节奏推进，交付相关的工具结果进 CallReview 收件箱等待复核。

会话模式决定 agent 如何使用它：`standard` 完全不读写 DAG，也不调用 Supervisor；`dag_record` 中 Coordinator 用 `dag_propose_mechanism` 提交机理草稿（harness 自动接受），并用 `dag_bind_evidence`（带 `stage_kind`）把完成的调用按序绑到各阶段，Supervisor 不运行；`dag_guided` 在相同基础上由 Supervisor 用 `dag_accept_mechanism` 接受草稿（接受前计算入口保持关闭）、用 `dag_review_call` 复核收件箱里每个交付相关调用并绑定阶段。分工不可逾越：**机理假设与 stage 契约由 Coordinator 提出**（mapping 后提交 occurrence 节点、候选边和每个元素的有序阶段清单，阶段初始为 `pending`），Supervisor 对图结构只读，只做接受/复核。Supervisor 的判定不是化学事实，agent 可以用新证据反驳；任何模式下都不得编造 evidence 指针。DAG 的 complete 只是 coverage contract 已满足（每个 required stage `supported` 或带理由 `skipped`；`pending`/`rejected` 都是未决缺口），不代替科学判断。交付仍有缺口时不能以 `complete` 停止，只能继续，或明确选择保留缺口的 `partial` / `user_terminated`。

# 1. 工具链总览

| 环节 | 工具 | 关键参数/用法 | 产出 |
| :--- | :--- | :--- | :--- |
| 机理假设 | RDKit 反应模板（`smiles_to_mol` / Bash 调 rdChemReactions） | reaction SMARTS 枚举候选中间体/产物 | 假设图（节点=物种，边=基元步） |
| 原子映射 | `reaction_mapping` | 两端 SMILES；可加具体 mol/sdf/xyz 与 `selected_candidate` | 映射候选、键变化、`watch_pairs`、可执行全原子 `atom_map` |
| 构象搜索 | `conformer_search` | `distance_filters` 锁定反应原子对 | 系综文件 + reactive conformer 候选 |
| 结构体检 | `internal_coordinates` mode=analyze | `reactive_atoms` / `watch_pairs` | 异常键/键角/二面角/立体化学报告 |
| TS 初猜（端点已知） | `ts_guess` mode=interpolate | IDPP 插值，`watch_pairs` | 候选帧坐标（可作 NEB 初始路径） |
| TS 初猜（约束扫描） | `ts_guess` mode=scan_prepare → `submit_compute_job` → `ts_guess` mode=scan_parse | Gaussian modredundant / ORCA `%geom Scan` | 探索性能量剖面 + TS 初猜 xyz；不作为 SI 验证证据 |
| TS 优化+频率 | `gjf_writer` + `submit_compute_job` | `opt=(ts,noeigen,calcfc) freq` | TS 结构 + 频率 |
| TS 验证 | `ts_guess` mode=verify `strict=True` | 1 个虚频 + 双向部分 IRC + 两个外帧优化中间体；可用 `watch_pairs` | 路径方向一致性的 pass/fail/inconclusive（无需完整 IRC） |
| 电子结构交叉验证 | `electronic_analysis` | `reactive_atoms` 聚焦；自由基用 spin>1 | partial bond / 自旋布居 / IBO 孤对 |
| 结果解析 | `gaussian_log_parser` / `format_converter` | 避免 cat 大日志、避免手写正则 | 能量、收敛状态 |
| 相对热化学 | `thermo_analysis` | 带符号系数、温度、标准态；`raw_rrho` 或显式 `goodvibes` | ΔE/ΔH/ΔG、假设与后端 provenance |

# 2. 流程状态机

**Step 0 条件与假设生成**：先把实验条件写成当前计算的显式假设，再判定反应类（见 `reaction-class-geometry.md` 查表），列出候选基元步与中间体，构成机理假设图。对每条有明确两端的边先调用 `reaction_mapping`：完整 atom-map 标签优先；未标号结果为 `ambiguous` 时保留候选并结合该边的机理选择，不能把低编辑数映射直接宣布为正确。每条边是一个待验证的 TS。工具本身不保存“已验证”状态；DAG 模式下由 harness 注册完整结构化结果，`dag_guided` 经 Supervisor 复核、`dag_record` 由 Coordinator 自绑后，才以证据指针绑定到对应阶段。

**Step 1 构象**：对反应物/中间体跑 `conformer_search`。若已知反应原子对，把映射输出的 `watch_pairs` 转成合适的 `distance_filters`，筛出 reactive conformer（成键原子已预组织靠近的构象）。注意 Curtin-Hammett：反应物全局最低构象不一定通向产物，不要只取 conf0。工具会保留最低能 reactive 候选，即使它在普通能窗外；必须连同它相对全局最低构象的能量罚分解释。

**Step 2 结构体检**：`internal_coordinates` analyze 确认结构合理（无 clash/异常键角），记录立体化学（R/S、E/Z），为后续机理报告留档。

**Step 3 TS 初猜（二选一或联用）**：
- 端点已知（假设明确的基元步）：对已有坐标，仅在 `reaction_mapping binding_status=complete` 且 `binding_source=concrete` 后，将全原子 `atom_map` 与已翻译到反应物坐标序号的顶层 `watch_pairs` 传给 `ts_guess` interpolate，生成 IDPP 图像并取推荐候选帧；或直接作为 ORCA NEB 的初始路径。`graph_watch_pairs` 仍是 SMILES 图序号，重原子映射或 `internal_generated` 映射不能冒充任意外部显式氢 XYZ 的全映射。
- 通用主路线：`ts_guess` scan_prepare 生成约束扫描输入（坐标选择查 `reaction-class-geometry.md`），`submit_compute_job` 提交（`is_async=True`），完成后 scan_parse 读剖面与判定。
- 初猜结构建议先展示给用户确认，再开正式 TS 搜索。
- `ts_guess interpolate`、`scan_prepare`、`scan_parse` 和默认 `verify` 都是找方向的探索步骤。它们最多支撑 delivery 边的 `ts_guess` advisory 阶段，**不能**满足 `ts_opt` / `frequency`，更不能把 elementary edge 提升为鞍点或端点已验证；扫描结果也不作为 SI 证据。

**Step 4 TS 优化 + 频率**：`gjf_writer` 生成 `opt=(ts,noeigen,calcfc) freq` 输入，收敛困难时加 `maxstep=10`、`int=ultrafine`。完成后可用默认 `ts_guess` verify 查看候选方向，但默认结果只是建议；严格验证要求恰好 1 个虚频。

**Step 5 IRC 验证**：`irc=(lqa,calcfc,maxpoint=80)`，级别与 TS 搜索一致。**双向每个方向至少 50 个有效点**（与 SKILL.md §4 Step 3 / 证据门槛对齐）；`maxpoint` 不足或一侧过早终止时加大重跑。不必等待 IRC 完整走到极小点：取 rx<0 与 rx>0 两侧最外有效帧，各自做无约束优化得到中间体；随后把 TS 频率日志、部分 IRC 日志和两个优化中间体传给 `ts_guess` verify，并设 `strict=True`。工具尝试两种无序配对，利用指定 `watch_pairs` 或自动选择的变化原子对，检查每个 IRC 外帧的距离坐标是否处于 TS 与对应中间体之间且更靠近中间体。随后用 `reaction_mapping` 把两个优化中间体的具体结构分别与原先声明的端点 SMILES 核对。`strict pass` 只证明路径方向一致，端点 `match` 只证明分子图身份；两者互不替代，也都不替代虚频振动模式、电子结构和化学合理性判断。曲线不平滑则按 SKILL.md §5 重搜策略处理。

在 delivery DAG 中，`endpoint-supported` 必须由相互独立的阶段证据按序合成：`ts_opt` + `frequency`（TS 优化收敛、恰好一个虚频），`short_irc`（short bidirectional IRC **两向均有足够有效点（各 ≥50）**），`endpoint_a` / `endpoint_b`（两侧 optimized endpoint 都正常收敛为无虚频极小点），`direction`（`ts_guess strict=True` 确认外帧位于 TS 与对应极小点之间），`identity`（`reaction_mapping` 确认两个优化端点与该边声明的中间体分子图一致）。少任何一个 required stage 都保持 `saddle-supported` 或更低；`strict pass`、扫描峰或初猜好看均不能单独越级。

**Step 6 能量学**：**仅在 Step 5 路径/端点验证通过后**，再提高泛函级别算单点能（SKILL.md §3 高低搭配；顺序见 SKILL.md §4 Step 3→4）。用 `thermo_analysis` 把 Gaussian 原文的频率级 H/G correction 叠到相应单点能，并用带符号化学计量系数组合 ΔE/ΔH/ΔG；`raw_rrho` 只表示日志原始 RRHO，只有显式 `goodvibes` 后端才应用准谐振低频修正。溶剂化按 SKILL.md §3.3。所有剖面必须写明日志温度/压力、目标 1 atm/1 M（或自定义浓度）、后端和能量来源；日志缺温度/压力不能默认为完整结果，非 1 atm 原始压力要先正规化。GoodVibes 缺失时的 `inconclusive` 不得静默退回 raw RRHO。能垒比较一律用同一约定下的 ΔG‡，不要只比电子能。疑似强多参考时按 SKILL.md §3.1.1 诊断并降级定量结论。

**Step 7 电子结构交叉验证**：对 TS 与关键中间体跑 `electronic_analysis`：成/断键应表现为 partial bond（非整数 Mayer 键级）；自由基步骤检查自旋布居迁移方向与 IBO 孤对变化是否与假设的电子推动一致。

**Step 8 报告**：以反应物为零点的相对 ΔG 剖面表（中间体、各 TS），标注决速步（已验证边中 ΔG‡ 最高者），与实验证据（速率、选择性、ee、KIE、中间体捕捉）对照。

# 3. delivery 图与 stage 契约的维护规则

delivery DAG 不使用 `verified/failed` 真值标签。每个元素携带 Coordinator 在机理草稿中声明的有序 **stage 契约**，阶段状态为 `pending / supported / skipped / rejected`（后两者必须附原因）：`skipped` 带理由是唯一的非成功处置；`rejected` 不是处置——它是仍欠的开放缺口，只能靠后续重新绑定或显式 skip 关闭。元素级证据层级 `proposed / structure-supported / saddle-supported / endpoint-supported / thermo-annotated / rejected / inconclusive` 由 harness 从阶段确定性派生，只作展示；模型只能手动设 proposed/rejected/inconclusive。命名在存储中可用下划线形式，文档中的连字符表示同一语义。

delivery 节点是同一 canonical species 在某条路径中的 occurrence。节点的 `geometry` 阶段至少要绑定优化极小点证据；SMILES 嵌入、初始构象或模型猜测不够。delivery 边的阶段通过指针引用 TS、频率、short IRC、optimized endpoints、endpoint mapping 与热化学结果。剪枝、决速步和选择性判断继续遵守本 SOP 的化学规则，图状态不能替代它们。

## Claisen 示例：`C=COCC=C` → `C=CCCC=O`

这是展示图如何随证据演化的例子，不是所有反应都照抄的固定脚本。开始时先记录未知实验条件；在 `standard` 中执行同样的化学流程但没有下面的图操作，在 `dag_record` 中 Coordinator 自提草稿（harness 自动接受）并用 `dag_bind_evidence` 自绑阶段，在 `dag_guided` 中还有 Supervisor 接受草稿并逐调用复核绑定。

| 阶段 | delivery DAG 与证据指针 |
| :--- | :--- |
| 假设与映射 | `reaction_mapping` 显式选中教材 [3,3] 候选 `[4,5,6,1,2,3]`，断 C3–O4、成 C1–C6。Coordinator 用 `dag_propose_mechanism` 提交草稿：R、P occurrence 分别指向 `C=COCC=C`、`C=CCCC=O` species；椅式、船式两条 R→P 候选边，以及需要时展开的双自由基 R→I→P 分支。occurrence 的 stage 契约取 `geometry`（可选 `frequency` / `single_point`），边取 `ts_guess → ts_opt → frequency → short_irc → endpoint_a → endpoint_b → direction → identity`（可选 `thermochemistry`），全部初始 `pending`。`dag_guided` 下 Supervisor 用 `dag_accept_mechanism` 接受后才解锁计算 |
| reactive conformer | 椅式/船式构象搜索；成键 C1···C6 `< 3.0 Å` 只作筛选，不能只拿 conf0。构象文件与搜索结果以 artifact/tool-result 指针挂到候选 |
| 初猜 | 对每个构象分别运行 IDPP `ts_guess interpolate`，必要时并行约束扫描与 `scan_parse`。初猜、扫描峰和默认 `verify` 只是 advisory evidence，只能支撑 `ts_guess` 阶段，不能证明 TS |
| TS 与频率 | `opt=(ts,noeigen,calcfc) freq` 的作业与日志解析留完整结果指针。恰好一个虚频且模式符合断/成键方向时，按序绑定 `ts_opt` 与 `frequency`（组合后即为 `saddle-supported`）；错误虚频数则换构象或重搜，塌缩或高阶鞍点保留失败原因，不删除 |
| 短 IRC 与端点 | 从 TS 双向各走部分 IRC，取两侧外帧分别无约束优化；再做 strict 方向检查和端点 `reaction_mapping`。IRC、两个极小点、strict 结果与 identity match 是独立指针，依次绑定 `short_irc → endpoint_a → endpoint_b → direction → identity` 后椅式边才达到 `endpoint-supported` |
| 竞争路径 | 船式及双自由基候选各自走同样验证；证据不足不能因“教材预期”直接关闭。不计算的分支把相应阶段显式 `skipped` 并附计算原因（唯一非成功处置）；被复核否定的证据是 `rejected` 开放缺口，必须重算重绑或显式跳过，不能删除来制造完整性 |
| 能量与交付 | 若用户要求能垒/选择性，运行统一条件下的单点和 `thermo_analysis`，绑定 `thermochemistry` 阶段。coverage contract 要求热化学时该阶段为 required，绑定后元素升 `thermo-annotated`。默认 contract 不要求热化学，不能反过来冒充用户已要求的自由能报告 |

交付前由 harness 从 delivery DAG 计算 coverage report。Claisen 主路径至少应有 R、P 两个 occurrence 的 required stages 全部 `supported`（或带理由 `skipped`）和一条达到 `endpoint-supported` 的边，所有竞争分支有明确 disposition；若用户要求自由能剖面，还必须满足热化学 gate。这个 report 证明“约定的证据槽已填齐”，不证明协同 Claisen 是宇宙中唯一可能的机理，agent 仍要检查电子结构、方法依赖与实验条件。

# 4. 失败诊断决策表

| 现象 | 可能原因 | 动作 |
| :--- | :--- | :--- |
| 扫描曲线全程单调 | 坐标选错 / 该步无势垒 | 核对 watch_pairs 是否覆盖全部成/断键；改扫另一坐标或改 NEB；若确认无垒则该步为扩散/络合控制 |
| 扫描曲线突跳（滑谷） | 其余自由度弛豫到别的构象谷 | 取跳变前帧作 TS 初猜；缩小扫描步长；或改用 NEB |
| 极大值在扫描边界 | 扫描范围不足 | 扩大范围重扫 |
| 多峰 | 途径多个浅中间体（如络合物） | 分段处理：每个峰一个 TS，中间谷一个中间体 |
| TS 优化塌缩回反应物/产物 | 初猜离 TS 太远 / 构象不对 | 回 `conformer_search` 换 reactive conformer；或用离扫描峰更近的帧 |
| verify 报 2+ 虚频 | 高阶鞍点 | 沿最大虚频振动模式双向位移扰动后重新 TS 优化 |
| IRC 接到错误产物 | 该 TS 属于别的基元步 | 记录此边（可能是新路径）；核对机理假设图，必要时重猜 |
| 自由基体系 `<S^2>` 偏差 > 0.1 | 自旋污染 | 检查对称性破缺是否合理；换泛函复算；结论标注不确定性 |
| SCF 不收敛 | 初猜差 / 近简并 | 换初猜（`guess=mix` 开壳层单重态）、小基组预收敛后 read、或 `stable=opt` 检查波函数稳定性 |
| 半经验（xTB）扫描结果奇异 | 半经验对 TS 精度不足 | 用 DFT 级别重扫（见 SKILL.md §4 Step 1 警告） |
| FOD / T1 / 破缺 ⟨S²⟩ 提示强多参考 | 单参考 DFT 边界 | 按 SKILL.md §3.1.1：r2SCAN/TPSS 缓解 + 标注不确定度；能垒降为定性；建议用户 NEVPT2/CASPT2 复核 |
| IRC 单侧有效点 < 50 | maxpoints/步长不足 | 加大 `maxpoint` 或调整步长重跑该向（SKILL.md §4 Step 3） |

# 5. 禁令与一致性

- **不使用 QST2/QST3**（项目既定政策）：统一走约束扫描 / IDPP 插值 + `opt=(ts,noeigen,calcfc)`。
- IRC 与振动分析与几何优化同基组；单点能可升基组（SKILL.md §2-6）。
- 弥散函数规则见 SKILL.md §2-7；`electronic_analysis` 的键级/布居分析避免弥散基组。

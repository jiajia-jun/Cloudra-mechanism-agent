# 化学工具接口简化与内部能力完善：评审草案

状态：用户已批准实施，核心改动已落地，验证记录见同名 plan 的实施记录。日期：2026-09-27。用户已确认 C1 接触上限采用 1.7 倍，并要求新增自动环构象打标、开放内部技术选型、强化自动化工作流引导和完善 ts_prepare。

## 1. 目标与阅读方式

让 LLM 说明“要研究什么、保持什么”，工具完成采样、输入生成、结果检查和流程衔接。减少接口选择与机械操作，不替 LLM 偷做科学决策。

本次保留现有工具：`conformer_search`（找结构）、`ts_guess`（准备/解析路径与验证）、`ts_prepare` / `ts_resume`（推进完整 TS 流程）。不新建总控工具、服务、数据库或题型专用模式。本文“预组织”指把参与分子摆成适合寻找反应路径的候选几何，不代表稳定结构，更不代表已验证的过渡态。

用户已明确：ring 与 filter 必须独立保留，可以拆开，也可以叠加；ring 同时是便捷入口和环构象引导。其余四项方向认可。本草案进一步给出行为细节，细节尚待审阅。

## 2. 现状：哪些已有，哪些要改

| 部分 | 当前实现 | 本次目标 |
|---|---|---|
| ring/filter | ring 触发引导生成；filter 单独使用主要在生成后筛选 | 两种声明独立；任一存在都能进入引导生成 |
| 环构象 | 有环序列与采样路径，没有自动几何标签 | 保留环构象搜索，并根据实际形状自动打标，不让 LLM 猜 |
| 扫描 | 已支持距离、角度、二面角；Gaussian 双坐标，ORCA 当前单坐标 | 添加一个统一的可选冻结列表 |
| 多碎片检查 | 用全局最近跨碎片原子对判断解离 | 检查所组装的全部组分是否连成整体 |
| TS 流程 | 已有端点闭环；路径失败会建议手工扫描，通知后仍需 Agent resume | 将声明式扫描接回流程；明确等待与继续操作 |
| guidance | 通用物理提示已有；自动化 SOP 提示主要在提交 TS/IRC 后触发 | 在手工路径开始前就引导回自动化入口，去重且不拦截 |

以上是静态代码核查，不是 HE3 等题目的失败归因，也不承诺这些修改必然解题成功。

## 3. 设计一：ring 与 filter 解耦，合并执行

### 用户看到的行为

| 输入 | 应有行为 |
|---|---|
| 都不填 | 保持现有普通构象搜索 |
| 只填 ring_order | 按环序列组织候选、采样环相关构象；缺少显式窗口的预期接触使用现有默认值并报告 |
| 只填 distance_filters | 直接用指定距离窗口指导生成，并检查输出；不要求虚构环 |
| 两者都填 | 环构象引导和距离窗口同时生效，窗口可以作用于环内或环外 |

示例含义：ring 告诉工具“这些原子按这个顺序围成预期的反应环”；filter 告诉工具“另外这两对原子还需保持接近”。原子身份延续完整构建器原子序，包括氢。公开编号按第 12 节：独立结构工具 1-based；引擎工作流跟随软件约定。

`distance_filters` 保留既有格式 `{atoms:[i,j], min_ang:数值, max_ang:数值}`，不增加 secondary_constraints/hbond_windows。本次在支持的预组织模式中统一为“生成时引导、输出时筛选”，这是 filter-only 的显式行为变更，不保留平行旧路径。

### ring 的独立作用与边界

环序列必须保留在内部计划与产物记录中，用于预期闭环关系和环相关构象的生成/采样；不能在接口里保留 ring，内部却直接丢掉。继续提供多候选与既有去重能力，不强制压平、不暗中固定成单一构象。

本轮新增自动构象打标，不要求 LLM 填“椅式还是船式”，也不承诺穷举所有构象。六元环形状优先覆盖 chair、boat、twist_boat、half_chair、envelope 等参考族；中间形状和近似平面不强行二选一。命名标签是几何描述，不代表能量最低、已验证极小值或已验证 TS。

标签对象包括：输入图明确识别的共价六元环，以及 ring_order 指定的六原子预期反应环。前者标 covalent_ring，后者未闭合时标 prospective_ring，并使用“chair-like”等形状措辞，不声称形成了共价环。纯共价环仍可由普通构象搜索产生并打标；本次不将 ring_order 扩展成任意环的专项搜索选择器。稠合环逐环报告，不给整分子一个椅式标签；其他环尺寸报告 unsupported，不套用六元环词汇。

拟采用 Cremer–Pople puckering 坐标和参考形状匹配：计算六原子相对平均平面的起伏，再与理想构象族比较。返回 ring_atoms、ring_kind、puckering 参数、nearest_family、与参考族的距离及歧义状态；摘要给出易读的形状标签，详细数据入候选清单。第一版将标签明确表述为“最接近的构象族”，保留第一/第二候选距离，不新增未经批准的“距离小于多少就算标准椅式”科学门槛或伪概率 confidence。数值退化无法判形时返回 indeterminate；平面附近的数值稳定性与容差需在实现前给出可复现依据。

刚体平移/旋转不改变族标签；环序列循环移动和反向不改变粗分类，但原子定位名称与相位需随编号约定正确转换。打标在实际最终候选坐标上进行，不能按初始模板名称贴标签。标签不进入筛选、评分或能量排序，不为凑齐类型保留不合格候选，也不自动发起额外 QM。

### 合并与错误

- 显式窗口覆盖同一原子对的自动默认窗口；不是把两者同时施加。
- 环外窗口照常保留；重复且一致的窗口去重，重复但不同的窗口明确报错，不自行取交集。
- 原子越界、重复环原子、非有限值、上下界倒置，在计算前报错并指出位置。
- 合法但无法满足的几何要求返回无候选，不自动放宽窗口。
- 距离限制不自动声明成键、配位键或键级变化。filter-only 不得靠豁免全部受约束原子对来绕过拓扑验收；预期键变化仍由已有科学声明确定。
- 能力范围先限现有 guided 后端组合：RDKit conformers、CREST conformers/nci。其他模式携带这类参数时明确说明不支持，不能忽略参数或新增策略开关。
- TS 流程的 prepare/resume 同样支持四种组合；清空 ring 不应清空 filter，反之亦然；精修已提交后继续遵守现有禁止修改几何引导的边界。

## 4. 设计二：扫描只增加“保持什么”

复用 `ts_guess(mode="scan_prepare")` 和既有 `scans`。新增一个可选字段，拟名 `freeze`：每项 `{coord_type:"bond"|"angle"|"dihedral", atoms:[...]}`。含义固定为“保持输入几何中的当前值”。省略或空列表表示不额外冻结。

这样 LLM 只需说明：“扫描这个二面角，同时保持这两处接触。” 本轮不支持冻结项的目标值、距离区间或自动推断配位，以避免含糊的起始几何修正；需要窗口的场合先用预组织生成结构。冻结距离和预组织距离窗口语义不同，不混用。

内部负责索引转换、原生输入写法、去重、冲突检查和实际冻结值记录。同一坐标既扫描又冻结、索引非法、退化的角度/二面角应在写文件前失败。Gaussian 与 ORCA 均需验证原生语法；ORCA 在一个 geom 块中组织 Scan 与 Constraints，不依赖重复块覆盖。与原始 orca_blocks 中同类几何声明发生重叠时拒绝混用并明确原因。

保留现有扫描维度限制，不新增 torsion/atropisomerism 模式，不自动选择联芳轴，不把扫描峰或带冻结的结果当作已验证 TS。后续无约束 TS 精修不继承 freeze。

## 5. 设计三：内部判断整个复合物是否连通

把每个输入组分当作一个点，合格的组分接触当作连线。A 接 B、B 接 C 可以通过；A 接 B、C 游离不能通过。只检查本次被声明要组装在一起的组分，不收集体系之外的其他物种。

**用户已批准的科学判据 C1：** 两个碎片取最近原子对，使用该原子对 vdW 半径和乘以 **1.7** 的接触上限；把原来“只查全局最近一对”改为“逐碎片对建图后查整体连通”。不改变当前 1.0 Å 碰撞下限。接触判据为距离小于等于上限；精确最近距离并列时按稳定原子序确定一对，保证可复现。不改为“任意原子对满足即可”。

该变化同时放宽接触半径、加强整体连通要求。双组分门限从 1.5 变为 1.7，三组分候选数量变化不能预先断言。单组分不做片间连通检查。返回断开的组分集合、原子身份与相关距离，沿用既有输出/诊断承载，不新增 LLM 检查模式。通过只表示几何整体连通，不证明物理结合稳定。

## 6. 设计四：让 ts_prepare 承接扫描路线和已有验证闭环

完整流程继续由 ts_prepare/ts_resume 承担，独立 ts_guess.verify 保持只读验证，不因为“缺材料”暗中启动计算。

流程已有：TS/Freq → 双向 IRC → 外帧提取 → 两侧无约束 Opt/Freq → 身份核对与方向证明。进一步核查发现：guess 当前走 xTB path/缺失时 IDPP；路径失败会把 Agent 引向 ts_guess 手工扫描，而 TsAdjustment 没有接回扫描声明的入口。这是本轮需要补的具体缺口。

拟新增唯一流程输入组 `scan`，可以在 declaration 或 adjustment 中提供：`{method, scans, freeze}`。scans/freeze 与独立扫描工具复用同一校验和生成实现；扫描探索方法显式声明并经过方法策略，最终 method 仍单独控制正式精修。不复制 engine/charge/multiplicity 等已知条件，不让 LLM 选择文件路径和中间日志位置。不提供 scan 时保留现有路径路线；提供后流程负责写扫描输入、走现有计算提交与通知、解析内部峰、提取候选、无约束 TS 精修及后续验证。没有峰则 blocked，给出测量事实和可调整字段，不自动改变坐标/范围/方法。

路径失败后，Agent 可以调用同一个 ts_resume 补 scan，留在原运行记录内；已有 attempt/证据留档。科学假设仍由 Agent 给：工具不从催化剂名字自动推导反应轴或扫描范围。无端点假设的探索仍允许独立 ts_guess；有端点声明的任务优先流程。

当前运行并非完全后台自动串行：作业终态通过既有通知唤醒 Agent，再由其调用无调整 ts_resume 推进下一步。本轮保留该机制，将其明确为正常续跑；不新建后台续跑服务或状态查询工具。将来若要零 LLM 续跑，需单独设计事件幂等与重启边界。

IRC 没收敛本身不等于失败；但双侧材料、极小值证据与方向证明仍按现有口径要求。缺材料时返回缺什么、已有文件在哪里；物种错误不能被自动改名消除。不自动无限延长 IRC 或重试。单独 verify 的补救建议不等于执行完成。

用户决定直接删除未生效的 max_compute_seconds：从 schema、描述和相关声明中移除，不为它新增总机时预算机制。2026-10-18 用户进一步要求移除所有 TS 任务的 max_interventions 上限，覆盖此前保留该限制的设计；保留 path_refinement_runs 及既有计算动作、模型请求和作业资源限制。不声称流程有总时间保障，不绕过调度容量与计算归属。

## 7. 设计五：prompt 与工具提示共同引导使用自动化

修改 small_mol 角色 prompt、dft-calculation 技能及 TS playbook，统一表达：端点和目标明确时默认 ts_prepare；blocked 时针对具体字段 ts_resume；waiting 时等待通知，收到后无调整 resume；需要扫描时优先补 scan 让流程继续。Coordinator 委派按目标与交付物描述，不给专家硬编码一条手工工具链。当前 dft 角色负责周期体系，不把分子 TS SOP 泛化塞进其 prompt。

将现有 guidance-ts-sop 的触发提前到 ts_guess 的 scan_prepare/scan/interpolate/xtb_path 等手工准备入口，以及可明确识别的 TS/IRC 输入准备与提交；复用既有幂等 pin，不每次调用追加，不新增 policy stage。提示提供具体自动化入口，但不阻拦合法的未知端点探索或用户明确要求的手工操作。通用物理思考提示保留；仍不新增催化剂/负电荷专项 pin。

Prompt 文案候选："For molecular TS tasks with declared endpoints, start with ts_prepare. If a scan is needed, supply scan to ts_prepare or ts_resume so the process owns submission, peak extraction and unconstrained refinement. When blocked, correct the named declaration; when waiting, wait for the compute notification and resume without changes. Use standalone tools for unsupported exploration or explicit manual requests, and retain the same evidence requirements."

局部失败由对应工具返回：哪个距离未满足、哪个组分游离、哪侧 IRC 证据缺失。不能只加“优先自动化”的口号却继续在失败结果里强迫走手工链。上述新文案只能在 scan 流程接线并验证后启用。

反馈只能依据测得的数据；不能无轨迹就说“氢键断裂”，不能以 charge<0 自动增加溶剂。详细记录落既有产物文件，模型摘要简洁，保持工具文案英文。已有按来源去重的反思通知继续使用，不重复注入阶段进度。

## 8. 全局边界与验收

- 不修改 Benchmark 题面、gold、权重和评分口径；不添加题号识别逻辑。
- 不自动改变溶剂、电荷、质子化、方法、基组、参与物种；C1 采用用户已批准的 1.7，其他科学门限不得擅改。
- 内部技术栈开放，以质量、耗时、约束支持和部署成本选型；不为每个库增加 LLM 选择参数。不新增服务或公共策略开关，不保留兼容分支。
- async 中同步计算/文件与数据库重活沿既有线程执行路径；科学证据判据继续复用唯一实现。
- 四种 ring/filter 组合有行为测试；ring-only 与组合路径保留环语义；filter-only 真正参与生成。
- 两引擎冻结输入、冲突、索引与无约束精修边界有测试。
- 六元环形状自动打标具有标准几何、扰动、刚体变换、序列置换、平面/退化和预期反应环测试；不以标签改变科学合格判据。
- 连通链通过、游离组分失败、两组分在批准的 1.7 阈值处符合预期有测试。
- 部分 IRC 闭环、缺侧、端点失败/错误身份不误报 verified 有测试。
- 工具公开数量不增加；新增 scan_prepare.freeze、流程 scan 输入组以及输出环几何注释，不新增 LLM 调库选择菜单。
- 自动化扫描链和 waiting/resume 有场景级回归，断言事件、结构化输出、作业身份与状态，不断言模型措辞或声称零 key 测试证明 LLM 偏好。

## 9. 技术选择与尚待落实的研究边界

1. 自动打标是输出能力，不增加“请求椅式/船式”的输入。采用最近参考族及连续几何数据避免未经批准的离散阈值；命名不能强行二选一。
2. freeze 第一版保持当前值，用户已接受此前方案；扫描窗口属于预组织或扫描声明，不增加第二套重叠参数。
3. C1=1.7 已明确批准，不需再次确认。
4. RDKit/CREST、ASE、PySCF 等均可评估。当前仓库已将 ASE 列为主依赖，PySCF 列为 chem extra。库已声明不代表本机可用。ASE 提供结构、优化算法与 calculator 接口；PySCF 提供电子结构计算并可对接几何优化器，二者不能仅凭名称当作完整构象搜索器。先用固定小型夹具比较现有路线与可用替代方案的合格候选数量、形状多样性、时间、失败透明度，再选最小必要实现，不为了选型把所有后端接上。
5. 几何打标本身不需要 QM。引入新计算方法仍须授权与方法策略约束；新优化依赖如需加入，走 pyproject chem extra，不运行时偷偷安装。正式 QM 不绕过统一作业归属、容量、取消和证据路径。
6. max_compute_seconds 按用户决定删除；扫描链依赖现有实际执行的限制，不再以设计总机时预算机制作为前置条件。

研究依据：[Cremer–Pople 原始论文](https://pubs.acs.org/doi/10.1021/ja00839a011)、[六元环参考构象定量描述](https://www.sciencedirect.com/science/article/abs/pii/S004040200001019X)、[ASE 官方文档](https://docs.ase-lib.org/)、[PySCF 几何优化文档](https://pyscf.org/user/geomopt.html)。已查摘要/文档用于选型；公式与分类实现仍须核对全文或可验证实现，并以标准几何验证，不能宣称已完成算法验证。

## 10. 代码导航（给实施者）

- `cloudra/tools/Chemtool/conformer_search.py`：公开结构搜索参数与分流。
- `cloudra/tools/core/preorganization.py`：窗口解析、环声明、引导生成与候选验收。
- `cloudra/tools/core/complex_assembly.py`：多组分采样、力场和片间检查。
- `cloudra/tools/Chemtool/ts_guess.py`：扫描输入与独立验证。
- `cloudra/tools/core/ts_process.py`、`cloudra/tools/Chemtool/ts_search_process.py`：流程声明、继续执行和端点闭环。
- `cloudra/runtime_v2/policies/guidance.py`：保留通用提示和幂等反思。

当前代码默认 reaction_center_window 为 1.6–3.0 Å，TS_PROCESS_SOP.md 中一处仍写 1.8–2.6 Å；实施时只同步文档到代码，不借机改科学默认值。

## 11. Schema 精简审查（用户确认第二版方向后追加）

结论：不需要再拆工具或增加策略对象；当前草案有输出过多、空对象必填、条目形状不透明的问题。优先收敛这些问题，不借审查重构全部旧接口。

### 保留的最小输入

- ring_order 与 distance_filters 分别保留，不能为缩短 schema 合并掉其中一个。
- 扫描工具新增 freeze，默认空列表。保留 coord_type，与既有 scans 一致，避免一个靠枚举、另一个靠数组长度猜类型。
- 流程新增 scan 对象，仅 method、scans、freeze；method/scans 必填，freeze 可省略。scan.method 是探索方法，declaration.method 是最终精修方法，两者语义不同，不能强行去掉一个或暗中继承。
- TsResume_input_schema.adjustment 改为默认空调整，正常续跑仅需 ts_resume(run_id)。有修改时再提供 adjustment。不能把 run_id、job_id、路径、owner 等内部状态再塞进 scan。
- 不增加 enabled、strategy、workflow_mode、ring_type、classification_threshold、confidence、fallback_chain 等字段；新后端不生成新的 LLM 选择菜单。ring 打标自动执行，无需开关。

### 类型明确，但不增加用户概念

目前 distance_filters/scans 使用 list[dict]，字段结构主要藏在 description 中。新增 freeze 不沿用此弱约束写法。为实际共用的三类条目各定义一个具体 Pydantic 类型：DistanceWindowInput(atoms,min_ang,max_ang)、ScanCoordinateInput(coord_type,atoms,scan_start?,scan_end,scan_steps)、FrozenCoordinateInput(coord_type,atoms)。具体类型拒绝未知键、检查数值有限性与原子数量；默认值只复用现有行为，不另定科学值。

这些是同一种 JSON 写法的类型说明，不要求 LLM 多填字段。独立工具与流程共用这些类型和校验，不分别抄两套，也不构造一个有许多可空字段的 UniversalConstraint。工具线缆投影必须验证能正确展示嵌套字段；不能只看 Python 类型而漏掉实际给 LLM 的声明。

### 输出分层

默认候选结果只附简短环摘要：环原子、共价/预期反应环标识、最接近的形状族或无法判别。puckering 数值、第一/第二参考距离及编号约定写既有 manifest，沿用已有路径字段，不增加一串顶层返回字段。没有标签不影响原有候选合格性。内部完整记录不等于全部塞入 LLM 上下文。

### 已有接口的本次处理与保留边界

- 原子编号混用纳入本次修复，按第 12 节统一软件约定，同时更新所有受影响生产者、消费者、文档和测试，不做猜测式兼容。
- max_compute_seconds 直接从公开声明删除，不构建替代框架，不再阻塞扫描链设计。
- ProductGeometry.kind 目前只有 rotate_about_bond 一个值，存在冗余，但不是本轮新增复杂度；不扩成几何操作插件系统。
- ts_guess 的多 mode 大 schema 是存量问题；本轮不拆成更多工具。新增字段说明简短，把操作教程留给技能与阻塞反馈。

本轮 schema 验收：用户 JSON 结构清楚、默认续跑无空对象、未知键不被静默吞掉、两入口同一坐标类型、环标签摘要简短、内部算法参数不外泄。


## 12. 原子编号统一：按目标软件，边界集中转换

用户要求按软件统一并在工具描述中说清楚。本规范采用以下确定规则，不新增 index_base 参数，也不按是否出现数字 0 猜测输入编号。

| 工具上下文 | 对 LLM 的原子编号 |
|---|---|
| Gaussian 工作流/扫描/验证 | 从 1 开始 |
| ORCA 工作流/扫描/验证 | 从 0 开始 |
| 不绑定引擎的结构生成、conformer_search、internal_coordinates 等 | 从 1 开始 |

同一引擎工作流中 reaction_center、product_geometry.atoms、ring_order、distance_filters.atoms、scans.atoms、freeze.atoms、watch_pairs 和 atom_map 的原子编号必须一致。所有原子都以实际完整结构顺序为准，包括氢；不使用原始 SMILES 的字符顺序。通用工具若输出关系对/映射，也按通用 1-based 约定；进入引擎工作流时由集中转换函数处理，不复制多份转换逻辑。

atom_map 的列表位置始终遵循 JSON 列表顺序：第 k 个条目表示产物第 k 个原子对应哪个反应物原子，映射值按目标软件编号。工具描述分别给 Gaussian 与 ORCA 的恒等映射示例：三原子分别为 [1,2,3] 和 [0,1,2]，不能把列表位置与原子编号混淆。

内部几何算法统一用 0-based；公开输入只在进入内部时转换一次，公开输出只在离开内部时转换一次。引擎输入文件按引擎原生语法写出。工作流内部调用通用结构能力走内部函数，不把某个公开 JSON 原样交给另一编号体系的工具。环打标纯函数也采用内部 0-based，输出给 LLM 的 ring_atoms 按所属入口转换。

工具 description 明确“本工具/本次 engine 的首个原子编号”；原子表及证据中引用原子的文字同步标注。阶段失败、扫描距离表、环标签、TS 参考映射与输入使用同一编号，不允许只有成功路径转换正确。跨工具复用时给出固定规则，不要求 LLM 猜测。共享条目类型仅表达字段结构，合法编号上下界由拥有 engine 上下文的边界验证器判定。

实施时逐一盘点受影响原子字段，包括图映射、结构测量、输入编写及其调用点。这里不改变原子序/身份、不扩大到无关图节点 ID、帧编号或普通列表索引。既有未完成 TS process 记录不得被新规则静默重解释：实施前检查运行记录的声明消费路径，内部持久记录保持规范化 0-based；若旧记录无可判定的格式版本，明确拒绝继续并说明需重新声明，不猜测转换或保留兼容分支。

这是接口语义变更，必须把描述、调用方、场景夹具、日志提取与生成输入一起改完；不能只改 schema 文案。验收需覆盖原子 0、最后一个原子、越界、氢、恒等/非恒等映射及相同物理操作跨软件等价。

# 化学工具接口简化 Implementation Plan

> **For agentic workers:** 批准后使用 superpowers:executing-plans 逐项实施。用户已授权实施；不提交或推送。

**Goal:** 在稳定工具入口下完成 ring/filter 解耦、自动环形状打标、扫描冻结、1.7 倍接触图检查，并让 ts_prepare 承接扫描路线，通过 prompt 与提示引导默认使用自动化。

**Architecture:** 保留公开工具，复用 preorganization、complex_assembly 与 ts_process 的唯一实现。ring/filter 统一进入几何引导，freeze 只影响扫描输入；科学证据与任务状态不新增平行实现。

**Tech Stack:** Python、Pydantic、pytest；内部构象技术不锁定 RDKit/CREST，允许评估 ASE、PySCF 及实际有用的依赖；Gaussian/ORCA 的正式输入与证据路径继续复用。

**Spec:** `docs/superpowers/specs/2026-09-27-chem-tool-interface-design.md` 第二版。实施者必须同时阅读。C1=1.7 已获明确批准；本轮已获实施授权。新 scan 流程与打标细节按第二版评审，不将前版认可扩大为所有技术细节的确认。

## Global Constraints

- 不修改 Benchmark 题面、gold、权重和评分口径；不添加题号识别逻辑。
- 不自动改变溶剂、电荷、质子化、方法、基组、参与物种；C1 采用用户已批准的 1.7，其他科学门限不得擅改。
- 内部技术栈开放，依赖按实际需要选择并声明；不新增服务或 LLM 后端选择菜单，不保留兼容分支。
- Python >=3.11、POSIX；代码与英文工具文案遵守 AGENTS.md。
- 不覆盖当前工作区已有改动，不提交或推送；实施开始时重新检查状态。
- 测试顺序 compileall → ruff → 相关文件测试；不跑全套。可选环境缺失按探测 skip。
- 原生引擎语法核对官方资料；验证范围按实际环境报告。

## Review Focus

1. filter-only 不能意外放行新共价连接：任务 1 覆盖拓扑守卫。
2. 清空 ring 后 filter 仍有效、清空 filter 后 ring 仍有效：任务 1 覆盖 resume。
3. 同坐标的反向索引和周期二面角不能漏过冲突检查：任务 2 覆盖。
4. 三组分的局部接触不能掩盖孤立组分，双组分只按批准的 1.7 门限改变：任务 3 覆盖。
5. 部分 IRC 外帧可用不等于端点已验证：任务 4 覆盖失败与证据不足。

## 任务 0：内部技术选型

**Files:** 读取 `pyproject.toml`、现有结构搜索实现、`cloudra/tools/core/ts_process.py` 和实际计算账本计时来源；选型结果补入 spec 的第 9 节。仅确有需要时修改 pyproject 的 chem extra。

- [ ] 检查已声明库与实际可用环境，核对 Cremer–Pople 公式/参考族；不得把网页摘要当完整算法规范。
- [ ] 固定小型夹具覆盖普通六元环、预期反应环和多组分约束；比較现有路线与一个确有优势的可用替代路线，不铺设所有后端。
- [ ] 记录候选合格率、形状多样性、耗时、依赖成本及失败原因；按这些结果选择实现，保持公开参数不扩张。科学能量模型保持授权范围。
- [ ] 确认未引入绕过作业归属与容量限制的新计算路径；不再研究或实现已决定删除的总机时预算字段。

**交付:** 有证据的最小技术选择；不新增通用插件框架。

## 任务 0B：Schema 收敛与真实线缆检查

**Files:** 新增 `cloudra/tools/core/geometry_inputs.py`，供 `conformer_search.py`、`ts_guess.py`、`ts_process.py` 共用；修改 `ts_search_process.py` 的 adjustment 默认值。测试新增 `tests/test_geometry_inputs.py` 并使用实际 `tool_catalog.py` 线缆投影验证嵌套类型，不另建 schema 输出器。

**Interfaces:** DistanceWindowInput(atoms,min_ang,max_ang)、ScanCoordinateInput(coord_type,atoms,scan_start?,scan_end,scan_steps)、FrozenCoordinateInput(coord_type,atoms)。具体默认行为与 spec 第 11 节一致；原子编号遵循第 12 节，由工具边界按 engine 验证后转为内部 0-based。已有内部 Mapping 消费点在单一边界转为其所需形式，不能让每一层复制转换。仅新增这三个有实际调用方的类型，不使用抽象继承树或万能约束对象。

- [ ] 读取现有 scan_start/steps 默认规则并原样保留；拒绝未知条目键，验证必需字段、有限数值、原子数和范围，复用已有科学默认值。
- [ ] 写条目 schema 与真实线缆回归：字段可见，不是空 object；未知键失败；独立工具和流程使用相同类型；原 JSON 字段名与形状不变。
- [ ] 使 TsResume_input_schema.adjustment 默认构造空 TsAdjustment；测试仅 run_id 的正常续跑，并确认不消耗干预次数。
- [ ] 任务 1B 输出只加摘要，详细几何参数留 manifest；任务 4A 的 scan 不复制 owner、engine、charge、路径和 job_id。
- [ ] compileall、ruff 后运行 `uv run pytest -q tests/test_geometry_inputs.py tests/test_ts_process.py tests/test_ts_guess.py tests/test_conformer_search.py`；线缆投影测试按实际所在文件另行聚焦运行，不运行全套。

**交付:** 机器可读且简短的 schema，不增加用户要理解的参数概念。

## 任务 1：ring/filter 独立输入、统一生成

**Files:** 修改 `cloudra/tools/core/preorganization.py`、`cloudra/tools/Chemtool/conformer_search.py`、`cloudra/tools/core/ts_process.py`；按需同步 `cloudra/tools/Chemtool/ts_search_process.py` 参数说明。测试 `tests/test_preorganization.py`、`tests/test_conformer_search.py`、`tests/test_ts_process.py`。

**Interfaces:** 保留 `search_guided(..., ring_order, distance_filters, ...)` 和 `resolve_guidance(prepared, ring_order, distance_filters, *, assembly_parameters=None)` 签名，允许 ring_order 为空序列；`GuidancePlan` 保留 ring_order、windows、forming_pairs、bonded_pairs 现有职责（实施时按真实字段名核对），filter 不生成键变化声明。没有引导时走原普通路径。

- [ ] 阅读候选生成和拓扑检查全链，保留 ring 的构象采样作用；自动打标由任务 1B 实现，不新增目标类型输入。
- [ ] 增加失败回归：四种输入组合；显式覆盖默认；环外窗口；重复冲突；filter-only 在生成时收到窗口；ring 序列保留在产物；拓扑异常仍被拒绝。
- [ ] 为 prepare/resume 增加清空一项保留另一项、失败后重建留档、精修后不允许改变引导的测试。
- [ ] 运行新增测试确认是当前行为差异导致失败。
- [ ] 让允许的后端在任一引导存在时进入统一路径，去掉 filter-only 的平行事后筛选分支；不支持的组合在前置校验明确失败。
- [ ] 检查候选判据不把所有 filter 对自动视作 forming_pairs；需要新的成键科学语义时停在明确缺口，不能放宽拓扑。
- [ ] 对修改文件做 compileall、ruff；运行 `uv run pytest -q tests/test_preorganization.py tests/test_conformer_search.py tests/test_ts_process.py`。通过或按环境合理 skip，无新失败。

**交付:** LLM 不增加参数，ring/filter 单独与组合调用均有一致生成语义。

## 任务 1B：自动环形状打标

**Files:** 新增 `cloudra/tools/core/ring_conformation.py` 与 `tests/test_ring_conformation.py`；在 `preorganization.py`、`conformer_search.py` 和 `ts_process.py` 的最终候选记录点复用。细节落现有候选清单，摘要复用现有输出承载。

**Interfaces:** 内部纯函数 `describe_ring_shape(positions, ring_atoms, *, ring_kind) -> dict`；positions 为完整坐标序列，ring_atoms 为完整内部 0-based 原子索引，ring_kind 为 covalent_ring/prospective_ring。返回 spec 规定的几何参数、最近参考族、参考距离与状态；无计算提交、无新工具、无筛选副作用。

- [ ] 基于任务 0 核实的定义建立可复核标准几何：chair、boat、twist_boat、half_chair、envelope、平面；明确参考族对编号变换的等价集合。
- [ ] 编写回归：标准形状粗分类、扰动后连续距离、平移旋转不变、环序列循环/反向不变、退化坐标 indeterminate、非六元环 unsupported、稠合环逐环、预期反应环标注为 shape-like。
- [ ] 实现纯几何描述与最近参考族比较，不定义“标准椅式合格阈值”、不输出伪概率。不从初始模板继承标签。
- [ ] 接到所有本次支持的最终候选路径，包括 filter-only 的共价六元环；标签失败/不支持不能伪造标签，也不凭标签丢弃原本合格的候选。
- [ ] compileall、ruff 后运行 `uv run pytest -q tests/test_ring_conformation.py tests/test_preorganization.py tests/test_conformer_search.py`；证据包括原始 puckering 值和分类，不只断言输出字符串。

**交付:** Agent 自动获得几何形状注释，不必自己“看图猜椅式”，无需新输入字段。

## 任务 2：统一扫描冻结入口

**Files:** 修改 `cloudra/tools/Chemtool/ts_guess.py`；测试 `tests/test_ts_guess.py`。复用现有坐标辅助函数，不新建通用约束框架。

**Interfaces:** `TsGuess_input_schema.freeze: list[FrozenCoordinateInput]`，默认空列表；每项仅 coord_type 与 atoms，固定当前值。公开索引按 engine 约定，内部 0-based。scans 改为共用 ScanCoordinateInput 条目，JSON 写法不变。原扫描输出字段保留，生效冻结值写现有结果说明/产物。

- [ ] 核对 Gaussian ModRedundant 与 ORCA geom Constraints 官方语法、当前值固定方式和坐标反向等价规则。
- [ ] 增加输入生成回归：两引擎各三种坐标、空列表不改变原输入、索引转换、重复去重、扫描与冻结冲突、越界/退化坐标、原始 geom 块冲突。
- [ ] 运行新增测试确认当前缺失 freeze 支持导致失败。
- [ ] 实现前置校验与两引擎渲染；ORCA 统一在单一 geom 块组织扫描和约束，不静默覆盖。
- [ ] 增加并验证扫描约束不进入后续无约束 TS 精修的边界测试，不新增隐式提交。
- [ ] compileall、ruff 后运行 `uv run pytest -q tests/test_ts_guess.py`；有引擎时进行小输入验证，无引擎则报告语法验证范围，不能称已实跑。

**交付:** LLM 可以声明扫描什么、保持什么，不需要编写原生约束文本。

## 任务 3：整体连通性检查（C1=1.7 已批准）

**Files:** 修改 `cloudra/tools/core/complex_assembly.py`，必要时由 `preorganization.py` 复用；测试 `tests/test_complex_assembly.py`、`tests/test_preorganization.py`。

**Interfaces:** 在现有组装验收位置用内部接触图计算替换全局最近对解离判断。消费已有 positions、groups、元素与 AssemblyParameters；结果进入既有 diagnostics/counts，不新建公共输入。

- [ ] 将既有 max_interfragment_vdw_factor 默认值从 1.5 更新为用户批准的 1.7；碰撞下限仍为 1.0 Å。
- [ ] 编写几何夹具：单组分；接触双组分；解离双组分；A-B-C 链；A-B 加孤立 C；多个连通簇；碰撞独立失败；边界距离。
- [ ] 断言各碎片对采用最近原子对对应的 1.7 × vdW 门限、最近对并列时确定性选择、三组分孤立不能通过、断开组分身份可定位；运行并确认差异复现。
- [ ] 内部逐对建接触图，用图遍历判断整体连通；双组分补 1.5 与 1.7 之间距离的通过测试及超过 1.7 的失败测试，保留碰撞检查。
- [ ] 在普通与 guided 多组分路径验证同一判据，避免重复实现。
- [ ] compileall、ruff 后运行 `uv run pytest -q tests/test_complex_assembly.py tests/test_preorganization.py`。

**交付:** 组装完整性由工具负责；LLM 无需选择判定模式。

## 任务 4A：将声明式扫描接入 ts_prepare/ts_resume

**Files:** `cloudra/tools/core/ts_process.py`、`cloudra/tools/Chemtool/ts_search_process.py`、`cloudra/tools/Chemtool/ts_guess.py`；必要时提取扫描校验/渲染到 `cloudra/tools/core/ts_scan.py`，两入口共同调用。测试 `tests/test_ts_process.py`、`tests/test_ts_guess.py`、新增 `tests/test_runtime_v2_ts_workflow_scenarios.py`。

**Interfaces:** `TsDeclaration.scan` 和 `TsAdjustment.scan` 为可选同型声明 `{method, scans, freeze}`；method 必填，scans/freeze 复用独立工具表示。新增内部路径来源 scan，不增加公共工具。scan 未提供保持既有路径；声明后沿既有 stage、process.json、作业账本推进。

- [ ] 确认 max_compute_seconds 已删除，扫描链仍遵守实际生效的干预/路径轮数限制及作业资源约束；不新增总时间预算机制。
- [ ] 编写真实流程回归：从 prepare 提供 scan；路径失败后 resume 补 scan；扫描完成解析内峰并接无约束精修；无峰 blocked；错误几何或方法拒绝；日志/候选缺失不提交后续。
- [ ] 明确调整语义：只允许尚未进入精修且无在途扫描作业时修改 scan；扫描失败后的新声明开新 attempt 并保留旧产物。省略不变，不用空对象隐式清除。恢复/重复通知不重复提交。
- [ ] 实现单一校验/输入生成复用，扫描作业有现有 owner 与节点归属，不由工具直接启动正式 QM。freeze 仅在扫描存在，精修输入不继承。
- [ ] 将 scan 加入 continuation/干预计数判断；无调整 waiting-resume 不消耗科学干预次数。扩展 path_kind 与阶段记录，使扫描来源可追溯。
- [ ] 用 ScenarioHarness 覆盖通知唤醒后 resume、blocked 修正、终态证据序列；不调用真实 LLM、不断言措辞、不把 ScriptedProvider 路线当作模型偏好测量。
- [ ] compileall、ruff，运行本任务测试及 `tests/test_no_sync_on_loop.py`。

**交付:** Agent 给扫描意图，流程承担提交、解析、精修和验证，不再被工具结果迫使手工串链。

## 任务 4B：验证已有 TS 闭环和简洁反馈

**Files:** 核查 `cloudra/tools/core/ts_process.py`、`cloudra/tools/Chemtool/ts_guess.py`；测试 `tests/test_ts_process.py`、`tests/test_ts_guess.py`、`tests/test_runtime_v2_guidance.py`。仅确认缺口后修改实现，不预设重写。

**Interfaces:** 保持 prepare/resume、verify 和既有过程记录/通知；verify 不提交作业。沿用现有 verified 证据判据与预算。

- [ ] 盘点已有测试，避免重复补齐已覆盖的实现镜像测试。
- [ ] 补缺失行为测试：部分 IRC 两侧外帧接 Opt/Freq、缺侧停止、端点不收敛/有虚频/身份不符不 verified、实际生效的干预预算耗尽不继续提交、恢复不重复提交。
- [ ] 运行测试，已有行为通过就保留；若发现缺陷，先复现，再在现有实现根治。Agent 级故障按 AGENTS.md 补场景测试。
- [ ] 检查新失败反馈只陈述测量事实，局部错误进入工具结果；不加催化剂/负电荷专项 pin，不扩大常驻提示。
- [ ] compileall、ruff 后运行该任务的三个测试文件；涉及异步执行变更时另跑 `tests/test_no_sync_on_loop.py`。

**交付:** 已有自动化能力可依赖，避免把重复串接工作交回 LLM。

## 任务 5：自动化优先的 prompt 与幂等提示

**Files:** `cloudra/prompts/small_mol.md`、`cloudra/prompts/coordinator.md`、`cloudra/skills/dft-calculation/SKILL.md`、`cloudra/skills/dft-calculation/references/ts-search-playbook.md`、`cloudra/runtime_v2/policies/guidance.py`、`cloudra/tools/Chemtool/ts_search_process.py`；测试 `tests/test_runtime_v2_guidance.py` 和任务 4A 场景。

- [ ] 任务 4A 完成后才宣传 scan 自动化能力；检查角色分工，不把分子 TS SOP 塞入周期体系 dft 角色。
- [ ] 同步默认路线：有端点先 prepare；需扫描补 scan；blocked 局部修正；waiting 等通知后 resume；未知端点/明确手工要求保留低层入口。删除与此矛盾的失败补救指令。
- [ ] 提前现有 guidance-ts-sop 触发到手工 TS 准备入口，复用同一幂等 key；已有流程调用不重复轰炸；提交时现有检测保留。
- [ ] 测试触发集合、重复调用 pin 去重、工具不被阻拦、非 TS 普通计算不收到 SOP 引导。所有断言围绕通知身份与状态，不锁模型措辞。
- [ ] compileall、ruff 后运行 `uv run pytest -q tests/test_runtime_v2_guidance.py tests/test_runtime_v2_ts_workflow_scenarios.py`。真实 LLM 是否更偏好自动化留待独立、受授权的实验，不声称本次测试证明。

**交付:** 默认说明、工具描述、失败建议和动态提示一致，并且描述的能力已经可用。

## 任务 6：文档与收尾验收

**Files:** `docs/TS_PROCESS_SOP.md`、`AGENTS.md`，以及实际受影响的工具参数描述。代码修改完成后按项目约定运行 `scripts/gen_copyright_source.py`，检查生成差异不覆盖用户原有改动。

- [ ] 文档同步 ring/filter 四种组合、自动形状打标及限度、freeze 当前值语义、1.7 整体连通性、scan 自动化及 verify/流程边界。
- [ ] 将 SOP 过期默认窗口说明与当前代码单一来源对齐，不改默认值。
- [ ] 审查公开接口差异：工具数量不变，新增 freeze 与流程 scan、形状注释；C1 仅按批准更新为 1.7；复用已有 SOP pin，不新增题型模式、服务、后端菜单。依赖变更必须有任务 0 的实际用途证据。
- [ ] 对最终修改文件 compileall；运行 `uv run ruff check cloudra tests`，区分原有问题与本次问题；相关测试已通过则不无理由重复跑，不跑全套。
- [ ] 汇报实际变更、通过/跳过的验证、未实跑引擎的限制和剩余科学决定。没有真实题目实验，不宣称 Benchmark 得分提升。

## 执行顺序与用户验收

建议按 0 → 0B → 0C → 1 → 1B → 2 → 3 → 4A → 4B → 5 → 6 顺序实施。先把工具能力接通，再强化 prompt，避免让 Agent 遵守一个实际走不通的流程。C1 已批准，不再重复询问；max_compute_seconds 直接删除；原子编号按软件统一并同步全部受影响调用方。实施结果记在下方。


## 任务 0C：删除空预算字段并统一软件原子编号

**Files:** `cloudra/tools/core/ts_process.py`、`cloudra/tools/Chemtool/ts_search_process.py`、`cloudra/tools/Chemtool/ts_guess.py`、`cloudra/tools/core/geometry_inputs.py`；盘点并修改实际受影响的 `conformer_search`、`internal_coordinates`、`reaction_mapping`、`qm_input_writer` 及其核心辅助调用方。文档/技能/测试随同修改，不靠描述掩盖实现。盘点后将确切文件补入本计划再实施。

**Interfaces:** 引擎入口 Gaussian=1-based、ORCA=0-based；通用结构入口=1-based；内部计算=0-based。不提供 index_base 字段，不自动侦测。共享转换函数接收已知入口基准，未知引擎报错。TsDeclaration.budget 删除 max_compute_seconds；保留实际执行的其他成员。

- [ ] 搜索受影响的原子字段及调用链，列出公开输入、内部记录、输出表格三者的基准；明确每个边界唯一转换点。禁止全局机械替换所有 +1/-1。
- [ ] 删除 max_compute_seconds 的 schema/文案/示例引用，并测试实际线缆不再包含该字段；不新增对应调度实现。
- [ ] 写测试：Gaussian 首原子 1、ORCA 首原子 0、通用工具首原子 1；末原子合法与越界拒绝；包含氢的原子顺序不变。
- [ ] 写跨入口等价测试：同一原子对、环序列、冻结二面角和产物旋转，在两引擎编号下选中同一物理原子；恒等/非恒等 atom_map、watch_pairs 与输出标签也一致。
- [ ] 将公开声明正规化为内部 0-based，内部持久状态与后续 resume 不重复减一；输出和错误消息按入口还原。明确旧未完成记录不可静默重解释，必要时以明确格式版本拒绝旧记录，不写猜测式兼容。
- [ ] 更新工具描述、示例、prompt/skills 中原子编号说明；测试实际线缆上的说明和行为一致，独立结构表转入引擎参数的例子清楚。
- [ ] 按盘点后的修改文件 compileall、ruff，然后运行对应前缀测试；不跑全套。TS 工作流场景覆盖重复 resume，确保编号不会逐次漂移。

**交付:** 同一软件工作流内所有原子字段使用同一编号；LLM 可以照软件习惯填写，内部统一处理转换，预算 schema 不再承诺未实现功能。


## 实施记录（2026-09-27）

核心功能已实现：ring/filter 统一生成与独立组合；六元环几何打标；C1 1.7 接触图；原生 freeze；声明式 scan 的准备、提交、等通知、解析及无约束精修；提前且去重的 SOP 提示；删除未接线预算字段；软件原生编号及具体嵌套 schema。工具数量未增加，未改科学方法和评分口径。

实现采用现有 RDKit/CREST 搜索与 NumPy 几何描述。ASE、PySCF 在本机可用，但本轮没有把电子结构计算接入纯几何打标，也没有新增依赖或后端菜单。未进行新后端性能比较，不声称现有后端最优；前述任务 0 的替代后端比较未开展。六元环测试覆盖 chair、boat、twist_boat、envelope、half_chair 参考几何及编号/刚体变换不变性，平面或退化不强行打标。

审查修复：几何变更清除旧扫描；guided 最终候选也检查整体连通；补 scan 不跳过前置阶段；缺扫描日志转为可修正的 blocked；扫描峰检查原子序及有限坐标；guided ensemble 包含所有候选。正常 resume 无需 adjustment，不计干预。

验证采用 compileall、全项目 ruff 和相关文件测试，没有跑全套。最近一组 105 项验收通过，覆盖共享 IRC、线缆投影、几何输入、构象和扫描状态；另跑 TS 工具、过程、guidance 与真实 ScenarioHarness。真实 CREST QCG 溶剂壳测试失败，使用 HEAD 版 conformer_search 独立复跑同样报 Wall Potential too small，保留为原有外部引擎失败。新 Gaussian/ORCA 冻结语法只验证生成输入，没有正式 QM 端到端或 Benchmark 跑分。

软著源程序生成器已在 /tmp/cloudra-chem-copyright 重建 txt/tex/pdf，避免覆盖用户已有未提交的软著文件。未提交或推送。

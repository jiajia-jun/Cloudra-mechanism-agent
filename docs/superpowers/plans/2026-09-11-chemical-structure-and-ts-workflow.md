# 化学结构构建、CREST 修复与自动 TS 搜索计划

> 执行者：按任务逐项实施，使用 superpowers:executing-plans；每个修复先建立失败测试再修改实现。本文不授权提交、推送或运行新的科研计算。

**Goal:** 便宜 agent 只提供反应物/产物 SMILES 和必要的科学条件，工具承担分片、映射、构象与复合物生成、路径搜索、TS 验证，并保存全过程。

**Architecture:** 收拢重复的 SMILES 建模入口，建立共享的结构与轨迹契约。先恢复基础工具可靠性和 CREST 现场可追溯性，再以真实案例选择端到端 TS 后端；长计算经过现有调度体系。

**Tech Stack:** 现有 RDKit、ASE、Pydantic、runtime_v2、计算调度器；CREST/xTB/ORCA 为外部引擎。autodE 是待评估候选，尚未批准作为新依赖。

**Spec:** 本会话的用户要求及 GitHub issue #33：https://github.com/yyywaa/Cloudra-mechanism-agent/issues/33 。本文是待讨论的实施计划；下列科学决策未获批准前，不把它们固化为默认行为。

## 约束与已知证据

- 不让 agent 手写三维坐标、手工做原子映射、试探扫描距离或解析日志。
- 复合物按分子图连通分量拆分，保留全部组分、形式电荷、立体化学与原子身份；不能将点号简单解释成“可删除的盐”。
- 科学参数、方法选择、拓扑变更接受规则、搜索预算由用户确认。拆分已获用户明确提出；组装距离和采样策略尚未获批。
- 不引入正则，不添加兼容 shim；异步入口不得阻塞事件循环；计算过程沿用归属与取消契约。
- 只修改必要模块。修复路径问题前先核对运行版本：当前 ts_guess 与 qm_input_writer 已有工作区解析，issue 参数名称与当前 schema 有差异。
- issue 第 5 条报错文本对应当前 internal_coordinates 的读取路径，不能直接断定来自 ts_guess。
- 当前 smiles_to_mol、qm_input_writer、CREST 种子分支各自嵌入与优化；RDKit 构象搜索分支的旧修复未统一覆盖这些入口。
- 当前 CREST 使用 TemporaryDirectory，结束后原始现场被删除；成功判定主要依赖产物存在，需要补充引擎结束与产物完整性检查。

## 第一阶段：结构构建与 CREST，优先交付

### Task 1：固定复现与版本证据

**Files:** tests/test_smiles_to_mol.py、tests/test_conformer_search.py、tests/test_internal_coordinates.py、tests/test_ts_guess.py；新增 tests/fixtures/chemtool_issue33/。

- [ ] 获取 #33 原始工具参数、结果、输入结构、引擎完整日志及运行代码版本；缺失的材料明确标记为未复现，不能用推测替代。
- [ ] 建立 `[F-].CCl`、`[O-]C=C.O.CC=O` 与单分子对照输入；另外保留一个已知合理的复合物 XYZ，以区分构建失败与 CREST 本身失败。
- [ ] 保存实际 CREST/xTB/ORCA 版本和命令行；不输出密钥或完整环境变量。
- [ ] 对每个缺陷先运行单个回归测试并确认因目标缺陷失败；没有真实引擎时用固定日志测试解析，真实计算验收另列，不能声称已验证 CREST 可用。

**交付:** 可定位到工具、版本和输入的复现表；分别记录观察事实与根因假设。0.139 Å 是 issue 报告值，不写成跨随机种子必须重现的测试断言。

### Task 2：统一分片建模与逐步轨迹

**Files:** 新增 cloudra/tools/core/structure_builder.py、cloudra/tools/core/structure_artifacts.py、tests/test_structure_builder.py；修改 smiles_to_mol.py、qm_input_writer.py、conformer_search.py 及对应测试。

**接口契约:** `prepare_structure(request) -> PreparedStructure`。request 明确携带输入 SMILES、总电荷/多重度信息、输出目录及已批准的构建策略；PreparedStructure 包含状态、组分、原子映射、候选结构路径、轨迹清单和诊断，不用自由文本表达收敛状态。具体 Pydantic 类型与现有输出 schema 一起改，不保留重复实现。

- [ ] 先写测试：拆分后元素/原子身份守恒，形式电荷总和一致，立体标记保留；重复同种组分不合并，单原子离子也保留。
- [ ] 用 RDKit 图连通分量拆分并保留原始索引映射，再加显式氢；为新增氢登记稳定身份，不能让 AddHs 后的数组位置充当跨反应映射。
- [ ] 分别生成、优化每个可处理组分。单原子组分无需调用力场；缺参数或不支持的自旋明确返回状态，不能以“坐标已生成”冒充优化成功。
- [ ] 以 RDKit MinimizeTrajectory 的逐步快照实现力场轨迹；保存初始帧、每个优化迭代帧、终态、能量单位、力场、随机种子、收敛码。每次回退/重试独立编号；失败轨迹同样保留。
- [ ] 轨迹测试检查初始和最终坐标、编号及元数据一致性，覆盖未收敛和异常退出；不要反复调用单步 Minimize 来模拟一条连续优化轨迹。
- [ ] 三个入口全部调用共享实现，删掉各自的 EmbedMolecule/MMFF 快捷路径。多片输入必须经过组装后才允许输出“复合物候选”，不能把重叠的片段坐标拼在一起返回成功。

**组装方案（待批准后实施）:** 对分片构象进行多个相对取向的采样；反应模式使用反应物/产物映射得到的反应中心引导组装，普通复合物模式不凭空指定成键中心。刚体摆放阶段保持片内几何；片间排斥检查通过后再按批准的方法弛豫。仅平移拉开距离不算完成反应复合物生成。

**科学决策:** 组装采样数、距离/碰撞标准、预优化方法、约束是否使用与何时释放、构象筛选规则。实施前给用户具体候选值与依据；不能由 agent 自动设置。

### Task 3：CREST 现场持久化与失败分层

**Files:** conformer_search.py；新增 cloudra/tools/core/crest_runner.py、tests/test_crest_runner.py。

**接口契约:** `run_crest(request) -> CrestRunResult`，返回运行目录、返回码、阶段、终止原因、日志与产物清单。科学成功与进程退出分开表达；失败输出不能进入成功构象排序。

- [ ] 写失败测试：非零退出但存在部分 crest_conformers.xyz 时不报成功；缺失、空、截断产物分别报错；超时与解析失败后日志和种子仍存在。
- [ ] 改为输出目录下每次独立的持久运行目录，保存命令参数、输入、版本、完整 stdout/stderr、xTB 日志及中间 XYZ，不再只返回末尾文本后删除现场。
- [ ] 根据所安装版本的实际日志标记与返回码分类，使用精确行/token 解析：初始优化失败、初始拓扑变化、搜索阶段失败、超时、产物不完整、未知失败。未知失败保留原文并明确报错。
- [ ] 固定日志测试覆盖所有分类；真实引擎测试再验证终止标记与结果一致。阶段识别不能以文件存在充当正常完成。

### Task 4：逐类解决 CREST 报错

**Files:** crest_runner.py、conformer_search.py、tests/test_crest_runner.py、tests/test_conformer_search.py。

- [ ] **Initial geometry optimization failed:** 先检查 Task 2 的实际输入与完整底层日志，区分碰撞、电子态输入、SCF/优化不收敛、版本或执行环境问题。这个报错不是“必然原子重叠”的充分证据。
- [ ] 同一合法种子、相同方法和电子态条件，比较独立 xTB 优化与 CREST 初始优化。独立也失败则处理具体结构/方法原因；独立成功则核对 CREST 的实际子引擎、参数和版本，禁止靠无限重试掩盖差异。
- [ ] **Change in topology:** 保存初始和优化后结构，报告片内键变化、片间变化及是否进入预期产物；只记录变化，不擅自把变化判为允许。
- [ ] 查实际版本是否支持 NCI 模式，并评估它的势能约束与采样行为是否适合目标复合物。NCI 模式作为候选策略，不直接对所有带点号 SMILES 开启。
- [ ] 如证据确认仅初始拓扑检查阻塞，向用户提交使用 `--noreftopo` 的具体适用条件。该选项只关闭初始检查，不能替代搜索过程中结构身份检查，也不与全面关闭拓扑检查混用。
- [ ] 修复后重复合理 XYZ 与 SMILES→分片→组装两条完整路径。正常完成却没有符合任务定义的复合物候选，应返回无可用候选而非成功完成任务；具体筛选科学规则先批准。

**验收:** 两类已复现失败各有红绿回归；失败现场完整可读；方法不支持明确报错；不会因选项变化把真实反应产物偷偷纳入反应物构象集合。

## 第二阶段：内坐标与产物衔接

### Task 5：独立几何分析及统一路径

**Files:** internal_coordinates.py、tests/test_internal_coordinates.py；按复现结果修改 qm_input_writer.py、ts_guess.py 及其测试。

- [ ] 测试中让进程 CWD 与 agent 工作区不同，分别覆盖路径读取、输出和文本输入默认路径；验证两个 agent 同名文件互不串目录。
- [ ] internal_coordinates 统一调用已有 resolve_tool_path。读取失败显示解析后的目标和具体错误，不再把不存在的文件误报成未提供参数。
- [ ] 几何距离/角度报告与 Z-matrix 导出分别给状态；chemcoord 缺失或 Z-matrix 失败不能让已完成的基础测量不可用。增加故意触发导出失败的测试。
- [ ] Z-matrix 输入改为显式结构化/逐 token 校验；未知引用、缺参数、非有限数值明确拒绝，删除正则和缺失值静默补零。合法绝对参考规则与非法缺字段分开测试。
- [ ] 不在此任务改变现有化学异常阈值；TS 的键级推断不确定性明确保留，不把几何启发式提升为已证实成键/断键。

### Task 6：日志路径与失败作业产物

**Files:** infra/compute_utils.py、services/compute_store.py、相关 Chemtool 读取入口与现有计算/解析测试；以真实复现决定最小修改范围。

- [ ] 用已登记的 compute job log_path/resolve_log_path 找日志，测试实际 `.cloudra/calc-<id>.out.log`，不添加新的文件名猜测链。
- [ ] 保留 ORCA 退出 139 的作业失败状态，测试失败作业仍能提取有来源的几何中间产物，同时频率/TS 验证不会被伪标完成。
- [ ] 核对段错误的原始日志、引擎版本和最小输入；仅在获得计算授权后比较联合作业与拆分优化/频率作业，不预先宣称 macOS 上必现或拆分必治。

## 第三阶段：从反应 SMILES 到已验证 TS

### Task 7：后端选型实验，先于集成

**候选:** autodE 的反应自动化流程；共享结构构建 + ORCA NEB-TS。二者在相同输入、方法和预算下比较，不能把“给好 XYZ”当作端到端完成。

- [ ] 从 #33 和既有任务池选择多碎片 SN2、质子转移、分子内重排案例；用户批准方法与预算后才运行。
- [ ] 全流程记录：输入校验、映射（含氢）、组装候选、路径、TS 优化、频率与 IRC；比较是否需 agent 手工补救、计算耗费、可追溯性及已验证结果数量。
- [ ] 检查 autodE 的外部计算提交接口能否适配现有 scheduler、方法白名单、取消与证据持久化；不能另起一条绕过计算管理的执行链。
- [ ] 交付选型报告及独立集成计划。未完成实验前，不引入新运行时依赖、不承诺所有体系均可自动找到 TS。

**最终接口目标:** `reaction_search` 接受两端 SMILES、必要电子态条件和已批准策略标识，返回运行 ID；内部有界推进，最终状态区分 verified、candidate_only、search_failed、invalid_input。搜索失败不等同于反应不可能。原子/电荷/自旋歧义须显式呈现，不能交给低成本 agent 猜坐标来绕过。

## 验证与交付顺序

1. Task 1 → Task 2/3 → Task 4：先消除重复坏种子与 CREST 黑盒。
2. Task 5/6：恢复几何检查、文件和日志闭环。
3. Task 7：用可靠底座评估完整 TS 自动化。

- [ ] 每次 Python 修改先执行 `uv run python -m compileall -q <改动文件>`。
- [ ] 跑对应 `tests/test_smiles_to_mol.py`、`tests/test_structure_builder.py`、`tests/test_crest_runner.py`、`tests/test_conformer_search.py`、`tests/test_internal_coordinates.py`、`tests/test_ts_guess.py` 与 QM writer 现有用例。
- [ ] 执行 `uv run ruff check cloudra tests` 和 `uv run pytest -q tests/`；化学可选依赖按仓库要求探测，真实 CREST 验收与跳过结果分开报告。
- [ ] 涉及 async 路径时运行 `tests/test_no_sync_on_loop.py`；不通过移动阻塞到另一个 async 函数来规避。
- [ ] 同步工具 schema、说明、调用示例与 AGENTS.md；删除重复建模分支。仅产出代码与验证结果，不自行 git 提交/推送。

## 参考依据

- CREST 选项说明（`--noreftopo` 只关闭搜索前初始拓扑检查）：https://crest-lab.github.io/crest-docs/page/documentation/keywords.html
- CREST 非共价体系示例：https://crest-lab.github.io/crest-docs/page/examples/example_3.html
- RDKit 逐步优化轨迹：https://rdkit.org/docs/source/rdkit.ForceField.rdForceField.html
- ORCA NEB-TS：https://www.faccts.de/docs/orca/6.1/tutorials/react/nebts.html
- autodE TS 搜索：https://duartegroup.github.io/autodE/reference/transition_states/locate_tss.html

# ts_prepare 自动化改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 xTB 优先的初猜准备和无需正常调用 ts_resume 的自动 TS 验证链。

**Architecture:** 参考固定版本 autodE 源码，在 Cloudra 内部移植必要优化算法和阶段恢复方式。所有计算复用 compute.db、准入及 guard；数据库保存阶段绑定与幂等提交，通知入口驱动确定性推进。

**Tech Stack:** 现有 Python、Pydantic、SQLite、数组/线性代数、RDKit、现有计算引擎；不增加依赖。

**Spec:** [2026-10-01-ts-prepare-autode-design.md](../specs/2026-10-01-ts-prepare-autode-design.md)

## Global Constraints

- 不引入 autodE 或其他新依赖；上游参考 commit `e7e71b33d8659fe921c16f877f9c1adddc4f9cff`。
- 单分子和多分子络合物的优化都先用 xTB，MMFF 是回退路径。
- 任何计算任务不得因 Cloudra 设定的时间上限而被结束。
- Cloudra 不另设优化、扫描、路径或计算迭代次数上限；原生软件使用自身默认值，只有用户明确指定时才传入覆盖值。
- 正常链由系统推进，agent 调用 ts_resume 为零；恢复通信或进程中断不属于用户干预。
- 保持既定机理、方法、溶剂、电荷、自旋、能垒参考态和科学验收口径。
- 不在 Mac 跑 QM，不停止现有计算，不重启承载正在运行 agent 的服务，不启动正式 benchmark。
- 保持现行 Paratera 32 CPU/56000 MB 总额和新任务优先八核要求；核数不是 TS 模块常量。
- 当前工作区有独立改动。执行前使用隔离工作树，并核对生产基线 `4021a79c` 及其后的合法提交；不得清理或覆盖用户工作区。
- 每项完成后仅提交该项文件；合并、推送和部署按用户授权与现有运行状态处理。

## Review Focus

1. 请求已被接受但响应丢失：相同幂等键必须返回原流程；不同声明不能复用同一键。归属 Task 1/9。
2. 多组分电荷、自旋无法唯一分配：不得给每个片段套用总电荷；应要求声明或按有证据的既有分配处理。归属 Task 6。
3. API 中断且远端计算仍活跃：不能重交、取消或误判失败。归属 Task 2/8。
4. 阻转异构体的 SMILES 相同：仍须用几何与立体身份区分端点，不能退化成同一构象。归属 Task 7/10。
5. 软件默认次数耗尽或 xTB SCF 失败：保留真实非收敛，不提高次数、不静默切 MMFF。归属 Task 3/6。

---

## 文件与接口约定

新增内部模块保持单一职责：

| 文件 | 职责 |
| --- | --- |
| `cloudra/services/ts_pipeline_store.py` | 流程、阶段尝试、作业绑定及事务 |
| `cloudra/tools/core/geometry_optimization.py` | 结构优化请求、能力选择及结果语义 |
| `cloudra/tools/core/constrained_optimization.py` | 持久化受限优化状态与参考 CRF/RFO 的数值步骤 |
| `cloudra/tools/core/constrained_coordinates.py` | 必要坐标变换、约束与单位逻辑 |
| `cloudra/tools/core/constrained_hessian.py` | 必要 Hessian 更新；独立可测试 |
| `cloudra/tools/core/ts_pipeline_driver.py` | 阶段推进、终态消费和 reconcile |
| `cloudra/runtime/chem_task.py` | 现有 guard 内的受控化学辅助任务适配 |

字段约定：流程保存 schema 版本、请求幂等键、项目、所有者、工作区、声明摘要、声明版本、状态与 revision。阶段键包含流程、声明版本、阶段/子阶段键和 attempt；梯度点、扫描点使用确定子键。资源来自请求或注册节点，输出和输入具有不可变版本路径。

本计划中的 `dict` 均表示可校验、可 JSON 持久化的内部 payload；在所属任务中用 Pydantic 定义字段，不接受未校验的 arbitrary dict 或反序列化 pickle。

### Task 1: 流程与作业原子绑定

**Files:** Modify `cloudra/persistence/database.py`, `cloudra/services/compute_store.py`; Create `cloudra/services/ts_pipeline_store.py`, `tests/test_ts_pipeline_store.py`。

**Interfaces:**

- `create_process(db: ComputeDB, *, request_key: str, payload: dict) -> dict`
- `get_process(db: ComputeDB, process_id: str) -> dict | None`
- `bind_stage_job(db: ComputeDB, *, process_id: str, declaration_revision: int, stage_key: str, attempt: int, job_payload: dict) -> int`
- `commit_stage_result(db: ComputeDB, *, process_id: str, expected_revision: int, stage_key: str, attempt: int, evidence: dict) -> bool`
- `process_for_job(db: ComputeDB, job_id: int) -> str | None`
- `list_unfinished_processes(db: ComputeDB, project_id: str) -> list[str]`

- [ ] 写失败测试：并发调用 `bind_stage_job` 只产生一行 compute job；相同请求键同声明返回同流程；相同键不同声明报冲突；同阶段不同声明版本保留历史；旧数据库迁移不修改既有作业。
- [ ] 运行 `pytest tests/test_ts_pipeline_store.py -q`，确认失败来自尚未实现的新契约。
- [ ] 在现有数据库内增加流程/阶段表及唯一约束；为 `compute_store` 提取可共享事务的入库操作，原入口行为保留。READY 与绑定同事务提交，解析产物不占事务。
- [ ] 重跑该文件，要求全部通过；检查两个数据库连接竞争时不存在重复入库。
- [ ] 仅提交本任务文件：`feat: persist TS stage bindings atomically`。

### Task 2: 计算寿命与辅助任务执行

**Files:** Modify `cloudra/tools/core/xtb_path_runner.py`, `crest_runner.py`, `preorganization.py`; Modify `cloudra/tools/Chemtool/ts_guess.py`, `conformer_search.py`, `electronic_analysis.py`, `thermo_analysis.py`, `mechanism_predict.py`; Modify `cloudra/tools/Bashtool/bash.py`, `cloudra/runtime/monitor.py`, `cloudra/infra/slurm.py`; Modify `cloudra/infra/compute_utils.py`, `cloudra/services/compute_admission.py`, `cloudra/runtime/compute_executor.py`, `cloudra/calculator.sh`; Create `cloudra/runtime/chem_task.py`, `tests/test_compute_lifetime.py`。

**Interfaces:**

- `validate_chem_task(manifest: dict) -> dict`：内部受控任务类型为 xTB path/gradient/analysis、CREST、GoodVibes、FlowER；允许明确 argv、输入产物清单及资源，拒绝任意 shell 字符串。
- `run_chem_task(manifest_path: str) -> int`：由现有 guard 执行，结束原因来自进程退出或显式取消，产物保存到声明目录。
- 既有任务准入增加内部 `chem_task`，不新增独立调度器或对 agent 暴露任意命令任务。

- [ ] 写失败测试：假引擎跨越旧期限仍活跃且无 terminate/kill；API 等待取消不结束已入账任务；Slurm 不写 Cloudra 墙钟指令；软件非收敛正常保留；辅助分析任务保存真实退出码及完整日志。
- [ ] 运行 `pytest tests/test_compute_lifetime.py -q`，确认新寿命契约未满足。
- [ ] 移除计算 deadline kill，把长期辅助计算接入既有 guard；兼容输入旧 timeout 时明确报告弃用且不执行杀进程语义。Slurm 外部强制限制如实记录；通信/锁期限保持与 QM 生命周期分离。
- [ ] 通用 bash 不再具有按默认超时杀其进程组的行为；管理操作可以返回等待/通信状态，计算必须使用账本入口。日志解析不以等待窗口耗尽代替真实输出判定；非计算探测不扩展为一般安装验收。
- [ ] 运行该文件及既有 `test_xtb_path_runner.py`, `test_crest_runner.py`, `test_electronic_analysis.py`, `test_thermo_analysis.py`, `test_mechanism_predict.py`，更新旧 timeout 预期为新契约，全部通过后提交 `fix: remove computation deadlines and preserve job ownership`。

### Task 3: 参数来源与 xTB 原生优化适配

**Files:** Create `cloudra/tools/core/geometry_optimization.py`, `tests/test_geometry_optimization.py`; Modify `cloudra/tools/core/xtb_path_runner.py`, `cloudra/infra/compute_utils.py`, `cloudra/runtime/chem_task.py`, `cloudra/tools/core/ts_process.py`。

**Interfaces:**

- `OptimizationRequest`：XYZ、身份/片段、电荷/自旋、探索方法与溶剂、限制、节点/资源、用户明确指定的引擎参数。
- `OptimizationResult`：状态、后端、失败类别、几何、能量/单位、收敛及约束证据、作业/产物引用。
- `select_optimizer(request: OptimizationRequest, capabilities: dict) -> str`：返回 `xtb_native`、`xtb_constrained`、`mmff`、`uff` 或明确能力错误。
- `build_xtb_optimization_manifest(request: OptimizationRequest) -> dict`
- `parse_xtb_optimization(request: OptimizationRequest, artifacts: dict) -> OptimizationResult`

- [ ] 写失败测试：单分子/多分子均 xTB 优先；ALPB/GBSA、charge、uhf、核数明确传递；无用户覆盖时不写 maxiter/nrun；用户参数原样保留；SCF 失败不同于未安装；Eh/Bohr 梯度转换与有限差分一致。
- [ ] 运行 `pytest tests/test_geometry_optimization.py -q`，确认缺失契约。
- [ ] 实现能力选择、受控 manifest、日志解析及来源字段；不从 autodE 包装器继承 GBSA 默认。移除默认路径轮数/干预次数预算，旧记录中的原始值保留为历史，不能冒充新请求的用户参数。
- [ ] 重跑新增测试及 xTB 现有 fixture 测试，确保非法自旋与单位错误明确拒绝，全部通过。
- [ ] 提交 `feat: select xTB optimization with explicit parameter provenance`。

### Task 4: 无新依赖的受限优化数值内核

**Files:** Create `cloudra/tools/core/constrained_optimization.py`, `constrained_coordinates.py`, `constrained_hessian.py`, `tests/test_constrained_optimization.py`, `tests/test_constrained_coordinates.py`, `docs/licenses/autode-derived-code.md`。

**Interfaces:**

- `initialize_constrained_state(request: OptimizationRequest) -> dict`
- `step_constrained_state(state: dict, evaluation: dict) -> dict`：evaluation 为同方法的能量与笛卡尔梯度；输出可持久化下一坐标、收敛或明确数值错误，不提交作业。
- `constraint_residuals(request: OptimizationRequest, xyz: list[list[float]]) -> dict`
- `validate_constraints(request: OptimizationRequest, xyz: list[list[float]]) -> bool`
- evaluation 与状态记录统一坐标/梯度单位，保留引擎原始单位及转换证据。

- [ ] 写失败测试：已知受限极小值、冻结自由度、区间内无中点吸引、越界活动边界、重复约束、奇异坐标、梯度符号、Hessian 更新和恢复后下一步一致；无自设总迭代上限。
- [ ] 运行两个新增测试文件，确认数值内核尚不存在。
- [ ] 从固定上游参考移植闭合的 CRF/RFO、必要坐标与 Hessian 代码；用现有数值依赖适配，保留许可。区间约束按活动边界扩展并单独验证，不能宣称上游已原生提供此语义。
- [ ] 使用解析能量/梯度的测试问题验证容差与约束残差，禁止为了通过修改容差；所有测试通过。
- [ ] 提交 `feat: add constrained optimization adapted from autodE`。

### Task 5: 优化计算的点级持久化

**Files:** Modify `geometry_optimization.py`, `constrained_optimization.py`, `ts_pipeline_store.py`; Create `tests/test_optimization_recovery.py`。

**Interfaces:**

- `advance_optimization(db: ComputeDB, *, process_id: str, stage_key: str, request: OptimizationRequest) -> dict`：返回 waiting/completed/blocked；原生优化一次入账，内部优化逐梯度点入账。
- 消费 Task 1 的绑定和 Task 4 的数值步骤，提交消费 Task 2 的受控辅助任务。

- [ ] 写失败测试：梯度已完成而状态未保存的崩溃恢复；状态已保存而下一梯度未入账；重复点通知；断连；仅用户取消结束计算；外层流程不重复占用内层核数。
- [ ] 运行 `pytest tests/test_optimization_recovery.py -q`，确认恢复尚缺失。
- [ ] 每点绑定确定子键，持久化状态和证据；只在成功解析同方法梯度后迈下一步；数值失败保存轨迹并阻塞。
- [ ] 重跑新增测试和 Task 1/4 测试，要求无重复梯度作业且恢复结果一致。
- [ ] 提交 `feat: checkpoint optimization evaluations in compute ledger`。

### Task 6: 接入结构构建、络合物组装和预组织

**Files:** Modify `cloudra/tools/core/structure_builder.py`, `complex_assembly.py`, `preorganization.py`, `ts_process.py`; Modify `tests/test_structure_builder.py`, `test_complex_assembly.py`, `test_preorganization.py`; Create `tests/test_ts_preparation_backends.py`。

**Interfaces:**

- 保留已有解析/嵌入接口；将嵌入输出与优化结果分开，增加 pending 作业引用，不伪造同步完成。
- `advance_preparation(db: ComputeDB, *, process_id: str, request: dict) -> dict`：消费 Task 5，返回端点/候选、后端、身份、限制、能量来源或明确等待/阻塞。

- [ ] 写失败测试：ETKDG 后首先 xTB；多片段总电荷不能直接复制给每个片段；MMFF 参数缺失的明确 UFF 来源；原生限制不支持时走内部 xTB 梯度；SCF 失败不自动切 MMFF；不同后端能量不混排。
- [ ] 运行新增测试及三个既有文件，确认旧后端顺序不满足新要求。
- [ ] 替换 MMFF-only 路径，删除 Cloudra 默认 maxIts/松弛步数预算；原生 MMFF 调用使用软件默认或用户参数。保留碰撞、解离、环拓扑、立体身份与实际约束检查。
- [ ] 重跑上述测试，使用假计算 fixture 完成异步构建断言，不运行 Mac QM。
- [ ] 提交 `feat: prepare structures and complexes with xTB first`。

### Task 7: 路径、扫描与检查点

**Files:** Modify `cloudra/tools/core/ts_process.py`, `xtb_path_runner.py`, `cloudra/tools/Chemtool/ts_guess.py`; Create `cloudra/tools/core/relaxed_scan.py`, `tests/test_relaxed_scan_recovery.py`; Modify `tests/test_ts_guess.py`, `test_xtb_path_runner.py`。

**Interfaces:**

- `advance_relaxed_scan(db: ComputeDB, *, process_id: str, stage_key: str, plan: dict) -> dict`：点键来自声明坐标索引，邻近已完成结构作为种子，等待/完成/阻塞明确。
- 路径调用 Task 2 的 manifest 与 Task 1 的绑定；产物解析沿既有 xTB/IDPP 身份规则。

- [ ] 写失败测试：三维扫描中点级恢复及重复事件；原子映射覆盖所有氢；相同 SMILES 的几何端点可区分；xTB 缺失允许既有适用 IDPP，而失败不能伪装缺失；峰不等于 gold。
- [ ] 运行新增及两个既有文件，确认持久化扫描尚缺失。
- [ ] 参考 RelaxedPES 的点与邻近种子组织方式，不复制独立进程池；保留声明搜索范围及编号，未声明的科学范围不擅自补定。
- [ ] 重跑测试，断言扫描和普通任务受同一资源额度约束，恢复不重算完成点。
- [ ] 提交 `feat: checkpoint path and relaxed scan preparation`。

### Task 8: 正式验证链的自动推进器

**Files:** Create `cloudra/tools/core/ts_pipeline_driver.py`, `tests/test_ts_pipeline_driver.py`; Modify `cloudra/tools/core/ts_process.py`, `cloudra/runtime_v2/compute_notify.py`, `cloudra/runtime_v2/core.py`; Modify `tests/test_runtime_v2_compute_notify.py`, `tests/test_compute_notify_reconcile.py`。

**Interfaces:**

- `advance_process(db: ComputeDB, process_id: str) -> dict`
- `handle_process_job_terminal(db: ComputeDB, job_id: int) -> dict | None`：非流程作业返回 None。
- `reconcile_processes(db: ComputeDB, project_id: str) -> list[dict]`
- broker 将绑定流程的终态交给推进器；只有 final/blocked 生成 agent 通知，普通作业维持现有通知语义。

- [ ] 写失败测试：一次 prepare 后无需 resume 即生成 TS/Freq/IRC/端点链；错误虚频阻止 IRC；broker 重复/并发消费；项目重新加载；输入已写/READY 已入账/解析已完成三类崩溃；API 断开不重交远端作业。
- [ ] 运行新增及两个 broker 文件，确认自动链尚不能完成。
- [ ] 用 Task 1 的数据库事实与 revision 推进现有阶段；解析在事务外，结果短事务 CAS 保存；完成通知不可先 ack 后丢失推进事实。运行输入不可变，频率/身份/IRC 验收复用现有规则。
- [ ] 重跑测试，断言每阶段尝试只有一次提交，所有正常中间阶段的 LLM wake 计数为零。
- [ ] 提交 `feat: advance TS validation from durable compute completion`。

### Task 9: 工具契约和旧流程兼容

**Files:** Modify `cloudra/tools/Chemtool/ts_search_process.py`, `cloudra/tools/core/ts_process.py`, `cloudra/prompts/small_mol.md`, `cloudra/prompts/coordinator.md`, `cloudra/skills/dft-calculation/SKILL.md`, `docs/TS_PROCESS_SOP.md`; Modify `tests/test_ts_process.py`; Create `tests/test_ts_process_migration.py`。

**Interfaces:**

- `ts_prepare` 接收可选稳定请求幂等键，创建 Task 1 流程并触发 Task 8，返回运行 ID/状态/关联作业。
- `ts_resume` 的非空 adjustment 只对 blocked 流程建立声明新版本；waiting 返回原作业；空 adjustment 仅查询。
- `import_legacy_process(db: ComputeDB, *, workspace_dir: str, run_id: str) -> dict`：识别旧格式与已绑定作业，禁止自动接管仍由旧 agent 执行的活跃流程。

- [ ] 写失败测试：prepare 响应丢失重试；waiting 不重交；空 resume 不推进；blocked 修改只失效受影响下游；旧 budget 值不被当作明确用户设置；旧活跃流程不被两个 owner 同时推进。
- [ ] 运行新旧测试文件，确认旧契约需要调整。
- [ ] 更新接口和提示词，移除“完成后空 resume”“提高预算继续”等指令；旧记录保留原始产物。只有明示移交且核对账本后才迁入新驱动。
- [ ] 重跑测试并核对工具输出中提交成功/科学成功不同，SOP 与实际代码一致。
- [ ] 提交 `feat: reserve ts_resume for explicit blocked interventions`。

### Task 10: 全链验收与远程交付

**Files:** Create `tests/test_ts_pipeline_acceptance.py`; Modify `docs/TS_PROCESS_SOP.md`, `docs/licenses/autode-derived-code.md`；部署记录另存既有归档位置。

**Interfaces:** 使用 Task 1–9 公共内部接口和现有节点执行入口，无新增科学 API。

- [ ] 写全链验收：正常单分子/络合物；相同 SMILES 的立体端点；错误鞍点/端点；不同引擎版本能量拒绝混减；旧期限跨越；全部崩溃点；32 CPU/56000 MB 共享额度与八核输入一致。
- [ ] 运行 `pytest tests/test_ts_pipeline_acceptance.py -q`，确认每个断言覆盖 spec 对应条款，不增加镜像实现的无效测试。
- [ ] 运行计划新增测试、受影响既有测试及 `ruff check`；检查无新增依赖、无 autode import、无计算 kill deadline、无默认迭代预算覆盖，源码来源和许可完整。
- [ ] 在授权远程节点以已有科学任务做真实链验证：保留科学模型、统一方法版本，不重复在跑作业，不在 Mac 计算，不另做一批安装小测试。
- [ ] 在安全的切换时机部署：旧活跃流程保持原 owner 完成，新请求走新驱动；若须重启承载活跃 agent 的服务，等其安全结束或另行请求明确操作，不强行重启。
- [ ] 核对真实证据后更新 SOP 与交付记录、提交相关文件；按授权推送并核实远端提交。不能仅凭成功提交计算宣称化学验收通过。

## 自审覆盖与执行选择

Spec 的优化后端/限制/排序由 Task 3–7 覆盖；自动推进与恢复由 Task 1/5/8 覆盖；resume 契约与兼容由 Task 9 覆盖；无超时/软件参数来源由 Task 2/3/6 覆盖；资源、科学证据与交付由 Task 8/10 覆盖。Review Focus 五项已分别落到相关任务的失败测试。

推荐由当前 agent 在隔离工作树内直接按任务实施，数值算法与数据库幂等性在完成后独立审查。任务间接口紧密，先把接口和阶段证据贯通，比同时分派多份相互依赖实现更容易控制一致性。若用户选择子 agent 逐项执行，则使用对应技能和逐任务审查。

当前仅完成设计和计划。开始产品代码修改前，等待用户核对本计划并选择执行方式。

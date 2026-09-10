# Benchmark 沙箱工具可用性与完整链路测试计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用尽量真实的完整链路测试守住 benchmark 中工具从投影、子 agent 调用、文件生成、计算提交到证据回传的可用性，先复现缺陷再修复。

**Architecture:** 保留生产 RuntimeCore、CommandBus、AgentRunner、TurnPipeline、InvocationService、真实 Node/QuickJS、LegacyToolExecutor、工具实现、SQLite、scheduler、guard 和 calculator。LLM 使用按角色和阶段驱动的确定性脚本；外部引擎使用真正启动的测试可执行程序。另设真实引擎验证层，避免模拟器与实现相互证明。

**Tech Stack:** Python >=3.11、pytest/pytest-asyncio、SQLite、POSIX flock、Node >=22、quickjs-emscripten；只用已有依赖。

**Spec:** 本文“诊断依据、测试真实性与验收契约”；仓库 `AGENTS.md`；用户要求诊断 benchmark 沙箱工具可用性、重点补测试、尽可能模拟到位。本文将这一要求落实为完整生产路径覆盖，不推断 FP 缩写的其他含义。

## 全局约束

- 本次交付是诊断和计划；未实施生产修复，未新增正式测试，未重跑 benchmark。
- 实施时先写能直接测红问题的测试，再修改责任模块；不加兼容 shim、不用文档代替修复、不顺手重构。
- 测试数据全部放 tmp_path，真实数据目录只读；不提交、不推送。
- 不调用真实 LLM、不发送邮件、不启动用户的生产守护进程。
- 不 kill 科研计算进程；只回收明确归属的 JS host 与测试替身进程，必须 wait/reap。测试引擎通过测试控制文件自行结束。
- async 路径不用同步数据库、同步网络或 subprocess.run；真实工具内部同步工作同样纳入审查。
- 不改方法白名单、科学阈值、评分权重、拒答规则或验收标准。任何科学语义扩展先问用户；格式/路径/回执问题无需改变科学规则。
- JS 最终验收必须真实 Node 跑通，不能全部 skip。真实引擎缺失须报告能力未验证，不能算作成功。

## 诊断依据与置信度

### 已证实

1. 最新 C1：`batch_875bb46d76014ea7`，2026-09-10 16:09–16:46（Asia/Singapore），项目 `prj_169928ea26ce4873`，small_mol 子 agent `as_bd6015c8c753437a`。作业 167、168 确实创建并运行，ORCA 随后失败。
2. `qm_input_writer` 相对路径落到进程 cwd：本次用真实 `QmInputWriter.tool_call`、绝对 XYZ 输入、相对 `probe.inp` 输出和设置了 working_directory 的 bridge，在独立临时目录复现。结果 `success=True, in_workspace=False, in_server_cwd=True`。`_get_coordinates` 也直接读取 source_value；输出直接传给 atomic_write_text。adapter 传了 workspace，但没有统一改变这些路径语义。
3. `submit_compute_job` 同步运行失败回执丢失已创建的 job_id/job_dir/state；目前失败测试只检查 false 与报错文本，因此不会测红编号丢失。
4. Web 批次测试通过手动 start_run/finish_run 完成任务，没有真实工具执行；CLI benchmark 的代表性集成测试强制 traditional 协议、使用 RecordingTools 并关闭 scheduler；JS 宿主测试使用假工具。因此这些测试分别通过，仍覆盖不到本次故障链。
5. C1 输入准备出现 5 次 XYZ 首行不是原子数的失败；ORCA 输入使用 Gaussian 子选项被拒绝。这些是正确拒绝错误输入的场景，不能为了“可用”放宽规则。
6. 原生 xTB 计算已受运行时支持，但 `benchmark/selfconsistency.py` 只对 gaussian/orca 类证据做物理自检。不能把“运行引擎支持”直接等同于“benchmark 评分支持”。

### 高置信假设，仍需对照复现

- calculator 已 cd 到输入目录，却把含 `Application Support` 的绝对输入路径交给 ORCA。167/168 的日志显示内部 orca_util 命令未引用该路径并报 unknown utility。子 agent 后续短文件名的原生 xTB 测试成功，但输入与运行位置也有变化，不能作为严格单变量证明。优先做同输入、同目录、仅绝对/相对参数变化的对照；不再把 hostname 当作已确认原因。
- `submit_compute_job` 直接 exists(input_file)，可能读取进程 cwd 的同名文件或报告不存在；应通过真实 executor 验证。

### 待验证风险

- CLI 自行追加 MethodPolicyStage，Web 则写 ProjectSettings.method_policy；两条入口对派生子 agent、Supervisor、默认 DAG 模式的行为是否等价。
- 工具目录里所有路径字段的语义并不必然一致；要按注册表盘点，不在运行代码里新建工具名白名单。
- Web 清空沙箱失败后仅 warning 并继续运行；两条入口重复运行都复用 sandboxes/task_id。旧科研计算独立存活时，清空目录可能与旧作业冲突。
- CLI finally 目前关闭 scheduler，没有显式 core.aclose；需测 JS host 和后台任务是否完整回收，不能仅凭代码片段判定泄漏。
- 外部 xTB 的 extinp 解析失败属于接口兼容问题；需要独立能力验证，不能由工具层假引擎测试宣布解决。

## 已执行基线

以下命令在本次诊断中退出码为 0：

```bash
uv run pytest -q tests/test_benchmark_batch.py tests/test_benchmark_watch.py tests/test_runtime_v2_method_policy.py tests/test_compute.py
```

未跑全套测试、真实 ORCA 对照或新的 FP 场景。以上通过仅说明现有覆盖未发现问题。

## 测试真实性与统一契约

### 三层验证

1. **责任模块回归**：用于精确定位和先红后绿；不能替代完整路径验收。
2. **完整生产路径模拟**：只替换 LLM、外部计算/检索服务。必须真实 spawn 子 agent、真实 JS 调用、真实工具 safe_call、真实 DB 与守护子进程。不能 fake 工具执行器、直接写终态或直接给父邮箱塞完成通知。
3. **本机引擎契约**：同一固定输入通过真实 ORCA/xTB 验证路径及输出接口。使用既有、已认可测试输入；不搜索 TS、不调整方法。区分 missing executable、unsupported interface、engine failure、passed。

### 断言以四个事实源交叉核对

- 磁盘：文件在目标沙箱，源内容/返回路径一致，server cwd 与另一题目录没有新增或覆盖产物。
- DB：作业编号、项目/会话归属、资源申请、失败原因、终态与通知标记一致。
- 事件：requested → started → result_recorded → finished 正常闭合；策略拦截不执行工具；无重复提交和重复执行。
- agent：子收到可追踪回执，父在合适时机收到通知；挂起不当作题目完成；取消后不复活。

### 受控引擎替身

新建 `tests/fixtures/benchmark_engines/engine.py`，由测试生成可执行入口并放入仅测试进程继承的 PATH。替身应：记录 argv/cwd/输入 sha256；按控制文件决定正常退出、失败退出或等待释放；输出来自现有真实日志 fixture 的固定内容。明确标注 fixture 是传输测试材料，不能充当科学计算结果。

ORCA 参数拆分缺陷单独设置严格参数契约测试：验证引擎收到安全的作业内文件引用。再以真实引擎单变量实验佐证，不能只让 fake 模仿猜想的 bug。

新建 `tests/benchmark_support.py`：组装生产 pipeline 的测试 fixture、按 role/session/run 驱动的 ScriptedLLM、条件等待、失败时事件/DB/子进程日志收集。ScriptedLLM 的每步校验上一轮工具回执；禁止盲按全局调用次数发下一条回复，避免并发串脚本。

## Task 1（P0）：沙箱文件路径一致性

**Files:** `tests/test_benchmark_tool_paths.py`（新建）；`tests/test_qm_input_writer.py`；责任实现 `cloudra/tools/Chemtool/qm_input_writer.py`、`submit_compute_job.py`，必要时统一路径原语放 `cloudra/persistence/workspace.py`。

**接口：** 使用生产 LegacyToolExecutor.execute(agent, call)，agent 由 CommandBus 在项目内创建；不通过 os.chdir 改变生产调用环境。测试进程 cwd 在 fixture 设置一次，双项目并发期间保持不变。

- [ ] 新增 `test_writer_relative_output_uses_project_workspace`：绝对合法 XYZ、相对输出，重现已确认缺陷；断言成功后文件在 workspace 且 server cwd 不存在同名文件。
- [ ] 新增 `test_relative_source_and_submit_use_same_workspace`：写入 → writer → submit → query → parser 使用同一沙箱的相对路径；server cwd 预放内容不同的同名输入，检查引擎所读 sha256，防止假成功。
- [ ] 参数化目录：普通目录、`Application Support/中文 C1`；绝对路径、嵌套相对路径。绝对路径保持既有权限语义，不擅自收紧科研节点访问。
- [ ] 新增 `test_concurrent_projects_do_not_cross_write`：C1/C2 同时生成 `calc/input.inp`，不同固定源内容，检查彼此文件、DB 归属和返回路径。
- [ ] 跑上述测试确认具体失败，再统一责任工具的路径解析；不使用全局 chdir，不以“模型必须传绝对路径”代替修复。
- [ ] 使用静态注册表/输入 schema 盘点其余工具文件参数，扩展同一契约到 read/write、format_converter、log_parser、ts_guess 的相关文件模式；每个字段记录 input/output/非文件字符串，禁止把 SMILES 当路径。

核心红测断言示意（使用现有 schema 构造参数）：

```python
result = await executor.execute(agent, call)
assert result.is_success
assert (workspace / "calc/input.inp").is_file()
assert not (server_cwd / "calc/input.inp").exists()
```

## Task 2（P0）：ORCA 启动参数与已提交失败回执

**Files:** `tests/test_compute.py`、`cloudra/calculator.sh`、`cloudra/tools/Chemtool/submit_compute_job.py`。

**接口：** build_calculator_cmd → 原始 calculator.sh → 测试引擎；同步和异步工具返回结构沿用当前 schema。

- [ ] 新增 `test_orca_input_argument_with_space_in_parent_directory`：测试引擎记录 argv/cwd，断言输入可读取且不会把含空格父路径带进内部 helper 参数；保留已有 executable symlink 与 PATH helpers 测试。
- [ ] 在真实 ORCA 层同输入同 cwd 对照绝对参数和文件名参数，记录版本、退出码、关键日志；如假设不成立，回到调用链调查，不能把未经证实修复写进验收结论。
- [ ] 加入含空格输入文件名用例，明确测出实际支持边界；仅改 basename 不一定解决这一情况。若失败，设计统一安全执行名/映射并保留日志、相对辅助文件与原始输入的可追踪性，不能静默改用户文件。
- [ ] 扩展现有 sync_failure：真实 guard 失败后 `job_id > 0`、`state == 'failed'`、job_dir 正确；query 同编号得到相同状态和日志。入库前校验失败应无 DB 行、无子进程，区分提交失败与执行失败。
- [ ] 异步失败断言先 ready、后 failed，始终同一编号；通知可查询、去重。不得以异常路径再插一条作业。
- [ ] 红测后修责任模块；复跑 compute 与执行器测试。

```python
assert result.is_success is False
assert result.job_id > 0
assert result.state == "failed"
assert result.job_dir == str(job_dir)
```

## Task 3（P0）：C1 生产协议完整回归

**Files:** `tests/benchmark_support.py`、`tests/test_benchmark_sandbox_fp.py`、`tests/fixtures/benchmark_engines/engine.py`（新建）；复用 `tests/test_runtime_v2_js_runtime.py` 的宿主探测模式。

**接口：** Web 从 BenchmarkService.start 进入；CLI 从 BenchmarkRunner + RuntimeV2Backend 进入。真实 LegacyToolExecutor，不传 RecordingTools。以测试 scheduler 的 worker_id 和隔离 compute.db 追踪归属。

- [ ] 先建立最小 standard 完整测试：脚本 Coordinator 通过正式子 agent 工具 spawn small_mol；子通过 JS 调用 writer、submit(async)、query、parser；真实 scheduler/guard 输出固定结果，ComputeNotifyBroker 回传，子报告，父完成，runner 评分并落库。
- [ ] 为 Web/CLI 参数化上述场景；默认 javascript 必须跑，traditional 只做一条等价补充用例，不做全面笛卡尔积。
- [ ] 加入 dag_guided 主场景：脚本 Coordinator 提草稿，真实 Supervisor 接受，子执行，显式送审，Supervisor 裁决，父按真实门禁结束。所有图/证据事件走生产工具，不能直接修改 DAG store 以越过门禁。
- [ ] 加入引擎失败后修正并重提：固定第一次失败、第二次成功；确保不同作业编号、旧失败记录保留、没有通知误绑。
- [ ] 加入 malformed XYZ → 正确 XYZ、ORCA 不合法子选项 → 合法输入：第一步可解释失败且无半成品，纠正后能继续；不依赖真实模型自我修复能力。
- [ ] 加入 JS 业务失败 envelope 场景：程序可以完成，但工具 is_success=false 时后续脚本不得当成成功；事件状态与返回值一致。
- [ ] 注入延迟引擎：父进入 wait_background 后 batch 仍未评分；释放测试引擎后完成回传才继续。

**验收：** 四个事实源全部断言；测试日志能从 batch_id → project_id → parent/child → execution_id/tool_call_id → job_id → artifact 定位。模拟器成功不等于真实科学引擎验证成功。

## Task 4（P1）：角色、策略与可用能力契约

**Files:** `tests/test_benchmark_sandbox_fp.py`、`tests/test_runtime_v2_method_policy.py`、`tests/test_benchmark.py`；责任实现 `cloudra/benchmark/backend.py` / `batch.py`，仅在红测证明必要时修改。

- [ ] 捕获 ScriptedLLM 实际收到的 tools，核对 Coordinator/small_mol/Supervisor 的生产投影；JS 客体实际调用一次允许工具，调用一次不可见/无权限工具，验证 fail-closed。
- [ ] 子代继承 unattended、clean_context、yolo、生效 orchestration_mode；ask_user 不暴露且强行调用被阻断，不进入 waiting_input；不能只检查父 settings。
- [ ] 白名单三入口分别测试合法 xTB、明确非法方法、无法解析的方法、带空格的磁盘输入引用；Web/CLI 和子 agent 的结论一致，block 时不创建计算行。
- [ ] 原生 `xTB2`、ProgExt、`xTB GFN2` 分别记录当前识别行为；新增别名只在已有语义有充分依据时进行。模糊科学等价关系先确认，不把所有包含 xtb 的文本都放行。
- [ ] 知识服务不可用时真实 provider 降级不阻断提交；通过 provider 边界替身模拟超时/空结果，不关闭整段 knowledge stage。

## Task 5（P1）：运行隔离、重跑和关闭

**Files:** `tests/test_benchmark_batch.py`、`tests/test_benchmark_sandbox_fp.py`、`tests/test_benchmark_watch.py`；责任实现 `batch.py`、`runner.py`、`backend.py`。

- [ ] 沙箱 reset 抛 OSError：断言不在旧目录继续 spawn/评分，返回明确基础设施失败；当前 Web warning 后继续的行为应测红。
- [ ] 同 task_id 第二轮开始时，第一轮仍有独立计算：引擎等待控制文件；验证不会删除正在用的输入/输出或让旧通知/证据污染新一轮。选择按运行隔离目录或拒绝占用目录的生命周期契约，禁止 kill 旧计算解决问题。
- [ ] 两题并发成功/失败混合：一题失败不终止另一题，资源账与证据路径独立。
- [ ] batch stop 级联取消推理子树，停止新的请求；活计算保持登记与运行。测试通过控制文件释放引擎后完成自身清理。
- [ ] CLI/Web 关闭均 await 登记后台任务并回收真实 JS host；不以事件里写了 cancelled 代替真实退出检查。使用拥有的进程句柄等待，不扫描 PID 文本。

## Task 6（P1）：从可执行到可评分的证据闭环

**Files:** `tests/test_benchmark.py`、`tests/test_benchmark_sandbox_fp.py`；诊断涉及 `integrity.py`、`selfconsistency.py`、`accuracy.py`。

- [ ] 用现有 ORCA/Gaussian 真实日志 fixture 走引擎输出 → log_parser → 不可变证据 → sandbox 扫描 → score_sandbox；只断言当前评分定义，不引入新标准。
- [ ] 验证 `.cloudra/calc-<id>.out.log` 等真实输出路径能被证据扫描发现；错误/未完成日志不能因存在文件就满足物理验证。
- [ ] XYZ 的 smiles 注释放合法第二行；机理图/输入文件不能伪装成成功计算证据；相对证据引用不跨题。
- [ ] 原生 xTB 单独记录运行能力与评分支持缺口；先用特征测试固定现状。是否扩展 xTB 物理自检与评分属于科学验收范围，需用户确认后另立实现任务。
- [ ] 真实外部 ProgExt 与原生 xTB 是两项独立能力测试；不能用原生成功替代外部接口验收。

## 执行与退出标准

推荐顺序：Task 1 → Task 2 → Task 3 → Task 4/5/6。先修可追踪、可定位的问题，再扩大完整场景。每个缺陷留先红后绿证据；纯覆盖新增测试若已通过，记录为覆盖增加，不伪称发现缺陷。

```bash
uv run pytest -q tests/test_benchmark_tool_paths.py tests/test_qm_input_writer.py
uv run pytest -q tests/test_compute.py tests/test_compute_executor.py
uv run pytest -q tests/test_benchmark_sandbox_fp.py
uv run pytest -q tests/test_benchmark.py tests/test_benchmark_batch.py tests/test_benchmark_watch.py tests/test_runtime_v2_method_policy.py
npm --prefix cloudra/runtime_v2/js_host test
uv run pytest -q tests/test_no_sync_on_loop.py
uv run pytest -q tests/
uv run ruff check cloudra tests
```

- [ ] 新增完整测试至少覆盖两入口、真实 JS、small_mol 子代、guided Supervisor、带空格中文目录、相对路径、并发、失败恢复、取消及回传。
- [ ] 宿主依赖缺失时按 AGENTS.md 手动安装；最终报告列出真实宿主执行数量与 skip 原因，不接受 FP 套件全 skip。
- [ ] 测试替身无需真实引擎也可稳定执行；本机引擎报告单独说明哪些接口已实测。
- [ ] 最终测试失败保留隔离目录、事件摘要与引擎 argv/cwd；输出不包含密钥或真实用户数据。
- [ ] 文档更新仅跟随实际改变的路径/关闭/命令契约；不改科学规则，不提交或推送。

## 本计划自检

覆盖用户要求的诊断、测试优先与尽量真实模拟；将确定缺陷、强假设和待验证风险分开；没有把这次 C1 的全部输入错误都归咎于 sandbox；没有承诺未经真实引擎实验的修复有效。完整链路采用可重复脚本来验证 harness，不声称测量模型的真实科研能力。

---

## 附：执行状态（2026-09-10 实施）

| 任务 | 状态 | 关键产出 |
| --- | --- | --- |
| Task 1 沙箱路径一致性 | ✅ 红→绿 | `resolve_tool_path` 原语；qm_input_writer / submit_compute_job 修复；契约扩展到 format_converter / log_parser / ts_guess；`tests/test_benchmark_tool_paths.py`（含工具路径字段盘点）；顺带修复并发 `ComputeDB.ainit()` 的 WAL 锁竞态 |
| Task 2 ORCA 参数与失败回执 | ✅ 红→绿（含真机对照） | 真机 ORCA 6.1.1 复现"含空格路径被拆词截断"；calculator.sh 安全执行名（basename / 硬链接）；同步失败回执带回 `job_id/state/job_dir` |
| Task 3 C1 完整链路回归 | ✅ | `tests/benchmark_support.py`（run/turn 键控 ScriptedLLM + 回执校验）；`tests/fixtures/benchmark_engines/`（受控引擎替身）；`tests/test_benchmark_sandbox_fp.py` 13 用例：CLI/Web 两入口 JS 全链路、traditional 等价、失败→重提、非法输入→纠正、JS 业务失败 envelope、dag_guided 督导三轮真实裁决 |
| Task 4 角色/策略/能力契约 | ✅ | 客体 fail-closed（direct-only 与未暴露工具）、无人值守继承 + ask_user 阻断、白名单三入口 + 原生 xTB 词表、知识服务降级 |
| Task 5 运行隔离/重跑/关闭 | ✅（含生产修复） | 沙箱清理失败落明确基建失败（不再 warning 后继续）；占用沙箱拒绝复用（不删旧输入、不 kill 旧计算）；并发混合成功/失败；stop 级联但活计算照跑；真实 JS host 句柄回收 |
| Task 6 证据闭环 | ✅ + 口径整改 | 真实日志→扫描→评分闭环；`.cloudra/calc-<id>.out.log` 可发现；输入/图 JSON 不得伪装成证据；XYZ 第二行 smiles 绑定；原生 xTB 运行能力与评分缺口分别记录；**评分口径整改见下节** |

验证：全套 **1880 用例 0 失败 0 错误**（4 个跳过均为 `test_ts_guess.py` 既有的"真实 ORCA 日志缺失"条件探测）；JS 宿主 `npm test` 18/18（真实 Node）；`ruff check cloudra tests` 全绿。

本机引擎实测（Task 6 第 3 层契约）：
- 原生 **xtb**：经 calculator.sh 单点跑通并写下 `normal termination of xtb`（`test_real_xtb_engine_run`）；
- 真实 **ORCA 6.1.1**：含空格父目录的绝对参数对照复现了引擎拆词截断（Task 2）；
- 真实 **ORCA + ProgExt(MACE)** 外部接口：`test_real_orca_progext_external_interface` 通过——日志含 `Program Version 6.1.1`、`Using external energy/gradient program given in input: …/bin/mace`、`****ORCA TERMINATED NORMALLY****`，并落盘 `water_ext.property.txt`/`.gbw`。

> 测试侧教训（已修）：真机用例**不得用管道**收外部引擎输出——ORCA 拉起的外部 MACE 进程会继承管道且不退出，父进程读不到 EOF 会永久阻塞（首次实测卡住 30 分钟，而 ORCA 早已算完）。判定引擎结束只能靠**直接子进程退出码 + 文本终止标记**（与 guard 口径一致）；生产侧 guard 本就把引擎输出落盘到 `.cloudra/calc-<id>.out.log`，无此问题。

## 附：Task 6 执行中发现的评分口径缺陷与整改（用户裁决 2026-09-10）

### 缺陷（用户指出）

`benchmark/backend.py::extract_reported_barrier` 用正则从 **LLM 最终消息散文**里抓
"`<number> kcal/mol`"，`accuracy.py` 再把该数字与 gold 比较；`refusal.py::classify_outcome`
同样用正则解析散文判定拒答。二者都违反仓库约定（校验路径禁止正则、禁止解析
agent/LLM 输出），等价于"拿模型自述给自己打分"。

### 用户裁决的口径

1. 能垒 = **决速步（RDS）基元反应的能垒**（题源协议句原文一致："for the
   rate-determining step, relative to the reactant complex"）。
2. 交付物双来源，**两者都必须有且一致才给分**：
   - 交付 `mechanism_graph.json`：**每条边逐条声明** `barrier_kcal_mol`（"我们会一个个把每一步的能垒算好的"）；
   - harness 从该步绑定的 ORCA/Gaussian 日志推算 `E(TS) − E(起点最小值)`（Hartree→kcal/mol）。
3. 一致性容差**复用 accuracy 现有 sigma**（不新增阈值）；缺失/冲突一律 fail-loud 记 0。
4. 拒答走**结构化声明**（可选字段）：`mechanism_graph.json` 内
   `{"refusal": {"refused": true, "reason": "..."}}`。

### 实施

- 新增 `benchmark/barrier_evidence.py`：逐步推算能垒（TS 由内容判定＝恰一个虚频；
  多候选时按"文件名携带该步 TS 身份"确定性优选，否则按路径序并记 note），RDS =
  推算能垒最高者（并列按 edge id 确定性）；`load_refusal_declaration` 读结构化声明。
- `accuracy.py` 重写：**逐步门禁**（任一步"未声明/无日志/声明与日志冲突"即 0 分），
  全部一致后按 RDS 对 gold 做既有高斯容差评分。
- `refusal.py` 重写为纯结构化分类：可解析交付图 → answered；结构化拒答声明 →
  refused；其余（含只写散文、崩溃、超时）→ failed。**正则与散文解析全部删除**。
- `runner.py`/`backend.py`/`batch.py`：删除 `BackendResult` 与后端回传的
  `barrier`/`final_message` 评分依赖（`score_sandbox(task, sandbox)` 只读交付物）；
  最终消息仅作为审计日志保留。
- `schema.py`：`MechanismEdge.barrier_kcal_mol`（交付侧逐条声明）+
  `RefusalDeclaration`（可选拒答声明）。
- 四档生成器协议句改写（逐条声明能垒 + TS 文件须带该步反应物的 `smiles:` 注释 +
  结构化拒答通道；query 保持纯 ASCII），并**重跑生成器**（60 个任务 JSON 同步）。
- 护栏：`tests/test_benchmark.py::test_scoring_modules_do_not_import_regex` 静态断言
  评分/校验模块不得出现 `re`。

### 新增/改写的测试

- `test_barrier_is_derived_from_logs_and_must_be_declared`（未声明 → 0；声明且一致 →
  按 gold 满分）
- `test_declared_barrier_must_match_logs`（声明与日志冲突 → 0）
- `test_scoring_ignores_prose_barrier`（**核心回归**：只有散文喊数 → 0；散文乱数不污染
  一致的交付物 → 满分）
- `test_barrier_requires_a_saddle_log`（无一阶鞍点日志 → 0）
- `test_accuracy_per_step_gate_and_rds_selection`（逐步门禁 + RDS 取最高）
- `test_evidence_loop_engine_output_to_score` / `test_captured_stdout_log_is_scanned_*` /
  `test_xyz_smiles_annotation_second_line_binds` 等（交付物扫描与绑定契约）
- `tests/fixtures/benchmark_synthetic/`（合成 ORCA 日志副本：一处频率取负 + 一处能量
  平移；**明确标注为传输测试材料，不是科学计算结果**）

### 未决（需用户另行确认，不擅自实施）

- 原生 xTB 的**评分侧**缺口（`selfconsistency` 只对 gaussian/orca 做物理自检、
  引擎嗅探把 xtb 日志归为通用 `log`）已按现状特征化固定
  （`test_native_xtb_run_capability_vs_scoring_gap`）；是否扩展 xTB 物理自检与
  能垒推算属科学验收范围，待用户批准。
- normal/hard 两档 `rubric.accuracy.enabled=false` 且 gold 无能垒数字：新口径下这些题
  的 accuracy 不评分（与现状一致，未改动）。

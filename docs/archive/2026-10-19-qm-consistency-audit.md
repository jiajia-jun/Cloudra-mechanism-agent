# Gaussian / ORCA 功能一致性审计（2026-10-19）

本轮确认了输入写出、IRC 核验、证据归属和坏日志隔离中的工程问题。除配对 IRC 的电荷传播小修外，下表问题尚未在本轮修复。没有改变科学阈值、方法选择、partial 路径验收或评分权重。

源码基线为 `42eda2401df5295b46a07031f805f021286f1e82`，重点复核该提交及 `7321f0e9`、`59bde756` 的调用链。附录摘自归档时工作区，包含已修复的电荷传参行；它是带行号的源码快照，后续修改不要求同步维护。完整实际 schema、入口、转发、转换、关键分支和结果返回见 [源码调用链附录](../evidence/qm_consistency_20261019/source-chain.md)。

环境已安装项目 `dev`、`chem` 依赖，但没有 Gaussian / ORCA 可执行程序。本轮运行的是公开工具调用、原生日志解析、证据归档和本地 dry-run；未运行真实 QM、LLM 或整题 easy。复现脚本退出 0 表示探针正常完成，不能解释为生产功能通过。原生日志副本、合成解析材料及 dry-run 替身在下文分别标明。

## 已复现结果

| 编号 | 问题 | 当前证据边界 | 状态 |
| --- | --- | --- | --- |
| A1 | ORCA Bohr 单位声明保留，但坐标仍按 Å 数字写出 | 公开 writer → 两种 native reader 均证实几何缩小；未实机计算 | 待修复 |
| A2 | Gaussian `fchk_name` 生成已知非法 `%fchk=` | 本轮证实成功写出；G16 Link-0 abort 来自仓库历史记录 | 待修复 |
| A3 | 通用 strict verify 对异常／缺失终止的 IRC 仍给 `pass` | Gaussian、ORCA 探针成立；未证明绕过 DAG 最终门禁 | 待统一入口口径 |
| A4 | Gaussian TS `ReadFC` 接受后没有传入频率 checkpoint | 输入、准入检查、远端 staging 和 calculator dry-run 均证实依赖缺口；未运行 Gaussian | 待修复 |
| A5 | 同目录邻居的 IRC manifest 被当作当前日志的归档 | 第二份有效 IRC 的 snapshot / binding 读取抛 hash mismatch | 待修复 |
| A6 | ORCA 缺自身侧车时，唯一 glob 可拾取另一作业端点 | 错误归属并被 DAG snapshot 冻结；尚未证明科学最终误验收 | 待修复归属判断 |
| A7 | 未绑定的坏 Gaussian 候选可使整题评分抛异常 | 有效基线通过，加入坏候选后 `score_sandbox` 抛 `ValueError` | 待修复异常隔离 |
| F1 | 配对分离产物 IRC 忽略显式电荷，未绑定时使用 0 | 同材料 single / paired 与 −1 / 0 电荷的 red-green 回归 | 本轮已修复 |
| E1 | 真实端点 Opt 从 corrector 前 Input 启动，未接上 canonical CURRENT 外帧 | 原件哈希校验、数值对照、共享 verifier 和实际 DAG 提交均复现 | 已定位几何断链，尚未修复 |

十一份可移植探针、原始重跑输出及材料说明位于 [证据目录](../evidence/qm_consistency_20261019/README.md)。以下命令均从仓库根目录执行；脚本也能由绝对路径从其他工作目录启动，生成文件与配置均隔离在 `/tmp`。E1 探针另需传入校验后的外部原件目录。

### A1：ORCA Bohr 输入没有保持原几何

`QmInputWriter._build_orca_input` 保留 `keywords` 和 `orca_blocks`，随后直接调用 `_coordinate_lines(mol)`；该函数通过 `to_xyz` 写出内部 Å 坐标。Gaussian 对照路径 `_build_gjf` 已在声明 Bohr 时执行除以 `Bohr` 的转换。位置：`cloudra/tools/Chemtool/qm_input_writer.py:258`、`:511`、`:565`；读回位置：`cloudra/tools/core/molecule.py:130`、`cloudra/tools/core/native_input_sections.py:128`。

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/cloudra_qm_unit_roundtrip_audit.py
```

同一份 H–H 距离为 1 Å 的 XYZ，公开 `tool_call` 的关键结果：

| 设置 | `is_success` | `validation_errors` | native 读回距离 / Å |
| --- | --- | --- | --- |
| ORCA 默认 | `True` | `[]` | `1.0` |
| ORCA `keywords='Bohrs'` | `True` | `[]` | `0.5291772105638411` |
| ORCA 单行／多行 `%coords Units Bohrs` | `True` | `[]` | `0.5291772105638411` |
| ORCA keyword 与 block 同时声明 Bohr | `True` | `[]` | `0.5291772105638411` |
| Gaussian `units=bohr`、`units=( bohr )`、`units=au` | `True` | `[]` | `1.0000000022030027` |

`native_input_geometry` 和 `read_molecule` 两种读回结果相同。ORCA 这些 Bohr 调用没有警告；冲突／未知单位也成功写出且没有警告，随后 native reader 明确拒读。Gaussian 冲突单位已有 `unknown_coordinate_units` 警告。

影响限于显式单位声明；默认 Å 路径正常。`validate_rendered_input`（`:476`）和 `compare_calculation_input`（`calculation_intent.py:732`）没有比较源结构与写出后的几何。建议在共享写出边界复用现有单位解析并转换坐标，再补写出／读回几何一致性回归，不新增科学判据。原始输出：[units.txt](../evidence/qm_consistency_20261019/outputs/units.txt)。

### A2：`fchk_name` 仍被拼成非法 Link0 卡

公开 schema `qm_input_writer.py:152` 接受 `fchk_name`；`_build_link0:328` 将它映射到 `fchk` 并统一拼成 `%{key}={value}`。公开调用实际成功写出 `%fchk=/tmp/.../water.fchk`，返回 `warnings=[]`、`unapplied_options=[]`。

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/probe_writer_fchk.py
```

探针还从生成文本删掉全部 Link0，再调用 `validate_rendered_input`，结果仍为 `[]`。这证明完整性检查未覆盖这些路径与资源卡，不代表本轮已观察到 writer 自发删除所有 Link0。

仓库历史实机记录 [2026-08-17 复盘](../superpowers/plans/2026-08-17-delivery-only-orchestration.md#L85) 明确记录同一非法 `%fchk=` 导致 G16 Link-0 abort。本轮只证实当前 writer 仍生成该卡，没有重跑 Gaussian。影响仅为显式传 `fchk_name` 的 Gaussian 调用。后续应去掉非法卡映射，并通过合法产物转换流程处理 formatted checkpoint。原始输出：[fchk.txt](../evidence/qm_consistency_20261019/outputs/fchk.txt)。

### A3：通用 strict verify 与外层门禁的终止口径不同

`TsGuess._verify` 只用频率日志的正常终止和优化状态建立前提（`ts_guess.py:2333`）；`_strict_path_verdict:2587` 提取 IRC 端点并调用 `verify_short_irc_direction`，共享核验链没有对该 IRC 调用 `normal_log`。实际端点 Opt/Freq 完整时，仍返回 `pass`。

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/irc_verify_audit.py
.venv/bin/python docs/evidence/qm_consistency_20261019/orca_irc_verify_audit.py
```

仅改变 `/tmp` IRC 副本的终止标记，保留原有帧及 TS、端点材料：

| IRC 终止标记 | Gaussian `ts_guess strict` | Gaussian Benchmark | ORCA strict / 单日志 / paired |
| --- | --- | --- | --- |
| 正常 | `pass` | `True` | `pass / True / True` |
| Error termination | `pass` | `False` | `pass / True / True` |
| 无终止标记 | `pass` | `False` | `pass / True / True` |

Gaussian IRC 为已捕获原生日志；频率和端点 Opt/Freq 为明确标注的合成解析材料。ORCA 材料为 native-shaped parser fixture。DAG `file_science._logs:104` 和 Benchmark `_strict_irc_proof:156` 的外层过滤仍拒绝非正常日志，因此这里没有证明端到端绕过交付门禁。建议让通用工具与门禁共享终止事实及核验口径；这不等于否定未达极小值、但实际端点优化链成立的正常短 IRC。原始输出：[Gaussian](../evidence/qm_consistency_20261019/outputs/gaussian_termination.txt)、[ORCA](../evidence/qm_consistency_20261019/outputs/orca_termination.txt)。

### A4：Gaussian `ReadFC` 没有得到已有频率 checkpoint

`QmCalculation`（`qm_calculation.py:26`）没有 checkpoint 源字段。TS `_write_irc_input`（`ts_process.py:2251`）接受 `irc=(readfc,reverse)`，共享 writer 给新目录默认生成 `irc.chk`，但没有 `%oldchk` 或复制已有 `frequency/freq.chk`。`_check_calculation_submission:1853` 仍给出 `matched=True`、无警告。

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/ts_native_dependency_audit.py
```

探针用明确标注的假 checkpoint / Hessian 字节检查文件传递，不把它们当作 QM 证据。Gaussian 结果是 `frequency_dependency_exists=True`、`irc_checkpoint_exists=False`；`_stage_native_paths` 只记录新 `irc.chk` 为 `role='inout'`，其 `source_sha256=null`。calculator dry-run 的替身只打印 cwd / 输入并故意退出 42，确认没有其他环节补入频率文件。

对照 ORCA 显式 `Hess_Filename`：真实路径被识别为 `role='dependency'`，内容哈希存在，输入被改写为 staging 路径。后续应为用户已明确选择的 `ReadFC` 绑定并传递兼容的实际 checkpoint，而非自动改选 Hessian 算法。原始输出：[readfc.txt](../evidence/qm_consistency_20261019/outputs/readfc.txt)。

### A5：邻居 manifest 可使有效 IRC 被误报损坏

`orca_frames._archived_irc_endpoints:950` 只按当前日志父目录寻找固定名称 `irc_endpoints.json`，随后立即将其 `log_sha256` 与当前日志比较。它没有先区分该文件是否属于同目录另一份 IRC。

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/cloudra_irc_neighbor_manifest_probe.py
```

两份 Gaussian 原生日志副本在 native 解析中均有效。把第一份真实 snapshot 生成的 manifest 放在共享目录后，第一份仍能归档，第二份 `snapshot_evidence_file` 与 `_LogProbe.irc_atom_binding` 均抛 `ValueError: Archived IRC log hash mismatch`；第二份 native 几何解析仍成立。

这是归档命名／归属问题。后续应按日志身份定位归档；对当前日志已绑定归档的篡改仍应拒绝，不能把所有 hash mismatch 静默忽略。原始输出：[neighbor_manifest.txt](../evidence/qm_consistency_20261019/outputs/neighbor_manifest.txt)。

### A6：ORCA 唯一 glob 可误归属其他作业侧车

`orca_frames._irc_endpoint_sidecar:899` 在精确名称失败后，对目录／父目录执行 glob；`:926` 对唯一命中直接返回，不要求证明它属于当前作业。`extract_irc_endpoints:980` 和 `snapshot_evidence_file:83` 随后使用并冻结该引用。

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/cloudra_orca_foreign_sidecars_probe.py
```

HCN IRC 缺自身端点时，snapshot 原本拒绝。向同目录加入另一真实 NU3 作业的侧车后，结果为：

```text
forward final_endpoint_file_glob other_job_IRC_F.xyz
backward final_endpoint_file_glob other_job_IRC_B.xyz
snapshot_accepted orca ['other_job_IRC_F.xyz', 'other_job_IRC_B.xyz']
```

已证明错误材料归属和归档接受；没有证明后续原子数、物种及端点优化链检查会最终误验收。建议只采用有当前作业来源依据的侧车，并使缺失材料明确失败。原始输出：[foreign_sidecars.txt](../evidence/qm_consistency_20261019/outputs/foreign_sidecars.txt)。

### A7：未绑定坏日志越过候选异常边界，导致整题评分失败

`_LogProbe._parse:102` 能将同一坏候选隔离为 `(None, None)`。但 `_strict_irc_proof`（`selfconsistency.py:200`）和 `bind_graph_to_evidence`（`integrity.py:418`）又直接调用 `normal_log`；它进入 `frequency_geometry_matches`，最终在 `gaussian_frames._parse_coord_block_after:387` 将 `**************` 转成浮点数，异常向上传播。

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/cloudra_unrelated_parse_failure_probe.py
```

有效 IRC 基线 `True`，独立 water `score_sandbox` 基线为 `1.0`。加入未被图绑定的合成破损 Gaussian 日志后，`audit_self_consistency`、`audit_integrity`、`score_sandbox` 均抛 `ValueError: could not convert string to float: '**************'`。

探针直接证实评分入口抛异常；生产 `_run_one_guarded`（`runner.py:522`）会捕获单题异常，写入 `task crashed` 的零分记录后继续批次，不能说会终止整个批次。本轮没有执行真实 LLM 批次。建议隔离未绑定坏候选，保留具体解析原因；对绑定的坏证据继续明确拒绝。原始输出：[malformed_candidate.txt](../evidence/qm_consistency_20261019/outputs/malformed_candidate.txt)。

### F1：已修复配对 IRC 的电荷传播

基线 `verify_short_irc_pair` 的分离产物分支使用 `(atom_binding or {}).get('charge', 0)`，没有绑定时忽略调用方显式 `charge=-1`。本轮仅改为与单日志入口一致的实际代码：

```python
verdict = verify_separated_product_direction((forward, reverse), geometry, source,
    product_smiles, target, charge=charge,
    atom_binding=atom_binding if ts_binding == atom_binding else None)
```

位置：`cloudra/tools/core/irc_evidence.py:660`。新增回归使用已捕获 NU3 几何加远处 hydroxide 旁观组分构成的合成 parser fixture，不声称是新实算。四例分别覆盖 single / paired 与显式 −1 / 错误 0：修前仅 paired / −1 失败，修后四例通过，错误电荷仍拒绝；`tests/test_irc_separated_products.py` 全模块 29 项通过。该修复尚不能作为真实 E1 根因已解决的证据。

## E1：已确认端点 Opt 的第一条几何断链

#210 作者已更正：`atom binding absent` 本身不是失败原因。现有 `test_unmanaged_native_gaussian_irc_accepts_complete_endpoint_opt_freq_chain` 及 DAG 正负例已证明，完整的 Gaussian IRC → 实际外帧 Opt → 同几何零虚频 Freq 链不要求凭空补造 binding / archive。缺少端点 Opt 的负例仍拒绝。

原件已从远端临时证据分支 `evidence/e1-irc-20261019`（commit `4f26105257d292deca0de0c3a8b434d2b8842b0d`）取回，全部 `SHA256SUMS` 校验通过，未合并该分支。真实日志显示 HPC 积分 scheme，并有 LQA predictor 和 corrector 收敛过程。独立核对发现：

- `ts1.log` 正常终止、优化收敛且有一个虚频；`irc3.log` 正常终止、双向路径存在、起点与 TS 相同。
- `endpoint_rev5.log` / `endpoint_fwd5.log` 正常终止、优化收敛且零虚频，声明物种身份通过；`_optimized_minima` 两侧各找到一个合法候选。
- 两个 Opt 输入及其原生日志首帧，逐位等于各终点校正前的 Input orientation。反向对应 `irc3.log:63346`（`:63870` 又重复该值），正向对应 `:49738`。
- canonical 外帧来自 corrected CURRENT：反向 `:63650`、正向 `:50045`。相对实际 Opt 首帧的 proper aligned 最大原子残差分别为 `3.6600335068e-5 Å` 和 `1.1025074122e-5 Å`，不是刚体转动或打印舍入。外帧到两个 Opt 起点的四种组合全部 `same_geometry=False`。

直接调用共享 `verify_short_irc_direction` 返回 `False`，唯一原因是实际 IRC 外帧没有通过提交的 Opt 日志连接到两侧零虚频极小值。第一条失败链接已确定为 corrected IRC 外帧 → 实际 Opt 起点，而非缺 binding、缺原生坐标、虚频数错误或物种身份错误。该拒收也不等于反应机理本身错误。

实际 DAG 重放也已完成：以交付 SMILES 重建 proposal，真实提交两个 species 得到 geometry passed；再以 seq 4736 的完整原始入参提交 step，得到与 seq 4761 原返回相同的 `frequency=passed`、`ts_opt=passed`、`short_irc=incomplete`。原始包与计算文件副本在重放前后哈希不变。原 DAG 数据库没有随包提供，因此重放没有恢复原审批／skipped 状态，只验证相同的科学提交检查路径。完整事实和原始调用回执见 [e1_native_replay.json](../evidence/qm_consistency_20261019/outputs/e1_native_replay.json) 与 [stdout](../evidence/qm_consistency_20261019/outputs/e1_native_replay.txt)；其中原调用描述是当时 agent 的声明，不作为本报告的科学结论。

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/e1_gaussian_print_semantics_audit.py /absolute/path/to/extracted/evidence/e1-irc-20261019/calc
.venv/bin/python docs/evidence/qm_consistency_20261019/cloudra_e1_native_replay.py /absolute/path/to/extracted/evidence/e1-irc-20261019
```

原件不随本审计合入主分支。逐项数值对照见 [e1_gaussian_print_semantics.json](../evidence/qm_consistency_20261019/outputs/e1_gaussian_print_semantics.json)。导出的 88 条记录只含 DAG 工具；这份筛选导出没有 `ts_guess`，不能据此断言完整轨迹未调用它。

对已有 HCN Euler-PC 原生日志的独立对照：

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/gaussian_irc_print_semantics_audit.py
```

20 个非零点的相邻 Input / CURRENT 比较全部 `same_geometry=False`。reverse Point 10 经 proper rotation 对齐后，最大原子残差为 `5.2929752755e-4 Å`，最大原子对距离差为 `7.2189866657e-4 Å`；最后 Input 重复之前的值，native 提取的反向外帧对应 corrected CURRENT。CURRENT 前存在真实 corrector 能量变化，因此“同一点两份打印必然只有舍入差异”也不适用于这份对照日志。HCN 与 E1 原件的积分过程不同，分别核对；本轮没有放宽全局 tolerance 或接受 predictor。逐点数值：[gaussian_irc_print_semantics.json](../evidence/qm_consistency_20261019/outputs/gaussian_irc_print_semantics.json)。

## 能力缺口与后续建议

原生 Gaussian 日志已经保留正确 CURRENT；问题是让后续优化稳定使用这份权威外帧。`complete_execution_evidence`（`compute_utils.py:502`）只有 ORCA 分支会复制几何并 `snapshot_irc_endpoints`，Gaussian 只冻结日志。独立 `ts_guess verify` 可以导出 canonical 两侧 XYZ，但常用 `log_parser` 只返回 IRC 摘要（`log_parser.py:404`），`format_converter` 只提供 final / CSV（`format_converter.py:145`），没有给后续 Opt 同样直观的双端产物回执。

建议由共享原生解析和计算产物层交付带来源的两侧外帧，让正常工具链直接接续 Opt/Freq，并让 Gaussian / ORCA 提供一致的产物接口。这样能减少模型在大日志中选择坐标表的负担。这是尚未实施的能力改进方向，不是新增的科学失败判据，也不授权放宽 tolerance、自动换取 predictor 或修改评分。

## 测试材料问题

另有两个既有 ORCA DAG 回归在检查中失败：`test_dag_keeps_opt_and_freq_when_minimum_logs_are_separate[False-False]`、`[False-True]`。根因为合成 helper `write_lineage_bundle.log` 缺少真实 ORCA 的 `FINAL ENERGY EVALUATION AT THE STATIONARY POINT` 标题，导致 shared facts 无法把后续 final 坐标与收敛标记关联。只补 helper 标题后，lineage wrappers 与 endpoint optimization 两模块共 19 项通过；没有修改生产门禁，不把这项测试材料问题算作新的生产缺陷。

## 交付与验证

本报告、十一份探针、保留输出及源码附录供审查；额外诊断没有实施 A1–A7 的生产修复。探针在 `/tmp` 创建副本、配置和 dry-run 替身，读取仓库 fixture 或明确传入的 E1 原件；不会提交计算或调用模型。归档脚本进行了语法及 ruff 检查，并从非仓库工作目录验证可移植入口。原始输出保留临时路径和可选 cclib 的解析告警，告警不代表执行过原生 QM。

集成验收的最新结果为 **75 passed，26 warnings，0 failed**（246.62 秒）：覆盖三个变更的 IRC 测试模块、DAG file science cache，以及七个消费同一 helper 的 benchmark / scenario 节点。26 条 warning 均为第三方 nmrglue / NumPy `dtype='a'` 弃用提示。`compileall cloudra tests`、`ruff check cloudra tests` 和 diff 检查通过。较早十模块的 331 用例检查得到 289 passed、40 skipped、2 failed；那两个失败就是上文所述合成 helper 缺原生标题，修正后重跑了这些消费路径。没有运行 `tests/` 全套，也不声称全套通过。

科学规则、输入方法、证据门禁、partial 策略和评分口径均未因这些发现而放宽。未执行真实 LLM / QM 整题运行；当前只做原件重放，不能据此宣称 easy 已跑通。

# QM 一致性审计：调用链源码快照附录

这是 2026-10-19 审计生成的**源码证据快照**，不是要求后续持续同步的维护文档。主报告中的结论与实验结果应和这里的实际分支逐项核对。

- 基线提交：`42eda2401df5295b46a07031f805f021286f1e82`（指定短号 `42eda240`）。
- 提取对象：生成时共享工作区的真实 Python AST 节点，保留完整 class/function、decorator、docstring 和内部局部函数；代码块无人工删节。
- 当前状态：`irc_evidence.py` 的 paired separated charge 单行已获授权修复，后文是**已修态**。测试文件亦有同期工作区修改，本附录不以测试 helper 的 stationary marker 缺失宣称生产缺陷。
- 共 38 个 Python 路径、342 个去重完整节点、9963 行节点源码；另附 Bash 的完整相关函数/dispatch。各路径的 SHA-256 位于分组标题下。
- 范围：覆盖这 9 项 finding 的局部实调用链，包含转发、参数/单位转换、关键分支和错误传播。未展开的第三方库内部实现、通用数据库/注册器基础设施和与所审路径无关的 sibling operation 不属于本次证据范围；父函数中的相关分支仍完整保留。
- 所有路径和行号均指生成时的源码。索引跳转至下文完整真实代码；同一函数仅贴一次。

## 公开 schema 读法

| schema | 当前字段事实（完整定义见后文） |
|---|---|
| QmCalculation / QmInputSettings | engine / method / basis_set；keywords、orca_blocks、end_setting、frequency_mode；nproc 与 mem。具体必填性、默认值和 validator 均以完整 class 为准。 |
| QmInputWriter input/output | 文件源 source_type / source_value、显式 charge / multiplicity、task_type、output_path；Gaussian chk_name / rwf_name / fchk_name；返回 is_success、input_path、calculation、warnings、unapplied_options。 |
| TsGuess input/output | mode=verify、freq_log、irc_log、strict、reactant/product参考与日志；返回 verification_status、verdict、checks、irc_end_a_path / irc_end_b_path 等。mode约束由模型validator与 schema常量共同给出。 |
| SubmitComputeJob input/output | input_file、job_type、is_async、execution_backend、node_id 与资源；返回提交 job_id / state。提交成功不是原生计算成功。 |
| TsInput / TsVerification | 局部 calculations 与阶段引用；frequency、irc、irc_log、reactant_endpoint / product_endpoint；没有公开 oldchk 字段。字段条件以完整引用解析与 validator 为准。 |

## 按 finding 的有序调用链


### A1 · ORCA Bohrs 坐标写出与读回

1. 公开 schema：[QmInputSettings](#s297) / [QmCalculation](#s298) → [QmInputWriter_input_schema](#s107)；入口 [QmInputWriter.tool_call](#s123) 解析路径、请求建议并返回 [QmInputWriter_output_schema](#s108)。
2. 本轮 XYZ 分支：[QmInputWriter._get_molecule](#s110) → [read_molecule](#s252) → [_read_xyz_structure](#s250) → [from_ase](#s254)；结构的坐标单位为 Å。
3. [QmInputWriter.render_input](#s121) → [QmInputWriter._build_orca_input](#s119) → [QmInputWriter._orca_task_keywords](#s116) / [QmInputWriter._orca_resource_lines](#s115) / [QmInputWriter._coordinate_lines](#s109) → [to_xyz](#s256)。`keywords` 与 `orca_blocks` 原样进入文本，坐标仍直接写 Å。
4. 写后检查：[validate_writer_request](#s152)、[intent_from_writer](#s151)、[inspect_input](#s161) → [_inspect_orca](#s158)；[QmInputWriter.validate_rendered_input](#s118) → [QmInputWriter._written_calculation](#s117) → [compare_calculation_input](#s166)；该比较没有源几何参数。
5. 读回边界：[native_input_geometry](#s167) → [orca_xyz_sections](#s261) / [orca_coordinate_units](#s262)；或 [read_molecule](#s252) → [_read_orca_structure](#s249) → [_cartesian_atoms](#s247)，Bohr 数字在这里乘 Bohr→Å 系数。
6. Gaussian 对照：[QmInputWriter._build_gjf](#s120) → [gaussian_sections](#s260) / [gaussian_coordinate_units](#s259)，写出时显式除以 `Bohr`；相同 native reader 再换回 Å。最终落盘由 [atomic_write_text](#s075) → [atomic_write_bytes](#s074) 完成。

### A2 · Gaussian fchk_name / Link0 与验证

1. [QmInputWriter_input_schema](#s107) 的 `fchk_name` → [QmInputWriter.tool_call](#s123) 解析该路径。
2. [QmInputWriter.render_input](#s121) → [QmInputWriter._build_gjf](#s120) → [QmInputWriter._build_link0](#s111) 将它映射为 `%fchk=`；route 由 [QmInputWriter._build_route](#s113) 生成。
3. [QmInputWriter.validate_rendered_input](#s118) → [compare_calculation_input](#s166) / [_inspect_gaussian](#s160) → [gaussian_sections](#s260)；检查目标没有 `fchk_name` / Link0 合法卡集合，再经 [QmInputWriter._prepare_gaussian_file_parents](#s122) 准备父目录、atomic write 落盘，成功输出来自 [QmInputWriter.tool_call](#s123) 的返回分支。

这是输入生成与校验路径；本轮没有运行真实 Gaussian，不能把“生成成功”写成“成功生成 fchk”。

### A3 · ts_guess strict 与外层原生终止闸门不一致

1. [TsGuess_input_schema](#s127) → [TsGuess.tool_call](#s133)（路径转换、`asyncio.to_thread`、异常包装）→ [TsGuess._verify](#s134) → [_parse_freq_log](#s132) → [read_qm_log](#s305) / [parse_qm_log_text](#s306)：此处检查的是频率日志的正常终止与收敛。
2. 期望端点：[_reference_molecules](#s130) → [_source_molecule](#s129) → [read_molecule](#s252)；虚频位移建议由 [_assess_imag_mode_alignment](#s131) 产生。
3. strict 路径：[TsGuess._strict_path_verdict](#s137) → [TsGuess._extract_irc_endpoints](#s135)；Gaussian → [extract_irc](#s192) → [extract_irc_from_text](#s193) → [_parse_irc](#s191)；ORCA → [TsGuess._extract_orca_irc_endpoints](#s136) → [extract_irc_endpoints](#s294) / [read_endpoint_geometry](#s296)。这些提取器不以 IRC 主日志正常终止为闸门。
4. 随后 [verify_short_irc_direction](#s229) → [irc_endpoint_geometries](#s218) / [irc_start_geometry](#s207) / [_usable_ts_geometries](#s224) / [_usable_minimum_geometries](#s225) → [_endpoint_optimization_proof](#s228)；TS 与端点用 `normal_log`，IRC 主日志自身未在该入口统一通过 `normal_log`。结果回 [TsGuess._verify](#s134) → [TsGuess_output_schema](#s128)。
5. DAG 外层：[file_scientific_checks](#s044) → [_file_scientific_checks](#s045) → [_logs](#s037) → [normal_log](#s215)，先过滤原生终止缺失/错误的绑定日志，再调用同一 core proof。
6. Benchmark 外层：[audit_self_consistency](#s029) → [_strict_irc_proof](#s028) → [normal_log](#s215) / [irc_start_geometry](#s207)，只把正常终止的 IRC 放入 `irc_logs`，然后调用 single / paired proof。

合成 parser fixture 用于改变终止标记的对照；其 helper 中是否打印 stationary marker 不是本项生产缺陷。完整函数保持现有条件，附录不把“IRC未到极小点”与“主作业错误终止”混为一谈。

### A4 · Gaussian ReadFC 的 Hessian 依赖与 ORCA 对照

1. 输入：[TsInput](#s330) → [TsVerification](#s327) → [QmCalculation](#s298)；`verification.irc` 由 [stage_calculation](#s333) → [resolve_calculation](#s312) 解析，不公开 oldchk 字段。
2. 流程调用点：[_refine](#s342) → [_write_irc_input](#s341)；找到 frequency step 的 `optimized.xyz` → [_stage_writer_tasks](#s337) → writer schema → [_writer_request_errors](#s335) → [QmInputWriter.render_input](#s121) → [_writer_render_error](#s336) → [_write_immutable_input](#s332)。Gaussian route 保留 `irc=(readfc,reverse)`，默认 `%chk` 是新 IRC 路径。
3. 提交校验：[_submit_step](#s340) → [_check_calculation_submission](#s339) → [compare_calculation_input](#s166)；此检查覆盖方法、原生关键词和几何，没有把频率 checkpoint 作为 ReadFC 依赖绑定/复制。公开普通提交接口另外见 `SubmitComputeJob_input_schema` / `SubmitComputeJob_output_schema`。
4. 远端 overlay：[_stage_native_paths](#s089) → [_native_file_tokens](#s088)；Gaussian `%oldchk` / 已存在 `%chk` 及 ORCA `Hess_Filename` 等显式路径经其嵌套 `relocate` 复制。缺少声明且位于 frequency 目录的 checkpoint 不会凭空进入 IRC stage；ORCA 显式 Hessian 路径会成为 dependency。
5. 真实远端代码延伸（未由 dry-run 执行）：[run_remote_compute](#s091) → [_stage_and_submit](#s090) → [remote_calculator_argv](#s084) → [build_remote_runner_script](#s085) 或 [build_batch_script](#s062) → staging → [SshTransport.push_dir](#s082) / [SshTransport.push_files](#s083) → [push_dir](#s072) / [push_files](#s073) → [_run_rsync](#s071) → [_submit_shell](#s087) / [_submit_slurm](#s086) → [SshTransport.checked](#s081) → [run_remote_checked](#s067) / [run_remote](#s066)。
6. 本轮实际 dry-run：[build_calculator_cmd](#s048) → [check_calculator_script](#s047) → [_default_calculator_path](#s046) → `cloudra/calculator.sh` 的参数与工作目录转换 → `run_gaussian` → spy `g16`；shell 的 Gaussian/ORCA 完整函数和 dispatch 在末尾摘录。

探针只调用写入、提交校验和 staging，再以退出码 42 的 g16 spy 读取输入；没有运行真实 Gaussian，也没有执行 SSH 传输。

### A5 · 同目录邻居 irc_endpoints.json 的 hash mismatch

1. 快照入口 [snapshot_evidence_file](#s032) → [_extract_qm_log](#s031) → [read_qm_log](#s305)；Gaussian IRC 分支还调用 [extract_irc](#s192)。
2. 随后 [_archived_irc_endpoints](#s293) 固定读取 `Path(log_path).parent / "irc_endpoints.json"` → `_ArchivedIrcEvidence.model_validate` → 比较当前 log sha256 与 manifest；不一致直接抛 `Archived IRC log hash mismatch`。
3. Benchmark 另一个直接入口：[_LogProbe.irc_atom_binding](#s027) → [_archived_irc_endpoints](#s293)；该调用没有把邻居 manifest 当作“无此日志的binding”处理。
4. 该 Gaussian 对照的原生日志可用性由 [normal_log](#s215) 与 [irc_endpoint_geometries](#s218) 判定；Gaussian 原生帧路径不需要同目录 manifest。

### A6 · ORCA 唯一 glob 误收 foreign sidecar，snapshot 接受

1. [extract_irc_endpoints](#s294) → [_archived_irc_endpoints](#s293)（无 archive 时继续）→ [_orca_sidecar_roots](#s287) → [_irc_endpoint_sidecar](#s290)。
2. 优先查精确 stem 的 final / trajectory；失败后 → [_sidecar_search_dirs](#s288)，glob 结果 `len(hits) == 1` 直接接受，只有多命中分支才调用 [_basename_matches_any_job](#s289)。
3. [snapshot_evidence_file](#s032) 的 ORCA IRC 分支 → [extract_irc](#s284) → [extract_irc_endpoints](#s294) → 检查至少一个 geometry_ref、沙箱范围并hash/copy → 写 manifest → 重解析 archived bytes → 返回 [FileEvidenceSnapshot](#s030)；该函数没有验证 foreign geometry 的原子数/归属与主日志一致。
4. 后续消费时 [read_endpoint_geometry](#s296) 按 origin 读完整文件或轨迹末帧；[orca_irc_endpoint_geometries](#s214) 会再解析几何，这不能逆转 snapshot 已接受邻居 bundle 的事实。

### A7 · 无关未绑定 Gaussian 坏坐标使评分异常传播

1. [BenchmarkRunner.score_sandbox](#s021) → [audit_integrity](#s015) → [find_graph_json](#s006) / [load_delivered_graph](#s007) → [scan_evidence_files](#s011) → [_classify](#s012) / [_smiles_in_native_log](#s010)。目录里的试错 `.log` 进入候选列表。
2. [bind_graph_to_evidence](#s014) 在建立节点绑定前，对候选调用 [normal_log](#s215)；这次调用在 `_geometry_species` 的 try/except 之前。
3. [normal_log](#s215) → [frequency_geometry_matches](#s216) → 其嵌套 `geometry` → [final_xyz_from_text](#s181) → [_parse_coord_block_after](#s185) → `float(parts[3])`：`**************` 在这里产生 ValueError。
4. 对照 [_LogProbe._parse](#s027) 经 [read_qm_log](#s305) 时捕获 `(OSError, ValueError)`，返回 `(None, None)`；这不能保护此前 integrity 调用。
5. `score_sandbox` 不捕获该异常。实际 runner 的源码延伸：[BenchmarkRunner.run_all](#s024) → [BenchmarkRunner._run_one_guarded](#s023) → [BenchmarkRunner.run_task](#s022) → `score_sandbox`；异常反向逃逸后 `_run_one_guarded` 捕获 Exception，构造 [RunResult](#s016)（各分量默认 0），记录 `task crashed`，调用 [BenchmarkDB.record](#s018) → `RunResult.to_row` 落库。

本轮探针直接实测 `score_sandbox` 抛 ValueError；“task crashed / 零分”是完整 runner 源码中的后续处理，不能写成该探针已真实执行整轮 benchmark。

### F1 · paired 分离产物显式 charge 传播（当前已修）

1. [_strict_irc_proof](#s028) / [_file_scientific_checks](#s045) 将显式 charge 传入 [verify_short_irc_pair](#s230)。
2. paired proof 的两侧外帧 → 本地 `outer_geometry` → [irc_frames_for](#s212) 或 ORCA sidecar → [irc_start_geometry](#s207) / [_usable_ts_geometries](#s224) / [_usable_minimum_geometries](#s225)。
3. `separated` 分支 → [verify_separated_product_direction](#s223)，当前源码传 `charge=charge`；向单路径 [verify_short_irc_direction](#s229) 的对应分支对照。
4. 分离产物身份 → [_geometry_matches_species](#s222) / [_ordered_graph_matches](#s219)；反应物方向 → [align_atom_order](#s241) → [evaluate_endpoint_between](#s243) → [perceive_bonds](#s239) / [_rdkit_bonds](#s238)。charge 会影响分子键感知，不应由binding缺失改为0。

本附录提取的是共享工作区已修态。基线 HEAD 的一行差异单独保留在快照元数据下；不把这项继续列作当前未修生产缺陷。

### E1 · Gaussian IRC 打印几何语义对照与 E1 原件分支

1. [extract_irc](#s192) → [_read_text](#s170) → [extract_irc_from_text](#s193) → [_parse_irc](#s191)；Point Number / Path Number 区段与 summary 表经 [_parse_irc_summary_table](#s189) 汇合。
2. 当前点 Cartesian 来源：[_parse_current_structure](#s186) → [_parse_coord_block_after](#s185)；备选/先前 Input orientation：[_parse_last_input_orientation](#s187) → 同一坐标解析 → [_coords_to_xyz](#s177) → FrameRecord。
3. 身份判据：[same_geometry](#s231) 的嵌套 `proper_rotation` 用 SVD / determinant 修正的 Kabsch proper rotation；先调用 [align_atom_order](#s241) → [dist_matrix](#s235) / [_hungarian](#s240)，再做严格 residual 验收；ties 再枚举 anchor 与严格对应。
4. 优化谱系消费：[_optimization_geometries](#s226) → [_optimized_minima](#s227) → [_endpoint_optimization_proof](#s228) 用 `same_geometry(source_start, source_end)` / target 对照；DAG 独立 Opt/Freq 还经 [validate_frequency_geometry](#s039) → [_final_geometry](#s038) → 同一 `same_geometry`。
5. 完整证据提交回放：[DagSubmitStepEvidenceInput](#s139) → [DagSubmitStepEvidence.tool_call](#s140) → [snapshot_evidence_file](#s032) / [validate_ts_mode](#s033) → `register_evidence` 与 `AttachRef` → [file_scientific_checks](#s044) → [_file_scientific_checks](#s045) → [verify_short_irc_direction](#s229) → [_endpoint_optimization_proof](#s228) → [DagToolOutput](#s138) 返回 scientific_checks；frequency / ts_opt passed，short_irc incomplete。

HCN Euler-PC 捕获日志的20个可比较点中，CURRENT 与此前 Input 打印均不被 same_geometry 接受；reverse Point 10 的 proper-aligned 最大原子残差约 5.292975e-4 Å，最大两原子距离差约 7.218987e-4 Å。CURRENT 对应真实 corrector energy 变化。该 HCN 对照不能据此放宽全局几何身份容差。后续 E1 原件分支的只读结果显示：端点 Opt 输入采用 corrector 前 Input 打印，与 CURRENT 的 proper-aligned 最大残差分别为 reverse 3.6600335e-5 Å、forward 1.1025074e-5 Å，均不是纯六位小数舍入；仓库 parser 外帧对应 CURRENT。完整 E1 DAG 回放已确认：原 seq4736 请求 / seq4761 回执中的 frequency 与 ts_opt 均 passed、short_irc incomplete，在隔离重建图中以相同材料复现。原件和副本计算文件的 SHA-256 前后不变。因为未提供原 DAG 数据库，回放没有恢复历史审批 / skipped 状态；不据此宣称复现了完整历史状态。打印差异不直接等于整轮 E1 失败的唯一生产根因。E1 原件不复制入仓库。

### 能力对照 · 常用入口的 Gaussian / ORCA 双端产物不对称

1. 计算完成归档：[complete_execution_evidence](#s052) → [_execution_receipt](#s050) / [get_log_path](#s049) → 复制本次 log；只有 ORCA 分支再调用 [_orca_geometry_output_paths](#s051)、复制原生几何 → [snapshot_irc_endpoints](#s295)。Gaussian 分支只冻结日志。
2. 公开读日志：[LogParser_input_schema](#s101) → [LogParser.tool_call](#s104) → [LogParser._resolve_requested_fields](#s103) → [LogParser._parse_log](#s105) → [extract_irc_from_text](#s193) 或 ORCA summary → [LogParser_output_schema](#s102)；IRC字段只返点数、rx范围、端点能量、收敛等摘要，不返双端XYZ路径。
3. 公开转换：[FormatConverter_input_schema](#s097) → [FormatConverter.tool_call](#s100) → [FormatConverter._convert_log](#s099) → Gaussian / ORCA `extract_frames_from_text`；CSV 分支 → [frames_to_csv](#s205)（含帧坐标）；XYZ 分支仅取 `frames[-1]` → [FormatConverter_output_schema](#s098)。
4. 显式 canonical 双端导出能力在 [TsGuess.tool_call](#s133) → [TsGuess._verify](#s134) → [TsGuess._extract_irc_endpoints](#s135) / [TsGuess._extract_orca_irc_endpoints](#s136) 中，写 `irc_end_a.xyz` / `irc_end_b.xyz` 并由 [TsGuess_output_schema](#s128) 返回。

这里记录当前能力边界，不据此认定缺 sidecar 本身就是 E1 根因，也不否认 native Gaussian 日志包含可由 parser 提取的双侧坐标。


## 已修 charge 的相对 HEAD 差异

```diff
diff --git a/cloudra/tools/core/irc_evidence.py b/cloudra/tools/core/irc_evidence.py
index 836afc43..6a223cf2 100644
--- a/cloudra/tools/core/irc_evidence.py
+++ b/cloudra/tools/core/irc_evidence.py
@@ -659,7 +659,7 @@ def verify_short_irc_pair(forward_log, reverse_log, ts_logs, endpoint_a_logs, en
     if separated:
         for geometry, ts_binding in ts:
             verdict = verify_separated_product_direction((forward, reverse), geometry, source,
-                product_smiles, target, charge=(atom_binding or {}).get('charge', 0),
+                product_smiles, target, charge=charge,
                 atom_binding=atom_binding if ts_binding == atom_binding else None)
             if verdict['is_match']:
                 return True, verdict['details']
```


## 按源码路径分组的完整定义


## `cloudra/base/tools_class.py`

文件 SHA-256：`b7c91f9a67763dd26472215516fdec1bacbbd0a64455556840762aabb891a877`


<a id="s001"></a>

### S001 · `input_schema`

`cloudra/base/tools_class.py:38–69`

```python
class input_schema(BaseModel):
    '''
    工具输入模式基类，定义工具需要的输入参数和格式。

    子类用法示例：
        class MyInput(input_schema):
            query: str = Field(description="搜索关键词")
            max_results: int = Field(default=10, description="最大返回条数")

    通过 to_parameters_schema() 可自动生成符合 OpenAI Function Calling 规范的 parameters 字典。
    '''

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def to_parameters_schema(cls) -> dict:
        '''
        生成符合 OpenAI Function Calling 的 parameters 字典。
        基于 Pydantic model_json_schema() 微调：
        - properties / required 已由 Pydantic 根据字段声明自动生成
        - 强制附加 additionalProperties: false，防止 LLM 传入未定义字段
        '''
        schema = cls.model_json_schema()
        parameters = {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
            "additionalProperties": False,
        }
        if "$defs" in schema:
            parameters["$defs"] = schema["$defs"]
        return parameters
```


<a id="s002"></a>

### S002 · `output_schema`

`cloudra/base/tools_class.py:71–75`

```python
class output_schema(BaseModel):
    '''
    工具输出模式基类，定义工具输出的格式。
    子类按普通 Pydantic Model 声明字段即可。
    '''
```


## `cloudra/benchmark/integrity.py`

文件 SHA-256：`a93b7131ee3c735f9d7e55322c71440214974bf66e859c4e7149fb612c4e5b8c`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/benchmark/integrity.py:110–110`

```python
_EVIDENCE_SUFFIXES = {".gjf", ".com", ".inp", ".xyz", ".log", ".out", ".sdf", ".mol", ".json"}
```


`cloudra/benchmark/integrity.py:113–113`

```python
MAX_METADATA_BYTES = 20 * 1024 * 1024
```


<a id="s003"></a>

### S003 · `EvidenceFile`

`cloudra/benchmark/integrity.py:118–123`

```python
@dataclass
class EvidenceFile:
    path: str
    smiles_found: list[str] = field(default_factory=list)
    kind: str = ""  # 'gaussian'|'orca'|'xyz'|'json'|'unknown'
    size: int = 0   # 原始字节数，仅作文件信息，不是科学资格条件
```


<a id="s004"></a>

### S004 · `NodeBinding`

`cloudra/benchmark/integrity.py:126–133`

```python
@dataclass
class NodeBinding:
    node_id: str
    bound_files: list[str] = field(default_factory=list)
    matched: bool = False
    # 绑定质量：1.0 = 指纹/哈希级全绑；(0, 1) = 仅质子化/电荷态不同的骨架
    # 匹配（partial credit，扣分不判零）；0 = 未绑定。
    quality: float = 0.0
```


<a id="s005"></a>

### S005 · `IntegrityReport`

`cloudra/benchmark/integrity.py:136–148`

```python
@dataclass
class IntegrityReport:
    graph_found: bool
    graph_parseable: bool
    graph_path: Optional[str] = None
    delivered_graph: Optional[GoldMechanismGraph] = None
    evidence_files: list[EvidenceFile] = field(default_factory=list)
    # 只含参与绑定评估的节点（accessible=true；TS 节点经边间接绑定）——
    # accessible=false 的节点不要求证据，不在此列
    node_bindings: list[NodeBinding] = field(default_factory=list)
    # 平均绑定质量（含 partial credit；分母只含参与绑定的节点）
    binding_quality: float = 1.0
    notes: list[str] = field(default_factory=list)
```


<a id="s006"></a>

### S006 · `find_graph_json`

`cloudra/benchmark/integrity.py:156–169`

```python
def find_graph_json(sandbox: Path) -> Optional[Path]:
    """Locate the agent-maintained mechanism_graph.json at the sandbox root,
    falling back to any *.json that parses to a mechanism graph shape."""
    direct = sandbox / "mechanism_graph.json"
    if direct.is_file():
        return direct
    for p in sorted(sandbox.rglob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(data, dict) and "nodes" in data and "edges" in data:
            return p
    return None
```


<a id="s007"></a>

### S007 · `load_delivered_graph`

`cloudra/benchmark/integrity.py:172–196`

```python
def load_delivered_graph(path: Path) -> Optional[GoldMechanismGraph]:
    """Parse a delivered graph JSON into GoldMechanismGraph.

    交付侧宽松加载（Postel）：agent 多写的键（energy/metadata 等）忽略、
    边缺 id 自动补；gold 侧仍由 strict schema 约束。端点引用完整性由
    GoldMechanismGraph 的 validator 把关：悬空 from/to/via → 校验失败、
    返回 None（不可解析），不再静默造幽灵节点进图比较。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    try:
        nodes = [_DeliveredNode.model_validate(n) for n in data.get("nodes", [])]
        edges = [_DeliveredEdge.model_validate(e) for e in data.get("edges", [])]
        return GoldMechanismGraph(
            nodes=[MechanismNode(**n.model_dump()) for n in nodes],
            edges=[
                MechanismEdge(**(e.model_dump() | {"id": e.id or f"e{i}"}))
                for i, e in enumerate(edges)
            ],
        )
    except Exception:
        return None
```


<a id="s008"></a>

### S008 · `_smiles_in_json`

`cloudra/benchmark/integrity.py:199–214`

```python
def _smiles_in_json(obj) -> list[str]:
    """结构化收集 JSON 里 smiles 键的值（含数组）。"""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == "smiles":
                if isinstance(v, str):
                    found.append(v)
                elif isinstance(v, list):
                    found.extend(s for s in v if isinstance(s, str))
            else:
                found.extend(_smiles_in_json(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_smiles_in_json(item))
    return found
```


<a id="s009"></a>

### S009 · `_smiles_in_text`

`cloudra/benchmark/integrity.py:217–239`

```python
def _smiles_in_text(text: str) -> list[str]:
    # Structured files are read as JSON; annotation parsing is for raw text.
    try:
        data = json.loads(text)
    except Exception:
        data = None
    if isinstance(data, (dict, list)):
        return _smiles_in_json(data)
    found = []
    for line in text.splitlines():
        offset = 0
        while (index := line.lower().find('smiles', offset)) >= 0:
            offset = index + len('smiles')
            if index and (line[index - 1].isalnum() or line[index - 1] == '_'):
                continue
            suffix = line[offset:].lstrip("'\" \t")
            if not suffix or suffix[0] not in ':=':
                continue
            value = suffix[1:].lstrip().lstrip("'\"")
            end = next((i for i, char in enumerate(value) if char.isspace() or char in ",;\"'}"), len(value))
            if end:
                found.append(value[:end])
    return found
```


<a id="s010"></a>

### S010 · `_smiles_in_native_log`

`cloudra/benchmark/integrity.py:242–275`

```python
def _smiles_in_native_log(lines, kind: str):
    archive_prefix: str | None = None
    archive_title: list[str] | None = None
    archive_tail = ""
    for line in lines:
        if kind == "gaussian" and line.lstrip().startswith(r"1\1\GINC-"):
            archive_prefix, archive_title, archive_tail = "", None, ""
        if archive_prefix is not None:
            if not line.strip():
                archive_prefix, archive_title, archive_tail = None, None, ""
                continue
            # Gaussian wraps archive records with one formatting space per
            # physical line. Decode their fields before parsing the title:
            # double backslashes separate route/title/charge+geometry, whereas
            # a single backslash inside a stereochemical SMILES is data.
            fragment = line.rstrip("\r\n").removeprefix(" ")
            if archive_title is None:
                archive_prefix += fragment
                fields = archive_prefix.split(r"\\", 3)
                if len(fields) == 4:
                    archive_title = _smiles_in_text(fields[2])
                    # The remaining archive may contain a quadratic-size
                    # Hessian. Retain no coordinates or numerical body.
                    archive_prefix = ""
                    del fields
            archive_tail = (archive_tail + fragment)[-3:]
            if archive_tail != r"\\@":
                continue
            archive_prefix = None
            if archive_title is not None:
                yield from archive_title
            continue
        if "smiles" in line.lower():
            yield from _smiles_in_text(line)
```


<a id="s011"></a>

### S011 · `scan_evidence_files`

`cloudra/benchmark/integrity.py:278–326`

```python
def scan_evidence_files(sandbox: Path, exclude: Optional[Path] = None) -> list[EvidenceFile]:
    files: list[EvidenceFile] = []
    for p in sorted(sandbox.rglob("*")):
        if not p.is_file():
            continue
        try:
            p.resolve().relative_to(sandbox.resolve())
        except ValueError:
            continue
        if p.suffix.lower() not in _EVIDENCE_SUFFIXES:
            continue
        if p.name == "mechanism_graph.json":
            continue
        # 兜底发现加载的交付图（如 sub/my_graph.json）同样不得计入证据——
        # 否则图文件内嵌的 SMILES 会自绑，零计算证据也能过 Layer 1
        if exclude is not None and p == exclude:
            continue
        kind = _classify(p)
        try:
            size = p.stat().st_size
            if kind in {'gaussian', 'orca'} and p.suffix.lower() in {'.log', '.out'}:
                # Native logs are not JSON. Discover annotations one line at a
                # time instead of making a second full-size in-memory copy.
                with p.open(encoding='utf-8', errors='replace') as stream:
                    smiles = list(dict.fromkeys(_smiles_in_native_log(stream, kind)))
                text = ''
            elif size > MAX_METADATA_BYTES:
                text, smiles = '', []
            else:
                text = p.read_text(encoding="utf-8", errors="replace")
                smiles = _smiles_in_text(text)
        except Exception:
            continue
        # 机理图形状的 JSON（顶层 nodes+edges）一律不是证据：交付图的多份改名
        # 拷贝若算证据，其内嵌 SMILES 会让图节点绑定到自己，零计算证据过 Layer 1
        if p.suffix.lower() == ".json" and text:
            try:
                data = json.loads(text)
            except Exception:
                data = None
            if isinstance(data, dict) and "nodes" in data and "edges" in data:
                continue
        files.append(EvidenceFile(
            path=str(p.relative_to(sandbox)),
            smiles_found=smiles,
            kind=kind,
            size=size,
        ))
    return files
```


<a id="s012"></a>

### S012 · `_classify`

`cloudra/benchmark/integrity.py:329–351`

```python
def _classify(p: Path) -> str:
    s = p.suffix.lower()
    if s in (".gjf", ".com"):
        return "gaussian"
    if s == ".inp":
        return "orca"
    if s == ".xyz":
        return "xyz"
    if s == ".json":
        return "json"
    if s in (".log", ".out"):
        # sniff engine by content header（只读头部，不整读）
        try:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(2000)
        except Exception:
            return "unknown"
        if "Entering Gaussian System" in head or "Gaussian" in head:
            return "gaussian"
        if "O   R   C   A" in head or "ORCA" in head:
            return "orca"
        return "log"
    return "unknown"
```


<a id="s013"></a>

### S013 · `_species_file_qualities`

`cloudra/benchmark/integrity.py:359–393`

```python
def _species_file_qualities(
    species_smiles: str,
    files: list[EvidenceFile],
    cfg: GedConfig,
    match_threshold: float,
    partial_quality: float,
) -> tuple[float, list[str]]:
    """逐证据文件评估该物种（一条 SMILES；络合物为点连接单条）的绑定质量，
    返回 (best_quality, [path, ...])。

    三档：指纹/哈希 cost ≤ match_threshold → 1.0；否则查质子化骨架——仅电荷
    态/质子化形式不同 → `protonation_variant_quality`（质量 = 1-(1-partial)·w，
    w = 指纹相对误差 1-Tanimoto：指纹退化的小分子离子对扣满到 partial_quality，
    大分子小扰动扣得少）；其余 → 0（不绑）。指纹对单重原子物种会退化
    （O vs [OH-] 的 Tanimoto=0），所以质子化通道必须在指纹之后独立兜底。"""
    best = 0.0
    paths: list[str] = []
    for f in files:
        if not f.smiles_found:
            continue
        q = 0.0
        for fs in f.smiles_found:
            # A similar fingerprint cannot replace missing molecular components.
            if len(fs.split(".")) != len(species_smiles.split(".")):
                continue
            if species_substitution_cost([species_smiles], [fs], cfg) <= match_threshold:
                q = 1.0
                break
            if partial_quality > 0.0:
                vq = protonation_variant_quality(species_smiles, fs, cfg, partial_quality)
                q = max(q, vq)
        if q > 0.0:
            paths.append(f.path)
            best = max(best, q)
    return best, paths
```


<a id="s014"></a>

### S014 · `bind_graph_to_evidence`

`cloudra/benchmark/integrity.py:396–518`

```python
def bind_graph_to_evidence(
    graph: GoldMechanismGraph,
    files: list[EvidenceFile],
    cfg: Optional[GedConfig] = None,
    match_threshold: float = 0.2,
    partial_quality: float = 0.7,
    *,
    sandbox: Path,
) -> list[NodeBinding]:
    """Bind each declared species to matching evidence for its complete identity.

    A dot-connected entry requires whole-complex geometry. Multiple entries
    describe separated species and each needs its own matching evidence.
    Inaccessible nodes are exempt; TS nodes retain explicit evidence lineage.
    """
    cfg = cfg or GedConfig()
    sandbox = Path(sandbox)
    available = files
    from cloudra.dag.file_science import _geometry_species
    verified = []
    for evidence in files:
        identities = []
        if evidence.kind == 'xyz' or normal_log(sandbox / evidence.path):
            for identity in evidence.smiles_found:
                try:
                    if _geometry_species(str(sandbox / evidence.path), identity):
                        identities.append(identity)
                except (ValueError, RuntimeError) as exc:
                    # Dependency failures must not become missing molecular evidence.
                    if isinstance(exc, RuntimeError) and isinstance(exc.__cause__, ImportError):
                        raise
                    continue
        verified.append(replace(evidence, smiles_found=identities))
    files = verified
    bindings: list[NodeBinding] = []
    by_id: dict[str, NodeBinding] = {}
    ts_ids = {n.id for n in graph.nodes if n.role == NodeRole.TRANSITION_STATE}

    # pass 1: accessible 物种节点（TS 节点第二趟按边端点判定）
    for node in graph.nodes:
        if not node.accessible:
            continue  # 不可达声明不要求证据
        nb = NodeBinding(node_id=node.id)
        by_id[node.id] = nb
        bindings.append(nb)
        if node.id in ts_ids:
            continue
        if 'evidence_log' in node.properties:
            raw = node.properties['evidence_log']
            try:
                path = (sandbox / raw).resolve() if isinstance(raw, str) else None
                relative = str(path.relative_to(sandbox.resolve())) if path is not None else None
                evidence = next((item for item in available if item.path == relative
                                 and item.kind in {'gaussian', 'orca'}), None)
                if evidence and node.smiles and normal_log(path):
                    identities = next(item.smiles_found for item in files if item.path == relative)
                    identities = list(identities)
                    identities.extend(identity for identity in node.smiles if _geometry_species(str(path), identity))
                    candidate = replace(evidence, smiles_found=list(dict.fromkeys(identities)))
                    qualities = [_species_file_qualities(identity, [candidate], cfg, match_threshold, partial_quality)[0]
                                 for identity in node.smiles]
                    if all(quality > 0 for quality in qualities):
                        nb.bound_files, nb.matched, nb.quality = [relative], True, min(qualities)
            except (ValueError, RuntimeError, OSError) as exc:
                if isinstance(exc, RuntimeError) and isinstance(exc.__cause__, ImportError):
                    raise
                pass
            continue  # A bad explicit reference must never select other history.
        if not node.smiles:
            # 物种节点不带 SMILES = 只有声明没有可取证内容，不予绑定；
            # 否则 agent 把 SMILES 全留空即可零证据通过本层。
            continue
        all_species_matched = True
        node_quality = 1.0
        for species_smiles in node.smiles:
            q, qpaths = _species_file_qualities(
                species_smiles, files, cfg, match_threshold, partial_quality
            )
            if qpaths:
                nb.bound_files.extend(qpaths)
            else:
                all_species_matched = False
            node_quality = min(node_quality, q)
        nb.bound_files = sorted(set(nb.bound_files))
        nb.matched = all_species_matched and bool(nb.bound_files)
        nb.quality = node_quality if nb.matched else 0.0

    # pass 2: TS nodes — 仅当某条边经由它且两端物种都已绑定证据；
    # accessible=false 的 TS 不在 by_id 里，自然跳过
    for ts_id in ts_ids:
        nb = by_id.get(ts_id)
        if nb is None:
            continue
        node = next(n for n in graph.nodes if n.id == ts_id)
        if 'evidence_log' in node.properties:
            raw = node.properties['evidence_log']
            try:
                path = (sandbox / raw).resolve() if isinstance(raw, str) else None
                relative = str(path.relative_to(sandbox.resolve())) if path is not None else None
                if any(f.path == relative and f.kind in {'gaussian', 'orca'} for f in available) and normal_log(path):
                    endpoint_quality = max((min(by_id[e.from_node].quality, by_id[e.to_node].quality)
                                            for e in graph.edges if e.via == ts_id and e.from_node in by_id and e.to_node in by_id), default=0.0)
                    nb.bound_files, nb.matched, nb.quality = [relative], True, endpoint_quality
            except (ValueError, OSError):
                pass
            continue
        for e in graph.edges:
            if e.via != ts_id:
                continue
            a, b = by_id.get(e.from_node), by_id.get(e.to_node)
            if a is not None and b is not None and a.matched and b.matched:
                nb.matched = True
                nb.quality = min(a.quality, b.quality)
                from cloudra.benchmark.barrier_evidence import (
                    _declared_node_energy_hartree,
                    _identify_by_declared_energy,
                )
                declared = _declared_node_energy_hartree(node)
                candidates = [f.path for f in available if f.kind in {'gaussian', 'orca'}]
                selected = _identify_by_declared_energy(sandbox, candidates, declared) if declared is not None else None
                nb.bound_files = [selected] if selected else []
                break
    return bindings
```


<a id="s015"></a>

### S015 · `audit_integrity`

`cloudra/benchmark/integrity.py:526–573`

```python
def audit_integrity(
    sandbox: Path,
    rubric: Optional[IntegrityRubric] = None,
    cfg: Optional[GedConfig] = None,
) -> IntegrityReport:
    """审计入口：只产出报告（图可解析性 + 逐节点绑定质量），不判通过与否。
    零证据倒扣与证据加权扣分都在 runner/graph_similarity 侧按报告事实计算。"""
    rubric = rubric or IntegrityRubric()
    report = IntegrityReport(graph_found=False, graph_parseable=False)

    graph_path = find_graph_json(sandbox)
    if graph_path is None:
        report.notes.append("mechanism_graph.json not found in sandbox")
        return report
    report.graph_found = True
    report.graph_path = str(graph_path.relative_to(sandbox))

    graph = load_delivered_graph(graph_path)
    if graph is None:
        report.notes.append("mechanism_graph.json present but not parseable")
        return report
    report.graph_parseable = True
    report.delivered_graph = graph

    # 兜底发现的交付图文件自身排除出证据扫描：其内嵌 SMILES 不构成计算证据
    report.evidence_files = scan_evidence_files(sandbox, exclude=graph_path)
    report.node_bindings = bind_graph_to_evidence(
        graph,
        report.evidence_files,
        cfg,
        match_threshold=rubric.match_threshold,
        partial_quality=rubric.protonation_partial_quality,
        sandbox=sandbox,
    )

    report.binding_quality = (
        sum(b.quality for b in report.node_bindings) / len(report.node_bindings)
    ) if report.node_bindings else 0.0
    bound = [b for b in report.node_bindings if b.matched]
    partial = [b.node_id for b in bound if b.quality < 1.0]
    if partial:
        report.notes.append(
            f"partial-credit binds (protonation/charge-state variants): {partial}"
        )
    unbound = [b.node_id for b in report.node_bindings if not b.matched]
    if unbound:
        report.notes.append(f"unbound nodes (no matching evidence file): {unbound}")
    return report
```


## `cloudra/benchmark/runner.py`

文件 SHA-256：`4b884cd853a791576036bffc588364a784f5b02d389cdc08d870d44320eb07e1`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/benchmark/runner.py:85–85`

```python
W_GRAPH = 0.1
```


`cloudra/benchmark/runner.py:86–86`

```python
W_SELFCONSISTENCY = 0.3
```


`cloudra/benchmark/runner.py:87–87`

```python
W_ACCURACY = 0.6
```


<a id="s016"></a>

### S016 · `RunResult`

`cloudra/benchmark/runner.py:99–125`

```python
@dataclass
class RunResult:
    task_id: str
    sandbox: str
    graph_score: float = 0.0
    selfconsistency_passed: bool = False
    accuracy_score: float = 0.0
    final_score: float = 0.0
    notes: list[str] = field(default_factory=list)
    # 批次归属（Web 控制面；CLI 每次调用也是一个批次）。空串 = 旧的未挂批记录。
    batch_id: str = ""
    # 行级消融臂标识（task.prompt.orchestration_mode）；旧行迁移为 ''。
    orchestration_mode: str = ""

    def to_row(self) -> tuple:
        return (
            self.task_id,
            self.sandbox,
            self.graph_score,
            int(self.selfconsistency_passed),
            self.accuracy_score,
            self.final_score,
            json.dumps(self.notes, ensure_ascii=False),
            int(time.time()),
            self.batch_id,
            self.orchestration_mode,
        )
```


<a id="s017"></a>

### S017 · `BenchmarkDB._connect`

`cloudra/benchmark/runner.py:178–179`

```python
    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))
```


<a id="s018"></a>

### S018 · `BenchmarkDB.record`

`cloudra/benchmark/runner.py:202–208`

```python
    def record(self, result: RunResult) -> None:
        # append-only：benchmark 数据珍贵，历史行永不由框架删除；"每题最新"
        # 只是查询语义（按 ts 取），不落为破坏性写。
        with self._lock, closing(self._connect()) as c, c:
            c.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)", result.to_row()
            )
```


<a id="s019"></a>

### S019 · `_covering_delivered_edge_ids`

`cloudra/benchmark/runner.py:285–311`

```python
def _covering_delivered_edge_ids(
    gold_edge: MechanismEdge,
    gold_graph: GoldMechanismGraph,
    delivered_graph: GoldMechanismGraph,
    cfg: GedConfig,
    match_threshold: float,
) -> list[str]:
    """覆盖某 gold 边的交付边 id 列表——accuracy 层 gold↔delivered 匹配的
    同口径（`_find_matching_step` 的端点物种判定：同向端点分别
    species_substitution_cost ≤ match_threshold；edge id 不参与匹配）。"""
    gold_nodes = {n.id: n for n in gold_graph.nodes}
    delivered_nodes = {n.id: n for n in delivered_graph.nodes}
    g_from, g_to = gold_nodes.get(gold_edge.from_node), gold_nodes.get(gold_edge.to_node)
    if g_from is None or g_to is None:
        return []
    out = []
    for e in delivered_graph.edges:
        d_from = delivered_nodes.get(e.from_node)
        d_to = delivered_nodes.get(e.to_node)
        if d_from is None or d_to is None:
            continue
        if species_substitution_cost(g_from.smiles, d_from.smiles, cfg) > match_threshold:
            continue
        if species_substitution_cost(g_to.smiles, d_to.smiles, cfg) > match_threshold:
            continue
        out.append(e.id)
    return out
```


<a id="s020"></a>

### S020 · `BenchmarkRunner._ged_config_for`

`cloudra/benchmark/runner.py:338–348`

```python
    def _ged_config_for(self, task: TaskSpec) -> GedConfig:
        """Per-task GED 参数：stereo 是否计代价按 rubric.graph_similarity 的
        stereo_tier_rule，其余全用 runner 默认（per-task 数值覆盖已取消）。"""
        return replace(
            self.ged_config,
            # hard 档立体化学计代价；easy/normal 忽略立体（stereo_free）
            stereo_free=(
                task.rubric.graph_similarity.stereo_tier_rule
                == "easy_normal_stereo_free"
            ),
        )
```


<a id="s021"></a>

### S021 · `BenchmarkRunner.score_sandbox`

`cloudra/benchmark/runner.py:350–503`

```python
    def score_sandbox(self, task: TaskSpec, sandbox: Path) -> RunResult:
        """按交付物评分：图（JSON）+ 日志，不读任何散文。"""
        res = RunResult(
            task_id=task.task_id,
            sandbox=str(sandbox),
            orchestration_mode=task.prompt.orchestration_mode.value,
        )
        ged_config = self._ged_config_for(task)

        integ: IntegrityReport = audit_integrity(sandbox, task.rubric.integrity, ged_config)
        res.notes.extend(integ.notes)

        # 逐节点绑定质量图并入图分：未绑定的 accessible 节点按代价 1.0 记账，
        # 质子化变体部分扣；accessible=false 节点不参与绑定、不在图里，
        # q 缺省 1.0 正好不罚（标志一致性由 graph_similarity 单独把关）。
        binding_quality = {b.node_id: b.quality for b in integ.node_bindings}
        if integ.delivered_graph is not None:
            ged: GedResult = mechanism_similarity(
                integ.delivered_graph,
                task.gold.mechanism_graph,
                ged_config,
                binding_quality=binding_quality,
            )
            res.graph_score = ged.score
        else:
            res.graph_score = 0.0
            res.notes.append("no delivered graph to compare")

        sc: SelfConsistencyReport = audit_self_consistency(
            integ.delivered_graph,
            integ.node_bindings,
            integ.evidence_files,
            sandbox,
            task.rubric.self_consistency,
            charge=task.system.charge,
            integrity_rubric=task.rubric.integrity,
            ged_config=ged_config,
        )
        res.selfconsistency_passed = sc.passed
        res.notes.extend(sc.notes)

        # 自洽回捞（2026-09-25 用户裁决）：gold 边被交付步覆盖、但覆盖它的
        # 交付步全部自洽不合格 → 该 gold 边赢下的图分覆盖贡献倒扣（违规交付
        # 边剔出交付图后重算 GED——同一 gold 边另有自洽合格的覆盖步时保留
        # 覆盖；有效不可达/accessible=false 的交付边本就被自洽豁免，不会进
        # 倒扣集）。不在 gold 子图里的额外交付边自洽不合格只落自洽层零分，
        # 不倒扣图分——gold 边出错与其他边出错严重程度不同。
        if integ.delivered_graph is not None and res.graph_score > 0.0:
            failed_edges = {
                c.element_id
                for c in sc.checks
                if c.kind == "edge" and not c.covered
            }
            if failed_edges:
                remove: set[str] = set()
                for g_edge in task.gold.mechanism_graph.edges:
                    covering = _covering_delivered_edge_ids(
                        g_edge,
                        task.gold.mechanism_graph,
                        integ.delivered_graph,
                        ged_config,
                        task.rubric.integrity.match_threshold,
                    )
                    failing = [e for e in covering if e in failed_edges]
                    if covering and len(failing) == len(covering):
                        remove.update(failing)
                        for eid in sorted(failing):
                            res.notes.append(
                                f"edge {eid}: selfconsistency failed, graph "
                                f"credit for gold edge {g_edge.id} clawed back"
                            )
                if remove:
                    pruned = GoldMechanismGraph(
                        nodes=list(integ.delivered_graph.nodes),
                        edges=[
                            e
                            for e in integ.delivered_graph.edges
                            if e.id not in remove
                        ],
                    )
                    res.graph_score = mechanism_similarity(
                        pruned,
                        task.gold.mechanism_graph,
                        ged_config,
                        binding_quality=binding_quality,
                    ).score

        barriers: BarrierEvidence = collect_barrier_evidence(sandbox)
        res.notes.extend(barriers.notes)
        # hard 档定性选择性：gold.selectivity 带 favored_channel 时替代 accuracy
        # 槽位（composite 的 accuracy 权重给选择性分；barrier spread 数值不评分）
        acc_fail_loud = False
        selectivity = task.gold.selectivity
        if selectivity is not None and selectivity.favored_channel:
            sel_score, sel_note = score_qualitative_selectivity(
                integ.delivered_graph, selectivity
            )
            res.accuracy_score = sel_score
            res.notes.append(sel_note)
        else:
            acc: AccuracyReport = score_accuracy(
                evidence=barriers,
                gold=task.gold,
                rubric=task.rubric.accuracy,
                delivered_graph=integ.delivered_graph,
                cfg=ged_config,
                match_threshold=task.rubric.integrity.match_threshold,
            )
            res.accuracy_score = acc.final_score
            res.notes.extend(acc.notes)
            acc_fail_loud = acc.fail_loud

        rub = task.rubric.integrity
        if not integ.graph_parseable:
            # 图缺失/不可解析 = 不可能有任何证据支撑 -> 零证据倒扣
            res.final_score = -rub.no_evidence_penalty
            res.notes.append(
                "no parseable mechanism graph -> no evidence possible; penalty applied"
            )
            return res
        accessible_species = [
            n
            for n in integ.delivered_graph.nodes
            if n.accessible and n.role is not NodeRole.TRANSITION_STATE
        ]
        evidenced = {b.node_id for b in integ.node_bindings if b.quality > 0.0}
        if accessible_species and not any(
            n.id in evidenced for n in accessible_species
        ):
            # 有 accessible 物种声明但无一绑到证据 = 无证据支撑的机理声明，
            # 比没交付更糟 -> 倒扣；全部节点都声明 accessible=false 是合法
            # 交付（纯不可达声明），不触发本条
            res.final_score = -rub.no_evidence_penalty
            res.notes.append(
                "no evidence bound to any accessible species node -> "
                "unsupported claims; penalty applied"
            )
            return res
        if acc_fail_loud:
            # fail-loud 短路：声明无据/不一致 -> 自洽与 accuracy 分量清零，
            # final 只保留图分
            res.final_score = round(W_GRAPH * res.graph_score, 4)
            res.notes.append(
                "accuracy fail-loud (unsupported or inconsistent declared "
                "barriers); final keeps the graph component only"
            )
            return res
        res.final_score = round(
            W_GRAPH * res.graph_score
            + W_SELFCONSISTENCY * (1.0 if res.selfconsistency_passed else 0.0)
            + W_ACCURACY * res.accuracy_score,
            4,
        )
        return res
```


<a id="s022"></a>

### S022 · `BenchmarkRunner.run_task`

`cloudra/benchmark/runner.py:505–520`

```python
    def run_task(self, task: TaskSpec) -> RunResult:
        # 沙箱按批次分目录：本批目录天然干净，不做任何删除——上一批的交付物
        # 与证据文件永久保留（benchmark 数据珍贵，清理永由用户显式执行）。
        if self.stop_event.is_set():
            raise BenchmarkStopped("benchmark batch stopped")
        sandbox = self.sandbox_for(task.task_id, self.batch_id)
        sandbox.mkdir(parents=True, exist_ok=True)
        self.backend(task, sandbox)
        if self.stop_event.is_set():
            raise BenchmarkStopped("benchmark batch stopped")
        result = self.score_sandbox(task, sandbox)
        if self.stop_event.is_set():
            raise BenchmarkStopped("benchmark batch stopped")
        result.batch_id = self.batch_id
        self.db.record(result)
        return result
```


<a id="s023"></a>

### S023 · `BenchmarkRunner._run_one_guarded`

`cloudra/benchmark/runner.py:522–539`

```python
    def _run_one_guarded(self, task: TaskSpec) -> RunResult:
        """单题异常不拖垮整批：失败题落一条 notes 带原因的零分结果行并继续。
        （后端崩溃记 0 而不是 no_evidence_penalty：基建失败不是 agent 的锅。）"""
        try:
            return self.run_task(task)
        except Exception as exc:
            stopped = isinstance(exc, BenchmarkStopped)
            if not stopped:
                print(f"[benchmark] task {task.task_id} crashed: {exc!r}")
            res = RunResult(
                task_id=task.task_id,
                sandbox=str(self.sandbox_for(task.task_id, self.batch_id)),
                batch_id=self.batch_id,
                orchestration_mode=task.prompt.orchestration_mode.value,
            )
            res.notes.append("cancelled by batch stop" if stopped else f"task crashed: {exc!r}")
            self.db.record(res)
            return res
```


<a id="s024"></a>

### S024 · `BenchmarkRunner.run_all`

`cloudra/benchmark/runner.py:541–561`

```python
    def run_all(self, tasks: list[TaskSpec], concurrency: int = 1) -> list[RunResult]:
        """串行（concurrency=1，默认）或受控并行。并行用线程池：单题都是
        IO 密集（LLM 请求 / 计算子进程），每题一个线程、线程内独立事件循环；
        沙箱按题隔离，benchmark.db 写入由 BenchmarkDB 内部锁串行化。"""
        if concurrency <= 1:
            return [self._run_one_guarded(t) for t in tasks]
        import concurrent.futures as cf

        results: dict[str, RunResult] = {}
        with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
            try:
                futures = {pool.submit(self._run_one_guarded, t): t for t in tasks}
                for fut in cf.as_completed(futures):
                    res = fut.result()
                    results[res.task_id] = res
            except BaseException:
                # Set this before the executor joins its workers: every private
                # runtime loop can then finish its own asynchronous cleanup.
                self.stop_event.set()
                raise
        return [results[t.task_id] for t in tasks]
```


## `cloudra/benchmark/selfconsistency.py`

文件 SHA-256：`b4bc1d094e39dc4787a2f3868dca6f0ca36658dcf950910ed6b0de47914e2ca8`


<a id="s025"></a>

### S025 · `ElementCheck`

`cloudra/benchmark/selfconsistency.py:71–81`

```python
@dataclass
class ElementCheck:
    """一个图元素（节点/边）的覆盖判定。"""

    element_id: str
    kind: str  # "species" | "transition_state" | "edge"
    declared_inaccessible: bool = False
    bound: bool = False
    covered: bool = False
    evidence_used: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
```


<a id="s026"></a>

### S026 · `SelfConsistencyReport`

`cloudra/benchmark/selfconsistency.py:84–88`

```python
@dataclass
class SelfConsistencyReport:
    checks: list[ElementCheck] = field(default_factory=list)
    passed: bool = False
    notes: list[str] = field(default_factory=list)
```


<a id="s027"></a>

### S027 · `_LogProbe`

`cloudra/benchmark/selfconsistency.py:91–153`

```python
class _LogProbe:
    """按路径缓存的日志探针：同一绑定文件可能被多个元素引用，只解析一次。

    只解析正常终止的 QM 日志（gaussian/orca）；
    其余一律返回 None——绑定了不可解析文件不等于有可用证据。"""

    def __init__(self, sandbox: Path, files_by_path: dict[str, EvidenceFile]):
        self._sandbox = sandbox
        self._files = files_by_path
        self._cache: dict[str, tuple[Optional[int], Optional[tuple]]] = {}

    def _parse(self, rel_path: str) -> tuple[Optional[int], Optional[tuple]]:
        """(虚频数, 末帧几何)。虚频数 None = 无频率块/文件不可解析。"""
        if rel_path not in self._cache:
            result: tuple[Optional[int], Optional[tuple]] = (None, None)
            f = self._files.get(rel_path)
            if (
                f is not None
                and f.kind in ("gaussian", "orca")
            ):
                try:
                    facts = read_qm_log(self._sandbox / rel_path)
                except (OSError, ValueError):
                    facts = None
                if facts is not None and facts.engine in {'gaussian', 'orca'} and facts.normal_termination:
                    freqs = facts.frequencies_cm
                    n_imag = sum(freq < 0 for freq in freqs) if freqs else None
                    result = (n_imag, facts.geometry)
            self._cache[rel_path] = result
        return self._cache[rel_path]

    def n_imag(self, rel_path: str) -> Optional[int]:
        return self._parse(rel_path)[0]

    def last_geometry(self, rel_path: str) -> Optional[tuple]:
        """末帧几何 (symbols, positions)；无坐标帧返回 None。"""
        return self._parse(rel_path)[1]

    def ts_witness(self, anchor, pool):
        from cloudra.tools.core.irc_path import same_geometry
        if self.n_imag(anchor) == 1:
            return anchor
        geometry = self.last_geometry(anchor)
        return next((p for p in sorted(pool) if self.n_imag(p) == 1 and
                     same_geometry(geometry, self.last_geometry(p))), None)

    def minimum_witness(self, anchor, pool):
        """Verify the bound geometry, never substitute a historical minimum."""
        from cloudra.tools.core.irc_path import same_geometry
        if self.n_imag(anchor) == 0:
            return anchor
        geometry = self.last_geometry(anchor)
        return next((p for p in sorted(pool) if self.n_imag(p) == 0 and
                     same_geometry(geometry, self.last_geometry(p))), None)

    def irc_atom_binding(self, rel_path: str):
        evidence = self._files.get(rel_path)
        if evidence is None or evidence.kind not in {'gaussian', 'orca'}:
            return None
        from cloudra.tools.core.orca_frames import _archived_irc_endpoints

        endpoints = _archived_irc_endpoints(str(self._sandbox / rel_path))
        return endpoints['forward'].get('atom_binding') if endpoints is not None else None
```


<a id="s028"></a>

### S028 · `_strict_irc_proof`

`cloudra/benchmark/selfconsistency.py:156–257`

```python
def _strict_irc_proof(
    probe: _LogProbe,
    pool: list[str],
    from_files: list[str],
    to_files: list[str],
    charge: int = 0,
    *, ts_files: list[str] | None = None, product_smiles: list[str] | None = None,
    reactant_smiles: list[str] | None = None, details: list[str] | None = None,
) -> Optional[tuple[list[str], list[str]]]:
    """Reconstruct the same native IRC→Opt→Freq proof used by DAG and tools."""
    from cloudra.tools.core import gaussian_frames, orca_frames
    from cloudra.tools.core.irc_evidence import irc_start_geometry
    from cloudra.tools.core.irc_path import same_geometry

    ts_candidates = [(p, witness) for p in sorted(ts_files if ts_files is not None else pool)
                     for witness in (probe.ts_witness(p, pool),) if witness is not None]

    def endpoint_candidates(anchors):
        candidates = set()
        for anchor in anchors:
            witness = probe.minimum_witness(anchor, pool)
            if witness is None:
                continue
            candidates.update((anchor, witness))
            geometry = probe.last_geometry(witness)
            candidates.update(path for path in pool
                              if same_geometry(geometry, probe.last_geometry(path)))
        return sorted(candidates)

    source = endpoint_candidates(from_files)
    target = endpoint_candidates(to_files)
    failures = [
        f"IRC proof TS candidates (anchor, frequency witness): {ts_candidates or ts_files}; "
        f"SOURCE endpoint evidence: {source or from_files}; TARGET endpoint evidence: {target or to_files}."
    ]

    def failed():
        if details is not None:
            details.extend(dict.fromkeys(failures))
        return None

    irc_logs = []
    for path in sorted(pool):
        native = probe._sandbox / path
        if normal_log(native) and irc_start_geometry(native) is not None:
            irc_logs.append(path)
            continue
        evidence = probe._files.get(path)
        if evidence is None or evidence.kind not in {'gaussian', 'orca'}:
            continue
        parser = gaussian_frames if evidence.kind == 'gaussian' else orca_frames
        try:
            jobs = parser.detect_job_types(str(native))
        except OSError as exc:
            failures.append(f'QM evidence candidate {path} could not be read: {exc}')
            continue
        if 'irc' not in jobs:
            continue
        try:
            parser.extract_irc(str(native))
        except ValueError as exc:
            failures.append(f'IRC candidate {path} is unusable: {exc}')
        if not normal_log(native):
            failures.append(f'IRC candidate {path} lacks normally terminated native evidence.')
        elif irc_start_geometry(native) is None:
            failures.append(f'IRC candidate {path} has no usable native starting saddle.')
    if not irc_logs:
        failures.append('No normally terminated IRC candidate supplies a native starting saddle.')
    if not (ts_candidates and source and target):
        failures.append('IRC proof requires a same-geometry first-order saddle witness and verified minima for both endpoints.')
        return failed()

    def absolute(paths):
        return [probe._sandbox / path for path in paths]

    for ts_path, frequency_path in ts_candidates:
        bindings = {}
        for path in irc_logs:
            binding = probe.irc_atom_binding(path)
            if binding and hashlib.sha256((probe._sandbox / frequency_path).read_bytes()).hexdigest() == binding.get('ts_log_sha256'):
                bindings[str(probe._sandbox / path)] = binding
                bindings[str(probe._sandbox / frequency_path)] = binding
                binding_status = 'verified for the selected frequency witness'
            else:
                binding_status = 'absent' if not binding else 'not associated with the selected frequency witness'
            failures.append(f'IRC candidate {path}, TS {ts_path}, frequency witness {frequency_path}: atom binding {binding_status}.')
        options = dict(atom_bindings=bindings, product_smiles=product_smiles,
                       reactant_smiles=reactant_smiles)
        for path in irc_logs:
            passed, proof_details = verify_short_irc_direction(probe._sandbox / path,
                absolute([frequency_path]), absolute(target), absolute(source),
                charge=charge, **options)
            if passed:
                return list(dict.fromkeys([ts_path, frequency_path, path, *source, *target])), proof_details
            failures.extend(f'IRC {path}, TS {frequency_path}: {item}' for item in proof_details)
        for forward, reverse in combinations(irc_logs, 2):
            passed, proof_details = verify_short_irc_pair(probe._sandbox / forward, probe._sandbox / reverse,
                absolute([frequency_path]), absolute(target), absolute(source), charge=charge, **options)
            if passed:
                return list(dict.fromkeys([ts_path, frequency_path, forward, reverse, *source, *target])), proof_details
            failures.extend(f'IRC pair {forward}; {reverse}, TS {frequency_path}: {item}' for item in proof_details)
    return failed()
```


<a id="s029"></a>

### S029 · `audit_self_consistency`

`cloudra/benchmark/selfconsistency.py:260–453`

```python
def audit_self_consistency(
    graph: Optional[GoldMechanismGraph],
    bindings: list[NodeBinding],
    evidence_files: list[EvidenceFile],
    sandbox: Path,
    rubric: Optional[SelfConsistencyRubric] = None,
    charge: int = 0,
    *,
    integrity_rubric: Optional[IntegrityRubric] = None,
    ged_config: Optional[GedConfig] = None,
) -> SelfConsistencyReport:
    rubric = rubric or SelfConsistencyRubric()
    integrity_rubric = integrity_rubric or IntegrityRubric()
    report = SelfConsistencyReport()
    if not (rubric.ts_first_order_saddle or rubric.irc_connects_endpoints):
        report.passed = True
        report.notes.append("self-consistency checks disabled by rubric; passthrough")
        return report
    if graph is None:
        report.notes.append("no delivered graph; self-consistency not assessable")
        return report

    files_by_path = {f.path: f for f in evidence_files}
    probe = _LogProbe(sandbox, files_by_path)
    qm_paths = [f.path for f in evidence_files if f.kind in {'gaussian', 'orca'}]
    bmap = {b.node_id: b for b in bindings}
    species_covered: dict[str, bool] = {}
    edge_checks: dict[str, ElementCheck] = {}

    # 物种节点：极小值证据须覆盖整络合物或每个分开交付的组分。
    for node in graph.nodes:
        if node.role == NodeRole.TRANSITION_STATE:
            continue
        chk = ElementCheck(element_id=node.id, kind="species")
        report.checks.append(chk)
        if not node.accessible:
            chk.declared_inaccessible = True
            chk.covered = True
            chk.notes.append("declared inaccessible; evidence not required")
        else:
            b = bmap.get(node.id)
            chk.bound = bool(b and b.matched)
            if not chk.bound:
                chk.notes.append("no evidence bound to this node")
            else:
                minimum_witnesses = {
                    p: witness for p in b.bound_files
                    for witness in (probe.minimum_witness(p, qm_paths),)
                    if witness is not None
                }
                if len(node.smiles) > 1 or any("." in species for species in node.smiles):
                    # Recheck component coverage using verified bound anchors;
                    # replacing anchors with Freq paths loses explicit references.
                    minimum_files = [files_by_path[p] for p in minimum_witnesses]
                    minimum_binding = bind_graph_to_evidence(
                        GoldMechanismGraph(nodes=[node], edges=[]), minimum_files,
                        ged_config,
                        match_threshold=integrity_rubric.match_threshold,
                        partial_quality=integrity_rubric.protonation_partial_quality,
                        sandbox=sandbox,
                    )[0]
                    chk.covered = minimum_binding.matched
                    if chk.covered:
                        chk.evidence_used.extend(dict.fromkeys(
                            path for anchor in minimum_binding.bound_files
                            for path in (anchor, minimum_witnesses[anchor])
                        ))
                    else:
                        chk.notes.append("verified minima do not cover every declared species; a complex needs its own minimum")
                else:
                    for p, witness in minimum_witnesses.items():
                        chk.covered = True
                        chk.evidence_used.extend(dict.fromkeys([p, witness]))
                        break
                if not chk.covered and not chk.notes:
                    chk.notes.append(
                        "no verified minimum (frequency block with zero "
                        "imaginary frequencies) among bound evidence"
                    )
        species_covered[node.id] = chk.covered

    # 边：TS 步查一阶鞍点 + IRC 方向区间证明（各按 rubric 开关），任一合格证据即覆盖
    for edge in graph.edges:
        chk = ElementCheck(element_id=edge.id, kind="edge")
        report.checks.append(chk)
        edge_checks[edge.id] = chk
        if not graph.edge_effectively_accessible(edge):
            # 有效不可达（边自身 accessible=false，或经由的 TS 节点不可达）视同
            # declared_inaccessible 豁免——与图分/accuracy 同一口径
            # （schema.edge_effectively_accessible）
            chk.declared_inaccessible = True
            chk.covered = True
            chk.notes.append(
                "effectively inaccessible (the edge or its via transition state); "
                "evidence not required"
            )
            continue
        if edge.via is None:
            endpoints_bound = all(
                (bmap.get(nid) is not None and bmap[nid].matched)
                for nid in (edge.from_node, edge.to_node)
            )
            chk.bound = endpoints_bound
            chk.covered = species_covered.get(edge.from_node, False) and (
                species_covered.get(edge.to_node, False)
            )
            if not chk.covered:
                chk.notes.append("no TS node on this edge; endpoint species not both covered")
            continue
        pool: set[str] = set()
        for nid in (edge.via, edge.from_node, edge.to_node):
            b = bmap.get(nid)
            if b and b.matched:
                pool.update(b.bound_files)
        ts_binding = bmap.get(edge.via)
        ts_files = list(ts_binding.bound_files) if ts_binding and ts_binding.matched else []
        # IRC logs are candidates only; the native starting geometry must match
        # the selected TS. Endpoint annotations do not establish that lineage.
        pool.update(qm_paths)
        chk.bound = bool(ts_files)
        if not ts_files:
            chk.notes.append(
                f"no evidence explicitly associated with TS {edge.via}; declare its evidence_log or energy_hartree"
            )
            continue
        saddle_ok = not rubric.ts_first_order_saddle
        irc_ok = not rubric.irc_connects_endpoints
        for p in sorted(ts_files):
            witness = probe.ts_witness(p, pool)
            if not saddle_ok and witness is not None:
                saddle_ok = True
                chk.evidence_used.extend(dict.fromkeys([p, witness]))
                break
        if not irc_ok:
            from_binding = bmap.get(edge.from_node)
            to_binding = bmap.get(edge.to_node)
            from_files = (
                list(from_binding.bound_files)
                if from_binding and from_binding.matched else []
            )
            to_files = (
                list(to_binding.bound_files)
                if to_binding and to_binding.matched else []
            )
            proof = _strict_irc_proof(probe, sorted(pool), from_files, to_files, charge,
                ts_files=ts_files,
                details=chk.notes,
                product_smiles=next(node.smiles for node in graph.nodes if node.id == edge.to_node),
                reactant_smiles=next(node.smiles for node in graph.nodes if node.id == edge.from_node))
            if proof is not None:
                irc_ok = True
                saddle_ok = True
                chk.evidence_used, details = proof
                chk.notes.extend(details)
        chk.covered = saddle_ok and irc_ok
        if not saddle_ok:
            chk.notes.append(
                "no first-order saddle (exactly one imaginary frequency) "
                "among bound evidence"
            )
        if not irc_ok:
            chk.notes.append(
                "no same-TS bidirectional IRC whose outer frames are connected by native "
                "converged optimization logs to the declared verified endpoint minima"
            )

    # TS 节点随边覆盖：至少一条 accessible 的边经由它且被覆盖；否则必须自我声明豁免
    for node in graph.nodes:
        if node.role != NodeRole.TRANSITION_STATE:
            continue
        chk = ElementCheck(element_id=node.id, kind="transition_state")
        report.checks.append(chk)
        covering = [
            e.id for e in graph.edges
            if e.via == node.id and e.accessible and edge_checks[e.id].covered
        ]
        if covering:
            chk.bound = True
            chk.covered = True
        elif not node.accessible:
            chk.declared_inaccessible = True
            chk.covered = True
            chk.notes.append("declared inaccessible; evidence not required")
        else:
            b = bmap.get(node.id)
            chk.bound = bool(b and b.matched)
            chk.notes.append("no accessible edge through this TS is covered")

    report.passed = all(c.covered for c in report.checks)
    for c in report.checks:
        if not c.covered:
            for n in c.notes:
                report.notes.append(f"{c.kind} {c.element_id}: {n}")
    return report
```


## `cloudra/dag/evidence_ingest.py`

文件 SHA-256：`802afdb3cd39d5a583d4f1f2b7ea42c7ebccdacbd4dbf88c8a2de341e0612626`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/dag/evidence_ingest.py:14–14`

```python
logger = logging.getLogger(__name__)
```


<a id="s030"></a>

### S030 · `FileEvidenceSnapshot`

`cloudra/dag/evidence_ingest.py:17–32`

```python
class FileEvidenceSnapshot(BaseModel):
    """不可变的文件证据快照记录。"""

    model_config = ConfigDict(extra="forbid")

    original_path: str
    snapshot_path: str
    sha256: str
    file_size: int
    is_qm_log: bool = False
    engine: str | None = None
    frequencies: list[float] | None = None
    imaginary_frequencies: list[float] | None = None
    normal_modes: list[dict[str, Any]] | None = None
    final_energy_hartree: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```


<a id="s031"></a>

### S031 · `_extract_qm_log`

`cloudra/dag/evidence_ingest.py:66–80`

```python
def _extract_qm_log(path: Path) -> tuple[bool, str | None, list[float] | None, list[float] | None, float | None, list[dict[str, Any]] | None]:
    """Extract the same native facts used by tools and TS verification."""
    from cloudra.tools.core.qm_log_facts import read_qm_log

    try:
        facts = read_qm_log(path)
    except (OSError, ImportError) as exc:
        logger.debug("QM facts unavailable for %s: %s", path, exc)
        return False, None, None, None, None, None
    if facts.engine == 'unknown' and facts.parser_data is None:
        return False, None, None, None, None, None
    freqs = facts.frequencies_cm
    imaginary = [freq for freq in freqs if freq < 0] if freqs is not None else None
    return (True, facts.engine if facts.engine != 'unknown' else None,
            freqs, imaginary, facts.electronic_energy_hartree, None)
```


<a id="s032"></a>

### S032 · `snapshot_evidence_file`

`cloudra/dag/evidence_ingest.py:83–211`

```python
def snapshot_evidence_file(
    file_path: str | Path,
    workspace_root: str | Path,
    conversation_id: str | None = None,
) -> FileEvidenceSnapshot:
    """对工作区内证据文件进行安全沙箱检查、sha256 签名与不可变快照复制。"""
    root = Path(workspace_root).expanduser().resolve(strict=True)
    p = Path(file_path).expanduser()

    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (root / p).resolve()

    if resolved.is_symlink():
        raise ValueError(f"Symlinks are not allowed as evidence: {file_path}")

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes workspace boundary: {file_path}") from exc

    if not resolved.exists():
        raise FileNotFoundError(f"Evidence file does not exist: {file_path}")
    if not resolved.is_file():
        raise ValueError(f"Evidence path is not a regular file: {file_path}")

    data = resolved.read_bytes()
    sha256_hex = hashlib.sha256(data).hexdigest()
    file_size = len(data)

    evidence_dir = root / ".cloudra" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    is_qm, engine, freqs, imag_freqs, energy, normal_modes = _extract_qm_log(resolved)
    sidecars = []
    irc_endpoints = None
    if engine == "orca":
        from cloudra.tools.core import orca_frames
        try:
            orca_frames.extract_irc(str(resolved))
        except ValueError:
            pass
        else:
            irc_endpoints = orca_frames.extract_irc_endpoints(str(resolved))
            if not any(endpoint.get("geometry_ref") for endpoint in irc_endpoints.values()):
                raise ValueError(
                    "ORCA IRC output has no associated endpoint geometries. Submit the original IRC log "
                    "from the compute job directory with its native endpoint/trajectory files; "
                    "do not copy or rename the log alone. The evidence snapshot archives the bundle automatically."
                )
            for endpoint in irc_endpoints.values():
                if endpoint.get("geometry_ref"):
                    sidecar = Path(endpoint["geometry_ref"]).resolve(strict=True)
                    sidecar.relative_to(root)
                    sidecars.append((sidecar, hashlib.sha256(sidecar.read_bytes()).hexdigest()))
    elif engine == "gaussian":
        from cloudra.tools.core import gaussian_frames, orca_frames

        try:
            _, irc_meta = gaussian_frames.extract_irc(str(resolved))
        except ValueError:
            pass
        else:
            archived = orca_frames._archived_irc_endpoints(str(resolved))
            # Gaussian's real outer frames live in the hashed native log;
            # the shared archive retains binding without inventing XYZ files.
            irc_endpoints = archived or {
                direction: {"geometry_ref": None, "origin": "native_log",
                            "converged": irc_meta.get(f"{direction}_converged")}
                for direction in ("forward", "backward")
            }
    metadata = {}
    from cloudra.services.ts_pipeline_context import pipeline_database
    from cloudra.services.ts_pipeline_store import atom_binding_for_log
    atom_binding = irc_endpoints['forward'].get('atom_binding') if irc_endpoints else None
    if atom_binding is None:
        atom_binding = atom_binding_for_log(pipeline_database(), resolved, root)
    if atom_binding is not None:
        metadata['atom_binding'] = atom_binding
    if irc_endpoints is not None:
        manifest = {"log_sha256": sha256_hex, "endpoints": {}}
        if atom_binding is not None:
            manifest["atom_binding"] = atom_binding
        for direction, endpoint in irc_endpoints.items():
            original = endpoint.get("geometry_ref")
            match = next(((p, h) for p, h in sidecars if str(p) == original), None)
            manifest["endpoints"][direction] = {
                "filename": match[0].name if match else None,
                "sha256": match[1] if match else None,
                "origin": endpoint.get("origin"), "converged": endpoint.get("converged"),
            }
        bundle_hash = hashlib.sha256(json.dumps(manifest).encode()).hexdigest()
        evidence_dir = evidence_dir / bundle_hash
        evidence_dir.mkdir(parents=True, exist_ok=True)
        metadata["irc_sidecars"] = []
        for original, digest in sidecars:
            archived = evidence_dir / original.name
            if not archived.exists():
                shutil.copy2(original, archived)
            metadata["irc_sidecars"].append({"snapshot_path": str(archived), "sha256": digest})
        manifest_path = evidence_dir / "irc_endpoints.json"
        if not manifest_path.exists():
            manifest_path.write_text(json.dumps(manifest))
        metadata["irc_manifest"] = {"snapshot_path": str(manifest_path),
                                    "sha256": hashlib.sha256(json.dumps(manifest).encode()).hexdigest()}
    snapshot_filename = f"{sha256_hex[:16]}_{resolved.name}"
    snapshot_path = evidence_dir / snapshot_filename
    if not snapshot_path.exists():
        snapshot_path.write_bytes(data)
    if hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != sha256_hex:
        raise ValueError('Evidence snapshot contents differ from their recorded hash.')
    if hashlib.sha256(resolved.read_bytes()).hexdigest() != sha256_hex:
        raise ValueError('Evidence file changed during snapshot; submit the settled file again.')
    # Parse the archived bytes rather than mutable source contents.
    is_qm, engine, freqs, imag_freqs, energy, normal_modes = _extract_qm_log(snapshot_path)

    return FileEvidenceSnapshot(
        original_path=str(resolved),
        snapshot_path=str(snapshot_path),
        sha256=sha256_hex,
        file_size=file_size,
        is_qm_log=is_qm,
        engine=engine,
        frequencies=freqs,
        imaginary_frequencies=imag_freqs,
        normal_modes=normal_modes,
        final_energy_hartree=energy,
        metadata={"filename": resolved.name, **metadata},
    )
```


<a id="s033"></a>

### S033 · `validate_ts_mode`

`cloudra/dag/evidence_ingest.py:214–271`

```python
def validate_ts_mode(
    freqs: list[float] | None,
    normal_modes: list[dict[str, Any]] | None = None,
    description: str = "",
    imaginary_freqs: list[float] | None = None,
) -> TSValidationResult:
    """只检查恰好一个虚频；不验证优化、反应坐标或端点身份。"""
    has_freq_data = (freqs is not None and len(freqs) > 0) or (
        imaginary_freqs is not None and len(imaginary_freqs) > 0
    )
    if not has_freq_data:
        return TSValidationResult(
            frequency_count_valid=False,
            frequency_data_present=False,
            n_imag=0,
            imaginary_frequencies=[],
            message=(
                "No frequency data available in the provided calculation output; the transition "
                "state is UNVERIFIED (submit a freq job for this structure)."
            ),
        )

    if imaginary_freqs is not None:
        imag = imaginary_freqs
    else:
        imag = [f for f in (freqs or []) if f < 0]
    n_imag = len(imag)

    if n_imag == 1:
        msg = f"Imaginary-frequency count criterion met: exactly 1 imaginary frequency ({imag[0]:.1f} cm⁻¹)."
        if description:
            msg += f" Submitted mode description (not verified): {description}."
        return TSValidationResult(
            frequency_count_valid=True,
            frequency_data_present=True,
            n_imag=1,
            imaginary_frequencies=imag,
            mode_matched=False,
            message=msg,
        )
    elif n_imag == 0:
        return TSValidationResult(
            frequency_count_valid=False,
            frequency_data_present=True,
            n_imag=0,
            imaginary_frequencies=[],
            mode_matched=False,
            message="Zero imaginary frequencies found; the structure is a local minimum, not a transition state saddle point.",
        )
    else:
        return TSValidationResult(
            frequency_count_valid=False,
            frequency_data_present=True,
            n_imag=n_imag,
            imaginary_frequencies=imag,
            mode_matched=False,
            message=f"Found {n_imag} imaginary frequencies ({imag}); this indicates a higher-order saddle point.",
        )
```


## `cloudra/dag/file_science.py`

文件 SHA-256：`cdb202ece7660a9c08ee48a3e827172793a8913dfc92947d481b048b45203d7a`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/dag/file_science.py:34–34`

```python
_SCIENCE_CACHE_LOCK = threading.Lock()
```


`cloudra/dag/file_science.py:35–35`

```python
_SCIENCE_CACHE: OrderedDict[str, tuple[dict, int]] = OrderedDict()
```


`cloudra/dag/file_science.py:36–36`

```python
_SCIENCE_CACHE_BYTES = 4 * 1024 * 1024
```


<a id="s034"></a>

### S034 · `ScientificCheck`

`cloudra/dag/file_science.py:27–31`

```python
class ScientificCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['passed', 'failed', 'incomplete']
    detail: str
    next_action: str = ''
```


<a id="s035"></a>

### S035 · `_science_cache_key`

`cloudra/dag/file_science.py:39–92`

```python
def _science_cache_key(store, graph, target_id, *, irc_files, workspace_root, evidence_refs, endpoint_refs):
    """Version only bound immutable dependencies; mutable workflow logs stay fresh."""
    from cloudra.dag.models import GraphRef

    element = next((n for n in graph.nodes if n.node_id == target_id), None)
    if element is None:
        element = next((e for e in graph.edges if e.edge_id == target_id), None)
    if element is None:
        return None
    elements = [element]
    if hasattr(element, 'source_node_id'):
        elements.extend(node for node in graph.nodes
                        if node.node_id in (element.source_node_id, element.target_node_id))
    refs = []
    for item in elements:
        if item is element and evidence_refs is not None:
            refs.extend(evidence_refs)
        else:
            refs.extend([*item.refs, *[stage.ref for stage in item.stages
                                     if stage.ref is not None and stage.status.value == 'supported']])
    refs.extend(GraphRef.model_validate(ref) for ref in (endpoint_refs or {}).values())
    payloads = []
    for ref in dict.fromkeys(refs):
        try:
            payload = store.resolve_evidence(ref)
        except InvalidGraphReference:
            return None
        if not isinstance(payload, dict):
            continue
        if 'snapshot_path' not in payload:
            if (payload.get('arguments') or {}).get('log_path'):
                return None
            continue
        payloads.append(payload)
    payloads.extend((irc_files or {}).values())
    versions = {}
    for payload in payloads:
        snap = FileEvidenceSnapshot.model_validate(payload)
        paths = [snap.snapshot_path, *[item['snapshot_path'] for item in snap.metadata.get('irc_sidecars', [])]]
        if snap.metadata.get('irc_manifest'):
            paths.append(snap.metadata['irc_manifest']['snapshot_path'])
        for raw in paths:
            path = Path(raw)
            try:
                stat = path.stat()
            except OSError:
                versions[str(path)] = None
            else:
                versions[str(path)] = (stat.st_dev, stat.st_ino, stat.st_mode, stat.st_size,
                                       stat.st_mtime_ns, stat.st_ctime_ns)
    payload = [graph.model_dump(mode='json'), target_id, str(workspace_root), payloads,
               [ref.model_dump(mode='json') for ref in evidence_refs] if evidence_refs is not None else None,
               irc_files, endpoint_refs, versions]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
```


<a id="s036"></a>

### S036 · `_qm_data`

`cloudra/dag/file_science.py:95–101`

```python
def _qm_data(path, parsed=None):
    if parsed is None:
        return _extract_qm_log(Path(path))
    key = str(path)
    if key not in parsed:
        parsed[key] = _extract_qm_log(Path(path))
    return parsed[key]
```


<a id="s037"></a>

### S037 · `_logs`

`cloudra/dag/file_science.py:104–161`

```python
def _logs(store, element, workspace_root=None, *, atom_bindings=None, parsed=None):
    """Use bound immutable file snapshots; never substitute a workflow verdict."""
    logs, problems = [], []
    refs = list(element.refs) + [s.ref for s in element.stages if s.ref is not None and s.status.value == 'supported']
    for ref in refs:
        try:
            payload = store.resolve_evidence(ref)
        except InvalidGraphReference as exc:
            problems.append(str(exc))
            continue
        if not isinstance(payload, dict):
            continue
        if 'snapshot_path' not in payload:
            raw = (payload.get('arguments') or {}).get('log_path')
            if not isinstance(raw, str) or not raw:
                continue
            path = Path(raw)
            if not path.is_absolute():
                if workspace_root is None:
                    problems.append(f'Relative stage log needs its workspace: {raw}')
                    continue
                path = Path(workspace_root) / path
            if not path.is_file():
                problems.append(f'Bound stage log is missing: {path}')
                continue
            is_qm, engine, freqs, imag, energy, modes = _qm_data(path, parsed)
            from cloudra.services.ts_pipeline_context import pipeline_database
            from cloudra.services.ts_pipeline_store import atom_binding_for_log
            binding = atom_binding_for_log(pipeline_database(), path, workspace_root or path.parent)
            snap = FileEvidenceSnapshot(original_path=str(path), snapshot_path=str(path),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), file_size=path.stat().st_size,
                is_qm_log=is_qm, engine=engine, frequencies=freqs,
                imaginary_frequencies=imag, final_energy_hartree=energy, normal_modes=modes,
                metadata={'atom_binding': binding} if binding else {})
        else:
            snap = FileEvidenceSnapshot.model_validate(payload)
        path = Path(snap.snapshot_path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != snap.sha256:
            problems.append(f'Immutable evidence is missing or changed: {path}')
            continue
        artifacts = [*snap.metadata.get("irc_sidecars", []),
                     *([snap.metadata["irc_manifest"]] if snap.metadata.get("irc_manifest") else [])]
        if any(not Path(item["snapshot_path"]).is_file() or
               hashlib.sha256(Path(item["snapshot_path"]).read_bytes()).hexdigest() != item["sha256"]
               for item in artifacts):
            problems.append(f'Immutable IRC endpoint evidence is missing or changed: {path}')
            continue
        if str(path) in logs:
            continue
        engine = snap.engine
        parser = {'orca': orca_frames, 'gaussian': gaussian_frames, 'xtb': xtb_frames}.get(engine)
        if parser is None or not (parser.normal_termination(path.read_text(errors='replace')) if engine == 'xtb' else normal_log(path)):
            problems.append(f'No usable normally terminated calculation segment in {path}; frequency and final geometry must describe the same calculation structure.')
            continue
        logs.append(str(path))
        if atom_bindings is not None and snap.metadata.get('atom_binding'):
            atom_bindings[str(path)] = snap.metadata['atom_binding']
    return logs, problems
```


<a id="s038"></a>

### S038 · `_final_geometry`

`cloudra/dag/file_science.py:164–173`

```python
def _final_geometry(path):
    from cloudra.tools.core.irc_path import parse_xyz
    from cloudra.tools.core.qm_engine import detect_qm_engine

    if Path(path).suffix.lower() == '.xyz':
        return parse_xyz(Path(path).read_text(errors='replace'))

    if detect_qm_engine(str(path)) == 'xtb':
        return parse_xyz(xtb_frames.final_xyz_from_text(Path(path).read_text(errors='replace')))
    return last_geometry(path, frames_for(path)[0])
```


<a id="s039"></a>

### S039 · `validate_frequency_geometry`

`cloudra/dag/file_science.py:176–192`

```python
def validate_frequency_geometry(opt_snap, freq_snap):
    """Require the same coordinates up to atom order, translation and rotation.

    The error bound is the rounding error of two six-decimal XYZ records,
    using the existing XYZ output precision; it is not a conformer/RMSD cutoff.
    Reflections and changes of molecular geometry are not rigid rotations.
    """
    from cloudra.tools.core.irc_path import same_geometry

    if opt_snap.sha256 == freq_snap.sha256:
        return
    geometries = [_final_geometry(s.snapshot_path) for s in (opt_snap, freq_snap)]
    if any(geo is None for geo in geometries):
        raise ValueError('Optimization/frequency identity requires final geometry in both files.')
    if not same_geometry(*geometries):
        raise ValueError('Optimization and frequency files contain different geometries; '
                         'submit the frequency calculation for the delivered optimized structure.')
```


<a id="s040"></a>

### S040 · `_geometry_species`

`cloudra/dag/file_science.py:195–247`

```python
def _geometry_species(path: str, smiles: str | list[str], *, diagnostics: list[str] | None = None) -> bool:
    """Match the actual final structure using the existing RDKit bond perception.

    A SMILES annotation alone is not molecular evidence. Failure to perceive
    bonds remains missing identity evidence, never an inferred match.
    """
    from collections import Counter

    try:
        from rdkit import Chem
        from rdkit.Chem import rdDetermineBonds
    except ImportError as exc:
        raise RuntimeError(
            "Species geometry identity requires RDKit; install or repair cloudra[chem] "
            "and re-submit the evidence."
        ) from exc

    from cloudra.tools.core.irc_path import xyz_block

    expected = Chem.MolFromSmiles(chemical_smiles(smiles))
    if expected is None:
        raise ValueError(f"Invalid species SMILES: {smiles}")
    for atom in expected.GetAtoms():
        atom.SetAtomMapNum(0)
    expected = Chem.AddHs(expected)
    geometry = _final_geometry(path)
    if geometry is None:
        raise ValueError(f"No final geometry in {path}")
    symbols, positions = geometry
    counts = Counter(atom.GetSymbol() for atom in expected.GetAtoms())
    if Counter(symbols) != counts:
        if diagnostics is not None:
            diagnostics.append(f'Geometry composition mismatch for declared {smiles}: '
                               f'expected {dict(counts)}, observed {dict(Counter(symbols))}.')
        return False
    actual = Chem.MolFromXYZBlock(xyz_block(symbols, positions))
    if actual is None:
        raise ValueError(f"Cannot read final geometry in {path}")
    rdDetermineBonds.DetermineBonds(actual, charge=Chem.GetFormalCharge(expected))
    # Compare both full explicit-H graphs. RemoveHs preserves neighbours of
    # non-tetrahedral stereocentres, so comparing it with an implicit-H query
    # incorrectly rejects e.g. a correctly perceived five-coordinate P ring.
    # Unspecified stereochemistry permits either configuration. Explicit
    # stereochemistry remains part of the query and must match.
    matches = (actual.GetNumAtoms() == expected.GetNumAtoms()
               and actual.GetNumBonds() == expected.GetNumBonds()
               and actual.HasSubstructMatch(expected, useChirality=True))
    if not matches and diagnostics is not None:
        diagnostics.append(f'Geometry identity mismatch: declared {smiles}; '
                           f'perceived {Chem.MolToSmiles(actual)}. '
                           'Check the optimized connectivity, charge and bond orders; '
                           'a mismatch is not proof of a perception failure.')
    return matches
```


<a id="s041"></a>

### S041 · `_species_minimum_check`

`cloudra/dag/file_science.py:250–276`

```python
def _species_minimum_check(smiles, logs, problems, *, parsed=None):
    if not smiles:
        return ScientificCheck(status='incomplete', detail='Species identity is not declared.',
            next_action='Declare the species SMILES before submitting minimum evidence.')
    minimum_logs = [p for p in logs if _qm_data(p, parsed)[3] == []]
    components = species_smiles(smiles)
    covered = set()
    for path in minimum_logs:
        for identity in dict.fromkeys(components):
            try:
                matches = _geometry_species(path, identity, diagnostics=problems)
            except (ValueError, RuntimeError) as exc:
                problems.append(str(exc))
                continue
            if matches:
                covered.add(identity)
    missing = sorted(set(components) - covered)
    if not missing:
        return ScientificCheck(status='passed', detail=(
            'All separated species have matching normally terminated zero-imaginary-frequency geometries; '
            'this does not verify a complex minimum or a combined energy reference.'
            if len(components) > 1 else
            'Normally terminated zero-imaginary-frequency geometry matches the complete species.'))
    return ScientificCheck(status='incomplete',
        detail='Missing matching minimum evidence for: ' + ', '.join(missing) + '. ' + ' '.join(dict.fromkeys(problems)),
        next_action='Submit matching normally terminated frequency logs for each declared species; a dot-connected complex requires its own minimum. '
                    'Keep IRC and complex-energy requirements separate; unsuccessful searches do not establish nonexistence.')
```


<a id="s042"></a>

### S042 · `_optimization_converged`

`cloudra/dag/file_science.py:279–286`

```python
def _optimization_converged(path: str, engine: str | None) -> bool | None:
    if engine in {'orca', 'gaussian'}:
        from cloudra.tools.core.qm_log_facts import read_qm_log

        return read_qm_log(path).opt_converged
    if engine == 'xtb':
        return xtb_frames.opt_converged(Path(path).read_text(errors='replace'))
    return None
```


<a id="s043"></a>

### S043 · `_ts_optimization_check`

`cloudra/dag/file_science.py:289–316`

```python
def _ts_optimization_check(logs: list[str], *, parsed=None) -> ScientificCheck:
    frequency_logs = [p for p in logs if len(_qm_data(p, parsed)[3] or []) == 1]
    problems = []
    failed = False
    for path in logs:
        engine = _qm_data(path, parsed)[1]
        converged = _optimization_converged(path, engine)
        if converged is False:
            failed = True
            problems.append(f'Optimization did not converge in {path}.')
            continue
        if converged is not True:
            continue
        for frequency in frequency_logs:
            def snapshot(p):
                return FileEvidenceSnapshot(original_path=p, snapshot_path=p,
                    sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest(), file_size=Path(p).stat().st_size)
            try:
                validate_frequency_geometry(snapshot(path), snapshot(frequency))
            except ValueError as exc:
                failed = True
                problems.append(str(exc))
                continue
            return ScientificCheck(status='passed',
                detail='Native optimization convergence and one-imaginary-frequency evidence for the same geometry passed; reaction direction is checked separately.')
    return ScientificCheck(status='failed' if failed else 'incomplete',
        detail='Native converged optimization with matching first-order-saddle frequency evidence required. ' + ' '.join(dict.fromkeys(problems)),
        next_action='Submit the normally terminated converged optimization and its matching frequency log; a frequency-only calculation is not optimization evidence.')
```


<a id="s044"></a>

### S044 · `file_scientific_checks`

`cloudra/dag/file_science.py:319–339`

```python
def file_scientific_checks(store, graph, target_id: str, *, irc_files=None, workspace_root=None, evidence_refs=None, endpoint_refs=None, use_cache=False) -> dict[str, dict]:
    """Reuse derived prompt checks only; submit/review/delivery always verify afresh."""
    options = dict(irc_files=irc_files, workspace_root=workspace_root,
                   evidence_refs=evidence_refs, endpoint_refs=endpoint_refs)
    key = _science_cache_key(store, graph, target_id, **options) if use_cache else None
    if key is not None:
        with _SCIENCE_CACHE_LOCK:
            cached = _SCIENCE_CACHE.get(key)
            if cached is not None:
                _SCIENCE_CACHE.move_to_end(key)
                return deepcopy(cached[0])
    checks = _file_scientific_checks(store, graph, target_id, **options)
    if key is not None and _science_cache_key(store, graph, target_id, **options) == key:
        size = len(json.dumps(checks).encode())
        if size <= _SCIENCE_CACHE_BYTES:
            with _SCIENCE_CACHE_LOCK:
                _SCIENCE_CACHE[key] = deepcopy(checks), size
                _SCIENCE_CACHE.move_to_end(key)
                while len(_SCIENCE_CACHE) > 64 or sum(item[1] for item in _SCIENCE_CACHE.values()) > _SCIENCE_CACHE_BYTES:
                    _SCIENCE_CACHE.popitem(last=False)
    return checks
```


<a id="s045"></a>

### S045 · `_file_scientific_checks`

`cloudra/dag/file_science.py:342–445`

```python
def _file_scientific_checks(store, graph, target_id: str, *, irc_files=None, workspace_root=None, evidence_refs=None, endpoint_refs=None) -> dict[str, dict]:
    element = next((n for n in graph.nodes if n.node_id == target_id), None)
    is_edge = element is None
    if is_edge:
        element = next((e for e in graph.edges if e.edge_id == target_id), None)
    if element is None:
        raise InvalidGraphReference(f"Delivery target {target_id!r} no longer exists in the current graph.")
    if evidence_refs is not None:
        element = element.model_copy(update={'refs': list(evidence_refs), 'stages': []})
    atom_bindings = {}
    parsed = {}
    logs, problems = _logs(store, element, workspace_root, atom_bindings=atom_bindings, parsed=parsed)
    if is_edge and endpoint_refs:
        from cloudra.dag.models import GraphRef
        refs = [GraphRef.model_validate(ref) for ref in endpoint_refs.values()]
        endpoint_logs, endpoint_problems = _logs(store, element.model_copy(update={'refs': refs, 'stages': []}), workspace_root, parsed=parsed)
        logs = [path for path in logs if path not in endpoint_logs]
        problems.extend(endpoint_problems)
    if not is_edge:
        return {'geometry': _species_minimum_check(element.smiles, logs, problems, parsed=parsed).model_dump()}
    frequencies = [_qm_data(p, parsed)[3] for p in logs]
    expected = 1 if is_edge else 0
    passed = any(f is not None and len(f) == expected for f in frequencies)
    status = 'passed' if passed else 'failed' if any(f is not None for f in frequencies) else 'incomplete'
    frequency_check = ScientificCheck(status=status,
        detail=f'Native normal termination and exactly {expected} imaginary frequencies required. ' + ' '.join(problems),
        next_action='' if passed else f'Submit a normally terminated frequency log showing {expected} imaginary frequencies; repair the calculation or supply missing evidence.')
    checks = {'frequency' if is_edge else 'geometry': frequency_check}
    if is_edge:
        checks['ts_opt'] = _ts_optimization_check(logs, parsed=parsed)
        source = next((n for n in graph.nodes if n.node_id == element.source_node_id), None)
        target = next((n for n in graph.nodes if n.node_id == element.target_node_id), None)
        source_logs, _ = _logs(store, source, workspace_root, parsed=parsed) if source else ([], [])
        target_logs, _ = _logs(store, target, workspace_root, parsed=parsed) if target else ([], [])
        def endpoint_candidates(key, node, candidates):
            node_candidates = candidates
            if endpoint_refs and key in endpoint_refs:
                from cloudra.dag.models import GraphRef
                ref = GraphRef.model_validate(endpoint_refs[key])
                if ref not in element.refs:
                    return []
                candidates, errors = _logs(store, element.model_copy(update={'refs': [ref], 'stages': []}), workspace_root, parsed=parsed)
                problems.extend(errors)
                # An explicit minimum fixes the final geometry, while a
                # separate bound Opt log supplies its native IRC starting frame.
                from cloudra.tools.core.irc_path import same_geometry
                minima = [_final_geometry(path) for path in candidates if _qm_data(path, parsed)[3] == []]
                candidates = list(dict.fromkeys([*candidates, *[path for path in node_candidates
                    if any(same_geometry(_final_geometry(path), minimum) for minimum in minima)]]))
            verified = []
            for path in candidates:
                try:
                    data = _qm_data(path, parsed)
                    if (node and node.smiles
                            and (data[3] == [] or _optimization_converged(path, data[1]) is True)
                            and any(_geometry_species(path, identity, diagnostics=problems)
                                    for identity in species_smiles(node.smiles))):
                        verified.append(path)
                except (ValueError, RuntimeError) as exc:
                    problems.append(str(exc))
            return verified
        source_logs = endpoint_candidates('endpoint_b', source, source_logs)
        target_logs = endpoint_candidates('endpoint_a', target, target_logs)
        charge = next((binding['charge'] for binding in atom_bindings.values() if 'charge' in binding), 0)
        if source_logs and source and source.smiles:
            from rdkit import Chem
            molecule = Chem.MolFromSmiles(chemical_smiles(source.smiles))
            if molecule is not None:
                charge = Chem.GetFormalCharge(molecule)
        details = list(problems)
        irc_passed = False
        for path in logs:
            try:
                engine = _qm_data(path, parsed)[1]
                if engine == 'orca':
                    orca_frames.extract_irc(path)
                elif engine == 'gaussian':
                    gaussian_frames.extract_irc(path)
                else:
                    continue
            except ValueError:
                continue
            try:
                irc_passed, reason = verify_short_irc_direction(path, logs, target_logs, source_logs,
                    charge=charge, atom_bindings=atom_bindings, product_smiles=target.smiles if target else None,
                    reactant_smiles=source.smiles if source else None)
                details.extend(reason)
            except Exception as exc:
                details.append(f'IRC direction proof could not be evaluated: {exc}')
            if irc_passed:
                details = reason
                break
        if not irc_passed and irc_files and irc_files.get('irc_forward_file') and irc_files.get('irc_reverse_file'):
            forward = FileEvidenceSnapshot.model_validate(irc_files['irc_forward_file']).snapshot_path
            reverse = FileEvidenceSnapshot.model_validate(irc_files['irc_reverse_file']).snapshot_path
            if forward in logs and reverse in logs:
                irc_passed, reason = verify_short_irc_pair(forward, reverse, logs, target_logs, source_logs,
                    charge=charge, atom_bindings=atom_bindings, product_smiles=target.smiles if target else None,
                    reactant_smiles=source.smiles if source else None)
                details = reason if irc_passed else [*details, *reason]
        checks['short_irc'] = ScientificCheck(status='passed' if irc_passed else 'incomplete',
            detail=' '.join(details) or ('Native IRC outer-frame optimization to the declared verified minima passed.' if irc_passed else 'No usable bound bidirectional IRC evidence.'),
            next_action='' if irc_passed else 'Submit same-TS bidirectional IRC and native Opt/Freq logs connecting each outer frame to its declared minimum; geometric interval checks are advisory. Separated products need each declared species minimum. Full IRC convergence is not required.')
    return {stage: check.model_dump() for stage, check in checks.items()}
```


## `cloudra/infra/compute_utils.py`

文件 SHA-256：`369cf5e6fcd2d4505195a5840e307a7c5069ca34b92088a520523f3ce4062265`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/infra/compute_utils.py:34–34`

```python
ORCA_NEB_GEOMETRY_INPUTS = frozenset({'neb_end_xyzfile', 'neb_ts_xyzfile'})
```


<a id="s046"></a>

### S046 · `_default_calculator_path`

`cloudra/infra/compute_utils.py:144–146`

```python
def _default_calculator_path() -> str:
    """返回项目内置的 calculator.sh 绝对路径。"""
    return str(Path(__file__).resolve().parents[1] / "calculator.sh")
```


<a id="s047"></a>

### S047 · `check_calculator_script`

`cloudra/infra/compute_utils.py:172–199`

```python
def check_calculator_script(workdir: str) -> tuple[bool, str]:
    """检查 calculator.sh 是否可用。

    工作目录下的 calculator.sh（按任务目录定制）只在
    ``compute.allow_local_calculator`` 显式开启时生效——工作目录是 agent
    可写区，默认忽略可防止 agent 放置的同名脚本被提升为计算执行入口；
    默认直接使用项目内置的 calculator.sh。
    Windows/Android 等没有 shebang 执行语义的环境需要同时找到 bash。

    Returns:
        (is_ok, script_path): is_ok 为 False 时 script_path 为空字符串。
    """
    from cloudra.infra.config import get_config

    bash_path = get_bash_path()
    if bash_path is None:
        return False, ""

    if get_config().compute.allow_local_calculator:
        local_script = os.path.join(workdir, "calculator.sh")
        if os.access(local_script, os.X_OK):
            return True, local_script

    default_script = _default_calculator_path()
    if os.access(default_script, os.X_OK):
        return True, default_script

    return False, ""
```


<a id="s048"></a>

### S048 · `build_calculator_cmd`

`cloudra/infra/compute_utils.py:202–230`

```python
def build_calculator_cmd(
    input_file: str,
    job_type: str,
    *,
    xtb_params: Optional[XtbParams] = None,
) -> tuple[bool, list[str], str]:
    """构建 calculator 子进程命令。

    xtb 作业必须带 ``xtb_params``（compute_jobs 行是唯一事实来源），其
    cli_args() 追加在 job_type 之后由 calculator.sh 翻译成 xtb CLI flag。

    Returns:
        (is_ok, cmd, message): is_ok 为 False 时 cmd 为空列表，message 为错误信息。
    """
    workdir = os.path.dirname(input_file)
    bash_path = get_bash_path()
    ok, script_path = check_calculator_script(workdir)
    if bash_path is None or not ok:
        return False, [], (
            f"calculator.sh or a usable bash was not found; confirm the script is installed and bash is on PATH. "
            f"The built-in script is {_default_calculator_path()}; a custom calculator.sh in the working "
            f"directory {workdir} is only honored when compute.allow_local_calculator is enabled."
        )
    cmd = [bash_path, script_path, input_file, job_type]
    if job_type == "xtb":
        cmd.extend((xtb_params or XtbParams()).cli_args())
    elif job_type == "chem_task":
        cmd.extend([sys.executable, str(Path(__file__).resolve().parents[2])])
    return True, cmd, ""
```


<a id="s049"></a>

### S049 · `get_log_path`

`cloudra/infra/compute_utils.py:355–367`

```python
def get_log_path(input_file: str, job_type: str = "gaussian") -> str:
    """根据输入文件路径推导计算软件生成的日志文件路径。

    Gaussian 默认生成与输入文件同名但后缀为 .log 的文件；
    ORCA、CP2K 生成 .out；xtb 主输出由 calculator.sh 重定向到 .out；
    VASP 的日志命名不固定，默认仍按 .out 处理。
    """
    path = Path(input_file)
    if job_type == "chem_task":
        return input_file
    if job_type == "gaussian":
        return str(path.with_suffix(".log"))
    return str(path.with_suffix(".out"))
```


<a id="s050"></a>

### S050 · `_execution_receipt`

`cloudra/infra/compute_utils.py:370–371`

```python
def _execution_receipt(input_file: str, task_id: int) -> Path:
    return Path(input_file).parent / '.cloudra' / f'execution-{task_id}'
```


<a id="s051"></a>

### S051 · `_orca_geometry_output_paths`

`cloudra/infra/compute_utils.py:374–421`

```python
def _orca_geometry_output_paths(input_file: str, *, protect_dependencies: bool = True) -> set[Path]:
    """Known native IRC outputs for the input stem and explicit %base prefixes."""
    source = Path(input_file)
    prefixes = {source.with_suffix('')}
    dependencies = set()
    in_neb = False
    text = source.read_text(encoding='utf-8', errors='replace') if source.is_file() else ''
    for line in text.splitlines():
        stripped = line.strip()
        first = stripped.split(maxsplit=1)[0].casefold() if stripped else ''
        if first == '%neb':
            in_neb = True
        if not (first in {'%base', '%neb', '*', '*xyzfile'} or in_neb):
            continue
        lexer = shlex.shlex(stripped, posix=True, punctuation_chars='=')
        lexer.whitespace_split = True
        lexer.commenters = '#'
        try:
            tokens = list(lexer)
        except ValueError:
            continue  # Native syntax is advisory; never fix a malformed solver string.
        neb_tokens = tokens[1:] if tokens and tokens[0].casefold() == '%neb' else tokens
        if in_neb and len(neb_tokens) >= 2 and neb_tokens[0].casefold() in ORCA_NEB_GEOMETRY_INPUTS:
            values = [token for token in neb_tokens[1:] if token != '=']
            if values:
                dependencies.add((source.parent / values[0]).resolve())
        if any(token.casefold() == 'end' for token in tokens):
            in_neb = False
        if tokens and tokens[0].casefold() == '%base':
            values = [token for token in tokens[1:] if token != '=']
            if values:
                prefixes.add((source.parent / values[0]).resolve())
        elif tokens and tokens[0].casefold() in {'*', '*xyzfile'}:
            geometry = tokens[1:] if tokens[0] == '*' else ['xyzfile', *tokens[1:]]
            if geometry and geometry[0].casefold() == 'xyzfile' and len(geometry) >= 4:
                dependencies.add((source.parent / geometry[3]).resolve())
    outputs = {prefix.with_name(prefix.name + suffix)
               for prefix in prefixes for suffix in ('_IRC_F.xyz', '_IRC_B.xyz', '_IRC_F_trj.xyz', '_IRC_B_trj.xyz', '_NEB-TS_converged.xyz')}
    for prefix in prefixes:
        if not prefix.parent.is_dir():
            continue
        for child in prefix.parent.iterdir():
            lead = prefix.name + '_im'
            if child.name.startswith(lead) and child.suffix == '.xyz' and child.name[len(lead):-4].isdigit():
                outputs.add(child)
    if protect_dependencies and any(output.resolve() in dependencies for output in outputs if output.exists()):
        raise ValueError('native IRC output overlaps an explicit XYZ input dependency')
    return outputs
```


<a id="s052"></a>

### S052 · `complete_execution_evidence`

`cloudra/infra/compute_utils.py:502–533`

```python
def complete_execution_evidence(input_file: str, job_type: str, task_id: int) -> str:
    """Freeze this execution's selected log and its native IRC endpoint bundle."""
    if job_type not in {'gaussian', 'orca'}:
        return resolve_log_path(input_file, job_type, task_id)
    receipt = _execution_receipt(input_file, task_id)
    metadata = receipt / 'evidence.json'
    record = json.loads(metadata.read_text()) if metadata.exists() else {}
    if record.get('log_file'):
        return record['log_file']
    native = Path(get_log_path(input_file, job_type))
    captured = Path(input_file).parent / '.cloudra' / f'calc-{task_id}.out.log'
    source = native if native.is_file() and native.stat().st_size else captured
    results = receipt / 'results'
    results.mkdir(parents=True, exist_ok=True)
    target = results / source.name
    if source.is_file():
        shutil.copy2(source, target)
        if job_type == 'orca':
            geometries = _orca_geometry_output_paths(input_file)
            record.update(input_file=input_file, job_type=job_type,
                          geometry_stems=sorted({path.name.removesuffix('_IRC_F.xyz') for path in geometries
                                                 if path.name.endswith('_IRC_F.xyz')}))
            atomic_write_json(metadata, record)
            for geometry in geometries:
                if geometry.is_file():
                    shutil.copy2(geometry, results / geometry.name)
            from cloudra.tools.core.orca_frames import snapshot_irc_endpoints

            snapshot_irc_endpoints(str(target), results)
    record['log_file'] = str(target)
    atomic_write_json(metadata, record)
    return str(target)
```


<a id="s053"></a>

### S053 · `resolve_log_path`

`cloudra/infra/compute_utils.py:536–589`

```python
def resolve_log_path(input_file: str, job_type: str = "gaussian", task_id: int | None = None) -> str:
    """解析计算作业的真实日志路径——query_compute_job 与完成通知统一走这里（GH #20）。

    预测路径（引擎惯例后缀）常与 guard 实际解析的日志不一致：部分引擎不自写
    日志文件（如本机 ORCA 6.1.1 macOS 构建把主输出全部写 stdout、从不落 .out），
    guard 会把 calculator stdout 捕获到 ``.cloudra/calc-<id>.out.log`` 并回退解析它，
    实际解析路径记录在 guard state json 的 ``log_file`` 字段。
    远端已有本轮 results 收据时只认收据内的原生日志/捕获，不读取旧本地证据。
    有执行收据时只认其冻结日志；尚未收尾时返回本次 capture。
    没有执行收据的已有记录仍可由其 state json 定位原来的日志。
    """
    if job_type == 'chem_task':
        return input_file
    if input_file and task_id is not None:
        workdir = Path(input_file).parent
        receipt = _execution_receipt(input_file, task_id)
        try:
            evidence = json.loads((receipt / 'evidence.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            evidence = None
        if evidence is not None or receipt.is_dir():
            # An execution receipt never falls back to a later shared output.
            if (evidence or {}).get('log_file'):
                return evidence['log_file']
            native = Path(get_log_path(input_file, job_type))
            if evidence is not None and native.is_file() and native.stat().st_size:
                return str(native)
            return str(workdir / '.cloudra' / f'calc-{task_id}.out.log')
        remote_results = workdir / '.cloudra' / f'remote-{task_id}' / 'results'
        if remote_results.is_dir():
            # A remote execution receipt must never fall back to evidence left
            # by a previous local/remote run in the shared input directory.
            native = remote_results / Path(get_log_path(input_file, job_type)).name
            if native.is_file() and native.stat().st_size:
                return str(native)
            captured = remote_results / '.cloudra' / f'calc-{task_id}.out.log'
            if captured.is_file():
                return str(captured)
            return str(native)
        try:
            recorded = json.loads(
                (workdir / f"state_{task_id}.json").read_text(encoding="utf-8")
            ).get("log_file")
        except (OSError, ValueError):
            recorded = None
        if recorded and Path(recorded).is_file():
            return str(recorded)
        native = Path(get_log_path(input_file, job_type=job_type))
        if job_type == 'gaussian' and native.is_file() and native.stat().st_size:
            return str(native)
        captured = workdir / ".cloudra" / f"calc-{task_id}.out.log"
        if captured.is_file():
            return str(captured)
    return get_log_path(input_file, job_type=job_type)
```


## `cloudra/infra/platform_utils.py`

文件 SHA-256：`2355ca339fb855655275d6db3cc479ad65faaafb0e3132fc191f257b13865a18`


<a id="s054"></a>

### S054 · `get_bash_path`

`cloudra/infra/platform_utils.py:27–29`

```python
def get_bash_path() -> str | None:
    """Return the absolute path to a usable ``bash`` executable, or None."""
    return shutil.which("bash")
```


## `cloudra/infra/slurm.py`

文件 SHA-256：`8acacf34265774f8d2822806765f105f1156907d5b828cb23a5267241b193d60`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/infra/slurm.py:29–29`

```python
_SBATCH_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:@+/%-")
```


`cloudra/infra/slurm.py:30–30`

```python
_MEMORY_SUFFIXES = frozenset("KMGTPkmgtp")
```


<a id="s055"></a>

### S055 · `SlurmError`

`cloudra/infra/slurm.py:41–42`

```python
class SlurmError(RuntimeError):
    pass
```


<a id="s056"></a>

### S056 · `_is_sbatch_value`

`cloudra/infra/slurm.py:52–53`

```python
def _is_sbatch_value(text: str) -> bool:
    return 1 <= len(text) <= 100 and all(char in _SBATCH_CHARS for char in text)
```


<a id="s057"></a>

### S057 · `_is_memory`

`cloudra/infra/slurm.py:56–58`

```python
def _is_memory(text: str) -> bool:
    number = text[:-1] if text and text[-1] in _MEMORY_SUFFIXES else text
    return 1 <= len(number) <= 7 and number[0] != "0" and number.isascii() and number.isdecimal()
```


<a id="s058"></a>

### S058 · `_is_time_limit`

`cloudra/infra/slurm.py:61–76`

```python
def _is_time_limit(text: str) -> bool:
    if not text.isascii():
        return False
    day, separator, clock = text.partition("-")
    if separator and (not day.isdecimal() or not 1 <= len(day) <= 3):
        return False
    parts = (clock if separator else text).split(":")
    return (
        len(parts) == 3
        and 1 <= len(parts[0]) <= 2
        and parts[0].isdecimal()
        and len(parts[1]) == 2
        and parts[1].isdecimal()
        and len(parts[2]) == 2
        and parts[2].isdecimal()
    )
```


<a id="s059"></a>

### S059 · `_is_environment_name`

`cloudra/infra/slurm.py:84–87`

```python
def _is_environment_name(text: str) -> bool:
    return text.isascii() and bool(text) and (text[0].isalpha() or text[0] == "_") and all(
        char.isalnum() or char == "_" for char in text[1:]
    )
```


<a id="s060"></a>

### S060 · `_directive`

`cloudra/infra/slurm.py:90–94`

```python
def _directive(name: str, value: object, validator: Callable[[str], bool] = _is_sbatch_value) -> str:
    text = str(value).strip()
    if not validator(text):
        raise SlurmError(f"无效的 Slurm {name}: {text!r}")
    return f"#SBATCH --{name}={text}"
```


<a id="s061"></a>

### S061 · `scheduler_setup_lines`

`cloudra/infra/slurm.py:97–126`

```python
def scheduler_setup_lines(scheduler: dict) -> list[str]:
    """batch/runner 脚本共用的环境准备行：module load + export 环境变量。

    逐项校验（modules 非空名单、变量名/值形状），非法即 SlurmError fail-loud；
    本地 Slurm batch 与远端 runner（runtime/remote_compute.py）共用一份。
    """
    lines: list[str] = []
    modules = scheduler.get("modules", [])
    if modules:
        lines.extend(
            [
                ". /etc/profile.d/modules.sh",
                shlex.join(["module", "load", *modules]),
            ]
        )
    environment = scheduler.get("environment") or {}
    if not isinstance(environment, dict):
        raise SlurmError("Slurm environment 必须是对象")
    for name, value in environment.items():
        if not isinstance(name, str) or not _is_environment_name(name):
            raise SlurmError(f"无效的 Slurm environment 变量名: {name!r}")
        if (
            not isinstance(value, str)
            or "\n" in value
            or "\r" in value
            or "\0" in value
        ):
            raise SlurmError(f"Slurm environment {name!r} 必须是单行字符串")
        lines.append(f"export {name}={shlex.quote(value)}")
    return lines
```


<a id="s062"></a>

### S062 · `build_batch_script`

`cloudra/infra/slurm.py:129–186`

```python
def build_batch_script(
    input_file: Path,
    job_type: str,
    task_id: int,
    scheduler: dict,
    *,
    xtb_params: XtbParams | None = None,
    calculator_cmd: list[str] | None = None,
    workdir: str | None = None,
) -> str:
    """生成 Slurm batch 脚本。

    ``calculator_cmd``/``workdir`` 是远端提交（runtime/remote_compute.py）的
    覆盖口：远端作业命令引用远端目录里的输入副本与随作业推送的
    calculator.sh，而不是本机解析出来的绝对路径；缺省行为不变。
    """
    if calculator_cmd is None:
        ok, calculator_cmd, message = build_calculator_cmd(
            str(input_file), job_type, xtb_params=xtb_params
        )
        if not ok:
            raise SlurmError(message)
    lines = [
        "#!/bin/bash",
        _directive("job-name", f"cloudra-{task_id}"),
        _directive("output", f"cloudra-slurm-{task_id}-%j.out"),
        _directive("error", f"cloudra-slurm-{task_id}-%j.err"),
    ]
    for key, directive_name in (
        ("partition", "partition"),
        ("account", "account"),
        ("qos", "qos"),
    ):
        value = scheduler.get(key)
        if value:
            lines.append(_directive(directive_name, value))
    if scheduler.get("time_limit"):
        lines.append(_directive("time", scheduler["time_limit"], _is_time_limit))
    if scheduler.get("cpus") is not None:
        cpus = int(scheduler["cpus"])
        if cpus < 1 or cpus > 4096:
            raise SlurmError("Slurm cpus 必须在 1..4096")
        lines.append(f"#SBATCH --cpus-per-task={cpus}")
    if scheduler.get("memory"):
        lines.append(_directive("mem", scheduler["memory"], _is_memory))
    lines.append("set -euo pipefail")
    lines.extend(scheduler_setup_lines(scheduler))
    lines.append(f"cd {shlex.quote(workdir or str(input_file.parent))}")
    if job_type.strip().lower() in {"gaussian", "orca", "shell"}:
        # Preserve the job output at the same path used by local/SSH execution
        # and result queries. ORCA also needs this stream for termination checks.
        capture = f".cloudra/calc-{task_id}.out.log"
        lines.append("mkdir -p .cloudra")
        lines.append(f"{shlex.join(calculator_cmd)} > {shlex.quote(capture)} 2>&1")
    else:
        lines.append(shlex.join(calculator_cmd))
    lines.append("")
    return "\n".join(lines)
```


## `cloudra/infra/ssh_transport.py`

文件 SHA-256：`2147577483c63bf8da04812f35915f8637601cf5c6ceb208495756b9839e64a4`


<a id="s063"></a>

### S063 · `SshError`

`cloudra/infra/ssh_transport.py:20–21`

```python
class SshError(RuntimeError):
    pass
```


<a id="s064"></a>

### S064 · `SshEndpoint`

`cloudra/infra/ssh_transport.py:24–67`

```python
@dataclass(frozen=True)
class SshEndpoint:
    """一个远端节点的连接参数。

    账本行 ``scheduler_options.connection`` 快照是唯一事实源（提交时从注册表
    拷入，之后改注册表不影响在飞作业）；``from_connection`` 只做形状校验，
    字符白名单在注册表加载（nodes.py）时已强制。
    """

    host: str
    user: str
    port: int
    remote_root: str
    identity_file: str | None = None

    @classmethod
    def from_connection(cls, connection: dict) -> "SshEndpoint":
        if str(connection.get("type") or "") != "ssh":
            raise SshError(f"connection is not ssh: {connection!r}")
        try:
            host = str(connection["host"]).strip()
            user = str(connection["user"]).strip()
            remote_root = str(connection["remote_root"]).strip()
            port = int(connection.get("port", 22))
        except (KeyError, TypeError, ValueError) as exc:
            raise SshError(f"incomplete ssh connection snapshot: {connection!r}") from exc
        if not host or not user or not remote_root:
            raise SshError(f"incomplete ssh connection snapshot: {connection!r}")
        identity = connection.get("identity_file")
        return cls(
            host=host,
            user=user,
            port=port,
            remote_root=remote_root,
            identity_file=str(identity) if identity else None,
        )

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}"

    def job_dir(self, task_id: int) -> str:
        """远端作业目录：``<remote_root>/cloudra-<task_id>``（按作业隔离）。"""
        return f"{self.remote_root}/cloudra-{task_id}"
```


<a id="s065"></a>

### S065 · `ssh_argv`

`cloudra/infra/ssh_transport.py:70–76`

```python
def ssh_argv(endpoint: SshEndpoint) -> list[str]:
    """ssh 命令前缀（BatchMode 禁交互，10s 连接超时）。"""
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if endpoint.identity_file:
        argv += ["-i", endpoint.identity_file]
    argv += ["-p", str(endpoint.port), endpoint.target]
    return argv
```


<a id="s066"></a>

### S066 · `run_remote`

`cloudra/infra/ssh_transport.py:79–93`

```python
def run_remote(
    endpoint: SshEndpoint, remote_cmd: str, *, timeout: float = 30
) -> tuple[int, str, str]:
    """在远端执行一条命令，返回 ``(rc, stdout, stderr)``；传输失败抛 SshError。"""
    try:
        completed = subprocess.run(
            [*ssh_argv(endpoint), remote_cmd],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SshError(f"ssh to {endpoint.target} failed: {exc}") from exc
    return completed.returncode, completed.stdout, completed.stderr
```


<a id="s067"></a>

### S067 · `run_remote_checked`

`cloudra/infra/ssh_transport.py:96–106`

```python
def run_remote_checked(
    endpoint: SshEndpoint, remote_cmd: str, *, timeout: float = 30
) -> str:
    """远端命令必须 rc=0，否则抛 SshError（带远端 stderr 摘要）。"""
    rc, stdout, stderr = run_remote(endpoint, remote_cmd, timeout=timeout)
    if rc != 0:
        raise SshError(
            f"remote command failed on {endpoint.target} (rc={rc}): "
            f"{(stderr or stdout).strip()[:2000]}"
        )
    return stdout
```


<a id="s068"></a>

### S068 · `_rsync_ssh_opt`

`cloudra/infra/ssh_transport.py:109–110`

```python
def _rsync_ssh_opt(endpoint: SshEndpoint) -> str:
    return shlex.join(ssh_argv(endpoint))
```


<a id="s069"></a>

### S069 · `_check_local_rsync`

`cloudra/infra/ssh_transport.py:113–118`

```python
def _check_local_rsync() -> None:
    if shutil.which("rsync") is None:
        raise SshError(
            "rsync is required for remote compute staging; install rsync on this "
            "machine and on the remote host."
        )
```


<a id="s070"></a>

### S070 · `_rsync_base`

`cloudra/infra/ssh_transport.py:121–122`

```python
def _rsync_base(endpoint: SshEndpoint) -> list[str]:
    return ["rsync", "-az", "-e", _rsync_ssh_opt(endpoint)]
```


<a id="s071"></a>

### S071 · `_run_rsync`

`cloudra/infra/ssh_transport.py:125–136`

```python
def _run_rsync(argv: list[str], timeout: float) -> None:
    try:
        completed = subprocess.run(
            argv, check=False, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SshError(f"rsync failed to start: {exc}") from exc
    if completed.returncode != 0:
        raise SshError(
            f"rsync failed (rc={completed.returncode}): "
            f"{(completed.stderr or completed.stdout).strip()[:2000]}"
        )
```


<a id="s072"></a>

### S072 · `push_dir`

`cloudra/infra/ssh_transport.py:139–154`

```python
def push_dir(
    endpoint: SshEndpoint,
    local_dir: str | Path,
    remote_dir: str,
    *,
    excludes: tuple[str, ...] = (),
    timeout: float = 300,
) -> None:
    """把本地目录内容同步进远端目录（自动先 ``mkdir -p`` 远端目录）。"""
    _check_local_rsync()
    run_remote_checked(endpoint, f"mkdir -p {shlex.quote(remote_dir)}")
    argv = [*_rsync_base(endpoint)]
    for pattern in excludes:
        argv += ["--exclude", pattern]
    argv += [f"{Path(local_dir)}/", f"{endpoint.target}:{shlex.quote(remote_dir)}/"]
    _run_rsync(argv, timeout)
```


<a id="s073"></a>

### S073 · `push_files`

`cloudra/infra/ssh_transport.py:157–172`

```python
def push_files(
    endpoint: SshEndpoint,
    local_paths: list[str | Path],
    remote_dir: str,
    *,
    timeout: float = 300,
) -> None:
    """把若干本地文件平铺推进远端目录（自动先 ``mkdir -p``）。"""
    _check_local_rsync()
    run_remote_checked(endpoint, f"mkdir -p {shlex.quote(remote_dir)}")
    argv = [
        *_rsync_base(endpoint),
        *[str(path) for path in local_paths],
        f"{endpoint.target}:{shlex.quote(remote_dir)}/",
    ]
    _run_rsync(argv, timeout)
```


## `cloudra/persistence/fs_utils.py`

文件 SHA-256：`f059402d35df93d795a28058dcc893188618a0b4d39b60f004e524eca41154d3`


<a id="s074"></a>

### S074 · `atomic_write_bytes`

`cloudra/persistence/fs_utils.py:17–42`

```python
def atomic_write_bytes(path: str, data: bytes, *, mode: int | None = None) -> None:
    """原子写入二进制内容到 ``path``。

    临时文件用 ``tempfile.mkstemp`` 生成唯一名称，避免多个写者撞用同一
    临时文件相互截断；写入成功后 ``os.replace`` 原子替换，失败时清理残留。
    目标文件已存在时沿用其权限位，避免 mkstemp 默认 0600 改变文件属性；
    ``mode`` 显式指定时覆盖该默认。
    """
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if mode is None:
            try:
                mode = os.stat(path).st_mode & 0o777
            except OSError:
                mode = 0o644
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
```


<a id="s075"></a>

### S075 · `atomic_write_text`

`cloudra/persistence/fs_utils.py:45–49`

```python
def atomic_write_text(
    path: str, content: str, encoding: str = "utf-8", *, mode: int | None = None
) -> None:
    """原子写入文本内容到 ``path``。"""
    atomic_write_bytes(path, content.encode(encoding), mode=mode)
```


<a id="s076"></a>

### S076 · `atomic_write_json`

`cloudra/persistence/fs_utils.py:52–61`

```python
def atomic_write_json(
    path: str,
    data: Any,
    *,
    ensure_ascii: bool = False,
    indent: int | None = 2,
) -> None:
    """原子写入 JSON 数据到 ``path``。"""
    text = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
    atomic_write_text(path, text)
```


## `cloudra/persistence/workspace.py`

文件 SHA-256：`3e95fd3785da9b1e95568c3afceb87a264b80079b83090806e96527928f2cc89`


<a id="s077"></a>

### S077 · `resolve_working_directory`

`cloudra/persistence/workspace.py:64–71`

```python
def resolve_working_directory(value: str | None = None) -> str:
    """把工作目录收成绝对路径；缺省用当前进程 cwd。

    隔离 TUI 的 runtime 进程 cwd 可能与用户启动目录不同。客户端应传入
    自己的目录，而不是让 runtime 用 getcwd 兜底。
    """
    raw = (value or "").strip() or os.getcwd()
    return str(Path(raw).expanduser().resolve())
```


<a id="s078"></a>

### S078 · `resolve_tool_path`

`cloudra/persistence/workspace.py:74–94`

```python
def resolve_tool_path(tool: Any, value: str) -> str:
    """把工具收到的文件路径参数统一到 agent 工作目录语义。

    绝对路径原样保留（科研节点上的显式访问是既有权限语义，不擅自收紧）；
    相对路径解析到绑定 agent 的 working_directory（per-project 沙箱），
    与 read/write/bash 的既有契约一致——修复相对路径落到进程 cwd 串目录
    的缺陷（C1：qm_input_writer/submit_compute_job 未走此原语）。仅在没有
    agent 桥（直接 CLI/单测调用）时回退进程 cwd。

    只对“文件路径字段”调用本函数；SMILES、文件名透传串等非路径语义由
    调用方自行甄别，禁止混用。
    """
    raw = (value or "").strip()
    if not raw:
        return value or ""
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    subagent = getattr(tool, "subagent", None)
    root = getattr(subagent, "working_directory", None) or os.getcwd()
    return str((Path(root) / p).resolve())
```


## `cloudra/runtime/remote_compute.py`

文件 SHA-256：`621efb1aa0947570575f65f5cda616ad1e5bce3557a6c86de38f71caa6254093`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/runtime/remote_compute.py:76–76`

```python
REMOTE_KINDS = ("ssh_local", "ssh_slurm")
```


`cloudra/runtime/remote_compute.py:77–77`

```python
_SHELL_HANDLE_PREFIX = "shell:"
```


`cloudra/runtime/remote_compute.py:79–79`

```python
_MAX_PULL_ATTEMPTS = 5
```


<a id="s079"></a>

### S079 · `SshTransport.__init__`

`cloudra/runtime/remote_compute.py:90–91`

```python
    def __init__(self, endpoint: SshEndpoint) -> None:
        self.endpoint = endpoint
```


<a id="s080"></a>

### S080 · `SshTransport.run`

`cloudra/runtime/remote_compute.py:93–94`

```python
    def run(self, remote_cmd: str, *, timeout: float = 30) -> tuple[int, str, str]:
        return run_remote(self.endpoint, remote_cmd, timeout=timeout)
```


<a id="s081"></a>

### S081 · `SshTransport.checked`

`cloudra/runtime/remote_compute.py:96–97`

```python
    def checked(self, remote_cmd: str, *, timeout: float = 30) -> str:
        return run_remote_checked(self.endpoint, remote_cmd, timeout=timeout)
```


<a id="s082"></a>

### S082 · `SshTransport.push_dir`

`cloudra/runtime/remote_compute.py:99–102`

```python
    def push_dir(
        self, local_dir: str | Path, remote_dir: str, *, excludes: tuple[str, ...] = ()
    ) -> None:
        push_dir(self.endpoint, local_dir, remote_dir, excludes=excludes)
```


<a id="s083"></a>

### S083 · `SshTransport.push_files`

`cloudra/runtime/remote_compute.py:104–105`

```python
    def push_files(self, local_paths: list[str | Path], remote_dir: str) -> None:
        push_files(self.endpoint, local_paths, remote_dir)
```


<a id="s084"></a>

### S084 · `remote_calculator_argv`

`cloudra/runtime/remote_compute.py:119–126`

```python
def remote_calculator_argv(
    input_name: str, job_type: str, xtb_params: XtbParams | None = None
) -> list[str]:
    """远端 calculator 命令：随作业推送的内置 calculator.sh + 输入副本 basename。"""
    argv = ["bash", "calculator.sh", input_name, job_type]
    if job_type == "xtb":
        argv.extend((xtb_params or XtbParams()).cli_args())
    return argv
```


<a id="s085"></a>

### S085 · `build_remote_runner_script`

`cloudra/runtime/remote_compute.py:129–192`

```python
def build_remote_runner_script(
    input_name: str,
    job_type: str,
    task_id: int,
    scheduler: dict,
    *,
    xtb_params: XtbParams | None = None,
    workdir: str,
    calculator_cmd: list[str] | None = None,
) -> str:
    """ssh_local 直跑脚本（无 SBATCH 头）。

    刻意不带 ``set -e``：引擎失败也必须写出退出文件——``.cloudra-exit-<id>``
    是 poller 的终态信号，缺它即使 runner 消失也保留在途状态。calculator
    stdout/stderr 统一捕获到 ``.cloudra/calc-<id>.out.log``（拉回后即被
    ``resolve_log_path`` 命中，与本地 guard / Slurm ORCA 捕获同口径）。
    """
    capture = f".cloudra/calc-{task_id}.out.log"
    lines = [
        "#!/bin/bash",
        "set -uo pipefail",
        f"cd {shlex.quote(workdir)}",
        f"echo $$ > {shlex.quote(f'.cloudra-runner-{task_id}.pid')}",
        "mkdir -p .cloudra",
        *scheduler_setup_lines(scheduler),
    ]
    # Only the live runner owns this job group; persisted PIDs never authorize kill.
    lines.append("set -m")
    lines.extend([
        f"{shlex.join(calculator_cmd or remote_calculator_argv(input_name, job_type, xtb_params))}"
        f" > {shlex.quote(capture)} 2>&1 &",
        "calc_pid=$!",
    ])
    cancel_file = shlex.quote(f".cloudra-cancel-{task_id}")
    lines.extend([
        "cancel_sent=0",
        'while [ -n "$(jobs -pr)" ]; do',
        f"    if [ -f {cancel_file} ]; then",
        "        if kill -TERM %1 2>/dev/null; then cancel_sent=1; fi",
        "        break",
        "    fi",
        "    sleep 0.1",
        "done",
    ])
    lines.extend([
        "wait $calc_pid",
        "rc=$?",
    ])
    # The calculator may exit before an engine child. Keep the receipt pending
    # until every member of the group owned by this runner has exited.
    lines.extend([
        'while kill -0 -- "-$calc_pid" 2>/dev/null; do',
        f'    if [ "$cancel_sent" -eq 0 ] && [ -f {cancel_file} ]; then',
        '        kill -TERM -- "-$calc_pid" 2>/dev/null || true',
        "        cancel_sent=1",
        "    fi",
        "    sleep 0.1",
        "done",
    ])
    lines.extend([
        f"echo \"$rc\" > {shlex.quote(f'.cloudra-exit-{task_id}')}",
        "",
    ])
    return "\n".join(lines)
```


<a id="s086"></a>

### S086 · `_submit_slurm`

`cloudra/runtime/remote_compute.py:195–202`

```python
def _submit_slurm(transport, remote_dir: str, script_name: str) -> str:
    out = transport.checked(
        f"cd {shlex.quote(remote_dir)} && sbatch --parsable {shlex.quote(script_name)}"
    )
    job_id = out.strip().split(";", 1)[0]
    if not _is_job_id(job_id):
        raise SshError(f"远端 sbatch 返回了无效 job id: {job_id!r}")
    return job_id
```


<a id="s087"></a>

### S087 · `_submit_shell`

`cloudra/runtime/remote_compute.py:205–215`

```python
def _submit_shell(transport, remote_dir: str, script_name: str, task_id: int) -> str:
    cmd = (
        f"cd {shlex.quote(remote_dir)} && "
        f"nohup bash {shlex.quote(script_name)} "
        f"> {shlex.quote(f'run-{task_id}.log')} 2>&1 < /dev/null & echo $!"
    )
    out = transport.checked(cmd)
    pid = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if not pid.isdigit():
        raise SshError(f"远端 runner 拉起未返回 PID: {out.strip()[:200]!r}")
    return f"{_SHELL_HANDLE_PREFIX}{pid}"
```


<a id="s088"></a>

### S088 · `_native_file_tokens`

`cloudra/runtime/remote_compute.py:326–356`

```python
def _native_file_tokens(text: str) -> list[tuple[int, int, str]]:
    """Read whitespace/quoted native tokens, retaining spans for path-only edits."""
    tokens = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        if text[position] == '#':
            newline = text.find('\n', position)
            position = len(text) if newline < 0 else newline + 1
            continue
        start = position
        if text[position] in {'"', "'"}:
            quote = text[position]
            newline = text.find('\n', position)
            line_end = len(text) if newline < 0 else newline
            end = text.find(quote, position + 1, line_end)
            if end < 0:
                # Unrelated malformed solver options remain the engine's input.
                # A file directive consuming this token is diagnosed below.
                position, value = line_end, text[start:line_end]
            else:
                position = end + 1
                value = text[start + 1:position - 1]
        else:
            while position < len(text) and not text[position].isspace() and text[position] != '#':
                position += 1
            value = text[start:position]
        tokens.append((start, position, value))
    return tokens
```


<a id="s089"></a>

### S089 · `_stage_native_paths`

`cloudra/runtime/remote_compute.py:359–542`

```python
def _stage_native_paths(input_file: Path, workdir: Path, task_id: int, job_type: str) -> Path | None:
    """Build an execution-only input overlay and a durable native path map.

    Native options are copied verbatim. Only declared file destinations and
    dependencies move into the remote job tree; the submitted local input stays
    immutable. The original files and pulled execution copy remain inspectable.
    """
    if job_type not in {'gaussian', 'orca'}:
        return None
    receipt = workdir / '.cloudra' / f'remote-{task_id}'
    stage = receipt / 'stage'
    stage.mkdir(parents=True, exist_ok=True)
    original = input_file.read_bytes()
    original_copy = receipt / 'original' / input_file.name
    original_copy.parent.mkdir(parents=True, exist_ok=True)
    if original_copy.exists() and original_copy.read_bytes() != original:
        raise ValueError('submitted native input changed since remote staging')
    original_copy.write_bytes(original)
    text = original.decode('utf-8')
    files: dict[str, dict] = {}
    geometry_outputs = _orca_geometry_output_paths(str(input_file)) if job_type == 'orca' else set()

    def relocate(value: str, role: str, *, directory: bool = False, prefix: bool = False) -> str:
        if not value:
            raise ValueError('empty native file path cannot be staged')
        # Freeze the actual destination before execution, including pre-existing
        # system/user symlinks. Later symlink changes cannot redirect results.
        local = (workdir / value).resolve()
        if local.resolve().is_relative_to((workdir / '.cloudra').resolve()):
            raise ValueError('native file path collides with the runtime receipt directory')
        if local.resolve() == input_file.resolve():
            raise ValueError('native artifact path would overwrite the submitted input')
        try:
            relative = local.relative_to(workdir)
        except ValueError:
            digest = hashlib.sha256(str(local).encode()).hexdigest()[:16]
            relative = Path(f'.cloudra-files-{task_id}') / digest / local.name
        if relative.parts and relative.parts[0] == '.cloudra':
            raise ValueError('native file path collides with the runtime receipt directory')
        staged = stage / relative
        if directory:
            staged.mkdir(parents=True, exist_ok=True)
        else:
            staged.parent.mkdir(parents=True, exist_ok=True)
        if role == 'dependency' and not local.is_file():
            raise ValueError(f'native file dependency is missing or not a regular file: {local}')
        if local.exists() and not directory and not prefix:
            if not local.is_file():
                raise ValueError(f'native file path is not a regular file: {local}')
            shutil.copy2(local, staged)
            saved = receipt / 'original-files' / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            if not saved.exists():
                shutil.copy2(local, saved)
        key = str(local)
        previous = files.get(key)
        source_sha256 = None
        if local.is_file() and not prefix:
            with local.open('rb') as stream:
                source_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
        files[key] = {
            'local_path': key,
            'staged_path': relative.as_posix(),
            'role': role if previous is None or previous['role'] == 'dependency' else previous['role'],
            'directory': directory,
            'prefix': prefix,
            'source_sha256': source_sha256,
        }
        if prefix and local.parent.is_dir():
            for child in local.parent.iterdir():
                suffix = child.name[len(local.name):] if child.name.startswith(local.name) else ''
                if not suffix.startswith(('.', '_')) or not child.is_file():
                    continue
                if (child.resolve() == input_file.resolve() or child.suffix.casefold() in {'.out', '.log'}
                        or child.name == 'irc_endpoints.json' or child in geometry_outputs
                        or child.name.endswith(('_IRC_F.xyz', '_IRC_B.xyz', '_IRC_F_trj.xyz', '_IRC_B_trj.xyz',
                                                '_NEB-TS_converged.xyz'))):
                    continue  # Logs and the submitted input are not restart data.
                staged_child = staged.with_name(staged.name + suffix)
                shutil.copy2(child, staged_child)
                saved = receipt / 'original-files' / relative.with_name(relative.name + suffix)
                saved.parent.mkdir(parents=True, exist_ok=True)
                if not saved.exists():
                    shutil.copy2(child, saved)
                with child.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                files[str(child)] = {
                    'local_path': str(child), 'staged_path': staged_child.relative_to(stage).as_posix(),
                    'role': 'inout', 'directory': False, 'prefix': False, 'source_sha256': digest,
                }
        return relative.as_posix() + ('/' if directory else '')

    if job_type == 'gaussian':
        lines = []
        in_link0 = True
        for line in text.splitlines(keepends=True):
            stripped = line.lstrip()
            if stripped.strip().casefold() == '--link1--':
                in_link0 = True
            elif stripped.startswith('#'):
                in_link0 = False
            key, separator, value = stripped.partition('=')
            directive = key.strip().casefold()
            roles = {'%chk': 'inout', '%oldchk': 'dependency', '%rwf': 'inout',
                     '%fchk': 'output', '%int': 'inout', '%d2e': 'inout'}
            if in_link0 and separator and directive in roles:
                bare = value.strip()
                quote = bare[0] if bare and bare[0] in {'"', "'"} else ''
                if quote:
                    if not bare.endswith(quote):
                        raise ValueError('unterminated Gaussian file path')
                    bare = bare[1:-1]
                if directive == '%rwf':
                    parts = bare.split(',')
                    for index in range(0, len(parts), 2):
                        path = parts[index].strip()
                        parts[index] = relocate(path, roles[directive], directory=path.endswith('/'))
                    mapped = ','.join(parts)
                else:
                    mapped = relocate(bare, roles[directive])
                start = len(line) - len(value) + len(value) - len(value.lstrip())
                end = len(line.rstrip())
                line = line[:start] + quote + mapped + quote + line[end:]
            lines.append(line)
        text = ''.join(lines)
    else:
        tokens = _native_file_tokens(text)
        replacements = []
        consumed = set()
        block = ''
        for index, (token_start, token_end, value) in enumerate(tokens):
            if index in consumed or text[token_start:token_end].startswith(('"', "'")):
                continue
            lowered = value.casefold()
            line_start = text.rfind('\n', 0, token_start) + 1
            starts_line = not text[line_start:token_start].strip()
            starts_statement = starts_line or (index > 0 and tokens[index - 1][2].casefold() == 'end')
            if lowered.startswith('%') and starts_statement:
                block = lowered[1:]
            elif lowered == 'end' or (starts_line and lowered.startswith(('!', '*'))):
                block = ''
            target_index = None
            role = 'dependency'
            if lowered in {'%moinp', '%pointcharges'} and starts_statement:
                target_index = index + 1
            elif lowered in {'hess_filename', 'inhessname'} and block in {'irc', 'geom'}:
                target_index = index + 1
            elif lowered in ORCA_NEB_GEOMETRY_INPUTS and block == 'neb':
                target_index = index + 1
            elif (lowered == '*xyzfile' and starts_line) or (
                    lowered == 'xyzfile' and index > 0 and tokens[index - 1][2] == '*'):
                target_index = index + 3
            elif lowered == '%base' and starts_statement:
                target_index, role = index + 1, 'output'
            if target_index is None:
                continue
            if target_index >= len(tokens):
                raise ValueError(f'native {value} file path is missing')
            start, end, path = tokens[target_index]
            raw = text[start:end]
            if raw[0] in {'"', "'"} and (len(raw) < 2 or raw[-1] != raw[0]):
                raise ValueError(f'unterminated quoted native file path for {value}')
            mapped = relocate(path, role, prefix=lowered == '%base')
            consumed.add(target_index)
            quote = raw[0] if raw[0] in {'"', "'"} else ('"' if any(c.isspace() for c in mapped) else '')
            replacements.append((start, end, quote + mapped + quote))
        for start, end, mapped in sorted(replacements, reverse=True):
            text = text[:start] + mapped + text[end:]
    (stage / input_file.name).write_text(text, encoding='utf-8')
    staged_files = {}
    for directory, directories, filenames in os.walk(workdir, followlinks=False):
        directories[:] = [name for name in directories if name not in {'.cloudra', '.g16_scratch'}]
        for name in filenames:
            path = Path(directory) / name
            if path.is_file() and not path.is_symlink():
                with path.open('rb') as stream:
                    staged_files[path.relative_to(workdir).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = {'input_file': str(input_file), 'job_type': job_type,
                'input_sha256': hashlib.sha256(original).hexdigest(),
                'files': list(files.values()), 'staged_files': staged_files}
    manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + '\n'
    (receipt / 'path-map.json').write_text(manifest_text, encoding='utf-8')
    (stage / f'.cloudra-path-map-{task_id}.json').write_text(manifest_text, encoding='utf-8')
    return stage
```


<a id="s090"></a>

### S090 · `_stage_and_submit`

`cloudra/runtime/remote_compute.py:647–706`

```python
def _stage_and_submit(
    transport,
    kind: str,
    task_id: int,
    input_file: Path,
    workdir: Path,
    remote_dir: str,
    job_type: str,
    row: dict,
    options: dict,
) -> tuple[str, str]:
    """推 stage 并远端提交；返回 ``(句柄, 本地脚本路径)``。"""
    xtb_params = XtbParams.from_row(row) if job_type == "xtb" else None
    calc_argv = remote_calculator_argv(input_file.name, job_type, xtb_params)
    if job_type == "chem_task":
        python = (options.get('environment') or {}).get('CLOUDRA_CHEM_PYTHON')
        if not isinstance(python, str) or not Path(python).is_absolute():
            raise ValueError('remote chem_task requires trusted node environment CLOUDRA_CHEM_PYTHON as an absolute interpreter path')
        transport.checked(shlex.join([python, '-c', 'import pydantic,numpy,rdkit']), timeout=30)
        calc_argv.extend([python, _stage_chem_runtime(workdir)])
    if kind == "ssh_slurm":
        script = build_batch_script(
            input_file,
            job_type,
            task_id,
            options,
            xtb_params=xtb_params,
            calculator_cmd=calc_argv,
            workdir=remote_dir,
        )
        script_name = f".cloudra-slurm-{task_id}.sh"
    else:
        script = build_remote_runner_script(
            input_file.name,
            job_type,
            task_id,
            options,
            xtb_params=xtb_params,
            workdir=remote_dir,
            calculator_cmd=calc_argv,
        )
        script_name = f".cloudra-run-{task_id}.sh"
    script_path = workdir / script_name
    script_path.write_text(script, encoding="utf-8")
    os.chmod(script_path, 0o700)
    native_stage = _stage_native_paths(input_file, workdir, task_id, job_type)
    excludes = ('.cloudra/', '.g16_scratch/')
    if native_stage:
        excludes += (input_file.name, Path(get_log_path(str(input_file), job_type)).name, f'state_{task_id}.json',
                     'irc_endpoints.json')
    if job_type == 'orca':
        excludes += ('*_IRC_F.xyz', '*_IRC_B.xyz', '*_IRC_F_trj.xyz', '*_IRC_B_trj.xyz',
                     '*_im[0-9]*.xyz', '*_NEB-TS_converged.xyz')
    transport.push_dir(workdir, remote_dir, excludes=excludes)
    transport.push_files([_default_calculator_path()], remote_dir)
    if native_stage:
        transport.push_dir(native_stage, remote_dir)
    if kind == "ssh_slurm":
        return _submit_slurm(transport, remote_dir, script_name), str(script_path)
    return _submit_shell(transport, remote_dir, script_name, task_id), str(script_path)
```


<a id="s091"></a>

### S091 · `run_remote_compute`

`cloudra/runtime/remote_compute.py:718–872`

```python
async def run_remote_compute(
    task_id: int,
    db_path: str,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    transport=None,
) -> int:
    """执行一条已认领的 ssh_local/ssh_slurm 作业；到达终态并落库后返回。"""
    db = ComputeDB.from_path(db_path)
    row = await aget_compute_job(db, task_id)
    if not row:
        raise SshError(f"compute job {task_id} 不存在")
    if row["state"] not in {"running", "cancel_requested"}:
        return 0 if row["state"] == "done" else 1
    kind = (row["scheduler"] or "").strip()
    if kind not in REMOTE_KINDS:
        raise SshError(f"compute job {task_id} 不是远端作业: {kind!r}")
    options = _scheduler_options(row)
    endpoint = SshEndpoint.from_connection(options.get("connection") or {})
    transport = transport or SshTransport(endpoint)
    job_type = (row["jobtype"] or "").strip()
    input_file = Path(row["path"]).expanduser()
    remote_dir = endpoint.job_dir(task_id)
    handle = (row["scheduler_job_id"] or "").strip()

    if not handle:
        # No handle is not proof that a previous submission never started.
        if row["state"] == "cancel_requested":
            return 1
        # 正常认领路径（ready → running 无句柄）与对账安全重投路径
        # （ssh_local 探明远端无 runner）共用：stage 幂等（rsync 覆盖）。
        input_file = input_file.resolve(strict=True)
        workdir = input_file.parent
        handle, script_path = await asyncio.to_thread(
            _stage_and_submit,
            transport,
            kind,
            task_id,
            input_file,
            workdir,
            remote_dir,
            job_type,
            row,
            options,
        )
        await amark_slurm_submitted(db, task_id, handle, script_path)

    workdir = input_file.parent
    poll_seconds = min(max(float(options.get("poll_seconds", 15)), 1), 300)
    last_observed = ""
    empty_after_seen = 0
    pull_failures = 0
    while True:
        current = await aget_compute_job(db, task_id)
        if current and current["state"] not in {"running", "cancel_requested"}:
            return 0 if current["state"] == "done" else 1
        if current and current["state"] == "cancel_requested":
            await asyncio.to_thread(
                _cancel_remote, transport, kind, remote_dir, task_id, handle
            )
        try:
            if kind == "ssh_slurm":
                state, exit_code = await asyncio.to_thread(
                    _query_slurm_state, transport, handle
                )
            else:
                state, exit_code = await asyncio.to_thread(
                    _query_shell_state, transport, remote_dir, task_id, handle
                )
        except SshError:
            await sleep(poll_seconds)
            continue

        latest = await aget_compute_job(db, task_id)
        if latest and latest["state"] == "cancel_requested":
            exited = (state in SLURM_TERMINAL_SUCCESS | SLURM_TERMINAL_FAILURE
                      if kind == "ssh_slurm" else state == "EXIT")
            if exited:
                await acancel_compute_job(db, task_id)
                return 1
            # Request acceptance, missing accounting and a vanished runner do not
            # establish child-process exit. Keep the request and capacity pending.
            await sleep(poll_seconds)
            continue

        base_error: str | None = None
        if kind == "ssh_slurm":
            if not state:
                if last_observed:
                    empty_after_seen += 1
                    if empty_after_seen >= 3:
                        await afinalize_compute_job(
                            db,
                            task_id,
                            "failed",
                            last_error="Slurm accounting row vanished after "
                            f"{last_observed}",
                        )
                        return 1
                await sleep(poll_seconds)
                continue
            empty_after_seen = 0
            last_observed = state
            await aupdate_scheduler_state(db, task_id, state)
            if state not in SLURM_TERMINAL_SUCCESS | SLURM_TERMINAL_FAILURE:
                await sleep(poll_seconds)
                continue
            if state in SLURM_TERMINAL_FAILURE:
                base_error = f"Slurm {state} ({exit_code})"
        else:
            await aupdate_scheduler_state(
                db, task_id, f"EXIT:{exit_code}" if state == "EXIT" else state
            )
            if state in {"RUNNING", "VANISHED"}:
                # A missing observer is not an execution receipt: its engine
                # children may still be alive. Retain capacity until real exit.
                await sleep(poll_seconds)
                continue

        # 终态：拉回全部产物（有界重试），shell 只认退出码，其余引擎复核日志。
        try:
            await asyncio.to_thread(_pull_remote_artifacts, transport, remote_dir, workdir, input_file, task_id, job_type)
        except (SshError, OSError, ValueError) as exc:
            pull_failures += 1
            if pull_failures < _MAX_PULL_ATTEMPTS:
                await sleep(poll_seconds)
                continue
            await afinalize_compute_job(
                db,
                task_id,
                "failed",
                last_error=(
                    f"artifact pull-back failed after {_MAX_PULL_ATTEMPTS} "
                    f"attempts: {exc}"
                )[:500],
            )
            return 1
        if job_type == "shell":
            succeeded = not base_error and exit_code == ("0:0" if kind == "ssh_slurm" else "0")
            final = "done" if succeeded else "failed"
            last_error = None if succeeded else base_error or f"shell exit code {exit_code or 'unknown'}"
        else:
            engine_ok = await asyncio.to_thread(
                _engine_success_from_log, job_type, str(input_file), task_id
            )
            final, last_error = _terminal_verdict(engine_ok, base_error)
        wrote = await afinalize_compute_job(db, task_id, final, last_error=last_error)
        if not wrote:
            latest = await aget_compute_job(db, task_id)
            if latest and latest["state"] in {"cancelled", "cancel_requested"}:
                # The query already confirmed actual execution exit.
                await acancel_compute_job(db, task_id)
                return 1
        # 终态通知由 ComputeNotifyBroker 轮询 compute_jobs 表补投，不再发 IPC
        return 0 if final == "done" else 1
```


## `cloudra/runtime_v2/method_policy.py`

文件 SHA-256：`043b2e735e9b4acc18b055685144e5251323e3096d0fe938fcb89149409566a0`


<a id="s092"></a>

### S092 · `_norm_basis`

`cloudra/runtime_v2/method_policy.py:130–132`

```python
def _norm_basis(b: str) -> str:
    """基组拼写归一：ORCA `def2-SVP` 与 Gaussian `def2svp` 是同一基组。"""
    return b.strip().lower().replace("-", "")
```


## `cloudra/services/ts_pipeline_context.py`

文件 SHA-256：`085b0b690e4f3401ba8ee71f1c9ad912143456aa59da8f7e247903048726e71d`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/services/ts_pipeline_context.py:7–7`

```python
_current_ledger: ContextVar[ComputeDB | None] = ContextVar('ts_pipeline_ledger', default=None)
```


`cloudra/services/ts_pipeline_context.py:25–25`

```python
_current_authority: ContextVar[object | None] = ContextVar('ts_pipeline_authority', default=None)
```


<a id="s093"></a>

### S093 · `pipeline_database`

`cloudra/services/ts_pipeline_context.py:10–11`

```python
def pipeline_database() -> ComputeDB:
    return _current_ledger.get() or ComputeDB()
```


<a id="s094"></a>

### S094 · `use_pipeline_authority`

`cloudra/services/ts_pipeline_context.py:28–34`

```python
@contextmanager
def use_pipeline_authority(resolver):
    token = _current_authority.set(resolver)
    try:
        yield
    finally:
        _current_authority.reset(token)
```


<a id="s095"></a>

### S095 · `require_pipeline_authority`

`cloudra/services/ts_pipeline_context.py:47–48`

```python
def require_pipeline_authority(project_id, owner_session_id):
    return require_pipeline_producer(project_id, owner_session_id)
```


## `cloudra/services/ts_pipeline_store.py`

文件 SHA-256：`a5ee652fa1d669644b83a8919343ff393fe26c02f7ac1be5fd96eb1424309909`


<a id="s096"></a>

### S096 · `atom_binding_for_log`

`cloudra/services/ts_pipeline_store.py:508–534`

```python
def atom_binding_for_log(db: ComputeDB, log_path: str | Path, workspace_dir: str | Path) -> dict | None:
    """Use only a completed job's frozen binding, never a current process record."""
    if not Path(db.path).is_file():
        return None
    from cloudra.infra.compute_utils import resolve_log_path

    path = Path(log_path).resolve()
    workspace = str(Path(workspace_dir).resolve())
    with db.connect() as con:
        rows = con.execute("SELECT j.id,j.path,j.jobtype,s.process_id,s.declaration_revision,s.evidence "
            "FROM ts_pipeline_stages s JOIN compute_jobs j ON j.id=s.job_id "
            "JOIN ts_pipeline_processes p ON p.process_id=s.process_id "
            "WHERE j.state='done' AND s.evidence IS NOT NULL AND json_extract(p.payload,'$.workspace_dir')=?",
            (workspace,)).fetchall()
    for job_id, input_path, engine, process_id, revision, raw in rows:
        if Path(resolve_log_path(input_path, engine, job_id)).resolve() != path:
            continue
        evidence = StageEvidence.model_validate_json(raw)
        binding = evidence.atom_binding
        if binding is None:
            return None
        if binding.get('process_id') != process_id or binding.get('declaration_revision') != revision:
            raise ValueError('Stage atom binding belongs to a different TS declaration.')
        if evidence.log_sha256 != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('Native log changed after its concrete atom binding was recorded.')
        return binding
    return None
```


## `cloudra/tools/Chemtool/format_converter.py`

文件 SHA-256：`fc8e27850541a252b94d546110252d52ffa5f02432f0ea02bcbc86e07931be3e`


<a id="s097"></a>

### S097 · `FormatConverter_input_schema`

`cloudra/tools/Chemtool/format_converter.py:87–106`

```python
class FormatConverter_input_schema(input_schema):
    input_path: str = Field(
        description="Path of the input file: absolute as-is, or relative to the "
                    "Agent working directory."
    )
    input_format: Literal["mol", "xyz", "gjf", "inp", "pdb", "cif", "sdf", "log", "poscar", "vasp"] = Field(
        description="Input format. gjf/inp require one inline Cartesian Gaussian/ORCA geometry. "
                    "log means a Gaussian or ORCA output log (.log/.out); then output must be csv or xyz."
    )
    output_format: Literal["mol", "xyz", "gjf", "inp", "pdb", "cif", "sdf", "csv", "poscar", "vasp"] = Field(
        description="Target output format. gjf/inp are geometry skeletons without method, basis or solver settings; "
                    "known molecular charge/multiplicity are retained, absent values use 0/1 with explicit disclosure. "
                    "XYZ comments and SDF properties retain native molecular-state metadata; "
                    "formats unable to carry it report that loss. Use qm_input_writer for production inputs. "
                    "When input_format='log', output can be 'csv' (key-frame table) or 'xyz' (final optimized frame)."
    )
    output_path: str = Field(
        description="Path of the output file: absolute as-is, or relative to the "
                    "Agent working directory."
    )
```


<a id="s098"></a>

### S098 · `FormatConverter_output_schema`

`cloudra/tools/Chemtool/format_converter.py:109–112`

```python
class FormatConverter_output_schema(output_schema):
    is_success: bool = Field(description="Whether conversion succeeded")
    output_path: str = Field(default="", description="Absolute path of the output file")
    message: str = Field(default="", description="Status or error message")
```


<a id="s099"></a>

### S099 · `FormatConverter._convert_log`

`cloudra/tools/Chemtool/format_converter.py:144–253`

```python
    @staticmethod
    def _convert_log(user_input: "FormatConverter_input_schema") -> FormatConverter_output_schema:
        """Gaussian/ORCA 日志 → 关键帧 CSV 或最终几何 XYZ。"""
        if user_input.input_format != "log":
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message="output_format='csv' is only supported for log input (input_format='log'). "
                        "For structure files, choose a structure output_format instead."
            )
        if user_input.output_format not in ("csv", "xyz"):
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message="When input_format='log', the output format must be 'csv' (key-frame table) or 'xyz' (final optimized frame)."
            )
        if not os.path.isfile(user_input.input_path):
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"Input file does not exist: {user_input.input_path}. "
                        "Check the path, then retry."
            )
        try:
            from cloudra.tools.core import gaussian_frames, orca_frames
            from cloudra.tools.core.gaussian_frames import frames_to_csv
            from cloudra.tools.core.qm_engine import detect_qm_engine

            # 日志全文只读一次：detect_job_types/extract_frames 都吃文本变体，
            # 不再各自独立整读大日志（detect_qm_engine 只嗅探头部 16 KiB，开销可忽略）。
            with open(user_input.input_path, encoding="utf-8", errors="replace") as fh:
                log_text = fh.read()
            engine = detect_qm_engine(user_input.input_path)
            frames_mod = orca_frames if engine == "orca" else gaussian_frames
            job_types = frames_mod.detect_job_types_from_text(log_text)
            if engine == "orca":
                frames = orca_frames.extract_frames_from_text(
                    log_text, log_path=user_input.input_path,
                )
            else:
                frames = gaussian_frames.extract_frames_from_text(log_text)
            # 按规范顺序展示（opt+ts+freq 风格，而非字母序）
            ordered = [j for j in ("opt", "ts", "freq", "scan", "irc", "sp") if j in job_types]
            if not frames:
                # 空帧必须带上**具体原因**：IRC 的路径点在边文件里、NEB 的几何在逐图像边文件里，
                # 两者都是"主输出没有但作业确实产出了几何"的情形，笼统一句"没有关键帧"没有信息量
                reason = None
                if engine == "orca":
                    reason = orca_frames.frames_unavailable_reason_from_text(
                        log_text, log_path=user_input.input_path,
                    )
                explanation = f" Reason: {reason}." if reason else (
                    " Check that the log contains a finished opt/scan job."
                )
                return FormatConverter_output_schema(
                    is_success=False,
                    output_path="",
                    message=(
                        f"No key frames could be extracted from the {engine or 'unknown'}-engine log "
                        f"(detected as {'+'.join(ordered) or 'unknown'}): {user_input.input_path}."
                        f"{explanation}"
                    ),
                )
            if user_input.output_format == "csv":
                frames_to_csv(frames, user_input.output_path)
                return FormatConverter_output_schema(
                    is_success=True,
                    output_path=user_input.output_path,
                    message=(
                        f"Detected {engine or 'unknown'} {'+'.join(ordered)}, wrote {len(frames)} "
                        f"frames from {user_input.input_path} -> {user_input.output_path}"
                    )
                )
            else:
                last_frame = frames[-1]
                xyz_text = last_frame.xyz
                if not xyz_text.endswith("\n"):
                    xyz_text += "\n"
                with open(user_input.output_path, "w", encoding="utf-8") as fh:
                    fh.write(xyz_text)
                return FormatConverter_output_schema(
                    is_success=True,
                    output_path=user_input.output_path,
                    message=(
                        f"Detected {engine or 'unknown'} {'+'.join(ordered)}, extracted final frame "
                        f"(frame {last_frame.frame}) from {user_input.input_path} -> "
                        f"{user_input.output_path}. NOTE: an extracted geometry is a coordinate "
                        "artifact only — it does not imply the source job terminated normally, and "
                        "requesting a geometry never validates frequencies/TS."
                    )
                )
        except IndexError:
            # 帧解析链路任何一环对空列表的裸索引都不能漏成 "list index out of range"——
            # 统一翻成有指引的解析失败
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"No key frames could be extracted from {user_input.input_path}: the parser "
                        "hit an empty section (the file is likely truncated or not a valid "
                        "Gaussian/ORCA computation log). Check that the job wrote a complete log; "
                        "you can also inspect it directly with log_parser.",
            )
        except Exception as e:
            return FormatConverter_output_schema(
                is_success=False,
                output_path="",
                message=f"Failed to process log: {str(e)}. "
                        "Check that the input is a valid computational chemistry log; "
                        "you can also read it directly with log_parser."
            )
```


<a id="s100"></a>

### S100 · `FormatConverter.tool_call`

`cloudra/tools/Chemtool/format_converter.py:255–264`

```python
    async def tool_call(self, user_input: FormatConverter_input_schema, session: Session) -> FormatConverter_output_schema:
        # 路径语义收口：相对路径解析到 agent 工作目录（沙箱），与
        # read/write/qm_input_writer 的契约一致。
        user_input.input_path = resolve_tool_path(self, user_input.input_path)
        user_input.output_path = resolve_tool_path(self, user_input.output_path)
        # 0. log 输入或 csv 输出分流（大日志帧提取是同步重活，卸载出事件循环）
        if user_input.input_format == "log" or user_input.output_format == "csv":
            return await asyncio.to_thread(self._convert_log, user_input)

        return await asyncio.to_thread(self._convert_structure, user_input)
```


## `cloudra/tools/Chemtool/log_parser.py`

文件 SHA-256：`77d25c5ee3e95d2e3ca5a1c5ff71ca1ffeff999e6cb261bc95d74428c7cac7c7`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/tools/Chemtool/log_parser.py:30–64`

```python
_AVAILABLE_PROPERTIES = {
    "energy": ["scf_energy_hartree", "scf_energy_ev", "electronic_energy_hartree"],
    "homo_lumo": [
        "homo_ev", "lumo_ev", "homo_lumo_gap_ev",
        "alpha_homo_ev", "alpha_lumo_ev", "beta_homo_ev", "beta_lumo_ev",
        "spin_crossover",
    ],
    "dipole": ["dipole_moment_debye"],
    "frequencies": ["frequencies_cm", "imaginary_frequencies", "imaginary_modes"],
    "thermochemistry": [
        "zero_point_correction_hartree",
        "thermal_energy_correction_hartree",
        "thermal_enthalpy_correction_hartree",
        "thermal_gibbs_correction_hartree",
        "total_zero_point_energy_hartree",
        "total_thermal_energy_hartree",
        "total_enthalpy_hartree",
        "total_gibbs_free_energy_hartree",
        "zero_point_energy_hartree",
        "thermal_energy_hartree",
        "enthalpy_hartree",
        "gibbs_free_energy_hartree",
    ],
    "mulliken_charges": ["mulliken_charges"],
    "convergence": ["normal_termination", "opt_converged"],
    "job_type": ["job_types"],
    "scan": ["scan_parameter", "scan_energies_ev"],
    "irc": [
        "irc_num_points_forward",
        "irc_num_points_backward",
        "irc_rx_coord_range",
        "irc_endpoint_energies_hartree",
        "irc_both_directions_converged",
    ],
}
```


<a id="s101"></a>

### S101 · `LogParser_input_schema`

`cloudra/tools/Chemtool/log_parser.py:67–87`

```python
class LogParser_input_schema(input_schema):
    log_path: str = Field(
        description="Path of the output log (Gaussian .log/.out, ORCA .out, or xtb .out): "
                    "absolute as-is, or relative to the Agent working directory."
    )
    properties: Optional[list[str]] = Field(
        default=None,
        description="Properties to extract. Allowed: "
                    "'energy', 'homo_lumo', 'dipole', 'frequencies', "
                    "'thermochemistry', 'mulliken_charges', 'convergence', "
                    "'job_type' (job-type detection), 'scan' (scan parameters and energy series), "
                    "'irc' (IRC path summary). "
                    "None extracts every available property."
    )
    watch_pairs: Optional[list[list[int]]] = Field(
        default=None,
        description="1-based atom pairs to score each imaginary mode against, "
                    "e.g. the step's declared forming/breaking pairs. When given, each entry of "
                    "imaginary_modes carries watch_pair_fraction (the pairs' share of the total "
                    "pair-projected displacement); ignored when there are no imaginary modes.",
    )
```


<a id="s102"></a>

### S102 · `LogParser_output_schema`

`cloudra/tools/Chemtool/log_parser.py:101–177`

```python
class LogParser_output_schema(output_schema):
    is_success: bool = Field(description="Whether parsing succeeded")
    scf_energy_hartree: Optional[float] = Field(default=None, description="Explicit SCF electronic energy (Hartree), excluding post-HF correlation; None when absent.")
    scf_energy_ev: Optional[float] = Field(default=None, description="Explicit SCF electronic energy (eV), excluding post-HF correlation; None when absent.")
    electronic_energy_hartree: Optional[float] = Field(default=None, description="Last explicitly reported native total electronic energy (Hartree), including correlation when reported; distinct from SCF. Native termination and method completion are checked separately.")
    homo_ev: Optional[float] = Field(default=None, description="HOMO energy (eV); open-shell: max of α/β HOMO (highest SOMO)")
    lumo_ev: Optional[float] = Field(default=None, description="LUMO energy (eV); open-shell: min of α/β LUMO")
    homo_lumo_gap_ev: Optional[float] = Field(default=None, description="HOMO-LUMO gap (eV); None when undecidable (open-shell spin crossover)")
    alpha_homo_ev: Optional[float] = Field(default=None, description="Open-shell only: α-channel HOMO (SOMO) energy (eV)")
    alpha_lumo_ev: Optional[float] = Field(default=None, description="Open-shell only: α-channel LUMO energy (eV)")
    beta_homo_ev: Optional[float] = Field(default=None, description="Open-shell only: β-channel HOMO (SOMO) energy (eV)")
    beta_lumo_ev: Optional[float] = Field(default=None, description="Open-shell only: β-channel LUMO energy (eV)")
    spin_crossover: Optional[bool] = Field(
        default=None,
        description="Open-shell only: True when the lowest virtual orbital lies below the highest "
                    "occupied one — the single-determinant HOMO-LUMO gap is then undecidable (not reported).",
    )
    dipole_moment_debye: Optional[float] = Field(default=None, description="Dipole moment (Debye)")
    frequencies_cm: Optional[list[float]] = Field(default=None, description="Vibrational frequencies (cm⁻¹)")
    imaginary_frequencies: Optional[list[float]] = Field(default=None, description="Imaginary frequencies (cm⁻¹, negative values), used to judge a TS")
    imaginary_modes: Optional[list[dict]] = Field(
        default=None,
        description="Composition summary per imaginary mode (Gaussian/ORCA only): frequency_cm, "
                    "top_displaced_atoms (atom, element, fraction), top_displaced_pairs "
                    "([i, j, projected score], 1-based), heavy_atom_fraction, watch_atom_fraction, and "
                    "watch_pair_fraction when watch_pairs were supplied. Atom fractions use unweighted "
                    "squared displacements, not mass weighting or a scientific pass/fail cutoff. None when normal-mode "
                    "displacements or the final geometry could not be parsed (xtb always None).",
    )
    zero_point_correction_hartree: Optional[float] = Field(default=None, description="Zero-point correction (Hartree)")
    thermal_energy_correction_hartree: Optional[float] = Field(default=None, description="Thermal energy correction (Hartree)")
    thermal_enthalpy_correction_hartree: Optional[float] = Field(default=None, description="Thermal enthalpy correction (Hartree)")
    thermal_gibbs_correction_hartree: Optional[float] = Field(default=None, description="Thermal Gibbs free-energy correction (Hartree)")
    total_zero_point_energy_hartree: Optional[float] = Field(default=None, description="Electronic energy plus ZPE (Hartree)")
    total_thermal_energy_hartree: Optional[float] = Field(default=None, description="Electronic energy plus thermal energy (Hartree)")
    total_enthalpy_hartree: Optional[float] = Field(default=None, description="Electronic energy plus thermal enthalpy (Hartree)")
    total_gibbs_free_energy_hartree: Optional[float] = Field(default=None, description="Electronic energy plus thermal Gibbs free energy (Hartree)")
    zero_point_energy_hartree: Optional[float] = Field(
        default=None,
        description="Compatibility alias of zero_point_correction_hartree (Hartree)",
    )
    thermal_energy_hartree: Optional[float] = Field(
        default=None,
        description="Compatibility alias of thermal_energy_correction_hartree (Hartree)",
    )
    enthalpy_hartree: Optional[float] = Field(
        default=None,
        description="Compatibility alias of total_enthalpy_hartree; this is total enthalpy, not the enthalpy correction (Hartree)",
    )
    gibbs_free_energy_hartree: Optional[float] = Field(
        default=None,
        description="Compatibility alias of total_gibbs_free_energy_hartree; this is total free energy, not the correction (Hartree)",
    )
    mulliken_charges: Optional[dict] = Field(default=None, description="Mulliken charges {atom index: charge}")
    normal_termination: Optional[bool] = Field(default=None, description="Whether the job terminated normally")
    opt_converged: Optional[bool] = Field(
        default=None,
        description="Geometry/TS optimization convergence: True=converged, False=reached max cycles unconverged, "
                    "None=not an optimization or undeterminable. Independent of normal_termination: "
                    "ORCA still terminates normally when an optimization hits the max-cycle limit.",
    )
    engine: Optional[str] = Field(default=None, description="Detected QM program: gaussian / orca / xtb")
    job_types: Optional[list[str]] = Field(default=None, description="Detected job types (subset of opt/ts/freq/scan/irc/sp, sorted)")
    scan_parameter: Optional[list[float]] = Field(default=None, description="Scan parameter series (relaxed PES scan)")
    scan_energies_ev: Optional[list[float]] = Field(default=None, description="Energy at each scan point (eV)")
    scan_has_internal_peak: bool | None = Field(
        default=None, description="Automatically reported for recognized scans: an internal maximum exists; null if not established."
    )
    scan_peak: ScanPeak | None = Field(
        default=None, description="Internal scan maximum and existing geometry: a seed for refinement, not an accepted TS."
    )
    irc_num_points_forward: Optional[int] = Field(default=None, description="IRC forward-path point count (excluding TS)")
    irc_num_points_backward: Optional[int] = Field(default=None, description="IRC reverse-path point count (excluding TS)")
    irc_rx_coord_range: Optional[list[float]] = Field(default=None, description="IRC reaction-coordinate range [min, max]")
    irc_endpoint_energies_hartree: Optional[list[float]] = Field(default=None, description="IRC endpoint energies (Hartree), ordered by reaction coordinate")
    irc_both_directions_converged: Optional[bool] = Field(default=None, description="Whether both IRC directions converged to a minimum")
    message: str = Field(default="", description="Status or error message")
```


<a id="s103"></a>

### S103 · `LogParser._resolve_requested_fields`

`cloudra/tools/Chemtool/log_parser.py:190–205`

```python
    @staticmethod
    def _resolve_requested_fields(properties: Optional[list[str]]) -> set[str]:
        """根据用户请求的属性列表，返回需要填充的输出字段集合。"""
        if not properties:
            # 默认提取全部
            fields = set()
            for flds in _AVAILABLE_PROPERTIES.values():
                fields.update(flds)
            return fields

        fields = set()
        for prop in properties:
            prop = prop.lower().strip()
            if prop in _AVAILABLE_PROPERTIES:
                fields.update(_AVAILABLE_PROPERTIES[prop])
        return fields
```


<a id="s104"></a>

### S104 · `LogParser.tool_call`

`cloudra/tools/Chemtool/log_parser.py:207–223`

```python
    async def tool_call(self, user_input: LogParser_input_schema, session: Session) -> LogParser_output_schema:
        # 路径语义收口：相对路径解析到 agent 工作目录（沙箱）。
        user_input.log_path = resolve_tool_path(self, user_input.log_path)
        log_path = user_input.log_path

        # 1. 校验日志文件是否存在
        if not os.path.isfile(log_path):
            return LogParser_output_schema(
                is_success=False,
                message=f"Log file not found: {log_path}. "
                        "Check the path, or locate the log with query_compute_job, then retry."
            )

        requested = self._resolve_requested_fields(user_input.properties)
        # 大日志的 cclib 解析与文本回退是分钟级同步 CPU 工作，整条流水线
        # 卸载出事件循环，避免冻结整个 API。
        return await asyncio.to_thread(self._parse_log, log_path, requested, user_input.watch_pairs)
```


<a id="s105"></a>

### S105 · `LogParser._parse_log`

`cloudra/tools/Chemtool/log_parser.py:225–457`

```python
    def _parse_log(self, log_path: str, requested: set[str], watch_pairs: Optional[list[list[int]]] = None) -> LogParser_output_schema:
        """同步解析流水线主体（cclib + ORCA/xtb 文本回退）；只经 to_thread 调用。"""
        try:
            import numpy as np

            from cloudra.tools.core import gaussian_frames, orca_frames, xtb_frames
            from cloudra.tools.core.qm_log_facts import read_qm_log

            facts = read_qm_log(log_path)
            engine, log_text, data = facts.engine, facts.text, facts.parser_data
            detected_jobs = facts.job_types
            if data is None and engine == "unknown":
                return LogParser_output_schema(
                    is_success=False,
                    message=f"No recognized native QM output or parser data in: {log_path}."
                )

            result: dict[str, Any] = {"is_success": True, "message": "Log parsed successfully.", "engine": engine}
            if data is None:
                if engine == "xtb":
                    result["message"] = (
                        "xtb logs are parsed by text extraction (tools.core.xtb_frames); "
                        "cclib is not consulted for this engine."
                    )
                else:
                    result["message"] = (
                        "The optional cclib parser could not read this log; "
                        "available native output facts were retained."
                    )

            # 3. 根据请求填充字段
            if {"scf_energy_hartree", "scf_energy_ev"} & requested:
                if facts.scf_energy_hartree is not None:
                    result["scf_energy_hartree"] = facts.scf_energy_hartree
                    result["scf_energy_ev"] = facts.scf_energy_hartree * 27.211386245988
            if "electronic_energy_hartree" in requested:
                result["electronic_energy_hartree"] = facts.electronic_energy_hartree

            if {
                "homo_ev", "lumo_ev", "homo_lumo_gap_ev",
                "alpha_homo_ev", "alpha_lumo_ev", "beta_homo_ev", "beta_lumo_ev",
                "spin_crossover",
            } & requested:
                if (
                    data is not None
                    and getattr(data, "moenergies", None) is not None
                    and getattr(data, "homos", None) is not None
                    and len(data.moenergies) > 0
                ):
                    # 与 electronic_analysis 共用同一套前线轨道原语：开壳层报
                    # α/β 两套 HOMO/LUMO（SOMO 语义），自旋交叉时 gap 不可判定。
                    homos = [int(h) for h in np.asarray(data.homos).ravel()]
                    if len(data.moenergies) == len(homos):
                        frontier = frontier_orbital_summary(
                            [list(mo) for mo in data.moenergies],
                            [h + 1 for h in homos],  # cclib homos 是 0-based 索引
                        )
                        if frontier["homo"] is not None:
                            result["homo_ev"] = frontier["homo"]
                        if frontier["lumo"] is not None:
                            result["lumo_ev"] = frontier["lumo"]
                        if frontier["gap"] is not None:
                            result["homo_lumo_gap_ev"] = frontier["gap"]
                        if frontier["open_shell"]:
                            result["alpha_homo_ev"] = frontier["alpha"]["homo"]
                            result["alpha_lumo_ev"] = frontier["alpha"]["lumo"]
                            result["beta_homo_ev"] = frontier["beta"]["homo"]
                            result["beta_lumo_ev"] = frontier["beta"]["lumo"]
                            result["spin_crossover"] = (
                                frontier["gap_status"] == GAP_UNDECIDABLE_SPIN_CROSSOVER
                            )
                            if result["spin_crossover"]:
                                result["message"] += (
                                    " Open-shell spin crossover: the lowest virtual orbital lies "
                                    "below the highest occupied one (max α/β HOMO above min α/β LUMO), "
                                    "so the HOMO-LUMO gap is undecidable for this single determinant "
                                    "and is not reported."
                                )
                    # moenergies/homos 通道数不一致是上游解析异常：不发任何前线
                    # 轨道字段（不可判定），绝不猜一个通道的值。
                elif engine == "xtb":
                    # xtb：cclib 对其日志解析不可靠，gap 从 SUMMARY 块文本回退
                    gap = xtb_frames.homo_lumo_gap_ev(log_text)
                    if gap is not None:
                        result["homo_lumo_gap_ev"] = gap

            if "dipole_moment_debye" in requested:
                if hasattr(data, "moments") and data.moments is not None and len(data.moments) >= 2:
                    # moments[1] 为偶极矩向量 (Debye)
                    dipole_vec = np.asarray(data.moments[1], dtype=float)
                    result["dipole_moment_debye"] = float(np.linalg.norm(dipole_vec))
                elif engine == "xtb":
                    # xtb：Property Printout 的 "full:" 行第四列（Debye）
                    dipole = xtb_frames.dipole_debye(log_text)
                    if dipole is not None:
                        result["dipole_moment_debye"] = dipole

            if {"frequencies_cm", "imaginary_frequencies"} & requested:
                vibfreqs = facts.frequencies_cm
                if vibfreqs is not None:
                    # 虚频保留负号（负值=虚频是 frames 原语与下游 DAG/benchmark
                    # 的原生语义）；frequencies_cm 只存非负实频。
                    result["frequencies_cm"] = [f for f in vibfreqs if f >= 0]
                    result["imaginary_frequencies"] = [f for f in vibfreqs if f < 0]
                    if (
                        "imaginary_modes" in requested
                        and result["imaginary_frequencies"]
                        and engine in ("orca", "gaussian")
                    ):
                        # 位移与末帧几何一律走文本权威通道（ORCA 6.1 日志 cclib
                        # 整体崩溃）；拿不到位移或几何时 imaginary_modes 保持 None。
                        from cloudra.tools.core.mode_analysis import imaginary_mode_summaries_from_text
                        modes = imaginary_mode_summaries_from_text(engine, log_text, vibfreqs, watch_pairs)
                        if modes:
                            result["imaginary_modes"] = modes

            thermo_fields = set(_AVAILABLE_PROPERTIES["thermochemistry"])
            if thermo_fields & requested:
                if engine in ("gaussian", "orca"):
                    thermo = facts.thermochemistry
                elif engine == "xtb":
                    # xtb：THERMODYNAMIC 块/最终块文本（cclib 热化学对 xtb 是
                    # 荒谬值，永不作为数据源）
                    thermo = xtb_frames.thermochemistry(log_text)
                else:
                    # 未知引擎：无热化学提取路径，留空
                    thermo = {}

                aliases = {
                    "zero_point_energy_hartree": "zero_point_correction_hartree",
                    "thermal_energy_hartree": "thermal_energy_correction_hartree",
                    "enthalpy_hartree": "total_enthalpy_hartree",
                    "gibbs_free_energy_hartree": "total_gibbs_free_energy_hartree",
                }
                for field in thermo_fields:
                    if field in requested and field in thermo:
                        result[field] = thermo[field]
                for alias, canonical in aliases.items():
                    if alias in requested and canonical in thermo:
                        result[alias] = thermo[canonical]

            if "mulliken_charges" in requested:
                if hasattr(data, "atomcharges") and data.atomcharges is not None:
                    mulliken = data.atomcharges.get("mulliken")
                    if mulliken is not None:
                        result["mulliken_charges"] = {
                            str(i + 1): float(charge)
                            for i, charge in enumerate(mulliken)
                        }

            if "normal_termination" in requested:
                result["normal_termination"] = facts.normal_termination
            if "opt_converged" in requested:
                result["opt_converged"] = facts.opt_converged

            # job_type / scan / irc 摘要（Gaussian IRC 逐点解析在 core.gaussian_frames 自写；
            # ORCA 侧由 core.orca_frames.extract_irc 从主输出的 FORWARD/BACKWARD
            # IRC 迭代块与 PATH SUMMARY 提取点数/收敛/端点能量）
            if "job_types" in requested:
                result["job_types"] = sorted(detected_jobs)

            if {"scan_parameter", "scan_energies_ev"} & requested:
                scanparm = getattr(data, "scanparm", None)
                scanenergies = getattr(data, "scanenergies", None)
                if scanparm is not None and len(scanparm) > 0:
                    result["scan_parameter"] = [float(v) for v in np.asarray(scanparm[0], dtype=float)]
                if scanenergies is not None and len(scanenergies) > 0:
                    result["scan_energies_ev"] = [float(v) for v in np.asarray(list(scanenergies), dtype=float)]

            if "scan" in detected_jobs and engine in {"orca", "gaussian"}:
                from cloudra.tools.Chemtool.ts_guess import _ScanStepsUngroupable, _SidecarIncomplete

                try:
                    scan = self._scan_summary(log_path, engine, log_text)
                    result["message"] += " " + scan.pop("message")
                    result.update(scan)
                except (ValueError, _ScanStepsUngroupable, _SidecarIncomplete) as exc:
                    result["message"] += f" Scan peak could not be established: {exc}"

            if any(f.startswith("irc_") for f in requested):
                if engine == "orca":
                    if "irc" in detected_jobs:
                        try:
                            irc_meta = orca_frames.extract_irc_from_text(log_text)
                            result["irc_num_points_forward"] = irc_meta["num_points_forward"]
                            result["irc_num_points_backward"] = irc_meta["num_points_backward"]
                            if irc_meta["endpoint_energies_hartree"] is not None:
                                result["irc_endpoint_energies_hartree"] = [
                                    float(v) for v in irc_meta["endpoint_energies_hartree"]
                                ]
                            result["irc_both_directions_converged"] = bool(
                                irc_meta["forward_converged"] and irc_meta["backward_converged"]
                            )
                        except ValueError as e:
                            result["message"] = f"Log parsed; ORCA IRC extraction failed: {e}"
                elif engine == "gaussian" and "irc" in detected_jobs:
                    try:
                        _irc_frames, irc_meta = gaussian_frames.extract_irc_from_text(log_text)
                        result["irc_num_points_forward"] = irc_meta["num_points_forward"]
                        result["irc_num_points_backward"] = irc_meta["num_points_backward"]
                        if irc_meta["rx_coord_range"] is not None:
                            result["irc_rx_coord_range"] = [float(v) for v in irc_meta["rx_coord_range"]]
                        if irc_meta["endpoint_energies_hartree"] is not None:
                            result["irc_endpoint_energies_hartree"] = [
                                float(v) for v in irc_meta["endpoint_energies_hartree"]
                            ]
                        result["irc_both_directions_converged"] = bool(
                            irc_meta["forward_converged"] and irc_meta["backward_converged"]
                        )
                    except ValueError as e:
                        result["message"] = f"Log parsed; IRC summary extraction failed: {e}"

            return LogParser_output_schema(**result)

        except FileNotFoundError:
            return LogParser_output_schema(
                is_success=False,
                message=f"Log file not found: {log_path}. "
                        "Check the path, or locate the log with query_compute_job, then retry."
            )
        except ImportError as e:
            return LogParser_output_schema(
                is_success=False,
                message=f"Required parser library is not installed: {str(e)}. "
                        "Install it with: pip install 'cloudra[chem]', then retry."
            )
        except Exception as e:
            return LogParser_output_schema(
                is_success=False,
                message=f"Failed to parse the log: {str(e)}. "
                        f"Check that {log_path} is a valid, complete log file; "
                        "if the job crashed, inspect the log tail for the cause."
            )
```


## `cloudra/tools/Chemtool/qm_input_writer.py`

文件 SHA-256：`a6cc94fbbfe8608d09f666a80e1b6a533c711df443680119c625c86c41190bc3`


<a id="s106"></a>

### S106 · `StructureBuildRefused`

`cloudra/tools/Chemtool/qm_input_writer.py:39–47`

```python
class StructureBuildRefused(Exception):
    """SMILES → 坐标 由共享构建器拒绝（带显式构建状态，不冒充路径/参数错误）。"""

    def __init__(self, status: str, message: str, diagnostics: list[str], artifact_path: str):
        super().__init__(message)
        self.status = status
        self.message = message
        self.diagnostics = diagnostics
        self.artifact_path = artifact_path
```


<a id="s107"></a>

### S107 · `QmInputWriter_input_schema`

`cloudra/tools/Chemtool/qm_input_writer.py:61–164`

```python
class QmInputWriter_input_schema(QmCalculation, QmInputSettings, input_schema):
    engine: Literal["gaussian", "orca"] = Field(
        description="Target QM program. 'gaussian': write a .gjf (submit with job_type='gaussian'); "
                    "'orca': write a .inp (submit with job_type='orca'). "
                    "task_type and known basis aliases map onto each program's input syntax; "
                    "method and additional keywords must use that program's native spelling.",
    )
    source_type: Literal["smiles", "xyz_file", "mol_file"] = Field(
        description="Molecular-structure source type. "
                    "'smiles': generate 3D coordinates from a SMILES string; "
                    "'xyz_file': read coordinates from a .xyz file; "
                    "'mol_file': read coordinates from a .mol file."
    )
    source_value: str = Field(
        description="Molecular-structure source value. "
                    "When source_type='smiles', a SMILES string (e.g. 'CC(=O)O'); "
                    "when source_type='xyz_file' or 'mol_file', the file's path — "
                    "absolute as-is, or relative to the Agent working directory."
    )
    external_program: Optional[str] = Field(
        default=None,
        description="Explicit external MLIP route: declare method='ExtOpt' for ORCA or 'external' "
                    "for Gaussian, and basis_set=''. ORCA: absolute path of the "
                    "ProgExt executable — emits '! ExtOpt <tasks>' plus a %method ProgExt block, "
                    "e.g. '/opt/conda/envs/chemai/bin/mace'; the file must exist, be executable, "
                    "and live outside the working directory/data dir. Gaussian: engine value of the "
                    "external=\"...\" route keyword, e.g. 'mace' — a single [a-z0-9_.-] token, no "
                    "spaces or program arguments (they would bypass method-policy parsing)."
    )
    external_params: Optional[str] = Field(
        default=None,
        description="ORCA only, requires external_program: Ext_Params string handed to the external "
                    "program, e.g. '--model /abs/model --device cpu --dtype float64'. For Gaussian, "
                    "fold program arguments into external_program instead."
    )
    task_type: list[dict] = Field(
        default=[{"opt": None}],
        description='''List of dicts whose keys are job types and values are their parameters.
                    Common aliases: opt/freq/irc/single_point ('sp' is equivalent); other native task keys are preserved.
                    Gaussian example: [{"opt":"TS,readfc"},{"freq":None}]. ORCA opt='ts' maps to OptTS;
                    Gaussian-specific suboptions are preserved with warnings, not silently translated.
                    Use native keywords and orca_blocks for ORCA controls. Gaussian scan is rigid;
                    relaxed scans use opt=modredundant and end_setting, or ts_guess scan_prepare.'''
    )
    frequency_mode: Literal["auto", "analytic", "numeric"] = Field(
        default="auto",
        description="Frequency evaluation mode. ORCA: 'numeric' with task_type=[{'freq':None}] "
                    "emits NumFreq (required for external potentials); 'analytic'/'auto' emit Freq. "
                    "Warns when no frequency task is requested; explicit native evaluation options take precedence.",
    )

    orca_blocks: Optional[str] = Field(
        default=None,
        description="ORCA-only: raw % block lines inserted between the `!` line and the coordinate "
                    "block, e.g. '%geom MaxIter 200 end'. Scans use ts_guess mode='scan_prepare'. "
                    "Native atom indices are 0-based and refer to the exact XYZ order including explicit H. "
                    "For a SMILES source, use the generated build's "
                    "prepared_structure.json atom_identities, not SMILES heavy-atom positions. "
                    "For Gaussian this text is preserved in the trailing section with a warning."
    )
    title: str = Field(
        default="Gaussian job generated by Cloudra",
        description="Job title (Gaussian title line; ORCA has no title card — emitted as a comment)."
    )
    end_setting: str = Field(
        default="",
        description="Extra settings appended at the end of the file, e.g. mixed basis or scan setup. "
                    "Example: B 1 34 S 15 0.02"
    )
    output_path: str = Field(
        description="Path of the Gaussian .gjf or ORCA .inp file (including filename): absolute as-is, "
                    "or relative to the Agent working directory."
    )
    artifact_dir: Optional[str] = Field(
        default=None,
        description="Directory for the SMILES-source build artifacts (per-component structures, "
                    "optimization trajectories, prepared_structure.json). Default: "
                    "'<output_path parent>/structure_build/<stem>/' next to the generated input file. "
                    "Relative paths resolve against the Agent working directory."
    )
    chk_name: Optional[str] = Field(
        default=None,
        description="Gaussian checkpoint path. Omit to generate an absolute '<output stem>.chk' "
                    "next to output_path. Explicit paths are absolute as-is or relative to the Agent "
                    "working directory, like output_path; their parent directories are created before writing."
    )
    rwf_name: Optional[str] = Field(
        default=None,
        description="Gaussian scratch file path, often large. Absolute as-is or relative to the Agent "
                    "working directory; its parent directory is created before writing the input."
    )
    fchk_name: Optional[str] = Field(
        default=None,
        description="Gaussian formatted-checkpoint path. Absolute as-is or relative to the Agent "
                    "working directory; its parent directory is created before writing the input."
    )

    @model_validator(mode='after')
    def explicit_external_route(self):
        if self.external_program:
            required = 'extopt' if self.engine == 'orca' else 'external'
            if self.method.casefold() != required or self.basis_set:
                raise ValueError(f"external_program requires method='{required}' and basis_set='' for {self.engine}")
        return self
```


<a id="s108"></a>

### S108 · `QmInputWriter_output_schema`

`cloudra/tools/Chemtool/qm_input_writer.py:167–188`

```python
class QmInputWriter_output_schema(output_schema):
    is_success: bool = Field(description="Whether the file was generated")
    input_path: str = Field(default="", description="Absolute path of the generated input file (.gjf or .inp, per `engine`)")
    message: str = Field(default="", description="Status or error message")
    calculation: QmCalculation | None = Field(default=None,
        description="Complete calculation settings written to the returned input, including explicit external route settings; file generation is not a scientific result.")
    interpreted_intent: dict = Field(
        default_factory=dict,
        description="CalculationIntent re-inspected from the GENERATED text (not from the "
                    "writer's own claim): tasks, frequency_mode, constraints, method signature.",
    )
    unapplied_options: list[str] = Field(
        default_factory=list,
        description="Options missing from, or unexpectedly added to, the generated file. Empty on success; "
                    "a successful write never silently drops an option.",
    )
    generation_path: str = Field(
        default="",
        description="How the file was produced, e.g. 'orca:simple+orca_blocks' or 'gaussian:route'.",
    )
    warnings: list[dict] = Field(default_factory=list,
        description="Calculation-option advice visible to the calling model; native settings are preserved.")
```


<a id="s109"></a>

### S109 · `QmInputWriter._coordinate_lines`

`cloudra/tools/Chemtool/qm_input_writer.py:257–262`

```python
    @staticmethod
    def _coordinate_lines(mol) -> str:
        """Render coordinates only at the native input-writing boundary."""
        if not all(math.isfinite(value) for position in mol.GetConformer().GetPositions() for value in position):
            raise ValueError("Source coordinates must be finite numbers")
        return "\n".join(to_xyz(mol).splitlines()[2:])
```


<a id="s110"></a>

### S110 · `QmInputWriter._get_molecule`

`cloudra/tools/Chemtool/qm_input_writer.py:308–325`

```python
    @staticmethod
    def _get_molecule(user_input: QmInputWriter_input_schema, artifact_dir: str):
        """Read or build a molecule; coordinate files remain an output boundary."""
        if user_input.source_type == "smiles":
            return QmInputWriter._smiles_molecule(user_input, artifact_dir)

        fmt = "xyz" if user_input.source_type == "xyz_file" else "mol"
        try:
            mol = read_molecule(input_path=user_input.source_value, input_format=fmt, charge=user_input.charge)
        except FileNotFoundError:
            raise
        except Exception as exc:
            hint = ("If it contains an MDL MOL block, use source_type='mol_file'." if fmt == "xyz" else
                    "Provide an MDL MOL file or use source_type='xyz_file' for XYZ coordinates.")
            raise ValueError(
                f"{fmt.upper()} source could not be read: {exc}. {hint}"
            ) from exc
        return mol, ""
```


<a id="s111"></a>

### S111 · `QmInputWriter._build_link0`

`cloudra/tools/Chemtool/qm_input_writer.py:327–341`

```python
    @staticmethod
    def _build_link0(user_input: QmInputWriter_input_schema) -> str:
        """拼装 Link0 段。"""
        parts = []
        link0_map = {
            "chk": user_input.chk_name,
            "rwf": user_input.rwf_name,
            "fchk": user_input.fchk_name,
            "nproc": user_input.nproc,
            "mem": user_input.mem,
        }
        for key, value in link0_map.items():
            if value:
                parts.append(f"%{key}={value}")
        return "\n".join(parts)
```


<a id="s112"></a>

### S112 · `QmInputWriter._gaussian_task_keywords`

`cloudra/tools/Chemtool/qm_input_writer.py:343–367`

```python
    @staticmethod
    def _gaussian_task_keywords(user_input: QmInputWriter_input_schema) -> list[str]:
        """Render task aliases while retaining every explicit native suboption."""
        keywords = []
        for task in user_input.task_type:
            for key, value in task.items():
                key_l = key.lower()
                if key_l == 'single_point':
                    key_l = 'sp'
                if key_l == 'scan' and str(value).strip().lower() == 'rigid':
                    keywords.append('scan')
                elif key_l == 'freq' and user_input.frequency_mode != 'auto':
                    mode = 'numer' if user_input.frequency_mode == 'numeric' else 'analytic'
                    options = str(value) if value is not None else ''
                    declared_modes = {'num', 'numer', 'numeric', 'numfreq', 'analytic'}
                    if not declared_modes & {option.strip().lower() for option in options.split(',')}:
                        options = ','.join(filter(None, [mode, options]))
                    keywords.append(f'freq=({options})' if ',' in options else f'freq={options}')
                elif value is None:
                    keywords.append(key_l)
                elif ',' in str(value):
                    keywords.append(f'{key_l}=({value})')
                else:
                    keywords.append(f'{key_l}={value}')
        return keywords
```


<a id="s113"></a>

### S113 · `QmInputWriter._build_route`

`cloudra/tools/Chemtool/qm_input_writer.py:369–381`

```python
    @staticmethod
    def _build_route(user_input: QmInputWriter_input_schema) -> str:
        """Build a native Gaussian route without replacing explicit parameters."""
        keywords = ['#p', *QmInputWriter._gaussian_task_keywords(user_input)]
        if user_input.external_program:
            keywords.append(f'external="{user_input.external_program}"')
        elif user_input.basis_set:
            keywords.append(f'{user_input.method}/{gaussian_basis_keyword(user_input.basis_set)}')
        else:
            keywords.append(user_input.method)
        if user_input.keywords:
            keywords.append(user_input.keywords)
        return ' '.join(keywords)
```


<a id="s114"></a>

### S114 · `QmInputWriter._orca_memory_mb`

`cloudra/tools/Chemtool/qm_input_writer.py:387–409`

```python
    @staticmethod
    def _orca_memory_mb(mem: str) -> float:
        """显式解析当前支持的总内存单位；非法值不能静默省略 %maxcore。"""
        text = mem.strip().lower()
        for unit, multiplier in (("gb", 1024), ("mb", 1), ("g", 1024), ("m", 1)):
            if not text.endswith(unit):
                continue
            number = text[:-len(unit)].strip()
            integer, dot, fraction = number.partition(".")
            digits = integer + fraction
            if (
                not integer or (dot and not fraction)
                or not digits.isascii() or not digits.isdecimal()
            ):
                break
            amount = float(number) * multiplier
            if math.isfinite(amount) and amount > 0:
                return amount
            break
        raise ValueError(
            f"ORCA mem {mem!r} must be a positive finite amount in MB/GB (or M/G), "
            "for example '4096MB' or '4GB'"
        )
```


<a id="s115"></a>

### S115 · `QmInputWriter._orca_resource_lines`

`cloudra/tools/Chemtool/qm_input_writer.py:411–416`

```python
    @staticmethod
    def _orca_resource_lines(mem: str, nproc: int) -> list[str]:
        """ORCA uses MB per process; keep the existing total-budget division."""
        mb = QmInputWriter._orca_memory_mb(mem)
        per_core = int(mb / nproc)
        return [f"%pal nprocs {nproc} end", f"%maxcore {per_core}"]
```


<a id="s116"></a>

### S116 · `QmInputWriter._orca_task_keywords`

`cloudra/tools/Chemtool/qm_input_writer.py:418–446`

```python
    @staticmethod
    def _orca_task_keywords(task_type: list[dict], frequency_mode: str = 'auto') -> list[str]:
        """Translate task aliases; preserve other explicitly declared text."""
        keywords = []
        for task in task_type:
            for key, value in task.items():
                key_l = key.lower()
                params = str(value) if value is not None else ''
                options = [part.strip() for part in params.split(',') if part.strip()]
                if key_l == 'opt':
                    keyword = 'OptTS' if 'ts' in {part.lower() for part in options} else 'Opt'
                    remainder = ','.join(part for part in options if part.lower() != 'ts')
                elif key_l == 'freq':
                    numeric_aliases = {'num', 'numer', 'numeric', 'numfreq'}
                    native_modes = {part.lower() for part in options} & (numeric_aliases | {'analytic'})
                    numeric = bool(native_modes & numeric_aliases) if native_modes else frequency_mode == 'numeric'
                    keyword = 'NumFreq' if numeric else 'Freq'
                    remainder = ','.join(part for part in options if part.lower() not in numeric_aliases | {'analytic'})
                elif key_l == 'irc':
                    keyword, remainder = 'IRC', params
                elif key_l in ('sp', 'single_point'):
                    keyword, remainder = 'SP', params
                else:
                    keyword = key if value is None else f'{key}=({params})' if ',' in params else f'{key}={params}'
                    remainder = ''
                keywords.append(keyword)
                if remainder:
                    keywords.append(remainder)
        return keywords
```


<a id="s117"></a>

### S117 · `QmInputWriter._written_calculation`

`cloudra/tools/Chemtool/qm_input_writer.py:457–473`

```python
    @staticmethod
    def _written_calculation(user_input: QmInputWriter_input_schema) -> QmCalculation:
        values = user_input.model_dump(include=set(QmCalculation.model_fields))
        tasks = (QmInputWriter._orca_task_keywords(user_input.task_type, user_input.frequency_mode)
                 if user_input.engine == 'orca' else QmInputWriter._gaussian_task_keywords(user_input))
        values['keywords'] = ' '.join([*tasks, *filter(None, [user_input.keywords])])
        if user_input.external_program:
            if user_input.engine == 'orca':
                values['orca_blocks'] = '\n'.join(filter(None, [
                    QmInputWriter._external_method_block(user_input), user_input.orca_blocks]))
            else:
                values['keywords'] = ' '.join(filter(None, [
                    f'external="{user_input.external_program}"', values['keywords']]))
        native_mode = intent_from_writer({**values, 'task_type': [], 'frequency_mode': 'auto'}).frequency_mode
        if native_mode != 'auto':
            values['frequency_mode'] = native_mode
        return QmCalculation.model_validate(values)
```


<a id="s118"></a>

### S118 · `QmInputWriter.validate_rendered_input`

`cloudra/tools/Chemtool/qm_input_writer.py:475–508`

```python
    @staticmethod
    def validate_rendered_input(user_input: QmInputWriter_input_schema, content: str, *, charge: int) -> list[str]:
        """Detect renderer data loss independently of native option advice."""
        advice = validate_writer_request(user_input.model_dump())
        indeterminate = any(entry['code'].startswith('malformed_native') for entry in advice)
        inspected = inspect_input(content, engine=user_input.engine)
        requested = intent_from_writer(user_input.model_dump())
        details = []
        if inspected.tasks != requested.tasks and not indeterminate:
            details.append(f'the generated file encodes tasks {sorted(inspected.tasks)} but {sorted(requested.tasks)} were requested')
        calculation = QmInputWriter._written_calculation(user_input)
        differences = compare_calculation_input(content, calculation.model_dump(),
            charge=charge, multiplicity=user_input.multiplicity)
        native_layout = any(entry['code'] in {'native_method_layout', 'native_basis_layout'} for entry in advice)
        for difference in differences:
            if difference.field == 'parse' and indeterminate:
                continue
            if difference.field in {'method', 'keywords'} and native_layout:
                continue
            details.append(difference.message)
        for field in ('keywords', 'orca_blocks', 'end_setting', 'method'):
            value = getattr(user_input, field)
            if value and value.strip() not in content:
                details.append(f'{field} was lost during rendering')
        basis = (orca_basis_keyword(user_input.basis_set) if user_input.engine == 'orca'
                 else gaussian_basis_keyword(user_input.basis_set))
        if basis and basis not in content:
            details.append('basis_set was lost during rendering')
        task_tokens = (QmInputWriter._orca_task_keywords(user_input.task_type, user_input.frequency_mode)
                       if user_input.engine == 'orca' else QmInputWriter._gaussian_task_keywords(user_input))
        for token in task_tokens:
            if token.lower() not in content.lower():
                details.append(f'task_type token {token!r} was lost during rendering')
        return details
```


<a id="s119"></a>

### S119 · `QmInputWriter._build_orca_input`

`cloudra/tools/Chemtool/qm_input_writer.py:510–550`

```python
    @staticmethod
    def _build_orca_input(user_input: QmInputWriter_input_schema, mol) -> str:
        """拼装 ORCA .inp：! 行 + %pal/%maxcore（+%method 外部势块）+ 坐标块。"""
        simple = QmInputWriter._orca_task_keywords(user_input.task_type, user_input.frequency_mode)
        method_block = ""
        if user_input.external_program:
            # 外部 MLIP 路由：ExtOpt 把能量/梯度交给外部程序，输入不含
            # method/basis（外部势没有基组概念），GH #16
            simple.insert(0, "ExtOpt")
            method_block = QmInputWriter._external_method_block(user_input)
        else:
            if user_input.method:
                simple.append(user_input.method)
            if user_input.basis_set:
                simple.append(orca_basis_keyword(user_input.basis_set))
        if user_input.keywords:
            simple.append(user_input.keywords)

        lines = []
        default_title = QmInputWriter_input_schema.model_fields["title"].default
        if user_input.title and user_input.title != default_title:
            lines.append(f"# {user_input.title}")
        if user_input.source_type == "smiles":
            lines.append(
                f"# expected_smiles: {user_input.source_value} "
                "(user-declared expectation; NOT an evidence-verified identity)"
            )
        lines.append("! " + " ".join(simple))
        lines.extend(QmInputWriter._orca_resource_lines(user_input.mem, user_input.nproc))
        if method_block:
            lines.append(method_block)
        if user_input.orca_blocks:
            lines.append(user_input.orca_blocks.strip())

        lines.append(f"* xyz {total_charge(mol)} {user_input.multiplicity}")
        lines.append(QmInputWriter._coordinate_lines(mol))
        lines.append("*")
        if user_input.end_setting:
            lines.append(user_input.end_setting)
        lines.append("")
        return "\n".join(lines)
```


<a id="s120"></a>

### S120 · `QmInputWriter._build_gjf`

`cloudra/tools/Chemtool/qm_input_writer.py:552–596`

```python
    @staticmethod
    def _build_gjf(user_input: QmInputWriter_input_schema, mol) -> str:
        """拼装完整的 .gjf 文本。

        Gaussian 要求坐标块后有一个空行作为输入结束标记，
        因此末尾统一保留一个空行。
        """
        link0 = QmInputWriter._build_link0(user_input)
        route = QmInputWriter._build_route(user_input)
        from ase.units import Bohr

        from cloudra.tools.core.native_input_sections import gaussian_coordinate_units, gaussian_sections

        coordinates = QmInputWriter._coordinate_lines(mol)
        units = gaussian_coordinate_units(gaussian_sections(route)[0].route)
        if units == 'bohr':
            coordinates = '\n'.join(f'{atom.GetSymbol():<4} {point[0] / Bohr:14.8f} {point[1] / Bohr:14.8f} {point[2] / Bohr:14.8f}'
                for atom, point in zip(mol.GetAtoms(), mol.GetConformer().GetPositions(), strict=True))
        title = user_input.title
        if user_input.source_type == "smiles":
            # provenance：声明的期望身份，不是证据验证过的身份（GH 协议：
            # 只有 evidence 绑定能证明身份，写注释不产生 verified 标签）
            title = (
                f"{title} | expected_smiles: {user_input.source_value} "
                "(unverified expectation)"
            )

        sections = [
            link0,
            route,
            "",                    # Route 后空行
            title,
            "",                    # Title 后空行
            f"{total_charge(mol)} {user_input.multiplicity}",
            coordinates,
            "",                    # 坐标后空行（Gaussian 输入结束标记）
        ]

        if user_input.end_setting:
            # 坐标块先以空行结束，再写扫描坐标或其他尾部设置。
            sections.extend([user_input.end_setting, ""])
        if user_input.orca_blocks:
            sections.extend([user_input.orca_blocks, ""])

        return "\n".join(sections) + "\n"
```


<a id="s121"></a>

### S121 · `QmInputWriter.render_input`

`cloudra/tools/Chemtool/qm_input_writer.py:598–610`

```python
    @staticmethod
    def render_input(user_input: QmInputWriter_input_schema, mol) -> str:
        """Render native input from the owned molecule and declared input settings."""
        if (user_input.charge is None and mol.HasProp('cloudra_graph_status')
                and mol.GetProp('cloudra_graph_status') == 'unresolved'):
            raise ValueError('XYZ calculation input requires an explicit total charge; declare charge=0 for neutral')
        if user_input.engine == 'orca':
            return QmInputWriter._build_orca_input(user_input, mol)
        if user_input.chk_name is None:
            user_input = user_input.model_copy(update={
                'chk_name': str(Path(user_input.output_path).resolve().with_suffix('.chk')),
            })
        return QmInputWriter._build_gjf(user_input, mol)
```


<a id="s122"></a>

### S122 · `QmInputWriter._prepare_gaussian_file_parents`

`cloudra/tools/Chemtool/qm_input_writer.py:612–635`

```python
    @staticmethod
    def _prepare_gaussian_file_parents(user_input: QmInputWriter_input_schema) -> None:
        """Prepare file destinations without opening or replacing existing QM artifacts."""
        paths = {
            'chk_name': user_input.chk_name if user_input.chk_name is not None else str(Path(user_input.output_path).with_suffix('.chk')),
            'rwf_name': user_input.rwf_name,
            'fchk_name': user_input.fchk_name,
        }
        for field, value in paths.items():
            if value is None:
                continue
            if not value.strip():
                raise ValueError(f'{field} must be a non-empty file path, or omitted')
            path = Path(value)
            try:
                if path.exists() and not path.is_file():
                    raise ValueError(f'{field} {path} is not a regular file destination')
                path.parent.mkdir(parents=True, exist_ok=True)
                if not os.access(path.parent, os.W_OK | os.X_OK):
                    raise ValueError(f'{field} {path}: parent directory {path.parent} is not writable')
                if path.exists() and not os.access(path, os.W_OK):
                    raise ValueError(f'{field} {path} is not writable')
            except OSError as exc:
                raise ValueError(f'{field} {path}: cannot prepare its parent directory: {exc}') from exc
```


<a id="s123"></a>

### S123 · `QmInputWriter.tool_call`

`cloudra/tools/Chemtool/qm_input_writer.py:637–864`

```python
    async def tool_call(self, user_input: QmInputWriter_input_schema, session: Session) -> QmInputWriter_output_schema:
        if not _RDKIT_AVAILABLE:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="RDKit is not installed; cannot generate the input file. "
                        "Install it with: pip install 'cloudra[chem]', then retry."
            )
        if user_input.engine == "orca":
            try:
                self._orca_memory_mb(user_input.mem)
            except ValueError as exc:
                return QmInputWriter_output_schema(
                    is_success=False,
                    message=f"qm_input_writer refused: {exc}",
                    unapplied_options=[str(exc)],
                )
        # 外部 MLIP 路由的参数校验（fail-loud，不静默吞掉配错的字段）
        if user_input.external_params and not user_input.external_program:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="external_params requires external_program: the Ext_Params string is only "
                        "meaningful together with a ProgExt executable. Set external_program, then retry.",
            )
        if user_input.external_params and user_input.engine == "gaussian":
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="external_params is ORCA-only; for the Gaussian external route the engine "
                        "value goes into external_program (e.g. external_program='mace').",
            )
        # 外部程序本身的安全校验：ORCA 可执行路径必须在 agent 可写范围之外，
        # Gaussian 引擎值必须能被 method_policy 词法解析（防白名单绕过）。
        if user_input.external_program:
            ext_error = await asyncio.to_thread(self._validate_external_program, user_input)
            if ext_error:
                return QmInputWriter_output_schema(
                    is_success=False,
                    input_path="",
                    message=f"qm_input_writer refused: {ext_error}",
                )
        if 'task_type' not in user_input.model_fields_set:
            native_tasks, unknown_tasks = declared_native_tasks(user_input.model_dump(exclude={'task_type'}))
            if native_tasks or unknown_tasks:
                user_input = user_input.model_copy(update={'task_type': []})
        # Validate request semantics before SMILES embedding or coordinate
        # optimization, both of which can take minutes for an invalid job.
        advice = validate_writer_request(user_input.model_dump())
        conflicts = [entry for entry in advice if entry['severity'] == 'error']
        option_warnings = [entry for entry in advice if entry['severity'] == 'warning']
        if user_input.engine == 'orca':
            per_core = self._orca_memory_mb(user_input.mem) / user_input.nproc
            if per_core != int(per_core):
                option_warnings.append(dict(code='resource_memory_precision', field='mem', severity='warning',
                    message=f'ORCA maxcore uses integer MB per process; {per_core:g} MB per process is rendered as {int(per_core)} MB without increasing the requested total memory.'))
        if conflicts:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="qm_input_writer refused: " + " | ".join(
                    f"[{c['code']}] {c['field']}: {c['message']}" for c in conflicts
                ),
                unapplied_options=[c["message"] for c in conflicts],
                warnings=option_warnings,
            )
        # 成功写出时在 interpreted_intent 里显式记录 scan 的刚性/松弛语义
        scan_semantics = None
        for task in user_input.task_type:
            if any(str(key).lower() == "scan" for key in task):
                scan_semantics = "rigid" if user_input.engine == "gaussian" else "relaxed"
                break
        # 路径语义收口：相对路径解析到 agent 工作目录（沙箱），绝对路径
        # 保持既有权限语义。SMILES 源不经过路径解析（绝不把 SMILES 当路径）。
        if user_input.source_type in ("xyz_file", "mol_file"):
            user_input.source_value = await asyncio.to_thread(resolve_tool_path, self, user_input.source_value)
        user_input.output_path = await asyncio.to_thread(resolve_tool_path, self, user_input.output_path)
        if user_input.engine == 'gaussian':
            for field in ('chk_name', 'rwf_name', 'fchk_name'):
                value = getattr(user_input, field)
                if value is not None:
                    setattr(user_input, field, await asyncio.to_thread(resolve_tool_path, self, value))
        if user_input.artifact_dir:
            user_input.artifact_dir = await asyncio.to_thread(resolve_tool_path, self, user_input.artifact_dir)
        else:
            base = os.path.dirname(user_input.output_path)
            stem = os.path.splitext(os.path.basename(user_input.output_path))[0]
            # 与 smiles_to_mol / conformer_search 同一命名规则：<父目录>/structure_build/<stem>/
            user_input.artifact_dir = build_artifact_dir(base or ".", stem)
        try:
            # 结构构建是重活（Embed/优化），离开事件循环线程
            mol, seed_note = await asyncio.to_thread(
                self._get_molecule, user_input, user_input.artifact_dir
            )
            content = await asyncio.to_thread(self.render_input, user_input, mol)
            if user_input.engine == "orca":
                engine_label = "ORCA"
                generation_path = "orca:simple+orca_blocks"
            else:
                engine_label = "Gaussian"
                generation_path = "gaussian:route"

            # 不信 writer 自述：从生成文本重新 inspect，任务集合不一致即失败。
            inspected = inspect_input(content, engine=user_input.engine)
            interpreted = inspected.model_dump(mode="json")
            if scan_semantics is not None:
                interpreted["scan_semantics"] = scan_semantics
            if inspected.certainty == 'unknown':
                option_warnings.append(dict(code='unclassified_native_intent', field='keywords', severity='warning',
                    message='The native task could not be classified; the original declaration is preserved. Inspect the engine input before interpreting results.'))
            written_calculation = self._written_calculation(user_input)
            render_errors = self.validate_rendered_input(user_input, content, charge=total_charge(mol))
            if render_errors:
                task_differences = sorted(inspected.tasks ^ intent_from_writer(user_input.model_dump()).tasks)
                return QmInputWriter_output_schema(is_success=False,
                    message='qm_input_writer internal mismatch: ' + ' | '.join(render_errors),
                    interpreted_intent=interpreted, unapplied_options=[*task_differences, *render_errors], warnings=option_warnings)

            limitation = seed_note
            if "ts_opt" in inspected.tasks and inspected.constraints:
                limitation += (
                    " NOTE: this input keeps constraints during a TS optimization; "
                    "the result may only be claimed as a CONSTRAINED saddle point, "
                    "not a full-space transition state."
                )

            parent_dir = os.path.dirname(user_input.output_path)
            if parent_dir:
                try:
                    await asyncio.to_thread(os.makedirs, parent_dir, exist_ok=True)
                except FileExistsError:
                    # exist_ok=True 仍会在叶子已存在且不是目录时炸 Errno 17——
                    # 必须翻译成有指引的报错，不把裸 errno 抛给调用方
                    return QmInputWriter_output_schema(
                        is_success=False,
                        input_path="",
                        message=(
                            f"Cannot create the output directory {parent_dir}: a non-directory "
                            "file already exists at that path. Choose a different output_path, "
                            "or remove the conflicting file, then retry."
                        ),
                    )
            input_path = user_input.output_path
            if user_input.engine == 'gaussian':
                await asyncio.to_thread(self._prepare_gaussian_file_parents, user_input)

            # 同路径重复生成：内容逐字节相同 → 幂等复用；不同 → fail-loud 给指引，
            # 绝不静默覆盖一份来源不明的既有文件。
            if await asyncio.to_thread(os.path.isfile, input_path):
                existing = await asyncio.to_thread(Path(input_path).read_bytes)
                if existing == content.encode("utf-8"):
                    return QmInputWriter_output_schema(
                        is_success=True,
                        input_path=input_path,
                        message=(
                            f"{engine_label} input file already exists with identical content; "
                            f"reused it as-is.{limitation}"
                        ),
                        interpreted_intent=interpreted,
                        calculation=written_calculation,
                        warnings=option_warnings,
                        unapplied_options=[],
                        generation_path=generation_path,
                    )
                return QmInputWriter_output_schema(
                    is_success=False,
                    input_path="",
                    message=(
                        f"Refused to overwrite {input_path}: a file already exists there with "
                        "different content. Choose a different output_path, or delete the "
                        "existing file first, then retry."
                    ),
                )

            await asyncio.to_thread(atomic_write_text, input_path, content)

            return QmInputWriter_output_schema(
                is_success=True,
                input_path=input_path,
                message=f"{engine_label} input file generated successfully.{limitation}",
                interpreted_intent=interpreted,
                calculation=written_calculation,
                warnings=option_warnings,
                unapplied_options=[],
                generation_path=generation_path,
            )
        except StructureBuildRefused as e:
            details = " | ".join(e.diagnostics) if e.diagnostics else e.message
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=(
                    f"qm_input_writer refused to write the file: the SMILES source could not be "
                    f"turned into a usable structure (build status: {e.status}). {e.message}"
                    + (f" Diagnostics: {details}" if details and details != e.message else "")
                    + f" Build artifacts: {e.artifact_path}"
                ),
            )
        except FileNotFoundError as e:
            missing = e.filename or user_input.source_value
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Coordinate source file not found: {missing}. "
                        "Check the path, or generate the structure first with smiles_to_mol / format_converter."
            )
        except FileExistsError as e:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Output path conflict: {e.filename or user_input.output_path} already exists "
                        "and cannot be created as a directory. Choose a different output_path, "
                        "or remove the conflicting file, then retry."
            )
        except ValueError as e:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Invalid input for qm_input_writer: {str(e)}. "
                        "Correct the reported field or coordinate source, then retry."
            )
        except Exception as e:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Failed to generate the {user_input.engine.upper()} input file: {str(e)}. "
                        "Verify the coordinate source and output path, then retry."
            )
```


## `cloudra/tools/Chemtool/submit_compute_job.py`

文件 SHA-256：`b56b40d9a5226ea00b6ba5d510e038a34e376c430c3b39ab00b413f2b2b827b9`


<a id="s124"></a>

### S124 · `SubmitComputeJob_input_schema`

`cloudra/tools/Chemtool/submit_compute_job.py:46–135`

```python
class SubmitComputeJob_input_schema(input_schema):
    input_file: str = Field(
        description="Path of the input file (e.g. a .gjf file or Bash script for shell): absolute as-is, "
                    "or relative to the Agent working directory."
    )
    job_type: Literal["gaussian", "vasp", "orca", "cp2k", "xtb", "chem_task", "shell"] = Field(
        default="gaussian",
        description="Job type. For 'xtb' the input is a plain XYZ; 'chem_task' accepts only a typed xtb_scan manifest prepared by ts_guess. "
                    "For 'shell', input_file is a Bash script; it runs in the script's directory and manages its own environment."
    )
    is_async: bool = Field(
        default=False,
        description="Whether to run the job asynchronously; recommended for long jobs"
            )
    execution_backend: Literal["auto", "local", "slurm"] = Field(
        default="auto",
        description=(
            "Execution backend. auto picks local/slurm from the Phase 8 node registry "
            "based on the input file's workspace; Slurm jobs are always submitted asynchronously."
        ),
    )
    node_id: str | None = Field(
        default=None,
        description=(
            "Target node from the node registry (e.g. an SSH remote server or an HPC "
            "login node). When given, the node's own scheduler/capacity/connection decide "
            "execution — omit execution_backend. Remote (SSH) nodes are always asynchronous: "
            "files are staged to the remote host and results pulled back automatically. "
            "Use query_compute_queue to list registered nodes and free capacity."
        ),
    )
    cpus: int | None = Field(
        default=None,
        ge=1,
        le=1024,
        description=(
            "CPU cores to reserve on the node. Omit to infer Gaussian %nprocshared/%nproc "
            "or ORCA PALn/%pal nprocs from the input; when absent there too, defaults to 1. "
            "An explicit value must be at least the input's request. Shell scripts are not parsed for resources; "
            "declare the cores their commands need, or omit for 1 CPU."
        ),
    )
    memory_mb: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Memory to reserve in MB (for ORCA: nprocs * maxcore). "
            "Omit to infer the input's %mem or %maxcore declaration; when the "
            "input has none, node admission applies its default reservation. For shell scripts, declare "
            "the required memory here; script text is not parsed."
        ),
    )
    priority: int = Field(
        default=0,
        ge=0,
        le=9,
        description=(
            "Queue priority, 0-9; higher runs first among queued jobs (same priority is FIFO). "
            "Use 5+ only for genuinely urgent jobs. Never preempts running jobs."
        ),
    )
    charge: int = Field(
        default=0,
        description=(
            "Molecular charge (xtb jobs only; passed as --chrg). xtb is CLI-flag driven: "
            "a charge/multiplicity line inside the .xyz comment is ignored by xtb — "
            "you MUST declare it here. Default 0."
        ),
    )
    multiplicity: int = Field(
        default=1,
        ge=1,
        description=(
            "Spin multiplicity (xtb jobs only; converted to --uhf = multiplicity-1). Default 1."
        ),
    )
    task: Literal["sp", "opt", "hess", "ohess"] = Field(
        default="sp",
        description=(
            "xtb run level (xtb jobs only): 'sp' single point (default), 'opt' geometry "
            "optimization (--opt), 'hess' frequencies (--hess), 'ohess' opt+freq (--ohess)."
        ),
    )
    solvent: str | None = Field(
        default=None,
        description=(
            "Implicit solvent name for xtb jobs (passed as --alpb NAME, e.g. 'water'). "
            "Omit for gas phase."
        ),
    )
```


<a id="s125"></a>

### S125 · `SubmitComputeJob_output_schema`

`cloudra/tools/Chemtool/submit_compute_job.py:138–143`

```python
class SubmitComputeJob_output_schema(output_schema):
    is_success: bool = Field(description="Whether submission succeeded")
    job_id: int = Field(default=-1, description="Compute job ID; query its status with query_compute_job")
    job_dir: str = Field(default="", description="Absolute path of the job working directory")
    state: str = Field(default="", description="Initial job state (normally 'ready')")
    message: str = Field(default="", description="Status or error message")
```


## `cloudra/tools/Chemtool/ts_guess.py`

文件 SHA-256：`0bae85973345033e94a94089f3e0c145415c4879beb24cbd5e5b1c1f2794261d`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/tools/Chemtool/ts_guess.py:70–70`

```python
_IMAG_MODE_WATCH_RATIO = 0.5
```


`cloudra/tools/Chemtool/ts_guess.py:74–78`

```python
_IRC_TRUNCATION_REMEDY = (
    "Optimize each actual IRC outer frame to its endpoint minimum and confirm zero imaginary "
    "frequencies. Submit the native Opt/Freq logs as reactant_logs / product_logs "
    "(combined or separate logs), with reactant_path / product_path identifying the expected species."
)
```


`cloudra/tools/Chemtool/ts_guess.py:111–124`

```python
_MODE_FIELDS = {
    'interpolate': {'engine', 'reactant_path', 'reactant_text', 'product_path', 'product_text',
                    'n_images', 'interp_method', 'watch_pairs', 'output_dir', 'selected_candidate',
                    'charge', 'multiplicity', 'electronic_character'},
    'xtb_path': {'engine', 'reactant_path', 'reactant_text', 'product_path', 'product_text',
                 'n_images', 'interp_method', 'watch_pairs', 'output_dir', 'timeout',
                 'refinement_runs', 'charge', 'multiplicity', 'electronic_character', 'selected_candidate'},
    'scan_prepare': {*QmCalculation.model_fields, 'input_path', 'input_text', 'scans', 'freeze',
                     *QmInputSettings.model_fields, 'output_path', 'force_constant', 'scan_mode', 'solvation'},
    'scan_parse': {'engine', 'log_path', 'ts_candidate_path', 'watch_pairs'},
    'verify': {'engine', 'freq_log', 'irc_log', 'reactant_path', 'reactant_text',
               'product_path', 'product_text', 'reactant_logs', 'product_logs', 'watch_pairs',
               'charge', 'strict', 'output_dir'},
}
```


`cloudra/tools/Chemtool/ts_guess.py:126–132`

```python
_RUN_MODE_FIELDS = {
    'xtb_path': {'method', 'refinement_runs', 'solvation'},
    'interpolate': {'n_images', 'interp_method', 'watch_pairs'},
    'scan_prepare': {*QmCalculation.model_fields, 'scans', 'freeze', 'force_constant', 'scan_mode', 'solvation'},
    'scan': {*QmCalculation.model_fields, 'scans', 'freeze', 'force_constant', 'scan_mode', 'solvation'},
    'provided': {'ts_candidate_path', 'evidence_refs'},
}
```


<a id="s126"></a>

### S126 · `_mode_json_schema`

`cloudra/tools/Chemtool/ts_guess.py:135–186`

```python
def _mode_json_schema(schema: dict[str, Any]) -> None:
    """Expose mode requirements alongside the shared field definitions."""
    def path_or_text(prefix: str) -> dict:
        return {"anyOf": [
            {"properties": {field: {"type": "string", "minLength": 1}}, "required": [field]}
            for field in (prefix + "_path", prefix + "_text")
        ]}

    branches = [
        {
            "properties": {"mode": {"const": mode}}, "required": ["mode"],
            "allOf": [path_or_text("reactant"), path_or_text("product")],
        }
        for mode in ("xtb_path", "interpolate")
    ]
    scan_array = next(item for item in schema["properties"]["scans"]["anyOf"]
                      if item.get("type") == "array")
    for mode in ("scan_prepare", "scan"):
        properties = {
            "mode": {"const": mode},
            "engine": {"enum": ['gaussian', 'orca', 'xtb']},
            "method": {"type": "string", "minLength": 1},
            "basis_set": {"type": "string"},
            "scans": dict(scan_array, minItems=1),
            "output_path": {"type": "string", "minLength": 1},
        }
        if mode == "scan":
            properties["log_path"] = {"enum": ["", None]}
        branches.append({
            "properties": properties, "required": ["mode", "engine", "method", "basis_set", "scans", "output_path"],
            **path_or_text("input"),
        })
    for mode, field in (("scan_parse", "log_path"), ("verify", "freq_log"), ("scan", "log_path")):
        branches.append({
            "properties": {"mode": {"const": mode}, field: {"type": "string", "minLength": 1}},
            "required": ["mode", field],
        })
    for branch in branches:
        mode = branch['properties']['mode']['const']
        selected = ('scan_parse' if 'log_path' in branch.get('required', []) else 'scan_prepare') if mode == 'scan' else mode
        allowed = _MODE_FIELDS[selected] | {'mode'}
        if mode == 'scan' and selected == 'scan_prepare':
            allowed.add('log_path')
        branch['properties'].update({field: {'not': {}} for field in schema['properties'] if field not in allowed})
    for mode, fields in _RUN_MODE_FIELDS.items():
        allowed = fields | {'mode', 'run_id'}
        branches.append({
            'properties': {'mode': {'const': mode}, 'run_id': {'type': 'string', 'minLength': 1},
                **{field: {'not': {}} for field in schema['properties'] if field not in allowed}},
            'required': ['mode', 'run_id'],
        })
    schema["oneOf"] = branches
```


<a id="s127"></a>

### S127 · `TsGuess_input_schema`

`cloudra/tools/Chemtool/ts_guess.py:189–383`

```python
class TsGuess_input_schema(QmInputSettings, input_schema):
    model_config = ConfigDict(json_schema_extra=_mode_json_schema)

    @classmethod
    def to_parameters_schema(cls) -> dict:
        parameters = super().to_parameters_schema()
        parameters["oneOf"] = cls.model_json_schema()["oneOf"]
        return parameters

    mode: Literal[
        "xtb_path", "interpolate", "scan_prepare", "scan_parse", "verify", "scan", "provided",
    ] = Field(
        description="Required sub-function; no calculation path is selected when mode is omitted. "
                    "DEFAULT SEED PATH when one forming/breaking bond/angle is known: "
                    "scan_prepare → submit → scan_parse (relaxed scan), then provide the peak to ts_prepare for formal TS refinement. "
                    "Do NOT default to xtb_path/interpolate just because they are cheap. "
                    "xtb_path: xTB metadynamics path search between endpoints (needs `xtb`); falls back to "
                    "interpolate with path_kind='idpp_fallback' when xtb is absent (never silently). "
                    "interpolate: IDPP/linear images — only when both endpoints and the all-atom map are already "
                    "trustworthy; it is not the default TS-seed start. "
                    "scan_prepare (write a scan input; atom indices should come from internal_coordinates first), "
                    "scan_parse (parse a scan log and judge), verify (frequency+IRC verification). "
                    "Alias: 'scan' maps to 'scan_prepare' (or 'scan_parse' if log_path is given). "
                    "NOTE: xtb_path/interpolate return a PATH AND A GUESS, never a saddle point — "
                    "unconstrained OptTS + frequency + IRC are still required. The former 'xtb_neb' alias is gone: xTB has no NEB."
    )

    run_id: str | None = Field(default=None, min_length=1,
        description='Existing TS run in the current project and workspace. Mutually exclusive with endpoint files/text, charge/multiplicity/electronic_character and output/resource overrides. Guess changes use the existing revision transaction and automatic queue.')
    selected_candidate: StrictInt | None = Field(default=None, ge=0,
        description='Independent endpoint analysis: choose a reported complete concrete atom-correspondence candidate (0-based). Omit when mapping is unique; genuine ambiguity requires an explicit choice.')
    evidence_refs: list[str] = Field(default_factory=list,
        description='provided with run_id: source evidence for the supplied TS candidate.')

    # ---------- interpolate ----------
    reactant_path: Optional[str] = Field(
        default=None,
        description="Independent path/interpolation: complete reactant MOL/SDF graph; verify also accepts XYZ reference geometry. Declared graphs are retained. "
                    "Absolute as-is, or relative to the Agent working directory.",
    )
    reactant_text: Optional[str] = Field(
        default=None,
        description="Reactant XYZ/MOL/SDF text; strict verify uses it to identify the expected reactant. Path takes precedence.",
    )
    product_path: Optional[str] = Field(
        default=None,
        description="Independent path/interpolation: complete product MOL/SDF graph; verify also accepts XYZ reference geometry. Declared graphs are retained. "
                    "Absolute as-is, or relative to the Agent working directory.",
    )
    product_text: Optional[str] = Field(
        default=None,
        description="Product XYZ/MOL/SDF text; strict verify uses it to identify the expected product. Path takes precedence.",
    )
    n_images: int = Field(default=10, description="interpolate: total image count (including endpoints), ≥2.")
    interp_method: Literal["idpp", "linear"] = Field(
        default="idpp", description="interpolate: interpolation method. idpp relaxes inter-image pair distances per Smidtstrup 2014; linear is linear interpolation."
    )
    watch_pairs: list[list[int]] = Field(
        default_factory=list,
        description="xtb_path/interpolate/scan_parse: pairs for distance monitoring; verify: pairs for advisory imaginary-mode alignment. "
                    "Indices refer to the concrete reactant XYZ for path/interpolation, each scan frame for scan_parse, "
                    "and the TS frequency geometry for verify, including explicit H. Gaussian/xTB are 1-based; ORCA is 0-based. "
                    "Use internal_coordinates on that file or reaction_mapping's concrete_watch_pairs with complete, current structure binding; "
                    "SMILES graph indices and indices from another atom order are not interchangeable. "
                    "If omitted, distance checks nominate bond-change and largest-distance-change pairs; imaginary-mode alignment is skipped.",
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="interpolate: image output directory (default ./ts_interp/); verify: directory to write IRC endpoints (default <freq_log_stem>_verify/). "
                    "Relative paths resolve against the Agent working directory.",
    )
    timeout: int = Field(
        default=900,
        description="xtb_path: subprocess timeout in seconds. On expiry only this run's own "
                    "process group is terminated; its logs and intermediate files are kept.",
    )
    refinement_runs: int = Field(
        default=DEFAULT_REFINEMENT_RUNS, ge=1,
        description="xtb_path: ceiling on the number of path-refinement cycles handed to xTB "
                    "($path nrun). This is a COMPUTE ceiling, not a convergence criterion: the "
                    "engine stops by itself when its own criterion is met. Do NOT lower it: the "
                    "engine's built-in default is 3 cycles, which measurably truncates the path "
                    "(the highest frame then sits in the reactant's own basin, 21 deg from the "
                    "start, and an OptTS started from it never converges). If a run reports "
                    "termination='path_not_converged', raise this and rerun.",
    )

    # ---------- scan_prepare ----------
    input_path: Optional[str] = Field(default=None, description="scan_prepare: input structure file path (XYZ/MOL/SDF). Absolute as-is, or relative to the Agent working directory.")
    input_text: Optional[str] = Field(default=None, description="scan_prepare: input structure XYZ/MOL/SDF text.")
    engine: Literal["gaussian", "orca", "xtb"] | None = Field(default=None, description="Required explicit engine for scan_prepare. For scan_parse/verify, omit to detect Gaussian/ORCA from the native log; an explicit engine must match the log. For geometry modes this selects atom numbering, not a calculation method.")
    scans: Optional[list[ScanCoordinateInput]] = Field(
        default=None,
        description=(
            "scan_prepare: scan-coordinate list, one entry per scanned coordinate. "
            "Each entry: {\"coord_type\": \"bond\"|\"angle\"|\"dihedral\", \"atoms\": [2|3|4 atom indices], "
            "Atoms refer to the exact input_path/input_text XYZ order, including explicit H. "
            "Gaussian and xTB use 1-based indices; ORCA uses 0-based indices. internal_coordinates on that same structure is 1-based: subtract 1 only for ORCA. "
            "\"scan_start\": optional start value (default the current geometry value), \"scan_end\": end value, "
            "\"scan_steps\": step count}. A single entry drives a 1D scan. Two ORCA coordinates require scan_mode='concerted' "
            "for a simultaneous path or 'grid' for an independent potential-energy surface. Gaussian uses an independent grid; "
            "xTB requires concerted or sequential. scan_parse does not derive a TS candidate from a grid. "
            "Scanning only one geometric coordinate is often not enough: TS search frequently needs a second, "
            "coupled coordinate (e.g. both the forming and the breaking bond) to see a barrier."
        )
    )
    freeze: list[FrozenCoordinateInput] = Field(
        default_factory=list,
        description="scan_prepare: coordinates held at the input geometry value; atoms belong to the exact input XYZ order including explicit H. "
                    "Gaussian/xTB atoms start at 1; ORCA at 0. Do not freeze a scanned coordinate.",
    )
    method: str | None = Field(default=None, description="scan_prepare requires one native method token. Put the basis only in basis_set and additional native settings only in keywords. Use the same calculation fields as qm_input_writer and ts_prepare. Current task requirements govern the method; MethodPolicy applies only to Benchmark tasks.")
    basis_set: str | None = Field(default=None, description="scan_prepare requires an explicit basis token, or an explicit empty string for a method with no basis. Declare the method and basis in their separate fields.")
    keywords: str = Field(default='', description="scan_prepare: explicitly requested native electronic keywords, e.g. D3BJ RIJCOSX def2/J TightSCF CPCM(DCM) for ORCA, or scrf=(solvent=water) for Gaussian.")
    frequency_mode: Literal['auto', 'analytic', 'numeric'] = Field(default='auto', description="Native frequency-mode declaration. Setting this without a frequency task produces a warning and does not add a frequency task.")
    output_path: Optional[str] = Field(default=None, description="scan_prepare: path to write the Gaussian/ORCA input or xTB typed manifest (required). Absolute as-is, or relative to the Agent working directory.")
    orca_blocks: Optional[str] = Field(
        default=None,
        description="scan_prepare: explicit native % blocks preserved beside generated scan coordinates. Additional %geom blocks produce advice; shared resource admission checks %pal/%maxcore declarations. For example, the external-potential block '%method\\n  ProgExt \"/abs/path/to/mace\"\\n  Ext_Params \"--model /abs/model --device cpu --dtype float64\"\\nend' when method='ExtOpt'. For Gaussian the text is preserved in the trailing section with a warning.",
    )

    end_setting: str = Field(default='', description='scan_prepare: explicit trailing native settings, after Gaussian ModRedundant coordinates. With ORCA the text is preserved with a native-syntax warning.')
    force_constant: float | None = Field(default=None, gt=0, allow_inf_nan=False, description='Native xTB scan restraint force constant in atomic units; required for engine=xtb.')
    scan_mode: Literal['concerted', 'sequential', 'grid'] | None = Field(default=None, description='Two-coordinate scan intent: ORCA requires concerted (simultaneous path, equal steps) or grid (independent surface, no automatic TS candidate); xTB supports concerted or sequential. Omit for one coordinate or Gaussian grids.')
    solvation: PathSolvation | None = Field(default=None, description='Native xTB solvation declaration, when used.')

    # ---------- scan_parse ----------
    log_path: Optional[str] = Field(default=None, description="scan_parse: Gaussian/ORCA scan log path, or xTB typed manifest path after completion. Absolute as-is, or relative to the Agent working directory.")
    ts_candidate_path: Optional[str] = Field(
        default=None, description="scan_parse: path to write the TS-guess xyz (default <log_stem>_ts_guess.xyz). Absolute as-is, or relative to the Agent working directory."
    )

    # ---------- verify ----------
    freq_log: Optional[str] = Field(default=None, description="verify: frequency-calculation log path. Absolute as-is, or relative to the Agent working directory.")
    irc_log: Optional[str] = Field(
        default=None,
        description="verify: IRC log path; optional in default mode, required in strict mode with valid frames on both rx<0 and rx>0 sides. "
                    "Absolute as-is, or relative to the Agent working directory.",
    )
    reactant_logs: list[str] = Field(default_factory=list,
        description="verify strict: native Opt and Freq logs proving an actual IRC outer frame was optimized to the expected reactant zero-imaginary minimum. Combined Opt/Freq or separate logs are accepted. Paths are absolute or relative to the Agent working directory.")
    product_logs: list[str] = Field(default_factory=list,
        description="verify strict: native Opt and Freq logs proving the opposite IRC outer frame was optimized to the expected product zero-imaginary minimum. Combined Opt/Freq or separate logs are accepted. Paths are absolute or relative to the Agent working directory.")
    strict: bool = Field(
        default=False,
        description="verify only: prove direction using the same TS and bidirectional IRC plus actual outer-frame Opt/Freq logs and expected endpoint structures. "
                    "IRC itself need not reach minima; the optimized endpoints must have zero imaginary frequencies. Imaginary-mode alignment and geometric intervals are advisory.",
    )

    @model_validator(mode="after")
    def require_mode_inputs(self):
        if self.run_id is not None:
            if self.mode not in _RUN_MODE_FIELDS:
                raise ValueError(f'{self.mode} is independent evidence analysis; omit run_id')
            unused = self.model_fields_set - (_RUN_MODE_FIELDS[self.mode] | {'mode', 'run_id'})
            if unused:
                raise ValueError(f'run {self.mode} does not use fields: {", ".join(sorted(unused))}; endpoint and resource state belongs to the run')
            return self
        if self.mode == 'provided':
            raise ValueError('provided requires run_id')
        mode = "scan_parse" if self.mode == "scan" and self.log_path else (
            "scan_prepare" if self.mode == "scan" else self.mode
        )
        if mode in {"xtb_path", "interpolate"}:
            if not (self.reactant_path or self.reactant_text):
                raise ValueError(f"{mode} requires reactant_path or reactant_text")
            if not (self.product_path or self.product_text):
                raise ValueError(f"{mode} requires product_path or product_text")
        elif mode == "scan_prepare":
            if not (self.input_path or self.input_text):
                raise ValueError("scan_prepare requires input_path or input_text")
            if not self.method or not self.method.strip():
                raise ValueError("scan_prepare requires an explicit method")
            if self.engine is None:
                raise ValueError('scan_prepare requires an explicit engine')
            if self.basis_set is None:
                raise ValueError("scan_prepare requires an explicit basis_set; use '' for no basis")
            QmCalculation.model_validate({field: getattr(self, field) for field in QmCalculation.model_fields})
            if self.engine == 'xtb' and 'mem' in self.model_fields_set:
                raise ValueError('native xTB scan does not use mem; this field is for Gaussian/ORCA inputs')
            if not self.scans:
                raise ValueError("scan_prepare requires scans: at least one scanned coordinate")
            if not self.output_path:
                raise ValueError("scan_prepare requires output_path")
        elif mode == "scan_parse" and not self.log_path:
            raise ValueError("scan_parse requires log_path")
        elif mode == "verify" and not self.freq_log:
            raise ValueError("verify requires freq_log")
        allowed = _MODE_FIELDS[mode] | {'mode'}
        if self.mode == 'scan' and mode == 'scan_prepare':
            allowed.add('log_path')
        unused = self.model_fields_set - allowed
        if unused:
            raise ValueError(f'{mode} does not use fields: {", ".join(sorted(unused))}; remove them or select the corresponding operation')
        return self
```


<a id="s128"></a>

### S128 · `TsGuess_output_schema`

`cloudra/tools/Chemtool/ts_guess.py:386–471`

```python
class TsGuess_output_schema(output_schema):
    is_success: bool = Field(description="Whether the operation succeeded")
    message: str = Field(default="", description="Status or error message")
    warnings: list[dict] = Field(default_factory=list, description="Native calculation advice; declared settings are preserved.")
    process: dict | None = Field(default=None,
        description='For run_id operations: authoritative TS process view after the accepted guess revision. A successful call is not scientific verification.')
    diagnostics: list[str] = Field(default_factory=list,
        description='Original independent path-runner diagnostics; retained on failure and explicit interpolation fallback.')
    mapping_candidates: list[dict] = Field(default_factory=list,
        description='Independent geometry analysis: complete concrete endpoint correspondences when mapping is ambiguous. Choose one with selected_candidate; these are mapping alternatives, not verified TS results.')
    calculation: QmCalculation | None = Field(default=None,
        description="scan_prepare: complete settings of the written input/manifest. Preparation is not a calculation result or TS validation.")

    # interpolate
    images_dir: str = Field(default="", description="interpolate/xtb_path: image directory, or the retained run directory on an unsuccessful xTB path search")
    distance_table: str = Field(default="", description="interpolate/scan_parse: per-frame observed distance text table; scan_parse marks missing or unaligned geometries explicitly")
    ts_candidate_index: Optional[int] = Field(default=None, description="TS candidate frame index (0-based)")
    # scan_parse 也复用 ts_candidate_path
    ts_candidate_path: str = Field(default="", description="TS-guess xyz path")
    refinement_termination: Literal["", "converged", "cycles_exhausted"] = Field(
        default="",
        description="xtb_path: what the engine's own path-refinement loop reported. 'converged' = "
                    "xTB declared its convergence criterion met (the only state in which the TS "
                    "candidate is handed over); 'cycles_exhausted' = the refinement hit the "
                    "`refinement_runs` ceiling and the path is TRUNCATED, so is_success is False.",
    )
    path_termination_reason: Optional[PathTermination] = Field(
        default=None,
        description="xtb_path: overall runner outcome, separate from the engine's refinement marker.",
    )
    path_kind: Literal["", "xtb_path", "idpp_fallback"] = Field(
        default="",
        description="How the path guess was produced. 'xtb_path' = xTB metadynamics path search; "
                    "'idpp_fallback' = xtb was unavailable so IDPP interpolation was used instead "
                    "(a degraded route, reported explicitly); '' = this mode does not produce a path. "
                    "Never treat a guess as a verified saddle point.",
    )

    # scan_prepare
    input_file_path: str = Field(default="", description="scan_prepare: generated input file path")
    run_hint: str = Field(default="", description="scan_prepare: submit/run hint")

    # scan_parse
    profile_table: str = Field(default="", description="scan_parse: per-point relative-energy text table (kcal/mol)")
    scan_has_internal_peak: Optional[bool] = Field(
        default=None,
        description="scan_parse: whether an analyzed energy profile has an internal maximum; null when no reliable energy profile was parsed, independent of geometry availability.",
    )
    verdicts: list[str] = Field(default_factory=list, description="scan_parse: profile verdicts")
    barrier_kcal: Optional[float] = Field(default=None, description="scan_parse: constrained-scan diagnostic only (highest point − first point, kcal/mol) — NOT a verified ΔE‡/ΔG‡; unconstrained OptTS + freq + IRC still required before any barrier claim")
    candidate: Optional[dict] = Field(
        default=None,
        description="scan_parse: unique constrained-scan local-peak candidate as {scan_index, energy, geometry_ref, source}; "
                    "not a validated TS. Multiple candidates are listed in verdicts with point/energy/XYZ for an existing provided-guess choice; "
                    "null when no unique candidate was selected or its geometry is unavailable.",
    )
    candidate_unavailable: bool = Field(
        default=False,
        description="scan_parse: an internal peak exists but its geometry could not be "
                    "recovered from this run's artifacts (a missing sidecar frame is NEVER "
                    "substituted with the last frame).",
    )

    # verify
    verdict: str = Field(
        default="",
        description="verify: default candidate/unlikely/inconclusive; strict is pass/fail/inconclusive.",
    )
    verification_status: Literal["", "candidate", "pass", "fail", "inconclusive"] = Field(
        default="",
        description="verify: structured status from the verification branch; empty outside verify or when verification could not run.",
    )
    n_imag: Optional[int] = Field(default=None, description="verify: number of imaginary frequencies")
    imag_freqs: list[float] = Field(default_factory=list, description="verify: imaginary frequencies (cm⁻¹, negative)")
    checks: list[str] = Field(default_factory=list, description="verify: per-check details")
    irc_end_a_path: str = Field(default="", description="verify: IRC endpoint A xyz path")
    irc_end_b_path: str = Field(default="", description="verify: IRC endpoint B xyz path")
    imag_mode_aligned: Optional[bool] = Field(
        default=None,
        description="verify: advisory heuristic of whether the imaginary normal mode matches the watch_pairs reaction coordinate; "
                    "None if skipped or undecidable. Does not decide strict verification.",
    )
    imag_mode_alignment: str = Field(
        default="",
        description="verify: explanation of the imaginary-mode vs reaction-coordinate alignment check.",
    )
```


<a id="s129"></a>

### S129 · `_source_molecule`

`cloudra/tools/Chemtool/ts_guess.py:478–484`

```python
def _source_molecule(user_input, role: str):
    """工具入口转换一次；内部继续传递完整分子，不丢弃声明图。"""
    declared = user_input.charge if "charge" in getattr(user_input, "model_fields_set", {"charge"}) else None
    return read_molecule(
        input_path=getattr(user_input, role + "_path"),
        input_text=getattr(user_input, role + "_text"), charge=declared,
    )
```


<a id="s130"></a>

### S130 · `_reference_molecules`

`cloudra/tools/Chemtool/ts_guess.py:487–489`

```python
def _reference_molecules(user_input):
    return {role: _source_molecule(user_input, role) for role in ("reactant", "product")
            if getattr(user_input, role + "_path") or getattr(user_input, role + "_text")}
```


<a id="s131"></a>

### S131 · `_assess_imag_mode_alignment`

`cloudra/tools/Chemtool/ts_guess.py:1045–1193`

```python
def _assess_imag_mode_alignment(
    vibfreqs: Sequence[float],
    vibdisps,
    watch_pairs: Sequence[Sequence[int]],
    symbols: Optional[Sequence[str]] = None,
    positions=None,
    charge: int = 0,
    index_base: int = 1,
    **_kwargs,
) -> dict[str, Any]:
    """检查最低虚频模式是否主要落在 watch_pairs 反应中心上。

    对每个原子对取 |d_i - d_j|；要求 watch_pairs 中至少一对达到全局最大相对位移的
    `_IMAG_MODE_WATCH_RATIO` 倍。缺位移数据时 status=missing。

    扭转/角主导的 TS（阻转、环翻转、锥形反转）：全局最大相对位移对**两端不成键**
    （用 TS 几何的 perceive_bonds 键图判）时，键对距离本就几乎不动，pair-distance
    对齐材料不足以判方向——status=undecidable。主导对是键对、或 TS 几何缺失
    无法判成键性时，维持原规则。该启发式仅作诊断，不决定 strict 验收。
    """
    import numpy as np

    if vibdisps is None:
        return {
            "status": "missing",
            "aligned": None,
            "message": "The frequency log lacks normal-mode displacements; cannot check the imaginary-frequency direction.",
            "details": [],
        }
    imag_idxs = [i for i, f in enumerate(vibfreqs) if f < 0]
    if not imag_idxs:
        return {
            "status": "missing",
            "aligned": None,
            "message": "No imaginary frequency; skipping the imaginary-mode alignment check.",
            "details": [],
        }
    mode_idx = min(imag_idxs, key=lambda i: vibfreqs[i])
    try:
        disps = np.asarray(vibdisps[mode_idx], dtype=float)
    except (IndexError, TypeError, ValueError):
        return {
            "status": "missing",
            "aligned": None,
            "message": "The frequency log lacks normal-mode displacements; cannot check the imaginary-frequency direction.",
            "details": [],
        }
    if disps.ndim != 2 or disps.shape[1] != 3 or disps.shape[0] < 2:
        return {
            "status": "missing",
            "aligned": None,
            "message": "The frequency log lacks normal-mode displacements; cannot check the imaginary-frequency direction.",
            "details": [],
        }

    n = disps.shape[0]
    pair_mags: list[tuple[tuple[int, int], float]] = []
    max_rel = 0.0
    max_pair = (0, 1)
    for i in range(n):
        for j in range(i + 1, n):
            rel = float(np.linalg.norm(disps[i] - disps[j]))
            pair_mags.append(((i, j), rel))
            if rel > max_rel:
                max_rel = rel
                max_pair = (i, j)

    if max_rel <= 0.0:
        return {
            "status": "missing",
            "aligned": None,
            "message": "All imaginary-mode displacements are zero; cannot check direction.",
            "details": [],
        }

    if not watch_pairs:
        return {
            "status": "skipped",
            "aligned": None,
            "message": "No watch_pairs provided; skipping the imaginary-mode vs reaction-coordinate alignment check.",
            "details": [f"Global max relative-displacement pair=({max_pair[0] + index_base},{max_pair[1] + index_base})"],
        }

    threshold = _IMAG_MODE_WATCH_RATIO * max_rel
    watch_set: set[frozenset[int]] = set()
    watch_details: list[str] = []
    best_watch = 0.0
    for raw in watch_pairs:
        if len(raw) != 2:
            continue
        i, j = int(raw[0]) - index_base, int(raw[1]) - index_base
        if not (0 <= i < n and 0 <= j < n) or i == j:
            watch_details.append(f"watch_pairs atom indices invalid: {raw}")
            continue
        lo, hi = (i, j) if i < j else (j, i)
        watch_set.add(frozenset((lo, hi)))
        rel = float(np.linalg.norm(disps[lo] - disps[hi]))
        best_watch = max(best_watch, rel)
        watch_details.append(
            f"Atom pair ({lo + index_base},{hi + index_base}) relative displacement={rel:.3f}"
            f" (threshold {_IMAG_MODE_WATCH_RATIO:.2f}×{max_rel:.3f}={threshold:.3f})"
        )

    max_fs = frozenset(max_pair)
    # 最大相对位移对本身在 watch_pairs 中 → 对齐；否则须严格超过比例阈值，
    # 避免「两端反向伸缩、监视原子静止」时 |d_i-d_j| 恰好 = 0.5×max 的假阳性。
    if max_fs in watch_set:
        aligned = best_watch >= threshold
    else:
        aligned = best_watch > threshold
    if aligned:
        message = (
            f"Imaginary mode is consistent with the declared reaction coordinate: watch_pairs max relative displacement {best_watch:.3f} "
            f"≥ {_IMAG_MODE_WATCH_RATIO:.2f}×global max {max_rel:.3f} "
            f"(max pair=({max_pair[0] + index_base},{max_pair[1] + index_base}))."
        )
        status = "aligned"
    else:
        # 扭转/角主导模式：全局最大相对位移对两端不成键时，键对距离几乎不动是
        # 这类模式的固有性质，pair-distance 对齐无法判方向——undecidable。
        dominant_bonded: Optional[bool] = None
        if symbols is not None and positions is not None and len(symbols) == n:
            bond_graph, _src = _perceive_bonds(list(symbols), positions, charge)
            dominant_bonded = (min(max_pair), max(max_pair)) in bond_graph
        if dominant_bonded is False:
            return {
                "status": "undecidable",
                "aligned": None,
                "message": (
                    f"The imaginary mode's dominant motion is on the NON-BONDED atom pair "
                    f"({max_pair[0] + index_base},{max_pair[1] + index_base}): a torsion/angle-dominated mode "
                    "(hindered rotation, ring flip, pyramidal inversion) barely moves bonded-pair "
                    "distances, so pair-distance alignment against watch_pairs cannot judge its "
                    "direction. The material is insufficient for a pass/fail verdict."
                ),
                "details": watch_details,
            }
        message = (
            f"Imaginary mode is inconsistent with the declared reaction coordinate: watch_pairs max relative displacement {best_watch:.3f} "
            f"< {_IMAG_MODE_WATCH_RATIO:.2f}×global max {max_rel:.3f} "
            f"(dominant motion on atom pair ({max_pair[0] + index_base},{max_pair[1] + index_base}))."
        )
        status = "misaligned"
    return {
        "status": status,
        "aligned": aligned,
        "message": message,
        "details": watch_details,
    }
```


<a id="s132"></a>

### S132 · `_parse_freq_log`

`cloudra/tools/Chemtool/ts_guess.py:1196–1242`

```python
def _parse_freq_log(log_path: str, engine: str) -> dict:
    """Read separate native termination, optimization and frequency facts."""
    from cloudra.tools.core.qm_log_facts import read_qm_log

    facts = read_qm_log(log_path)
    if facts.engine != engine:
        raise ValueError(f"Expected {engine} frequency output, detected {facts.engine}: {log_path}")
    text = facts.text
    vibfreqs = facts.frequencies_cm
    vibdisps = None
    if vibfreqs is None:
        raise ValueError(f"Failed to parse vibrational frequencies from the frequency log: {log_path}")
    # Keep vectors paired with the frequencies and geometry from the same log.
    data = facts.parser_data
    if data is not None:
        vd = getattr(data, 'vibdisps', None)
        vf = getattr(data, 'vibfreqs', None)
        if vd is not None and vf is not None and len(vd) == len(vibfreqs) and len(vf) == len(vibfreqs):
            import numpy as np

            if np.array_equal(np.asarray(vf, dtype=float), np.asarray(vibfreqs, dtype=float)):
                vibdisps = np.asarray(vd, dtype=float)
    if vibdisps is None and engine == "gaussian":
        vibdisps = gaussian_frames.vibdisps_from_text(text, len(vibfreqs))
    elif vibdisps is None and engine == "orca":
        # cclib 也可能只解析出裁掉零频的频率。原生位移按完整 3N 轴编号，
        # 必须连同原生频率一起取，不能拿裁剪后的轴推算原子数或匹配位移。
        native_freqs = orca_frames.vibfreqs_from_text(text)
        n_atoms = len(native_freqs) // 3 if native_freqs and len(native_freqs) % 3 == 0 else 0
        if n_atoms > 0:
            native_disps = orca_frames.vibdisps_from_text(text, len(native_freqs), n_atoms)
            if native_disps is not None:
                vibfreqs, vibdisps = native_freqs, native_disps
    symbols, positions = (None, None)
    if facts.geometry is not None:
        import numpy as np

        symbols = list(facts.geometry[0])
        positions = np.asarray(facts.geometry[1], dtype=float)
    return {
        "vibfreqs": vibfreqs,
        "vibdisps": vibdisps,
        "normal_termination": facts.normal_termination,
        "opt_converged": facts.opt_converged,
        "symbols": symbols,
        "positions": positions,
    }
```


<a id="s133"></a>

### S133 · `TsGuess.tool_call`

`cloudra/tools/Chemtool/ts_guess.py:1259–1314`

```python
    async def tool_call(self, user_input: TsGuess_input_schema, session: Session) -> TsGuess_output_schema:
        if user_input.run_id is not None:
            try:
                return await self._run_guess(user_input, session)
            except (ValueError, OSError) as exc:
                return TsGuess_output_schema(is_success=False, message=f'ts_guess: {exc}')
        # 路径语义收口：所有文件路径字段的相对路径统一解析到 agent 工作
        # 目录（沙箱）；绝对路径保持既有权限语义。
        user_input = user_input.model_copy(
            update={
                **{
                    field: resolve_tool_path(self, value)
                    for field, value in {
                        "reactant_path": user_input.reactant_path,
                        "product_path": user_input.product_path,
                        "input_path": user_input.input_path,
                        "output_path": user_input.output_path,
                        "log_path": user_input.log_path,
                        "ts_candidate_path": user_input.ts_candidate_path,
                        "freq_log": user_input.freq_log,
                        "irc_log": user_input.irc_log,
                        "output_dir": user_input.output_dir,
                    }.items()
                    if value
                },
                **{field: [resolve_tool_path(self, path) for path in getattr(user_input, field)]
                   for field in ("reactant_logs", "product_logs")},
            }
        )
        mode = user_input.mode
        if mode == "scan":
            mode = "scan_parse" if user_input.log_path else "scan_prepare"

        handlers = {
            "xtb_path": self._xtb_path,
            "interpolate": self._interpolate,
            "scan_prepare": self._scan_prepare,
            "scan_parse": self._scan_parse,
            "verify": self._verify,
        }
        if mode not in handlers:
            import difflib
            matches = difflib.get_close_matches(mode, list(handlers.keys()), n=1, cutoff=0.35)
            suggestion = f" Did you mean {matches[0]!r}?" if matches else ""
            return TsGuess_output_schema(
                is_success=False,
                message=f"Unknown mode {mode!r}.{suggestion} Allowed modes: {sorted(handlers.keys())}",
            )
        try:
            # handler 是同步重活（xtb_path 会 proc.communicate 等 xTB 子进程、
            # scan_parse 逐帧啃大日志）：卸载出事件循环，避免冻结整个 API。
            return await asyncio.to_thread(handlers[mode], user_input)
        except _UnconfirmedEndpointMapping as exc:
            return TsGuess_output_schema(is_success=False, message=str(exc), mapping_candidates=exc.candidates)
        except Exception as e:
            return TsGuess_output_schema(is_success=False, message=f"{user_input.mode} failed: {e}")
```


<a id="s134"></a>

### S134 · `TsGuess._verify`

`cloudra/tools/Chemtool/ts_guess.py:2311–2454`

```python
    def _verify(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        if not user_input.freq_log:
            raise ValueError("verify requires freq_log")
        if not os.path.isfile(user_input.freq_log):
            raise ValueError(f"Frequency log does not exist: {user_input.freq_log}")

        engine = detect_qm_engine(user_input.freq_log)
        if engine not in {"gaussian", "orca"}:
            raise ValueError(f"Cannot verify frequency log with unknown or unsupported engine: {engine}")
        if user_input.engine is not None and user_input.engine != engine:
            raise ValueError(
                f"Frequency log engine mismatch: requested {user_input.engine}, detected {engine}"
            )
        # Use the same detected engine for native parsing, IRC dispatch and atom indices.
        user_input = user_input.model_copy(update={"engine": engine})
        freq = _parse_freq_log(user_input.freq_log, user_input.engine)
        vibfreqs = freq["vibfreqs"]
        imag = [f for f in vibfreqs if f < 0]
        n_imag = len(imag)
        checks: list[str] = []
        references = {}
        reference_error = None
        frequency_usable = freq['normal_termination'] and freq['opt_converged'] is not False
        if frequency_usable and n_imag == 1:
            try:
                references = _reference_molecules(user_input)
            except Exception as exc:
                reference_error = str(exc)

        irc_end_a_path = ""
        irc_end_b_path = ""
        imag_mode_aligned: Optional[bool] = None
        imag_mode_alignment = ""

        def _record_mode_alignment() -> None:
            nonlocal imag_mode_aligned, imag_mode_alignment
            assessment = _assess_imag_mode_alignment(
                vibfreqs,
                freq.get("vibdisps"),
                user_input.watch_pairs,
                symbols=freq.get("symbols"),
                positions=freq.get("positions"),
                index_base=atom_index_base(user_input.engine),
                charge=total_charge(references["reactant"]) if "reactant" in references else user_input.charge or 0,
            )
            imag_mode_aligned = assessment["aligned"]
            imag_mode_alignment = assessment["message"]
            warning = (
                "[warning] Imaginary-mode alignment is advisory; strict verification uses actual IRC endpoint proof. "
                if assessment["status"] in {"missing", "undecidable", "misaligned"} else ""
            )
            checks.append(warning + assessment["message"])
            checks.extend(assessment.get("details") or [])

        if reference_error is not None:
            checks.append(f"Endpoint reference structures could not be parsed: {reference_error}")
            verdict = "inconclusive: the endpoint reference structures could not be parsed."
            status = "inconclusive"
        elif user_input.strict:
            if not frequency_usable:
                checks.append("The frequency job lacks native normal termination or reports an unconverged optimization; the first-order saddle-point premise cannot be established.")
                verdict = "inconclusive: the frequency job lacks normal termination or optimization convergence; the available material is insufficient for a strict judgement."
                status = "inconclusive"
            elif n_imag != 1:
                if n_imag == 0:
                    checks.append("A normally terminated frequency job has no imaginary frequency: the structure is a minimum, not a first-order saddle point.")
                else:
                    checks.append(
                        f"A normally terminated frequency job has {n_imag} imaginary frequencies "
                        f"({', '.join(f'{f:.1f}' for f in imag)} cm⁻¹): the structure is a higher-order saddle point."
                    )
                verdict = "fail: the strict check requires exactly one imaginary frequency."
                status = "fail"
            else:
                checks.append(f"Exactly 1 imaginary frequency ({imag[0]:.1f} cm⁻¹): the first-order saddle-point premise holds.")
                _record_mode_alignment()
                status, verdict, info = self._strict_path_verdict(user_input, checks, references)
                if info is not None:
                    irc_end_a_path = info["path_a"]
                    irc_end_b_path = info["path_b"]
        else:
            if not frequency_usable:
                checks.append("The frequency job lacks native normal termination or reports an unconverged optimization; cannot judge the TS candidate from it.")
                verdict = "inconclusive: the frequency job lacks normal termination or optimization convergence."
                status = "inconclusive"
            elif n_imag == 0:
                checks.append("No imaginary frequency: the structure is a minimum, not like a first-order saddle point.")
                verdict = "unlikely: no imaginary frequency; the structure looks more like a minimum."
                status = "fail"
            elif n_imag > 1:
                checks.append(
                    f"{n_imag} imaginary frequencies ({', '.join(f'{f:.1f}' for f in imag)} cm⁻¹): "
                    "the structure looks more like a higher-order saddle point."
                )
                verdict = "unlikely: multiple imaginary frequencies; the structure looks more like a higher-order saddle point."
                status = "fail"
            else:
                checks.append(
                    f"Exactly 1 imaginary frequency ({imag[0]:.1f} cm⁻¹): acceptable as a first-order saddle-point candidate, but this is not sufficient proof."
                )
                _record_mode_alignment()
                irc_ok: Optional[bool] = None
                info = self._extract_irc_endpoints(
                    user_input.irc_log, checks, engine=user_input.engine,
                    output_dir=user_input.output_dir or os.path.splitext(user_input.freq_log)[0] + "_verify",
                    require_two_sides=False,
                )
                if info is not None:
                    irc_end_a_path = info["path_a"]
                    irc_end_b_path = info["path_b"]
                    irc_ok = self._check_irc_connectivity(
                        user_input, info["end_a"], info["end_b"], checks, references,
                    )

                if user_input.irc_log and info is None:
                    verdict = "inconclusive: IRC was provided, but comparable endpoint geometries could not be obtained."
                    status = "inconclusive"
                elif irc_ok is False:
                    verdict = "unlikely: the rough connectivity of the IRC endpoints is inconsistent with the expected structures."
                    status = "fail"
                elif irc_ok == "inconclusive":
                    verdict = (
                        "inconclusive: the IRC endpoints could not be compared with the expected "
                        "structures (atom order or element mismatch); connectivity is undecidable."
                    )
                    status = "inconclusive"
                else:
                    reason = "one imaginary frequency" + ("; rough IRC connectivity consistent" if irc_ok else "")
                    verdict = f"candidate: {reason}; advisory only for the agent's next step, not a strict proof of the TS."
                    status = "candidate"

        return TsGuess_output_schema(
            is_success=True,
            verdict=verdict,
            verification_status=status,
            n_imag=n_imag,
            imag_freqs=[round(f, 2) for f in imag],
            checks=checks,
            irc_end_a_path=irc_end_a_path,
            irc_end_b_path=irc_end_b_path,
            imag_mode_aligned=imag_mode_aligned,
            imag_mode_alignment=imag_mode_alignment,
            message=f"TS verification complete: {verdict}",
        )
```


<a id="s135"></a>

### S135 · `TsGuess._extract_irc_endpoints`

`cloudra/tools/Chemtool/ts_guess.py:2456–2522`

```python
    @staticmethod
    def _extract_irc_endpoints(irc_log: str | None, checks: list[str], *,
                               engine: str, output_dir: str,
                               require_two_sides: bool) -> Optional[dict]:
        """提取有坐标的 IRC 外侧帧；strict 时必须分别来自 rx<0 与 rx>0。"""
        if not irc_log:
            checks.append("No IRC log provided.")
            return None
        if not os.path.isfile(irc_log):
            raise ValueError(f"IRC log does not exist: {irc_log}")

        if engine == "orca":
            return TsGuess._extract_orca_irc_endpoints(
                irc_log, checks, output_dir=output_dir, require_two_sides=require_two_sides,
            )

        from cloudra.tools.core import gaussian_frames

        try:
            frames, meta = gaussian_frames.extract_irc(irc_log)
        except Exception as e:
            checks.append(f"IRC endpoint extraction failed: {e}")
            return None

        valid = [frame for frame in frames if frame.xyz.strip()]
        if require_two_sides:
            negative = [
                frame for frame in valid
                if frame.reaction_coordinate is not None and frame.reaction_coordinate < 0
            ]
            positive = [
                frame for frame in valid
                if frame.reaction_coordinate is not None and frame.reaction_coordinate > 0
            ]
            if not negative or not positive:
                checks.append("The IRC log does not provide valid coordinate frames on both rx<0 and rx>0 sides.")
                return None
            end_a = min(negative, key=lambda frame: frame.reaction_coordinate)
            end_b = max(positive, key=lambda frame: frame.reaction_coordinate)
        else:
            if len(valid) < 2:
                checks.append("Fewer than two path frames with coordinates in the IRC log.")
                return None
            end_a, end_b = valid[0], valid[-1]

        out_dir = output_dir
        os.makedirs(out_dir, exist_ok=True)
        path_a = os.path.join(out_dir, "irc_end_a.xyz")
        path_b = os.path.join(out_dir, "irc_end_b.xyz")
        atomic_write_text(path_a, end_a.xyz.rstrip() + "\n")
        atomic_write_text(path_b, end_b.xyz.rstrip() + "\n")
        checks.append(
            f"IRC outer frames extracted: irc_end_a.xyz (rx={end_a.reaction_coordinate}), "
            f"irc_end_b.xyz (rx={end_b.reaction_coordinate}) -> {out_dir}"
        )
        if require_two_sides and not (
            meta.get("forward_converged", False) and meta.get("backward_converged", False)
        ):
            checks.append("The IRC did not reach a minimum on at least one side; strict requires separate optimization and zero-imaginary frequency evidence for its actual outer frames.")
        return {
            "end_a": end_a,
            "end_b": end_b,
            "frames": frames,
            "meta": meta,
            "path_a": path_a,
            "path_b": path_b,
        }
```


<a id="s136"></a>

### S136 · `TsGuess._extract_orca_irc_endpoints`

`cloudra/tools/Chemtool/ts_guess.py:2524–2585`

```python
    @staticmethod
    def _extract_orca_irc_endpoints(irc_log: str, checks: list[str], *,
                                    output_dir: str, require_two_sides: bool) -> Optional[dict]:
        """ORCA IRC 端点：复用 orca_frames 的 final endpoint / F-B trajectory
        读取（解析规则不在这里复制）。forward/backward 是轨迹方向标签，
        不自动映射 reactant/product。收敛与否只记录、绝不做闸门：与 Gaussian
        通道同口径，每侧取最外侧可用几何（未收敛方向的轨迹末帧同样是合法的
        部分端点），strict 通过实际外侧帧的 Opt/Freq 日志核对方向。"""
        from types import SimpleNamespace

        from cloudra.tools.core import orca_frames

        endpoints = orca_frames.extract_irc_endpoints(irc_log)
        forward, backward = endpoints["forward"], endpoints["backward"]
        for label, info in (("forward", forward), ("backward", backward)):
            converged = info.get("converged")
            if converged is False:
                checks.append(
                    f"The ORCA IRC {label} direction terminated WITHOUT converging; "
                    "the trajectory's outermost frame is used as that side's partial endpoint; "
                    "strict requires its actual endpoint Opt/Freq evidence."
                )
            elif converged:
                checks.append(
                    f"The ORCA IRC {label} direction converged; a short converged path "
                    "needs no padding to a fixed point count."
                )

        xyz_a = orca_frames.read_endpoint_geometry(forward)
        xyz_b = orca_frames.read_endpoint_geometry(backward)
        if xyz_a is None or xyz_b is None:
            checks.append(
                "ORCA IRC endpoint geometries are not available on both sides "
                "(final endpoint files or F/B trajectories are missing); one side's "
                "geometry is never reused as the other side."
            )
            return None

        end_a = SimpleNamespace(xyz=xyz_a, reaction_coordinate=None)
        end_b = SimpleNamespace(xyz=xyz_b, reaction_coordinate=None)
        out_dir = output_dir
        os.makedirs(out_dir, exist_ok=True)
        path_a = os.path.join(out_dir, "irc_end_a.xyz")
        path_b = os.path.join(out_dir, "irc_end_b.xyz")
        atomic_write_text(path_a, xyz_a.rstrip() + "\n")
        atomic_write_text(path_b, xyz_b.rstrip() + "\n")
        checks.append(
            "ORCA IRC endpoints extracted (forward/backward are trajectory directions, "
            f"NOT reactant/product assignments): irc_end_a.xyz ({forward.get('origin')}), "
            f"irc_end_b.xyz ({backward.get('origin')}) -> {out_dir}"
        )
        return {
            "end_a": end_a,
            "end_b": end_b,
            "frames": [end_a, end_b],
            "meta": {
                "forward_converged": bool(forward.get("converged")),
                "backward_converged": bool(backward.get("converged")),
            },
            "path_a": path_a,
            "path_b": path_b,
        }
```


<a id="s137"></a>

### S137 · `TsGuess._strict_path_verdict`

`cloudra/tools/Chemtool/ts_guess.py:2587–2646`

```python
    def _strict_path_verdict(self, user_input: TsGuess_input_schema,
                             checks: list[str], references) -> tuple[str, str, Optional[dict]]:
        """核对同一 TS 的 IRC 外侧帧实际优化到两侧身份正确的零虚频极小点。"""
        from rdkit import Chem

        from cloudra.tools.core.irc_evidence import verify_short_irc_direction

        def inconclusive(reason: str, info):
            checks.append(_IRC_TRUNCATION_REMEDY)
            return "inconclusive", f"inconclusive: {reason} {_IRC_TRUNCATION_REMEDY}", info

        info = self._extract_irc_endpoints(
            user_input.irc_log, checks, engine=user_input.engine,
            output_dir=user_input.output_dir or os.path.splitext(user_input.freq_log)[0] + "_verify",
            require_two_sides=True,
        )
        if info is None:
            return inconclusive("no usable bidirectional IRC endpoints.", None)
        if not all(role in references for role in ("reactant", "product")):
            return inconclusive("missing the expected reactant and product structures.", info)
        if not user_input.reactant_logs or not user_input.product_logs:
            return inconclusive("missing actual endpoint optimization and zero-imaginary frequency logs.", info)

        def species(role):
            from rdkit.Chem import rdDetermineBonds

            molecule = Chem.Mol(references[role])
            if molecule.HasProp("cloudra_graph_status") and molecule.GetProp("cloudra_graph_status") == "unresolved":
                rdDetermineBonds.DetermineBonds(molecule, charge=total_charge(references[role]))
            molecule = Chem.RemoveHs(molecule)
            for atom in molecule.GetAtoms():
                atom.SetAtomMapNum(0)
            return Chem.MolToSmiles(molecule)

        try:
            reactant_smiles, product_smiles = species("reactant"), species("product")
        except (ValueError, RuntimeError) as exc:
            checks.append(f"Expected endpoint identity cannot be resolved; supply a complete MOL/SDF graph: {exc}")
            return inconclusive("the expected endpoint molecular identity is unresolved.", info)

        passed, details = verify_short_irc_direction(
            user_input.irc_log, [user_input.freq_log],
            user_input.product_logs, user_input.reactant_logs,
            charge=total_charge(references["reactant"]),
            reactant_smiles=reactant_smiles, product_smiles=product_smiles,
        )
        checks.extend(details)
        if passed:
            return (
                "pass",
                "pass: both actual IRC outer frames optimize to the expected zero-imaginary endpoint minima.",
                info,
            )
        checks.append(_IRC_TRUNCATION_REMEDY)
        return (
            "fail",
            "fail: the submitted logs do not prove that both actual IRC outer frames optimize "
            f"to the expected zero-imaginary endpoint minima. {_IRC_TRUNCATION_REMEDY}",
            info,
        )
```


## `cloudra/tools/Plantool/dag_tools/_common.py`

文件 SHA-256：`aa5ec1cd03d27f706849d9f3b1357efddcd7f15b6cf7ee4e1a4888cd7d0546c1`


<a id="s138"></a>

### S138 · `DagToolOutput`

`cloudra/tools/Plantool/dag_tools/_common.py:169–175`

```python
class DagToolOutput(output_schema):
    is_success: bool
    action: str
    result: dict[str, Any] = Field(default_factory=dict)
    accepted: bool | None = None
    rejection_code: str | None = None
    error: str = ""
```


## `cloudra/tools/Plantool/dag_tools/dag_submit_step_evidence.py`

文件 SHA-256：`c33494470996852ce7bfce64b71ec2b3d24cf11b651e795ee4e14aef14386f0c`


<a id="s139"></a>

### S139 · `DagSubmitStepEvidenceInput`

`cloudra/tools/Plantool/dag_tools/dag_submit_step_evidence.py:32–60`

```python
class DagSubmitStepEvidenceInput(input_schema):
    step_name: str = Field(
        description="Name of the elementary step in the delivery graph (e.g. 'step1')."
    )
    ts_file: str = Field(
        description="Path to the transition state frequency/optimization output file."
    )
    opt_file: Optional[str] = Field(default=None,
        description="Separate converged TS optimization output, when ts_file is frequency-only. Both files must contain the same geometry.")
    irc_file: Optional[str] = Field(
        default=None,
        description="Optional original combined IRC output path. Keep native ORCA endpoint/trajectory files in the job directory; this tool archives them together. Do not submit a renamed standalone copy.",
    )
    irc_forward_file: Optional[str] = Field(
        default=None,
        description="Optional path to forward IRC calculation output file.",
    )
    irc_reverse_file: Optional[str] = Field(
        default=None,
        description="Optional path to reverse IRC calculation output file.",
    )
    reaction_coordinate_description: str = Field(
        default="",
        description="Description of the reaction coordinate (e.g. bonds formed/cleaved along the mode).",
    )
    source_minimum_file: str | None = Field(default=None,
        description='Path to the minimum calculation output for the SOURCE species of this step. Final geometry must match the complete source species and have zero imaginary frequencies. The tool archives and binds the file automatically.')
    target_minimum_file: str | None = Field(default=None,
        description='Optional minimum output for the complete TARGET species, with zero imaginary frequencies. For separated products declared as smiles=[B, C], first attach all component logs with dag_submit_species_evidence(opt_file=[...]) and omit this field. A dot-connected smiles="B.C" remains a complex requiring its own minimum. SOURCE/TARGET roles are independent of IRC forward/reverse direction.')
```


<a id="s140"></a>

### S140 · `DagSubmitStepEvidence.tool_call`

`cloudra/tools/Plantool/dag_tools/dag_submit_step_evidence.py:88–319`

```python
    async def tool_call(
        self, user_input: DagSubmitStepEvidenceInput, session: Session
    ) -> DagToolOutput:
        mode = self._mode()
        if mode is OrchestrationMode.STANDARD:
            return self._standard_disabled()

        ctx = await self._prepare(session)
        workspace_root = getattr(self.subagent, "working_directory", None) or os.getcwd()

        # 1. Check if step exists in delivery graph
        snapshot = await asyncio.to_thread(ctx.store.load_snapshot)
        matching_edges = [
            e
            for e in snapshot.delivery.edges
            if getattr(e, "name", "") == user_input.step_name
            or getattr(e, "label", "") == user_input.step_name
            or e.edge_id == user_input.step_name
        ]
        if not matching_edges:
            return fail(
                "dag_submit_step_evidence",
                f"Step '{user_input.step_name}' does not exist in the delivery graph",
                accepted=False,
            )
        step = matching_edges[0]
        endpoint_refs = {}
        for key, field_name, path in [
            ('endpoint_b', 'source_minimum_file', user_input.source_minimum_file),
            ('endpoint_a', 'target_minimum_file', user_input.target_minimum_file),
        ]:
            if path:
                try:
                    minimum = await asyncio.to_thread(snapshot_evidence_file, path,
                        workspace_root=workspace_root, conversation_id=ctx.conversation_id)
                    endpoint_refs[key] = await asyncio.to_thread(ctx.store.register_evidence,
                        session.id, Path(path).name, minimum.model_dump(mode='json'), source_type='file')
                except Exception as exc:
                    return fail('dag_submit_step_evidence',
                        f"Failed to ingest {field_name} '{path}': {exc}", accepted=False)

        # 2. Snapshot TS file and validate vibration mode
        # snapshot_evidence_file 全量读文件 + cclib 解析（同步重活），卸载出事件循环。
        try:
            ts_snap = await asyncio.to_thread(
                snapshot_evidence_file,
                user_input.ts_file,
                workspace_root=workspace_root,
                conversation_id=ctx.conversation_id,
            )
        except Exception as exc:
            return fail("dag_submit_step_evidence", f"Failed to ingest TS file: {exc}", accepted=False)

        opt_snap = None
        if user_input.opt_file:
            try:
                opt_snap = await asyncio.to_thread(snapshot_evidence_file, user_input.opt_file,
                    workspace_root=workspace_root, conversation_id=ctx.conversation_id)
                from cloudra.dag.file_science import validate_frequency_geometry
                await asyncio.to_thread(validate_frequency_geometry, opt_snap, ts_snap)
            except Exception as exc:
                return fail('dag_submit_step_evidence', f'Optimization/frequency evidence mismatch: {exc}', accepted=False)

        ts_val = validate_ts_mode(
            ts_snap.frequencies,
            ts_snap.normal_modes,
            description=user_input.reaction_coordinate_description,
            imaginary_freqs=ts_snap.imaginary_frequencies,
        )
        if ctx.mode is OrchestrationMode.DAG_RECORD and not ts_val.frequency_count_valid:
            kind = "was not verified" if not ts_val.frequency_data_present else "failed validation"
            return fail(
                "dag_submit_step_evidence",
                f"TS {kind}: {ts_val.message}",
                accepted=False,
            )

        # 3. Snapshot optional IRC files
        irc_snaps: dict[str, Any] = {}
        irc_refs = []
        for key, path in [
            ("irc_file", user_input.irc_file),
            ("irc_forward_file", user_input.irc_forward_file),
            ("irc_reverse_file", user_input.irc_reverse_file),
        ]:
            if path:
                try:
                    snap = await asyncio.to_thread(
                        snapshot_evidence_file,
                        path,
                        workspace_root=workspace_root,
                        conversation_id=ctx.conversation_id,
                    )
                    irc_snaps[key] = snap.model_dump(mode="json")
                    irc_refs.append(
                        await asyncio.to_thread(
                            ctx.store.register_evidence,
                            session.id,
                            Path(path).name,
                            snap.model_dump(mode="json"),
                            source_type="file",
                        )
                    )
                except Exception as exc:
                    return fail("dag_submit_step_evidence", f"Failed to ingest IRC file '{path}': {exc}", accepted=False)

        # 4. Register evidence in store
        ref = await asyncio.to_thread(
            ctx.store.register_evidence,
            session.id,
            Path(user_input.ts_file).name,
            ts_snap.model_dump(mode="json"),
            source_type="file",
        )
        opt_refs = []
        if opt_snap is not None:
            opt_refs.append(await asyncio.to_thread(ctx.store.register_evidence, session.id,
                Path(opt_snap.original_path).name, opt_snap.model_dump(mode='json'), source_type='file'))

        operations: list[GraphOperation] = [
            AttachRef(
                op="attach_ref",
                graph="delivery",
                target_type="edge",
                target_id=step.edge_id,
                ref=evidence_ref,
            )
            for evidence_ref in [ref, *opt_refs, *irc_refs, *endpoint_refs.values()]
        ]

        # 5. Adjudicate according to orchestration mode
        if ctx.mode is OrchestrationMode.DAG_RECORD:
            # dag_record 只挂快照；evidence_level 由阶段绑定派生，不在这里写。
            mutation = await asyncio.to_thread(
                apply_mutation,
                ctx.store,
                ctx.engine,
                session_id=session.id,
                actor=GraphActor.HARNESS,
                actor_id="harness",
                operations=operations,
                rationale=f"Auto-accept step evidence for {user_input.step_name}",
            )
            if not mutation.accepted:
                return fail(
                    "dag_submit_step_evidence",
                    mutation.rejection_reason or "Failed to record step evidence mutation",
                    accepted=False,
                )
            return DagToolOutput(
                is_success=True,
                action="dag_submit_step_evidence",
                accepted=True,
                result={
                    "step_name": user_input.step_name,
                    "status": "attached",
                    "ts_validation": ts_val.model_dump(),
                    "message": (
                        f"Step '{user_input.step_name}' evidence attached; "
                        "bind stages with dag_bind_evidence / dag_review_call."
                    ),
                },
            )

        # DAG_GUIDED mode: submit for supervisor review
        mutation = await asyncio.to_thread(
            apply_mutation,
            ctx.store,
            ctx.engine,
            session_id=session.id,
            actor=GraphActor.HARNESS,
            actor_id="harness",
            operations=operations,
            rationale=f"Attach step evidence for {user_input.step_name}",
        )
        if not mutation.accepted:
            return fail(
                "dag_submit_step_evidence",
                mutation.rejection_reason or "Failed to attach step evidence",
                accepted=False,
            )

        from cloudra.dag.file_science import file_scientific_checks
        graph = await asyncio.to_thread(ctx.store.load_snapshot)
        scientific_checks = await asyncio.to_thread(file_scientific_checks, ctx.store, graph.delivery, step.edge_id, irc_files=irc_snaps, workspace_root=workspace_root,
            evidence_refs=[ref, *opt_refs, *irc_refs, *endpoint_refs.values()], endpoint_refs=endpoint_refs)

        review = ActiveReview(
            review_id=f"rev_{uuid.uuid4().hex}",
            kind="step",
            target_name=user_input.step_name,
            target_id=step.edge_id,
            requester=session.id,
            details={
                "scientific_checks": scientific_checks,
                "element_type": "step",
                "step_name": user_input.step_name,
                "target_identity": review_target_identity(snapshot.delivery, "step", step.edge_id),
                "ts_file": user_input.ts_file,
                "opt_file": user_input.opt_file,
                "ts_validation": ts_val.model_dump(),
                "irc_files": irc_snaps,
                "endpoint_refs": {key: ref.model_dump(mode='json') for key, ref in endpoint_refs.items()},
                "reaction_coordinate_description": user_input.reaction_coordinate_description,
            },
            supporting_refs=[ref, *opt_refs, *irc_refs, *endpoint_refs.values()],
            basis_fingerprint=ts_snap.sha256,
        )
        enqueued = await asyncio.to_thread(
            ReviewContextManager.set_active_review,
            ctx.conversation_id, review, ctx.db,
        )

        if not enqueued:
            return fail("dag_submit_step_evidence", "Failed to persist evidence review request", accepted=False)

        # 督导唤醒不在工具内做：queued review 落库后由 DAG policy 完成钩子
        # （_trigger_supervisor_after_tool）按这里的回执统一 notify_supervisor。
        return DagToolOutput(
            is_success=True,
            action="dag_submit_step_evidence",
            accepted=True,
            result={
                "step_name": user_input.step_name,
                "status": "submitted_for_review",
                "scientific_checks": scientific_checks,
                "ts_validation": ts_val.model_dump(),
                "review_id": review.review_id,
                "enqueued": enqueued,
                "message": f"Step '{user_input.step_name}' evidence submitted for Supervisor review.",
            },
        )
```


## `cloudra/tools/core/calculation_intent.py`

文件 SHA-256：`6e3f88854e7a3953dde133a9ece6884ef1189b97b4876fccb2169fe22186b81c`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/tools/core/calculation_intent.py:31–31`

```python
_WRITER_TASK_KEYS = frozenset({"opt", "freq", "irc", "scan", "sp", "single_point"})
```


`cloudra/tools/core/calculation_intent.py:34–34`

```python
_WRITER_KEY_CANONICAL = {"sp": "single_point"}
```


`cloudra/tools/core/calculation_intent.py:36–36`

```python
_GAUSSIAN_ONLY_OPT_SUBOPTIONS = {"calcfc", "noeigen", "calcall", "qst2", "qst3"}
```


`cloudra/tools/core/calculation_intent.py:38–38`

```python
_FREQ_NUMERIC_ALIASES = {"num", "numer", "numeric", "numfreq"}
```


`cloudra/tools/core/calculation_intent.py:39–39`

```python
_ORCA_FREQUENCY_MODES = {'freq': 'analytic', 'anfreq': 'analytic', 'numfreq': 'numeric'}
```


`cloudra/tools/core/calculation_intent.py:43–46`

```python
_NATIVE_UNCLASSIFIED_TASK_TOKENS = {
    'orca': {'engrad', 'gradient', 'md', 'eprnmr', 'nmr', 'polar', 'neb', 'neb-ci'},
    'gaussian': {'force', 'gradient', 'nmr', 'polar', 'bomd', 'admp', 'stable', 'volume'},
}
```


`cloudra/tools/core/calculation_intent.py:459–474`

```python
_ORCA_SIMPLE_TASK_TOKENS = {
    "sp": "single_point",
    "opt": "minimum_opt",
    "tightopt": "minimum_opt",
    "verytightopt": "minimum_opt",
    "looseopt": "minimum_opt",
    "optts": "ts_opt",
    "scants": "ts_opt",
    "neb-ts": "ts_opt",
    "loose-neb-ts": "ts_opt",
    "tight-neb-ts": "ts_opt",
    "fast-neb-ts": "ts_opt",
    "zoom-neb-ts": "ts_opt",
    **dict.fromkeys(_ORCA_FREQUENCY_MODES, 'frequency'),
    "irc": "irc",
}
```


<a id="s141"></a>

### S141 · `CalculationIntent`

`cloudra/tools/core/calculation_intent.py:50–63`

```python
class CalculationIntent(BaseModel):
    """Normalized calculation intent; unknown fields stay None/unknown."""

    engine: str
    engine_version: str | None = None
    provider: str | None = None
    tasks: set[str] = Field(default_factory=set)
    frequency_mode: Literal["auto", "analytic", "numeric"] = "auto"
    constraints: list[dict] = Field(default_factory=list)
    charge: int | None = None
    multiplicity: int | None = None
    method_signature: str | None = None
    geometry_hash: str | None = None
    certainty: Literal["known", "partial", "unknown"] = "unknown"
```


<a id="s142"></a>

### S142 · `_entry`

`cloudra/tools/core/calculation_intent.py:66–67`

```python
def _entry(code: str, field: str, message: str, *, severity: str = 'warning') -> dict:
    return {"code": code, "field": field, "message": message, "severity": severity}
```


<a id="s143"></a>

### S143 · `_gaussian_keyword`

`cloudra/tools/core/calculation_intent.py:75–80`

```python
def _gaussian_keyword(token: str) -> tuple[str, str]:
    head, opening, options = token.partition('(')
    if opening and head.removesuffix('=') in {'opt', 'freq', 'irc', 'scan'}:
        return head.removesuffix('='), options.removesuffix(')')
    key, _, value = token.partition('=')
    return key, value
```


<a id="s144"></a>

### S144 · `_orca_task_head`

`cloudra/tools/core/calculation_intent.py:83–85`

```python
def _orca_task_head(token: str) -> str:
    """Classify a simple native task while retaining any supplied parameters."""
    return token.partition('=')[0].partition('(')[0].strip()
```


<a id="s145"></a>

### S145 · `_gaussian_tasks`

`cloudra/tools/core/calculation_intent.py:88–99`

```python
def _gaussian_tasks(tokens: list[str]) -> set[str]:
    tasks = set()
    for token in tokens:
        key, value = _gaussian_keyword(token)
        if key == 'opt':
            options = set(value.strip('()').replace(' ', '').split(','))
            tasks.add('ts_opt' if options & {'ts', 'qst2', 'qst3'} else 'minimum_opt')
        elif key == 'freq':
            tasks.add('frequency')
        elif key in {'irc', 'scan', 'sp'}:
            tasks.add({'irc': 'irc', 'scan': 'relaxed_scan', 'sp': 'single_point'}[key])
    return tasks
```


<a id="s146"></a>

### S146 · `_gaussian_modredundant`

`cloudra/tools/core/calculation_intent.py:102–104`

```python
def _gaussian_modredundant(tokens: list[str]) -> bool:
    return any(key == 'opt' and 'modredundant' in value.strip('()').replace(' ', '').split(',')
               for key, value in map(_gaussian_keyword, tokens))
```


<a id="s147"></a>

### S147 · `_gaussian_scan_cards`

`cloudra/tools/core/calculation_intent.py:107–127`

```python
def _gaussian_scan_cards(tokens: list[str]) -> bool:
    """Recognize typed ModRedundant S cards, not letters in a title or basis."""
    for index, token in enumerate(tokens):
        count = {'b': 2, 'a': 3, 'd': 4}.get(token)
        if count is None or index + count + 3 >= len(tokens):
            continue
        try:
            for atom in tokens[index + 1:index + count + 1]:
                if atom != '*':
                    int(atom)
            action = index + count + 1
            if tokens[action] != 's':
                float(tokens[action])  # An optional explicit coordinate value.
                action += 1
            if tokens[action] == 's' and action + 2 < len(tokens):
                int(tokens[action + 1])
                float(tokens[action + 2])
                return True
        except (ValueError, IndexError):
            continue
    return False
```


<a id="s148"></a>

### S148 · `declared_native_tasks`

`cloudra/tools/core/calculation_intent.py:130–186`

```python
def declared_native_tasks(arguments: Mapping[str, Any]) -> tuple[set[str], list[str]]:
    """Normalize declared tasks and native keywords independently of rendering."""
    tasks: set[str] = set()
    unknown: list[str] = []
    engine = str(arguments.get('engine') or 'gaussian').lower()
    opt_tokens = []
    for task in arguments.get("task_type") or []:
        if not isinstance(task, dict):
            unknown.append(repr(task))
            continue
        for key, value in task.items():
            key_l = str(key).lower()
            params = str(value).lower() if value is not None else ""
            if key_l not in _WRITER_TASK_KEYS:
                if engine == 'orca' and _orca_task_head(key_l) in _ORCA_SIMPLE_TASK_TOKENS:
                    tasks.add(_ORCA_SIMPLE_TASK_TOKENS[_orca_task_head(key_l)])
                else:
                    unknown.append(key_l)
                continue
            if key_l == "opt":
                opt_tokens.append('opt=' + params)
                ts_options = {'ts', 'qst2', 'qst3'} if engine == 'gaussian' else {'ts'}
                if ts_options & {p.strip(' ()') for p in params.split(",") if p.strip()}:
                    tasks.add("ts_opt")
                else:
                    tasks.add("minimum_opt")
            elif key_l == "freq":
                tasks.add("frequency")
            elif key_l == "irc":
                tasks.add("irc")
            elif key_l == "scan":
                if engine == 'gaussian':
                    tasks.add("relaxed_scan")
                else:
                    unknown.append(key_l)
            elif key_l in ("sp", "single_point"):
                tasks.add("single_point")
    try:
        tokens = native_tokens(str(arguments.get('keywords') or ''))
        if engine == 'gaussian':
            tasks.update(_gaussian_tasks(tokens))
            if ('minimum_opt' in tasks and _gaussian_modredundant(opt_tokens + tokens)
                    and _gaussian_scan_cards(native_tokens(str(arguments.get('end_setting') or '')))):
                tasks.remove('minimum_opt')
                tasks.add('relaxed_scan')
        elif engine == 'orca':
            tasks.update(_ORCA_SIMPLE_TASK_TOKENS[_orca_task_head(token)] for token in tokens
                         if _orca_task_head(token) in _ORCA_SIMPLE_TASK_TOKENS)
            geom = orca_directives(str(arguments.get('orca_blocks') or ''))[1].get('geom', [])
            if 'scan' in geom:
                tasks.discard('minimum_opt')
                tasks.add('relaxed_scan')
        unknown.extend(token for token in tokens
                       if token.partition('=')[0].partition('(')[0] in _NATIVE_UNCLASSIFIED_TASK_TOKENS.get(engine, set()))
    except ValueError as exc:
        unknown.append(str(exc))
    return tasks, unknown
```


<a id="s149"></a>

### S149 · `_frequency_declarations`

`cloudra/tools/core/calculation_intent.py:189–216`

```python
def _frequency_declarations(arguments: dict[str, Any]) -> list[tuple[str, str]]:
    declarations = []
    mode = str(arguments.get('frequency_mode') or 'auto').lower()
    if mode in {'numeric', 'analytic'}:
        declarations.append(('frequency_mode', mode))
    for task in arguments.get('task_type') or []:
        if isinstance(task, dict):
            for key, value in task.items():
                key_l = str(key).lower()
                if str(arguments.get('engine') or 'gaussian').lower() == 'orca':
                    key_l = _orca_task_head(key_l)
                if (str(arguments.get('engine') or 'gaussian').lower() == 'orca'
                        and key_l in _ORCA_FREQUENCY_MODES and key_l != 'freq'):
                    declarations.append(('task_type', _ORCA_FREQUENCY_MODES[key_l]))
                if key_l == 'freq' and value is not None:
                    for option in str(value).strip(' ()').lower().split(','):
                        if option in _FREQ_NUMERIC_ALIASES or option == 'analytic':
                            declarations.append(('task_type', 'numeric' if option in _FREQ_NUMERIC_ALIASES else 'analytic'))
    tokens = native_tokens(str(arguments.get('keywords') or ''))
    if str(arguments.get('engine') or 'gaussian').lower() == 'gaussian':
        for key, value in map(_gaussian_keyword, tokens):
            if key == 'freq':
                options = set(value.strip('()').split(','))
                declarations.append(('keywords', 'numeric' if options & _FREQ_NUMERIC_ALIASES else 'analytic'))
    else:
        declarations.extend(('keywords', _ORCA_FREQUENCY_MODES[_orca_task_head(token)])
                            for token in tokens if _orca_task_head(token) in _ORCA_FREQUENCY_MODES)
    return declarations
```


<a id="s150"></a>

### S150 · `_writer_frequency_mode`

`cloudra/tools/core/calculation_intent.py:219–229`

```python
def _writer_frequency_mode(arguments: dict[str, Any]) -> str:
    mode = str(arguments.get("frequency_mode") or "auto").lower()
    if mode != "auto":
        return mode
    try:
        declarations = _frequency_declarations(arguments)
    except ValueError:
        return 'auto'  # validate_writer_request reports the malformed native field.
    if declarations:
        return declarations[0][1]
    return "auto"
```


<a id="s151"></a>

### S151 · `intent_from_writer`

`cloudra/tools/core/calculation_intent.py:232–258`

```python
def intent_from_writer(arguments: dict[str, Any]) -> CalculationIntent:
    """Normalize qm_input_writer arguments into a CalculationIntent."""
    engine = str(arguments.get("engine") or "gaussian").lower()
    tasks, unknown = declared_native_tasks(arguments)
    external = arguments.get("external_program")
    provider = Path(str(external)).name.lower() if external else None
    method = str(arguments.get("method") or "").strip()
    basis = str(arguments.get("basis_set") or "").strip()
    if external:
        method_signature = f"external:{provider}"
    elif method and basis:
        method_signature = f"{method}/{basis}"
    elif method:
        method_signature = method
    else:
        method_signature = None
    certainty = "known" if tasks and not unknown else ("partial" if tasks else "unknown")
    return CalculationIntent(
        engine=engine,
        provider=provider,
        tasks=tasks,
        frequency_mode=_writer_frequency_mode(arguments),  # type: ignore[arg-type]
        charge=arguments.get("charge"),
        multiplicity=arguments.get("multiplicity"),
        method_signature=method_signature,
        certainty=certainty,
    )
```


<a id="s152"></a>

### S152 · `validate_writer_request`

`cloudra/tools/core/calculation_intent.py:261–452`

```python
def validate_writer_request(arguments: dict[str, Any]) -> list[dict]:
    """Return model-visible option advice and structural syntax errors.

    Engine-specific settings are preserved even when questionable. Only an
    ``error`` entry means the request cannot be structurally interpreted.
    """
    entries: list[dict] = []
    engine = str(arguments.get("engine") or "gaussian").lower()
    task_type = arguments.get("task_type") or []
    from cloudra.tools.core.qm_keywords import is_basis_keyword

    method = str(arguments.get('method') or '')
    basis = str(arguments.get('basis_set') or '')
    _, separator, suffix = method.partition('/')
    if any(character.isspace() for character in method) or is_basis_keyword(method) or (separator and is_basis_keyword(suffix)):
        entries.append(_entry('native_method_layout', 'method',
            'method contains a basis or multiple native tokens. Its text is preserved; use separate method, basis_set and keywords fields to make the declaration unambiguous.'))
    if any(character.isspace() for character in basis):
        entries.append(_entry('native_basis_layout', 'basis_set',
            'basis_set contains multiple native tokens. Its text is preserved; check the engine basis syntax.'))
    for token in str(arguments.get('keywords') or '').split():
        head, slash, tail = token.rpartition('/')
        auxiliary = slash and is_basis_keyword(head) and tail.lower() in {'j', 'jk', 'jksmall', 'c'}
        if not auxiliary and (is_basis_keyword(token) or (slash and is_basis_keyword(tail))):
            entries.append(_entry('orbital_basis_in_keywords', 'keywords',
                f'Native keywords contain orbital basis {token!r}; its text is preserved. Review it together with basis_set.'))
    for field in ('method', 'basis_set', 'orca_blocks', 'end_setting'):
        try:
            native_tokens(str(arguments.get(field) or ''))
        except ValueError as exc:
            entries.append(_entry('malformed_native_' + field, field, str(exc)))

    seen: dict[str, Any] = {}
    for task in task_type:
        if not isinstance(task, dict):
            entries.append(_entry(
                "malformed_task", "task_type",
                f"task_type entries must be dicts like {{'opt': None}}; got {task!r}.",
                severity='error',
            ))
            continue
        for key, value in task.items():
            key_l = str(key).lower()
            try:
                native_tokens(str(key) + ('=' + str(value) if value is not None else ''))
            except ValueError as exc:
                entries.append(_entry('malformed_native_task', 'task_type', str(exc)))
            if key_l not in _WRITER_TASK_KEYS and not (engine == 'orca' and _orca_task_head(key_l) in _ORCA_SIMPLE_TASK_TOKENS):
                entries.append(_entry(
                    "unknown_task_key", "task_type",
                    f"Task {key!r} is outside Cloudra's task classification; its native spelling "
                    "and value are preserved. Check the engine's task syntax.",
                ))
            # 语义等价拼写（sp/single_point）归一后判重，不能借拼写绕过
            canonical = _WRITER_KEY_CANONICAL.get(key_l, key_l)
            if canonical in seen and seen[canonical] != value:
                entries.append(_entry(
                    "conflicting_task", "task_type",
                    f"Task {canonical!r} given twice with conflicting parameters "
                    f"({seen[canonical]!r} vs {value!r}); merge them into one entry.",
                ))
            elif canonical in seen:
                entries.append(_entry(
                    "duplicate_task", "task_type",
                    f"Task {canonical!r} appears more than once; keep a single entry.",
                ))
            seen[canonical] = value

    tasks, _ = declared_native_tasks(arguments)
    try:
        tokens = native_tokens(str(arguments.get('keywords') or ''))
        declarations = _frequency_declarations(arguments)
    except ValueError as exc:
        entries.append(_entry('malformed_native_keywords', 'keywords', str(exc)))
        tokens, declarations = [], []
    if len({mode for _, mode in declarations}) > 1:
        entries.append(_entry('conflicting_frequency_mode', 'keywords' if any(field == 'keywords' for field, _ in declarations) else 'frequency_mode',
            'Conflicting frequency evaluation settings: ' + ', '.join(f'{field}={mode}' for field, mode in declarations)
            + '; declare one consistent analytic/numeric evaluation.'))
    if engine == 'gaussian':
        opt_tasks = _gaussian_tasks(tokens) & {'minimum_opt', 'ts_opt'}
        if 'opt' in seen:
            opt_tasks.update(_gaussian_tasks(['opt=' + str(seen['opt'] or '').lower()]))
    else:
        opt_tasks = {_ORCA_SIMPLE_TASK_TOKENS[_orca_task_head(token)] for token in tokens
                     if _orca_task_head(token) in _ORCA_SIMPLE_TASK_TOKENS} & {'minimum_opt', 'ts_opt'}
        if 'opt' in seen:
            opt_tasks.add('ts_opt' if 'ts' in str(seen['opt']).lower().split(',') else 'minimum_opt')
    if len(opt_tasks) > 1:
        entries.append(_entry('conflicting_task', 'keywords',
            'task_type and keywords declare conflicting minimum and TS optimizations; keep one consistent opt declaration.'))
    mode = str(arguments.get("frequency_mode") or "auto").lower()
    if mode not in ("auto", "analytic", "numeric"):
        entries.append(_entry(
            "unknown_frequency_mode", "frequency_mode",
            f"frequency_mode must be one of auto/analytic/numeric; got {mode!r}.",
        ))
    elif mode != "auto" and "frequency" not in tasks:
        entries.append(_entry(
            "frequency_mode_without_frequency", "frequency_mode",
            "frequency_mode was set but no frequency task was requested; "
            "add {'freq': None} or drop frequency_mode.",
        ))

    if engine == "orca":
        for token in tokens:
            head = _orca_task_head(token)
            if head in _ORCA_SIMPLE_TASK_TOKENS and token != head:
                entries.append(_entry('native_task_parameters', 'keywords',
                    f'ORCA simple task {head!r} was given parameters in {token!r}; the original text is preserved. Check native keyword/% block syntax.'))
        try:
            raw_blocks = str(arguments.get('orca_blocks') or '')
            block_tokens = native_tokens(raw_blocks)
            for index, token in enumerate(block_tokens):
                if token.startswith('%') and token != '%maxcore':
                    following = next((i for i in range(index + 1, len(block_tokens)) if block_tokens[i].startswith('%')), len(block_tokens))
                    if 'end' not in block_tokens[index + 1:following] and token not in {'%base', '%moinp', '%pointcharges'}:
                        entries.append(_entry('malformed_native_blocks', 'orca_blocks',
                            f'Native block {token} has no closing end; the original block text is preserved.'))
        except ValueError as exc:
            entries.append(_entry('malformed_native_blocks', 'orca_blocks', str(exc)))
        _, malformed_constraints = _orca_constraints(str(arguments.get('orca_blocks') or ''))
        for message in malformed_constraints:
            entries.append(_entry('native_constraint_parameters', 'orca_blocks', message))
        if "scan" in seen:
            entries.append(_entry(
                "scan_requires_ts_guess", "task_type",
                "ORCA scans need native %geom Scan coordinates, or ts_guess mode='scan_prepare'. "
                "The declared native text is preserved; a task label alone does not define a scan.",
            ))
        for key, value in seen.items():
            if (_orca_task_head(key) in _ORCA_SIMPLE_TASK_TOKENS and key not in _WRITER_TASK_KEYS
                    and (value is not None or key != _orca_task_head(key))):
                entries.append(_entry('native_task_parameters', 'task_type',
                    f'ORCA simple task {key!r} was given parameters {value!r}; the original text is preserved. Check native keyword/% block syntax.'))
            params = {p.strip() for p in str(value).lower().split(",") if p.strip()} if value is not None else set()
            if key == "opt":
                bad = sorted(params & _GAUSSIAN_ONLY_OPT_SUBOPTIONS)
                if bad:
                    entries.append(_entry(
                        "gaussian_only_suboption", "task_type",
                        f"ORCA inputs do not accept Gaussian opt sub-options {bad}; "
                        "control the TS Hessian through native orca_blocks "
                        "(%geom Calc_Hess / Hess_Source) instead.",
                    ))
                remaining = sorted(params - {'ts'} - _GAUSSIAN_ONLY_OPT_SUBOPTIONS)
                if remaining:
                    entries.append(_entry('native_task_parameters', 'task_type',
                        f"ORCA opt parameters {remaining} are passed through unchanged after the task keyword; "
                        "use native keywords (for example TightOpt) or orca_blocks for engine-specific controls."))
            if key == "freq" and value is not None:
                unknown_freq = sorted(params - _FREQ_NUMERIC_ALIASES - {'analytic'})
                if unknown_freq:
                    entries.append(_entry(
                        "unknown_freq_suboption", "task_type",
                        f"Unknown ORCA freq sub-options {unknown_freq}; use "
                        "frequency_mode='numeric' for NumFreq or native orca_blocks.",
                    ))
            if key in {'irc', 'scan', 'single_point'} and value is not None:
                entries.append(_entry('native_task_parameters', 'task_type',
                    f"ORCA {key} parameters {value!r} are preserved verbatim; check native keyword/% block syntax."))
        if str(arguments.get("end_setting") or "").strip():
            entries.append(_entry(
                "gaussian_only_field", "end_setting",
                "end_setting is a Gaussian end-of-file section; ORCA has no such "
                "card — express the setting in orca_blocks instead.",
            ))
    elif engine == 'gaussian':
        from cloudra.tools.core.native_input_sections import gaussian_coordinate_units

        if gaussian_coordinate_units(tokens) == 'unknown':
            entries.append(_entry('unknown_coordinate_units', 'keywords',
                'Gaussian coordinate units are unknown or conflicting; the native declaration is preserved. Coordinate conversion cannot be determined.'))
        if arguments.get('orca_blocks'):
            entries.append(_entry('orca_only_field', 'orca_blocks',
                'orca_blocks is not Gaussian syntax; its text is preserved in the trailing section.'))
        if 'scan' in seen and str(seen['scan']).lower() != 'rigid':
            entries.append(_entry('gaussian_scan_semantics', 'task_type',
                "Gaussian scan is RIGID; RELAXED scans use opt=modredundant and trailing coordinates. "
                "The original task and parameters are preserved."))
        hessian_options = {'calcfc', 'calcall', 'readfc', 'rcfc'}
        task_tokens = [str(key) + '=' + str(value or '').lower() for key, value in seen.items() if key in {'opt', 'irc'}]
        for token in tokens + task_tokens:
            key, value = _gaussian_keyword(token)
            options = set(value.strip('()').replace(' ', '').split(','))
            if key == 'opt' and 'ts' in options and not options & hessian_options:
                entries.append(_entry('initial_hessian_unspecified', 'task_type' if 'opt' in seen else 'keywords',
                    'Gaussian TS optimization has no explicit initial-Hessian setting; review the native engine defaults for this calculation. No solver option was added.'))
            elif key == 'irc' and not options & hessian_options:
                entries.append(_entry('initial_hessian_unspecified', 'keywords',
                    'Gaussian IRC has no explicit initial-Hessian setting; review the native engine defaults for this calculation. No solver option was added.'))
    return entries
```


<a id="s153"></a>

### S153 · `native_tokens`

`cloudra/tools/core/calculation_intent.py:477–523`

```python
def native_tokens(text: str) -> list[str]:
    """Tokenize native directives, keeping parenthesized and quoted values intact."""
    tokens, current = [], []
    quote = ""
    depth = 0
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
        elif char in ("\"", "'"):
            quote = char
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced native parentheses")
            current.append(char)
        elif char.isspace() and depth == 0:
            if current:
                tokens.append("".join(current).lower())
                current = []
        else:
            current.append(char)
    if quote or depth:
        raise ValueError("unclosed native quote or parentheses")
    if current:
        tokens.append("".join(current).lower())
    joined = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if i + 2 < len(tokens) and tokens[i + 1] == '=':
            token += '=' + tokens[i + 2]
            i += 2
        elif i + 1 < len(tokens) and token.endswith('='):
            token += tokens[i + 1]
            i += 1
        elif i + 1 < len(tokens) and tokens[i + 1].startswith('='):
            token += tokens[i + 1]
            i += 1
        joined.append(token)
        i += 1
    return joined
```


<a id="s154"></a>

### S154 · `_orca_code`

`cloudra/tools/core/calculation_intent.py:526–544`

```python
def _orca_code(text: str) -> str:
    lines = []
    for line in text.splitlines():
        code, quote, comment = [], "", False
        for char in line:
            if quote:
                code.append(char)
                if char == quote:
                    quote = ""
            elif char in ("\"", "'") and not comment:
                quote = char
                code.append(char)
            elif char == "#":
                comment = not comment
                code.append(" ")
            elif not comment:
                code.append(char)
        lines.append("".join(code))
    return "\n".join(lines)
```


<a id="s155"></a>

### S155 · `gaussian_routes`

`cloudra/tools/core/calculation_intent.py:547–550`

```python
def gaussian_routes(text: str) -> list[list[str]]:
    from cloudra.tools.core.native_input_sections import gaussian_sections

    return [native_tokens(' '.join(section.route)) for section in gaussian_sections(text)]
```


<a id="s156"></a>

### S156 · `orca_directives`

`cloudra/tools/core/calculation_intent.py:553–571`

```python
def orca_directives(text: str) -> tuple[list[str], dict[str, list[str]]]:
    simple, blocks = [], {}
    active = None
    for line in _orca_code(text).splitlines():
        line = line.strip()
        if line.startswith("!/"):
            continue
        if line.startswith("!"):
            simple.extend(native_tokens(line[1:]))
            active = None
        elif line.startswith("%"):
            tokens = native_tokens(line)
            active = tokens[0][1:]
            blocks.setdefault(active, []).extend(tokens[1:])
        elif line.startswith("*"):
            active = None
        elif active:
            blocks[active].extend(native_tokens(line))
    return simple, blocks
```


<a id="s157"></a>

### S157 · `_native_charges`

`cloudra/tools/core/calculation_intent.py:574–579`

```python
def _native_charges(text: str, engine: str) -> list[tuple[int, int]]:
    from cloudra.tools.core.native_input_sections import gaussian_sections, orca_xyz_sections

    if engine == 'orca':
        return [charge for charge, _ in orca_xyz_sections(text)]
    return [section.charge for section in gaussian_sections(text) if section.charge is not None]
```


<a id="s158"></a>

### S158 · `_inspect_orca`

`cloudra/tools/core/calculation_intent.py:582–612`

```python
def _inspect_orca(text: str) -> CalculationIntent:
    tokens, blocks = orca_directives(text)
    task_heads = {_orca_task_head(token) for token in tokens}
    tasks = {_ORCA_SIMPLE_TASK_TOKENS[head] for head in task_heads if head in _ORCA_SIMPLE_TASK_TOKENS}
    geom = blocks.get("geom", [])
    neb = blocks.get("neb", [])
    for i, token in enumerate(neb):
        if token.partition("=")[0] == "neb_ts":
            tail = [token.partition("=")[2]] if "=" in token else [t for t in neb[i + 1:i + 3] if t != "="]
            if tail and tail[0] == "true":
                tasks.add("ts_opt")
            elif tail and tail[0] == "false":
                tasks.discard("ts_opt")
    if "scan" in geom:
        tasks.discard("minimum_opt")
        tasks.add("relaxed_scan")
    constraints, _ = _orca_constraints(text)
    provider = None
    method_tokens = blocks.get("method", [])
    if "extopt" in tokens and "progext" in method_tokens:
        pos = method_tokens.index("progext")
        if pos + 1 < len(method_tokens):
            provider = Path(method_tokens[pos + 1].strip("\"'")).name.lower()
    charges = _native_charges(text, "orca")
    return CalculationIntent(engine="orca", provider=provider, tasks=tasks,
        frequency_mode=('numeric' if 'numfreq' in task_heads else
                        'analytic' if task_heads & _ORCA_FREQUENCY_MODES.keys() else 'auto'),
        constraints=constraints, charge=charges[0][0] if charges else None,
        multiplicity=charges[0][1] if charges else None,
        method_signature=f"external:{provider}" if provider else None,
        certainty="known" if tasks else "unknown")
```


<a id="s159"></a>

### S159 · `_orca_constraints`

`cloudra/tools/core/calculation_intent.py:615–627`

```python
def _orca_constraints(text: str) -> tuple[list[dict], list[str]]:
    constraints, messages = [], []
    for raw in _orca_code(text).splitlines():
        tokens_c = raw.replace("{", " { ").replace("}", " } ").split()
        if "{" in tokens_c and "}" in tokens_c:
            start, end = tokens_c.index("{"), tokens_c.index("}")
            body = tokens_c[start + 1:end]
            if len(body) >= 4 and body[0].upper() in {"B", "A", "D", "C"} and body[-1].upper() == "C":
                try:
                    constraints.append(dict(type={"B": "bond", "A": "angle", "D": "dihedral", "C": "cartesian"}[body[0].upper()], atoms=[int(x) for x in body[1:-2]], value=float(body[-2])))
                except ValueError as exc:
                    messages.append(f'Native constraint {raw.strip()!r} could not be interpreted ({exc}); its original text is preserved.')
    return constraints, messages
```


<a id="s160"></a>

### S160 · `_inspect_gaussian`

`cloudra/tools/core/calculation_intent.py:630–657`

```python
def _inspect_gaussian(text: str) -> CalculationIntent:
    routes = gaussian_routes(text)
    tasks, provider, mode = set(), None, "auto"
    trailing = _gaussian_trailing_cards(text)
    for index, route in enumerate(routes):
        route_tasks = _gaussian_tasks(route)
        if ('minimum_opt' in route_tasks and _gaussian_modredundant(route)
                and index < len(trailing) and _gaussian_scan_cards(trailing[index])):
            route_tasks.remove('minimum_opt')
            route_tasks.add('relaxed_scan')
        tasks.update(route_tasks)
        for token in route:
            key, value = _gaussian_keyword(token)
            if key == "freq":
                mode = 'numeric' if set(value.strip('()').split(',')) & _FREQ_NUMERIC_ALIASES else 'analytic'
            elif key == "external" and value:
                provider = Path(value.strip("\"'")).name.lower()
    constraints = []
    for line in text.splitlines():
        tokens = line.upper().split()
        if tokens and tokens[0] in {'B','A','D'} and tokens[-1] == 'F':
            constraints.append(dict(type=tokens[0], atoms=tokens[1:-1]))
    charges = _native_charges(text, "gaussian")
    return CalculationIntent(engine="gaussian", provider=provider, tasks=tasks, constraints=constraints,
        frequency_mode=mode, charge=charges[0][0] if charges else None,
        multiplicity=charges[0][1] if charges else None,
        method_signature=f"external:{provider}" if provider else None,
        certainty="known" if tasks else "unknown")
```


<a id="s161"></a>

### S161 · `inspect_input`

`cloudra/tools/core/calculation_intent.py:660–670`

```python
def inspect_input(text: str, *, engine: str) -> CalculationIntent:
    """Re-read an input file's text and report the intent it actually encodes."""
    engine_l = engine.lower()
    try:
        if engine_l == "orca":
            return _inspect_orca(text)
        if engine_l == "gaussian":
            return _inspect_gaussian(text)
    except ValueError:
        return CalculationIntent(engine=engine_l, certainty='unknown')
    return CalculationIntent(engine=engine_l, certainty="unknown")
```


<a id="s162"></a>

### S162 · `_gaussian_trailing_cards`

`cloudra/tools/core/calculation_intent.py:679–682`

```python
def _gaussian_trailing_cards(content):
    from cloudra.tools.core.native_input_sections import gaussian_sections

    return [native_tokens(' '.join(section.trailing)) for section in gaussian_sections(content)]
```


<a id="s163"></a>

### S163 · `_generated_gaussian_coordinates`

`cloudra/tools/core/calculation_intent.py:685–705`

```python
def _generated_gaussian_coordinates(tokens):
    i = 0
    while i < len(tokens):
        count = {'b': 2, 'a': 3, 'd': 4}.get(tokens[i])
        if count is None or i + count + 1 >= len(tokens):
            return False
        try:
            for atom in tokens[i+1:i+count+1]:
                int(atom)
            i += count + 1
            if tokens[i] == 'f':
                i += 1
            elif tokens[i] == 's' and i + 2 < len(tokens):
                int(tokens[i+1])
                float(tokens[i+2])
                i += 3
            else:
                return False
        except ValueError:
            return False
    return True
```


<a id="s164"></a>

### S164 · `_writer_orca_controls`

`cloudra/tools/core/calculation_intent.py:708–722`

```python
def _writer_orca_controls(name, tokens):
    if name in ('pal', 'maxcore'):
        return True  # Shared admission independently validates resources.
    allowed = {'geom': {'scan','simul_scan','constraints','b','a','d','c','{','}','=','end'}}.get(name)
    if allowed is None:
        return not tokens
    for token in tokens:
        if token in allowed:
            continue
        try:
            for value in token.split('='):
                float(value.rstrip(','))
        except ValueError:
            return False
    return True
```


<a id="s165"></a>

### S165 · `MethodDifference`

`cloudra/tools/core/calculation_intent.py:725–729`

```python
class MethodDifference(BaseModel):
    field: str
    expected: object
    actual: object
    message: str
```


<a id="s166"></a>

### S166 · `compare_calculation_input`

`cloudra/tools/core/calculation_intent.py:732–843`

```python
def compare_calculation_input(content: str, expected: Mapping[str, object], *, charge: int, multiplicity: int) -> list[MethodDifference]:
    """Compare the complete accepted declaration with every native method card.

    Scheduling resources and writer-owned task/geometry controls are independent
    of the electronic-structure contract. Unrecognized electronic tokens remain
    visible differences, rather than being guessed into an allowed method.
    """
    from cloudra.runtime_v2.method_policy import _norm_basis
    engine = str(expected["engine"]).lower()
    differences = []
    def diff(field, want, got):
        if want != got:
            differences.append(MethodDifference(field=field, expected=want, actual=got, message=f"{field}: expected {want!r}; actual {got!r}"))
    try:
        actual = inspect_input(content, engine=engine)
        charges = _native_charges(content, engine)
        diff("charge", [charge] * max(1, len(charges)), [c for c, _ in charges])
        diff("multiplicity", [multiplicity] * max(1, len(charges)), [m for _, m in charges])
        family = str(expected["method"]).strip().lower()
        basis = str(expected["basis_set"]).strip()
        want_method = [family] + ([_norm_basis(basis)] if basis else [])
        want_keywords = sorted(t.replace(" ", "") for t in native_tokens(str(expected.get("keywords") or "")))
        if engine == "orca":
            tokens, blocks = orca_directives(content)
            native_cards = [tokens]
            cards = [[t for t in tokens if _orca_task_head(t) not in _ORCA_SIMPLE_TASK_TOKENS]]
            declared_tasks = [t for t in want_keywords if _orca_task_head(t) in _ORCA_SIMPLE_TASK_TOKENS]
            expected_blocks = orca_directives(str(expected.get("orca_blocks") or ""))[1]
            # These blocks are generated by the writer for the requested task;
            # other blocks must exactly match the explicit native declaration.
            owned = {'pal', 'maxcore', 'geom', 'irc'}
            for name in sorted(set(blocks) | set(expected_blocks)):
                actual_block = list(blocks.get(name, []))
                expected_block = list(expected_blocks.get(name, []))
                if name not in owned:
                    diff('orca_blocks', (name, expected_blocks.get(name)), (name, blocks.get(name)))
                    continue
                if expected_block:
                    position = next((i for i in range(len(actual_block)) if actual_block[i:i+len(expected_block)] == expected_block), None)
                    if position is None:
                        diff('orca_blocks', (name, expected_block), (name, actual_block))
                        continue
                    del actual_block[position:position+len(expected_block)]
                if not _writer_orca_controls(name, actual_block):
                    diff('orca_blocks', (name, 'only explicit settings and writer task controls'), (name, actual_block))
        elif engine == "gaussian":
            trailing = _gaussian_trailing_cards(content)
            expected_tail = native_tokens('\n'.join(filter(None, [str(expected.get('end_setting') or ''), str(expected.get('orca_blocks') or '')])))
            for tail in trailing:
                # Generated ModRedundant scan/freeze cards are task coordinates,
                # not extra electronic settings. All other trailing directives
                # must be explicitly declared.
                if 'relaxed_scan' in actual.tasks:
                    remaining_tail = list(tail)
                    if expected_tail:
                        position = next((i for i in range(len(tail)) if tail[i:i+len(expected_tail)] == expected_tail), None)
                        if position is None:
                            diff('end_setting', expected_tail, tail)
                            continue
                        del remaining_tail[position:position+len(expected_tail)]
                    if not _generated_gaussian_coordinates(remaining_tail):
                        diff('end_setting', 'only explicit settings and generated scan coordinates', tail)
                else:
                    diff('end_setting', expected_tail, tail)
            native_cards = gaussian_routes(content)
            cards = [[t for t in card if _gaussian_keyword(t)[0] not in {"opt", "freq", "irc", "scan", "sp"}] for card in native_cards]
            declared_tasks = [t for t in want_keywords if _gaussian_keyword(t)[0] in {'opt', 'freq', 'irc', 'scan', 'sp'}]
        else:
            diff("engine", "native ORCA or Gaussian input", engine)
            return differences
        # Writer-owned task controls may be added independently, but a task
        # explicitly present in keywords must survive with its exact options.
        for native_card, card in zip(native_cards, cards, strict=True):
            available = [token.replace(' ', '') for token in native_card]
            for token in declared_tasks:
                if token in available:
                    card.append(token)
                    available.remove(token)
        for card in cards:
            remaining = list(card)
            if engine == "gaussian":
                if family == 'external':
                    matched = next((token for token in remaining if _gaussian_keyword(token)[0] == 'external'), None)
                    actual_method = 'external' if matched else None
                elif basis:
                    matched = next((token for token in remaining if token == family + '/' + basis.lower()
                        or (token.rpartition('/')[0] == family and _norm_basis(token.rpartition('/')[2]) == _norm_basis(basis))), None)
                    actual_method = matched.rpartition('/')[0] + '/' + _norm_basis(matched.rpartition('/')[2]) if matched else None
                else:
                    matched = next((token for token in remaining if token == family), None)
                    actual_method = matched
                diff("method", family + ("/" + _norm_basis(basis) if basis else ""), actual_method)
                if matched and family != 'external':
                    remaining.remove(matched)
            else:
                for token in want_method:
                    matched = next((t for t in remaining if (t == token if token == family else _norm_basis(t) == token)), None)
                    diff("method", token, (matched if token == family else _norm_basis(matched)) if matched else None)
                    if matched:
                        remaining.remove(matched)
            diff("keywords", want_keywords, sorted(t.replace(" ", "") for t in remaining))
        mode = expected.get("frequency_mode", "auto")
        if "frequency" in actual.tasks and mode != "auto":
            diff("frequency_mode", mode, actual.frequency_mode)
        if engine == 'orca' and expected.get("end_setting"):
            # Native trailing directives remain ordered; require an exact token
            # sequence at the end, including every scientific setting.
            tail = native_tokens(str(expected["end_setting"]))
            diff("end_setting", tail, native_tokens(content)[-len(tail):])
    except (ValueError, TypeError, KeyError) as exc:
        differences.append(MethodDifference(field="parse", expected="determinate native input", actual=str(exc), message=str(exc)))
    return differences
```


<a id="s167"></a>

### S167 · `native_input_geometry`

`cloudra/tools/core/calculation_intent.py:846–858`

```python
def native_input_geometry(content: str, *, engine: str) -> list[tuple[str, tuple[float, float, float]]]:
    """Read one explicit Cartesian geometry in Angstrom, preserving atom order."""
    from cloudra.tools.core.molecule import _read_gaussian_structure, _read_orca_structure

    if engine.lower() == 'gaussian':
        atoms, _, _, _ = _read_gaussian_structure(content)
    elif engine.lower() == 'orca':
        atoms, _, _, _ = _read_orca_structure(content)
    else:
        raise ValueError(f"Unsupported native geometry engine: {engine}")
    return [(symbol, tuple(map(float, point))) for symbol, point in zip(
        atoms.get_chemical_symbols(), atoms.get_positions(), strict=True,
    )]
```


## `cloudra/tools/core/gaussian_frames.py`

文件 SHA-256：`2746eb2845c4212d22d86866055de6939d241d79acace614807bed03b63da8a6`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/tools/core/gaussian_frames.py:23–23`

```python
EV_PER_HARTREE = 27.211386245988
```


`cloudra/tools/core/gaussian_frames.py:26–26`

```python
_THERMOCHEMISTRY_FLOAT = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DdEe][+-]?\d+)?)"
```


`cloudra/tools/core/gaussian_frames.py:27–38`

```python
_THERMOCHEMISTRY_PATTERNS = {
    "zero_point_correction_hartree": rf"Zero-point correction=\s*{_THERMOCHEMISTRY_FLOAT}",
    "thermal_energy_correction_hartree": rf"Thermal correction to Energy=\s*{_THERMOCHEMISTRY_FLOAT}",
    "thermal_enthalpy_correction_hartree": rf"Thermal correction to Enthalpy=\s*{_THERMOCHEMISTRY_FLOAT}",
    "thermal_gibbs_correction_hartree": rf"Thermal correction to Gibbs Free Energy=\s*{_THERMOCHEMISTRY_FLOAT}",
    "total_zero_point_energy_hartree": rf"Sum of electronic and zero-point Energies=\s*{_THERMOCHEMISTRY_FLOAT}",
    "total_thermal_energy_hartree": rf"Sum of electronic and thermal Energies=\s*{_THERMOCHEMISTRY_FLOAT}",
    "total_enthalpy_hartree": rf"Sum of electronic and thermal Enthalpies=\s*{_THERMOCHEMISTRY_FLOAT}",
    "total_gibbs_free_energy_hartree": rf"Sum of electronic and thermal Free Energies=\s*{_THERMOCHEMISTRY_FLOAT}",
    "temperature_k": rf"Temperature\s+{_THERMOCHEMISTRY_FLOAT}\s+Kelvin",
    "pressure_atm": rf"Pressure\s+{_THERMOCHEMISTRY_FLOAT}\s+Atm",
}
```


`cloudra/tools/core/gaussian_frames.py:211–211`

```python
_FREQ_LINE_RE = re.compile(r"Frequencies --\s+(.*)")
```


`cloudra/tools/core/gaussian_frames.py:212–212`

```python
_ATOM_DISP_HEADER_RE = re.compile(r"^\s*Atom\s+AN\s+X\s+Y\s+Z", re.MULTILINE)
```


`cloudra/tools/core/gaussian_frames.py:216–216`

```python
_NATIVE_FLOAT = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DdEe][+-]?\d+)?)"
```


`cloudra/tools/core/gaussian_frames.py:217–217`

```python
_SCF_ENERGY_RE = re.compile(rf"SCF Done:\s+E\([^)]*\)\s*=\s*{_NATIVE_FLOAT}")
```


`cloudra/tools/core/gaussian_frames.py:218–220`

```python
_CORRELATED_ENERGY_RE = re.compile(
    rf"(?:EUMP[2345]|UMP4\((?:DQ|SDQ|SDTQ)\)|MP5|E\(CORR\)|CCSD\(T\))\s*=\s*{_NATIVE_FLOAT}"
)
```


`cloudra/tools/core/gaussian_frames.py:359–359`

```python
_POINT_HEADER_RE = re.compile(r"Point Number:\s*(\d+)\s+Path Number:\s*(\d+)")
```


`cloudra/tools/core/gaussian_frames.py:360–360`

```python
_NET_RX_RE = re.compile(r"NET REACTION COORDINATE UP TO THIS POINT =\s*(-?[\d.]+)")
```


`cloudra/tools/core/gaussian_frames.py:361–361`

```python
_TS_ENERGY_RE = re.compile(r"Energies reported relative to the TS energy of\s*(-?[\d.]+)")
```


`cloudra/tools/core/gaussian_frames.py:362–365`

```python
_SUMMARY_TABLE_RE = re.compile(
    r"Summary of reaction path following\s*\n\s*-+\s*\n\s*Energy\s+RxCoord\s*\n(.*?)\n\s*-+",
    re.S,
)
```


<a id="s168"></a>

### S168 · `extract_thermochemistry_from_text`

`cloudra/tools/core/gaussian_frames.py:41–80`

```python
def extract_thermochemistry_from_text(text: str) -> dict[str, float]:
    """Read only the last native thermochemistry block, including its conditions.

    Partial final blocks stay partial. Electronic energy is inferred from the
    totals and literal corrections in that block, never from a later SP job.
    """
    starts = list(re.finditer(r"^\s*-\s*Thermochemistry\s*-\s*$", text, re.M))
    if not starts:
        starts = list(re.finditer(r"^\s*Zero-point correction=", text, re.M))
    if not starts:
        return {}
    target = text[starts[-1].start():]
    end = re.search(r"Normal termination|Error termination|--Link1--", target)
    if end:
        target = target[:end.start()]
    values = {
        field: float(match.group(1).replace("D", "E").replace("d", "e"))
        for field, pattern in _THERMOCHEMISTRY_PATTERNS.items()
        if (match := re.search(pattern, target)) is not None
    }
    electronic = [
        values[total] - values[correction]
        for total, correction in (
            ("total_enthalpy_hartree", "thermal_enthalpy_correction_hartree"),
            ("total_gibbs_free_energy_hartree", "thermal_gibbs_correction_hartree"),
        )
        if total in values and correction in values
    ]
    if not electronic:
        electronic = [
            values[total] - values[correction]
            for total, correction in (
                ("total_zero_point_energy_hartree", "zero_point_correction_hartree"),
                ("total_thermal_energy_hartree", "thermal_energy_correction_hartree"),
            )
            if total in values and correction in values
        ]
    if electronic:
        values["electronic_energy_hartree"] = sum(electronic) / len(electronic)
    return values
```


<a id="s169"></a>

### S169 · `FrameRecord`

`cloudra/tools/core/gaussian_frames.py:83–97`

```python
@dataclass
class FrameRecord:
    """A geometry frame and its reported electronic energy.

    The energy can be a native total or an available SCF value for that frame;
    it does not certify the final requested method of the entire log.
    """

    frame: int
    path_number: int | None = None          # IRC 路径号（1=正向 2=反向），其余任务为 None
    reaction_coordinate: float | None = None  # IRC 反应坐标 / 扫描参数值
    electronic_energy_hartree: float | None = None
    frequencies_cm: list[float] = field(default_factory=list)  # 有符号，负值=虚频
    xyz: str = ""                            # 标准 XYZ 块（原子数行+注释行+坐标行）
    converged: bool | None = None            # 末帧/端点帧的收敛标记，其余为 None
```


<a id="s170"></a>

### S170 · `_read_text`

`cloudra/tools/core/gaussian_frames.py:104–106`

```python
def _read_text(log_path: str) -> str:
    with open(log_path, encoding="utf-8", errors="replace") as f:
        return f.read()
```


<a id="s171"></a>

### S171 · `normal_termination`

`cloudra/tools/core/gaussian_frames.py:109–116`

```python
def normal_termination(text: str) -> bool:
    """引擎自报正常结束：出现 Normal termination 且没有 Error termination。

    cclib metadata.success 不是终态权威（缺坐标/ccwrite 失败会丢掉一份
    已经 Normal termination 的日志）。与 ts_guess 同一对标记。
    """
    return (text.rfind("Normal termination") >= last_job_start(text)
            and "Error termination" not in text)
```


<a id="s172"></a>

### S172 · `last_job_start`

`cloudra/tools/core/gaussian_frames.py:119–123`

```python
def last_job_start(text: str) -> int:
    """Last explicitly started Gaussian job, including native Link1 steps."""
    positions = [match.start() for match in re.finditer(
        r"^\s*(?:Link1:\s+Proceeding to internal job step number|Entering Gaussian System)", text, re.M)]
    return positions[-1] if positions else 0
```


<a id="s173"></a>

### S173 · `opt_converged`

`cloudra/tools/core/gaussian_frames.py:126–132`

```python
def opt_converged(text: str) -> bool | None:
    """独立优化的原生收敛标记；IRC corrector 的收敛不构成驻点证据。"""
    if "Optimization stopped." in text:
        return False
    if "Optimization completed." in text or "Stationary point found." in text:
        return True
    return None
```


<a id="s174"></a>

### S174 · `_collect_route_card`

`cloudra/tools/core/gaussian_frames.py:135–154`

```python
def _collect_route_card(text: str) -> str:
    """收集日志中回显的路由行（` #` 开头，可能跨行缠绕），拼接为小写字符串。

    Gaussian 的路由回显块中每行以 " #" 开头；跨行缠绕多为行写满后从 token
    中间断开（如 "stepsize=10,m" / "axpoint=100"），因此同一块内直接无空格
    拼接。IRC 日志里的 " # OF POINTS ALONG THE PATH" 等计数行不是路由，剔除。
    """
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.upper().startswith("# OF"):
            current.append(stripped[1:].strip())
        else:
            if current:
                blocks.append("".join(current))
                current = []
    if current:
        blocks.append("".join(current))
    return " ".join(blocks).lower()
```


<a id="s175"></a>

### S175 · `detect_job_types`

`cloudra/tools/core/gaussian_frames.py:157–166`

```python
def detect_job_types(log_path: str) -> set[str]:
    """识别 Gaussian 日志的任务类型，返回 {"opt","ts","freq","scan","irc","sp"} 的子集。

    依据路由卡（` #` 回显行）+ 结构标记兜底（IRC 的 "IRC-IRC-IRC" 块与
    "Summary of reaction path following"，扫描的 "Summary of Optimized
    Potential Surface Scan" 等）。`ts` 只在路由中出现 opt=(ts...) / opt=ts 时给出。

    限制：Link1 多步任务不拆分 section，按整文件取合集（v1）。
    """
    return detect_job_types_from_text(_read_text(log_path))
```


<a id="s176"></a>

### S176 · `detect_job_types_from_text`

`cloudra/tools/core/gaussian_frames.py:169–191`

```python
def detect_job_types_from_text(text: str) -> set[str]:
    """detect_job_types 的文本变体：调用方已读过日志时避免重复 IO。"""
    route = _collect_route_card(text)
    jobs: set[str] = set()

    if (
        re.search(r"\birc\b|irc\s*[=(]", route)
        or "IRC-IRC-IRC" in text
        or "Summary of reaction path following" in text
    ):
        jobs.add("irc")
    if re.search(r"\bscan\b", route) or "Summary of Optimized Potential Surface Scan" in text:
        jobs.add("scan")
    if re.search(r"\bopt\b|opt\s*=", route) or "Optimization completed" in text:
        jobs.add("opt")
    if re.search(r"opt\s*=\s*\(?\s*ts\b", route) or re.search(r"opt\s*=\s*\([^)]*\bts\b", route):
        jobs.add("ts")
    if re.search(r"\bfreq", route) or "Harmonic frequencies" in text:
        jobs.add("freq")
    if not jobs & {"irc", "scan", "opt", "ts"}:
        # 无几何移动的任务（含 freq-only）视为单点
        jobs.add("sp")
    return jobs
```


<a id="s177"></a>

### S177 · `_coords_to_xyz`

`cloudra/tools/core/gaussian_frames.py:198–204`

```python
def _coords_to_xyz(atomnos, coords, comment: str = "") -> str:
    """atomnos + 坐标（Angstrom）生成标准 XYZ 块。"""
    from ase.data import chemical_symbols
    lines = [str(len(atomnos)), comment]
    for z, (x, y, zc) in zip(atomnos, coords, strict=True):
        lines.append(f"{chemical_symbols[int(z)]:<2} {x:>15.8f} {y:>15.8f} {zc:>15.8f}")
    return "\n".join(lines)
```


<a id="s178"></a>

### S178 · `scf_energy_hartree`

`cloudra/tools/core/gaussian_frames.py:223–226`

```python
def scf_energy_hartree(text: str) -> float | None:
    """Last explicitly reported SCF energy, without post-HF substitutions."""
    matches = list(_SCF_ENERGY_RE.finditer(text))
    return float(matches[-1].group(1).replace('D', 'E').replace('d', 'e')) if matches else None
```


<a id="s179"></a>

### S179 · `electronic_energy_hartree`

`cloudra/tools/core/gaussian_frames.py:229–235`

```python
def electronic_energy_hartree(text: str) -> float | None:
    """Last native SCF or explicitly reported correlated total energy."""
    matches = [* _SCF_ENERGY_RE.finditer(text), * _CORRELATED_ENERGY_RE.finditer(text)]
    if not matches:
        return None
    match = max(matches, key=lambda item: item.start())
    return float(match.group(1).replace('D', 'E').replace('d', 'e'))
```


<a id="s180"></a>

### S180 · `vibfreqs_from_text`

`cloudra/tools/core/gaussian_frames.py:238–242`

```python
def vibfreqs_from_text(text: str) -> list[float]:
    """Signed frequencies in the last native harmonic-frequency section."""
    section = text.rsplit('Harmonic frequencies', 1)[-1]
    return [float(value.replace('D', 'E').replace('d', 'e'))
            for match in _FREQ_LINE_RE.finditer(section) for value in match.group(1).split()]
```


<a id="s181"></a>

### S181 · `final_xyz_from_text`

`cloudra/tools/core/gaussian_frames.py:245–252`

```python
def final_xyz_from_text(text: str) -> str:
    """Last printed Cartesian orientation, never an inferred geometry."""
    index = max(text.rfind('Standard orientation:'), text.rfind('Input orientation:'))
    if index < 0:
        return ''
    lines = text[index:].splitlines()
    rows = _parse_coord_block_after(lines, 1, has_type_col=True)
    return _coords_to_xyz([row[0] for row in rows], [row[1:] for row in rows]) if rows else ''
```


<a id="s182"></a>

### S182 · `vibdisps_from_text`

`cloudra/tools/core/gaussian_frames.py:255–321`

```python
def vibdisps_from_text(text: str, n_freqs: int):
    """从 Gaussian 频率块解析简正模式位移，返回 shape (n_modes, n_atoms, 3) 或 None。

    按 Frequencies 行分块；每块最多 3 个模式，后接 Atom AN 位移表。块数不足
    n_freqs 或任一块缺位移表时返回 None（调用方保持"缺位移"语义）。
    """
    import numpy as np

    freq_matches = list(_FREQ_LINE_RE.finditer(text))
    if not freq_matches or n_freqs <= 0:
        return None

    mode_chunks: list[list[list[list[float]]]] = []
    for idx, match in enumerate(freq_matches):
        block_freqs = []
        for tok in match.group(1).split():
            try:
                block_freqs.append(float(tok))
            except ValueError:
                break
        if not block_freqs:
            continue
        start = match.end()
        end = freq_matches[idx + 1].start() if idx + 1 < len(freq_matches) else len(text)
        block = text[start:end]
        header = _ATOM_DISP_HEADER_RE.search(block)
        if header is None:
            return None
        rows: list[list[list[float]]] = []
        for line in block[header.end():].splitlines():
            stripped = line.strip()
            if not stripped:
                if rows:
                    break
                continue
            parts = stripped.split()
            if len(parts) < 2 + 3 * len(block_freqs):
                if rows:
                    break
                continue
            try:
                coords = [float(x) for x in parts[2:2 + 3 * len(block_freqs)]]
            except ValueError:
                if rows:
                    break
                continue
            atom_modes = [
                coords[3 * m: 3 * m + 3] for m in range(len(block_freqs))
            ]
            rows.append(atom_modes)
        if not rows:
            return None
        # rows: natoms × nmodes_in_block × 3  → 转成 per-mode
        per_mode = []
        for m in range(len(block_freqs)):
            per_mode.append([rows[a][m] for a in range(len(rows))])
        mode_chunks.append(per_mode)

    flat_modes: list[list[list[float]]] = []
    for chunk in mode_chunks:
        flat_modes.extend(chunk)
    if len(flat_modes) < n_freqs:
        return None
    arr = np.asarray(flat_modes[:n_freqs], dtype=float)
    if arr.ndim != 3 or arr.shape[2] != 3:
        return None
    return arr
```


<a id="s183"></a>

### S183 · `std_orientation_frames`

`cloudra/tools/core/gaussian_frames.py:324–352`

```python
def std_orientation_frames(text: str) -> list[list[tuple[int, float, float, float]]]:
    """解析所有 "Standard orientation:" 坐标块，返回 [(atomno, x, y, z), ...] 列表的列表。"""
    blocks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if "Standard orientation:" in lines[i]:
            j = i + 1
            dash = 0
            rows: list[tuple[int, float, float, float]] = []
            while j < len(lines):
                s = lines[j].strip()
                if s and set(s) == {"-"}:
                    dash += 1
                    j += 1
                    if dash == 3:
                        break
                    continue
                if dash == 2:
                    parts = s.split()
                    if len(parts) >= 6:
                        rows.append((int(parts[1]), float(parts[3]), float(parts[4]), float(parts[5])))
                j += 1
            if rows:
                blocks.append(rows)
            i = j
        else:
            i += 1
    return blocks
```


<a id="s184"></a>

### S184 · `_is_dash_line`

`cloudra/tools/core/gaussian_frames.py:368–370`

```python
def _is_dash_line(line: str) -> bool:
    s = line.strip()
    return len(s) > 3 and set(s) == {"-"}
```


<a id="s185"></a>

### S185 · `_parse_coord_block_after`

`cloudra/tools/core/gaussian_frames.py:373–390`

```python
def _parse_coord_block_after(lines: list[str], start: int, has_type_col: bool):
    """从 lines[start] 之后第一个双虚线表的坐标区解析 (atomno, x, y, z) 列表。"""
    dash_seen = 0
    rows = []
    for i in range(start, len(lines)):
        line = lines[i]
        if _is_dash_line(line):
            dash_seen += 1
            if dash_seen == 3:
                break
            continue
        if dash_seen == 2:
            parts = line.split()
            if has_type_col and len(parts) >= 6:
                rows.append((int(parts[1]), float(parts[3]), float(parts[4]), float(parts[5])))
            elif not has_type_col and len(parts) == 5:
                rows.append((int(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])))
    return rows or None
```


<a id="s186"></a>

### S186 · `_parse_current_structure`

`cloudra/tools/core/gaussian_frames.py:393–399`

```python
def _parse_current_structure(segment: str):
    """解析点段内 "CURRENT STRUCTURE" 的 Cartesian 坐标块（无 Type 列，5 列）。"""
    lines = segment.splitlines()
    for i, line in enumerate(lines):
        if "CURRENT STRUCTURE" in line:
            return _parse_coord_block_after(lines, i + 1, has_type_col=False)
    return None
```


<a id="s187"></a>

### S187 · `_parse_last_input_orientation`

`cloudra/tools/core/gaussian_frames.py:402–411`

```python
def _parse_last_input_orientation(region: str):
    """解析文本区域内最后一个 "Input orientation:" 坐标块（含 Type 列，6 列）。"""
    lines = region.splitlines()
    last_idx = None
    for i, line in enumerate(lines):
        if "Input orientation:" in line:
            last_idx = i
    if last_idx is None:
        return None
    return _parse_coord_block_after(lines, last_idx + 1, has_type_col=True)
```


<a id="s188"></a>

### S188 · `irc_start_xyz`

`cloudra/tools/core/gaussian_frames.py:414–438`

```python
def irc_start_xyz(text: str) -> str:
    """Initial IRC geometry, including Gaussian's Cartesian checkpoint echo."""
    prefix = text.partition('Point Number:')[0]
    lines = prefix.splitlines()
    for index, line in enumerate(lines):
        if 'Input orientation:' in line or 'Standard orientation:' in line:
            rows = _parse_coord_block_after(lines, index + 1, has_type_col=True)
            if rows:
                return _coords_to_xyz([row[0] for row in rows], [row[1:] for row in rows])
    _, marker, coordinates = prefix.partition('cartesian coordinates used.')
    if not marker:
        return ''
    rows = []
    for line in coordinates.splitlines():
        parts = line.split()
        if not parts and not rows:
            continue
        if len(parts) != 4:
            break
        try:
            values = [float(value) for value in parts[1:]]
        except ValueError:
            break
        rows.append(f'{parts[0]} ' + ' '.join(str(value) for value in values))
    return f'{len(rows)}\n\n' + '\n'.join(rows) + '\n' if rows else ''
```


<a id="s189"></a>

### S189 · `_parse_irc_summary_table`

`cloudra/tools/core/gaussian_frames.py:441–469`

```python
def _parse_irc_summary_table(text: str):
    """解析结尾汇总表，返回 (ts_energy_hartree, [(energy_rel, rx_coord), ...])。

    表中能量为相对 TS 能量的差值，行按反应坐标从负到正排列（TS 行为 rx=0）。
    """
    m_ts = _TS_ENERGY_RE.search(text)
    m_tab = _SUMMARY_TABLE_RE.search(text)
    if not m_ts or not m_tab:
        if "Error termination" in text:
            state = "native error termination; inspect the calculation failure before resubmitting"
        elif normal_termination(text):
            state = "normally terminated but IRC evidence is incomplete; inspect the full native output"
        else:
            state = (
                "native normal termination is absent; the calculation may still be running or the output "
                "may be truncated; check the registered job state before retrying"
            )
        raise ValueError(
            "Gaussian IRC: " + state + ". Missing 'Summary of reaction path following' "
            "or its TS energy reference; reaction coordinates and energies cannot be extracted."
        )
    rows = []
    for line in m_tab.group(1).splitlines():
        parts = line.split()
        if len(parts) == 3:
            rows.append((float(parts[1]), float(parts[2])))
    if not rows:
        raise ValueError("IRC 汇总表为空。")
    return float(m_ts.group(1)), rows
```


<a id="s190"></a>

### S190 · `_irc_direction_converged`

`cloudra/tools/core/gaussian_frames.py:472–484`

```python
def _irc_direction_converged(text: str, direction: str) -> bool:
    """判断 IRC 某个方向（FORWARD/REVERSE）是否收敛到极小点。

    Gaussian 在路径自然终止于 PES 极小点时直接打印
    "Calculation of XXX path complete."；若因步数耗尽终止则先打印
    "Maximum number of steps reached."。cclib 的 optstatus 对 IRC 点一律记为
    DONE，无法区分这两种情形，故以文本标记为准。
    """
    idx = text.find(f"Calculation of {direction} path complete.")
    if idx < 0:
        return False
    window = text[max(0, idx - 500):idx]
    return "Maximum number of steps reached" not in window
```


<a id="s191"></a>

### S191 · `_parse_irc`

`cloudra/tools/core/gaussian_frames.py:487–617`

```python
def _parse_irc(text: str):
    """解析 IRC 日志，返回 (frames, meta)。

    - 反应坐标与能量：结尾 "Summary of reaction path following" 汇总表
      （能量 = TS 能量 + 相对能量）；
    - 坐标：每个 "Point Number: N / Path Number: M" 标记后的 CURRENT STRUCTURE
      坐标块（即 corrector 收敛后的该点结构；点段内的 Input orientation 是
      下一点的 predictor 猜测结构，不采用）。Point 0（TS）无 CURRENT STRUCTURE
      块时，回退到该标记之前最后一个 Input orientation 块，仍无则 xyz 留空；
    - 汇总表按 rx 从负到正排列，通过各点 "NET REACTION COORDINATE"（到 TS 的
      距离，恒正）与 |rx| 匹配，确定正/负侧对应哪个 Path Number；
    - 输出帧按反应坐标升序排列（反向端点 → TS → 正向端点）。
    """
    ts_energy, rows = _parse_irc_summary_table(text)

    headers = list(_POINT_HEADER_RE.finditer(text))
    if not headers:
        raise ValueError("IRC 日志中未找到 'Point Number: N / Path Number: M' 标记。")

    # 每个点段：从当前标记到下一标记
    points: dict[int, list[dict]] = {1: [], 2: []}
    for i, m in enumerate(headers):
        point_no, path_no = int(m.group(1)), int(m.group(2))
        seg_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        segment = text[m.end():seg_end]
        coords = _parse_current_structure(segment)
        if point_no == 0 and coords is None:
            # TS 起始点：尝试取标记之前（初始结构 SCF）的最后一个 Input orientation
            coords = _parse_last_input_orientation(text[:m.start()])
        m_net = _NET_RX_RE.search(segment)
        points.setdefault(path_no, []).append({
            "point": point_no,
            "path": path_no,
            "net_rx": float(m_net.group(1)) if m_net else (0.0 if point_no == 0 else None),
            "coords": coords,
        })

    # 拆分汇总表：rx=0 为 TS 行，负/正两侧按到 TS 距离升序
    neg_rows = sorted((r for r in rows if r[1] < 0), key=lambda r: -r[1])
    pos_rows = sorted((r for r in rows if r[1] > 0), key=lambda r: r[1])
    ts_rows = [r for r in rows if r[1] == 0]

    def _mismatch(pts, side_rows):
        n = min(len(pts), len(side_rows))
        return sum(
            abs((pts[i]["net_rx"] or 0.0) - abs(side_rows[i][1]))
            for i in range(n)
        )

    # Path 1 的点列与负/正侧各匹配一次，取总误差小的归属
    pts1 = sorted(points.get(1, []), key=lambda p: p["point"])
    pts2 = sorted(points.get(2, []), key=lambda p: p["point"])
    pts1 = [p for p in pts1 if p["point"] > 0]
    pts2 = [p for p in pts2 if p["point"] > 0]
    score_a = _mismatch(pts1, pos_rows) + _mismatch(pts2, neg_rows)
    score_b = _mismatch(pts1, neg_rows) + _mismatch(pts2, pos_rows)
    path_rows = {1: pos_rows, 2: neg_rows} if score_a <= score_b else {1: neg_rows, 2: pos_rows}

    conv = {
        1: _irc_direction_converged(text, "FORWARD"),
        2: _irc_direction_converged(text, "REVERSE"),
    }

    def _make_frame(frame_idx, path_no, pt, row):
        energy_rel, rx = row
        energy = ts_energy + energy_rel
        coords = pt["coords"] if pt else None
        atomnos = [c[0] for c in coords] if coords else None
        xyz = ""
        if coords:
            xyz = _coords_to_xyz(
                atomnos,
                [c[1:] for c in coords],
                comment=f"irc point={pt['point']} path={path_no} rx={rx:.5f} E={energy:.8f} Eh",
            )
        return FrameRecord(
            frame=frame_idx,
            path_number=path_no,
            reaction_coordinate=rx,
            electronic_energy_hartree=energy,
            xyz=xyz,
            converged=None,
        )

    frames: list[FrameRecord] = []
    idx = 0
    # 反向侧（rx 更负）：点号从大到小
    for path_no in (1, 2):
        side = path_rows[path_no]
        if side and side[0][1] < 0:
            pts = pts1 if path_no == 1 else pts2
            for i in range(len(side) - 1, -1, -1):
                pt = pts[i] if i < len(pts) else None
                fr = _make_frame(idx, path_no, pt or {"point": i + 1, "coords": None}, side[i])
                if i == len(side) - 1:
                    fr.converged = conv[path_no]  # 该方向端点
                frames.append(fr)
                idx += 1
    # TS
    ts_pt = next((p for p in points.get(1, []) if p["point"] == 0), None)
    ts_row = ts_rows[0] if ts_rows else (0.0, 0.0)
    frames.append(_make_frame(idx, ts_pt["path"] if ts_pt else 1,
                              ts_pt or {"point": 0, "coords": None}, ts_row))
    idx += 1
    # 正向侧（rx 更正）：点号从小到大
    for path_no in (1, 2):
        side = path_rows[path_no]
        if side and side[0][1] > 0:
            pts = pts1 if path_no == 1 else pts2
            for i in range(len(side)):
                pt = pts[i] if i < len(pts) else None
                fr = _make_frame(idx, path_no, pt or {"point": i + 1, "coords": None}, side[i])
                if i == len(side) - 1:
                    fr.converged = conv[path_no]
                frames.append(fr)
                idx += 1

    rx_values = [f.reaction_coordinate for f in frames if f.reaction_coordinate is not None]
    meta = {
        "ts_energy_hartree": ts_energy,
        "num_points_forward": len(pts1),
        "num_points_backward": len(pts2),
        "rx_coord_range": (min(rx_values), max(rx_values)) if rx_values else None,
        "endpoint_energies_hartree": (
            frames[0].electronic_energy_hartree,
            frames[-1].electronic_energy_hartree,
        ) if frames else None,
        "forward_converged": conv[1],
        "backward_converged": conv[2],
    }
    return frames, meta
```


<a id="s192"></a>

### S192 · `extract_irc`

`cloudra/tools/core/gaussian_frames.py:620–622`

```python
def extract_irc(log_path: str):
    """解析 IRC 日志，返回 (list[FrameRecord], meta dict)。供 log_parser 汇总用。"""
    return extract_irc_from_text(_read_text(log_path))
```


<a id="s193"></a>

### S193 · `extract_irc_from_text`

`cloudra/tools/core/gaussian_frames.py:625–627`

```python
def extract_irc_from_text(text: str):
    """extract_irc 的文本变体：调用方已读过日志时避免重复 IO。"""
    return _parse_irc(text)
```


<a id="s194"></a>

### S194 · `_ccread`

`cloudra/tools/core/gaussian_frames.py:634–635`

```python
def _ccread(log_path: str):
    return _ccread_from_text(_read_text(log_path), source_desc=log_path)
```


<a id="s195"></a>

### S195 · `_ccread_from_text`

`cloudra/tools/core/gaussian_frames.py:638–658`

```python
def _ccread_from_text(text: str, source_desc: str = "<in-memory log text>"):
    """_ccread 的文本变体：调用方已读过日志时避免重复 IO（cclib 吃 StringIO）。"""
    import io

    import cclib

    try:
        data = cclib.io.ccread(io.StringIO(text))
    except IndexError as exc:
        # cclib 内部对截断/畸形日志会裸抛 "list index out of range"——翻译成
        # 有语义的解析失败，调用方（format_converter 等）才能给出可读指引
        raise ValueError(
            f"日志解析器内部索引越界（疑似截断或损坏的计算日志）: {source_desc}"
        ) from exc
    except AssertionError as exc:
        # ORCA GFN2-xTB 的简版偶极矩块会触发 cclib 断言；归为解析失败，
        # 让 ORCA 帧提取继续使用已有的原生日志解析，而非中断 TS 恢复。
        raise ValueError(f"cclib 日志解析器内部断言失败: {source_desc}") from exc
    if data is None:
        raise ValueError(f"cclib 未能解析日志: {source_desc}")
    return data
```


<a id="s196"></a>

### S196 · `_as_float_list`

`cloudra/tools/core/gaussian_frames.py:661–664`

```python
def _as_float_list(values) -> list[float]:
    import numpy as np

    return [float(v) for v in np.asarray(list(values), dtype=float)]
```


<a id="s197"></a>

### S197 · `_get_vibfreqs`

`cloudra/tools/core/gaussian_frames.py:695–699`

```python
def _get_vibfreqs(data) -> list[float]:
    vibfreqs = getattr(data, "vibfreqs", None)
    if vibfreqs is None or len(vibfreqs) == 0:
        return []
    return _as_float_list(vibfreqs)
```


<a id="s198"></a>

### S198 · `_extract_opt_frames`

`cloudra/tools/core/gaussian_frames.py:702–727`

```python
def _extract_opt_frames(log_text: str) -> list[FrameRecord]:
    try:
        data = _ccread_from_text(log_text)
    except Exception:
        return _native_frames(log_text)
    energies = getattr(data, "scfenergies", None)
    atomcoords = getattr(data, "atomcoords", None)
    atomnos = getattr(data, "atomnos", None)
    if energies is None or atomcoords is None or atomnos is None:
        return _native_frames(log_text)
    energies_ev = _as_float_list(energies)
    n = min(len(energies_ev), len(atomcoords))
    converged = opt_converged(log_text)
    freqs = vibfreqs_from_text(log_text) or _get_vibfreqs(data)

    frames = []
    for i in range(n):
        is_last = i == n - 1
        frames.append(FrameRecord(
            frame=i,
            electronic_energy_hartree=energy_ev_to_hartree(energies_ev[i]),
            frequencies_cm=freqs if (is_last and freqs) else [],
            xyz=_coords_to_xyz(atomnos, atomcoords[i], comment=f"opt step={i}"),
            converged=converged if is_last else None,
        ))
    return frames
```


<a id="s199"></a>

### S199 · `_extract_sp_frames`

`cloudra/tools/core/gaussian_frames.py:730–748`

```python
def _extract_sp_frames(log_text: str) -> list[FrameRecord]:
    try:
        data = _ccread_from_text(log_text)
    except Exception:
        return _native_sp_frames(log_text)
    energies = getattr(data, "scfenergies", None)
    atomcoords = getattr(data, "atomcoords", None)
    atomnos = getattr(data, "atomnos", None)
    if atomcoords is None or atomnos is None or len(atomcoords) == 0:
        return _native_sp_frames(log_text)
    energy_hartree = electronic_energy_hartree(log_text)
    if energy_hartree is None and energies is not None and len(energies) > 0:
        energy_hartree = energy_ev_to_hartree(_as_float_list(energies)[-1])
    return [FrameRecord(
        frame=0,
        electronic_energy_hartree=energy_hartree,
        frequencies_cm=vibfreqs_from_text(log_text) or _get_vibfreqs(data),
        xyz=final_xyz_from_text(log_text) or _coords_to_xyz(atomnos, atomcoords[-1], comment="single point"),
    )]
```


<a id="s200"></a>

### S200 · `_native_sp_frames`

`cloudra/tools/core/gaussian_frames.py:751–754`

```python
def _native_sp_frames(text: str) -> list[FrameRecord]:
    xyz = final_xyz_from_text(text)
    return [FrameRecord(frame=0, electronic_energy_hartree=electronic_energy_hartree(text),
        frequencies_cm=vibfreqs_from_text(text), xyz=xyz)] if xyz else []
```


<a id="s201"></a>

### S201 · `_native_frames`

`cloudra/tools/core/gaussian_frames.py:757–775`

```python
def _native_frames(text: str) -> list[FrameRecord]:
    """Pair explicit SCF steps with their preceding printed orientations."""
    frames = []
    for match in _SCF_ENERGY_RE.finditer(text):
        xyz = final_xyz_from_text(text[:match.start()])
        if xyz:
            frames.append(FrameRecord(frame=len(frames),
                electronic_energy_hartree=float(match.group(1).replace('D', 'E').replace('d', 'e')),
                xyz=xyz))
    final_xyz = final_xyz_from_text(text)
    if not frames and final_xyz:
        frames.append(FrameRecord(frame=0, electronic_energy_hartree=scf_energy_hartree(text), xyz=final_xyz))
    elif frames and final_xyz and final_xyz != frames[-1].xyz:
        frames.append(FrameRecord(frame=len(frames), xyz=final_xyz))
    if frames:
        # Frequency output can reprint the final orientation after the SCF step.
        frames[-1].frequencies_cm = vibfreqs_from_text(text)
        frames[-1].converged = opt_converged(text)
    return frames
```


<a id="s202"></a>

### S202 · `extract_frames`

`cloudra/tools/core/gaussian_frames.py:782–784`

```python
def extract_frames(log_path: str) -> list[FrameRecord]:
    """按识别到的任务类型提取关键帧。无法识别的日志返回空列表。"""
    return extract_frames_from_text(_read_text(log_path))
```


<a id="s203"></a>

### S203 · `extract_frames_from_text`

`cloudra/tools/core/gaussian_frames.py:787–798`

```python
def extract_frames_from_text(text: str) -> list[FrameRecord]:
    """extract_frames 的文本变体：调用方已读过日志时避免重复 IO。"""
    jobs = detect_job_types_from_text(text)
    if "irc" in jobs:
        frames, _meta = _parse_irc(text)
        return frames
    if "scan" in jobs:
        return _extract_scan_frames(text)
    if "opt" in jobs or "ts" in jobs:
        return _extract_opt_frames(text)
    # freq / sp：单帧
    return _extract_sp_frames(text)
```


<a id="s204"></a>

### S204 · `_fmt_float`

`cloudra/tools/core/gaussian_frames.py:801–802`

```python
def _fmt_float(value: float, digits: int = 12) -> str:
    return f"{value:.{digits}g}"
```


<a id="s205"></a>

### S205 · `frames_to_csv`

`cloudra/tools/core/gaussian_frames.py:805–828`

```python
def frames_to_csv(frames: list[FrameRecord], output_path: str) -> str:
    """将关键帧写为 CSV（xyz 为多行字段，靠 csv 引号机制，pandas/DictReader 可读）。"""
    columns = [
        "frame", "path_number", "reaction_coordinate",
        "electronic_energy_hartree", "electronic_energy_ev", "frequencies_cm", "xyz",
    ]
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for fr in frames:
            hartree = fr.electronic_energy_hartree
            writer.writerow({
                "frame": fr.frame,
                "path_number": "" if fr.path_number is None else fr.path_number,
                "reaction_coordinate": "" if fr.reaction_coordinate is None else _fmt_float(fr.reaction_coordinate),
                "electronic_energy_hartree": "" if hartree is None else _fmt_float(hartree),
                "electronic_energy_ev": "" if hartree is None else _fmt_float(hartree * EV_PER_HARTREE),
                "frequencies_cm": ";".join(_fmt_float(v) for v in fr.frequencies_cm),
                "xyz": fr.xyz,
            })
    return output_path
```


## `cloudra/tools/core/geometry_inputs.py`

文件 SHA-256：`098c760f6ea13fd38012821bb63e8283c108d65caae30238574603849e7d3f98`


<a id="s206"></a>

### S206 · `atom_index_base`

`cloudra/tools/core/geometry_inputs.py:47–52`

```python
def atom_index_base(engine: str | None = None) -> int:
    if engine == "orca":
        return 0
    if engine in (None, "gaussian", "xtb"):
        return 1
    raise ValueError(f"Unknown atom numbering context: {engine!r}")
```


## `cloudra/tools/core/irc_evidence.py`

文件 SHA-256：`9162a867d608a5954cdceb48657cc60cfa2594a6ef3fc3298f01ffa1c4d56b9d`


<a id="s207"></a>

### S207 · `irc_start_geometry`

`cloudra/tools/core/irc_evidence.py:27–47`

```python
def irc_start_geometry(path):
    """Native IRC starting saddle, never a predictor or a terminal path frame."""
    engine = qm_engine.detect_qm_engine(str(path))
    try:
        if engine == 'gaussian':
            frames, _ = gaussian_frames.extract_irc(str(path))
            return next((parse_xyz(frame.xyz) for frame in frames
                         if frame.reaction_coordinate == 0.0 and frame.xyz.strip()),
                        parse_xyz(gaussian_frames.irc_start_xyz(Path(path).read_text(errors='replace'))))
        if engine == 'orca':
            text = Path(path).read_text(errors='replace')
            orca_frames.extract_irc_from_text(text)
            start = text.find('Intrinsic Reaction Coordinate Calculation')
            if start < 0:
                return None
            index = text.rfind('CARTESIAN COORDINATES (ANGSTROEM)', 0, start)
            xyz = orca_frames._xyz_block_at(text, index) if index >= 0 else orca_frames.input_xyz_from_text(text[:start])
            return parse_xyz(xyz)
    except (ValueError, OSError):
        return None
    return None
```


<a id="s208"></a>

### S208 · `frames_for`

`cloudra/tools/core/irc_evidence.py:50–68`

```python
def frames_for(path):
    """Parse frames and IRC metadata independently from one native text read."""
    try:
        text = Path(path).read_text(errors='replace')
    except OSError:
        return [], None
    engine = qm_engine.detect_qm_engine_from_text(text)
    mod = orca_frames if engine == 'orca' else gaussian_frames
    try:
        frames = (mod.extract_frames_from_text(text, log_path=str(path))
                  if engine == 'orca' else mod.extract_frames_from_text(text))
    except Exception:
        frames = []
    try:
        raw_irc = mod.extract_irc_from_text(text)
    except Exception:
        raw_irc = None
    irc_meta = raw_irc[1] if isinstance(raw_irc, tuple) and len(raw_irc) == 2 else raw_irc
    return frames, irc_meta
```


<a id="s209"></a>

### S209 · `freqs_for`

`cloudra/tools/core/irc_evidence.py:71–76`

```python
def freqs_for(path, frames) -> list[float]:
    """Signed native frequencies; no frequency calculation is never zero modes."""
    from cloudra.tools.core.qm_log_facts import read_qm_log

    del frames
    return read_qm_log(path).frequencies_cm or []
```


<a id="s210"></a>

### S210 · `imag_freqs`

`cloudra/tools/core/irc_evidence.py:79–80`

```python
def imag_freqs(freqs: list[float]) -> list[float]:
    return [f for f in freqs if f < 0]
```


<a id="s211"></a>

### S211 · `last_geometry`

`cloudra/tools/core/irc_evidence.py:83–88`

```python
def last_geometry(path, frames) -> Optional[tuple]:
    """The final native geometry shared with tools and file evidence."""
    from cloudra.tools.core.qm_log_facts import read_qm_log

    del frames
    return read_qm_log(path).geometry
```


<a id="s212"></a>

### S212 · `irc_frames_for`

`cloudra/tools/core/irc_evidence.py:91–100`

```python
def irc_frames_for(path):
    """IRC 逐点帧。Gaussian 主日志内含逐点坐标；ORCA 的逐点坐标在边文件里，
    主日志没有（端点几何走 orca_irc_endpoint_geometries 的边文件通道）。"""
    try:
        raw = gaussian_frames.extract_irc(str(path))
    except Exception:
        return []
    if isinstance(raw, tuple) and raw:
        return list(raw[0]) if raw[0] else []
    return []
```


<a id="s213"></a>

### S213 · `gaussian_irc_endpoints_from_frames`

`cloudra/tools/core/irc_evidence.py:103–123`

```python
def gaussian_irc_endpoints_from_frames(frames) -> Optional[tuple]:
    """ts_guess strict 同口径的 Gaussian IRC 端点：rx<0 / rx>0 两侧各自最外侧
    的带坐标帧（不要求收敛到极小值）。两侧都有可用几何才返回。"""
    valid = [fr for fr in frames if getattr(fr, "xyz", "").strip()]
    neg = [
        fr for fr in valid
        if fr.reaction_coordinate is not None and fr.reaction_coordinate < 0
    ]
    pos = [
        fr for fr in valid
        if fr.reaction_coordinate is not None and fr.reaction_coordinate > 0
    ]
    if not neg or not pos:
        return None
    end_a = min(neg, key=lambda fr: fr.reaction_coordinate)
    end_b = max(pos, key=lambda fr: fr.reaction_coordinate)
    geo_a = parse_xyz(end_a.xyz)
    geo_b = parse_xyz(end_b.xyz)
    if geo_a is None or geo_b is None:
        return None
    return geo_a, geo_b
```


<a id="s214"></a>

### S214 · `orca_irc_endpoint_geometries`

`cloudra/tools/core/irc_evidence.py:126–149`

```python
def orca_irc_endpoint_geometries(path) -> Optional[tuple]:
    """ts_guess strict 同口径的 ORCA IRC 端点：几何来自终点文件/F-B 轨迹边
    文件（未收敛方向取轨迹末帧，同样是合法的部分端点）；IRC 收敛与否不做闸门，
    方向依据两侧外帧的真实优化链。两侧都有可用几何才返回。

    前提是文件本身确实是 IRC 计算日志：输入文件（.inp）旁边恰好有同名
    轨迹边文件时，没有 IRC 段就没有任何"端点"可言。"""
    try:
        orca_frames.extract_irc(str(path))
    except Exception:
        return None  # 无 IRC 段（输入文件、非 IRC 作业）→ 不是 IRC 证据
    try:
        endpoints = orca_frames.extract_irc_endpoints(str(path))
    except Exception:
        return None
    xyz_a = orca_frames.read_endpoint_geometry(endpoints.get("forward", {}))
    xyz_b = orca_frames.read_endpoint_geometry(endpoints.get("backward", {}))
    if xyz_a is None or xyz_b is None:
        return None
    geo_a = parse_xyz(xyz_a)
    geo_b = parse_xyz(xyz_b)
    if geo_a is None or geo_b is None:
        return None
    return geo_a, geo_b
```


<a id="s215"></a>

### S215 · `normal_log`

`cloudra/tools/core/irc_evidence.py:152–162`

```python
def normal_log(path) -> bool:
    """Native normally terminated QM evidence with matching frequency geometry."""
    path = Path(path)
    if not path.is_file():
        return False
    engine = qm_engine.detect_qm_engine(str(path))
    parser = {'orca': orca_frames, 'gaussian': gaussian_frames}.get(engine)
    text = path.read_text(errors='replace')
    if parser is None or not parser.normal_termination(text):
        return False
    return frequency_geometry_matches(path)
```


<a id="s216"></a>

### S216 · `frequency_geometry_matches`

`cloudra/tools/core/irc_evidence.py:165–179`

```python
def frequency_geometry_matches(path) -> bool:
    """The last spectrum must belong to the final geometry in the native log."""
    engine = qm_engine.detect_qm_engine(str(path))
    text = Path(path).read_text(errors='replace')
    frequency_marker = 'VIBRATIONAL FREQUENCIES' if engine == 'orca' else 'Frequencies --'
    frequency_index = text.rfind(frequency_marker)
    if frequency_index < 0:
        return True  # No frequency claim; probe_log still returns n_imag=None.

    def geometry(region):
        if engine == 'orca':
            return parse_xyz(orca_frames.final_xyz_from_text(region))
        return parse_xyz(gaussian_frames.final_xyz_from_text(region))

    return same_geometry(geometry(text), geometry(text[:frequency_index]))
```


<a id="s217"></a>

### S217 · `probe_log`

`cloudra/tools/core/irc_evidence.py:182–191`

```python
def probe_log(path) -> tuple[Optional[int], Optional[tuple]]:
    """Return native imaginary count and final geometry; missing modes stay None."""
    from cloudra.tools.core.qm_log_facts import read_qm_log

    p = Path(path)
    if not normal_log(p):
        return None, None
    facts = read_qm_log(p)
    n_imag = len(imag_freqs(facts.frequencies_cm)) if facts.frequencies_cm is not None else None
    return n_imag, facts.geometry
```


<a id="s218"></a>

### S218 · `irc_endpoint_geometries`

`cloudra/tools/core/irc_evidence.py:194–204`

```python
def irc_endpoint_geometries(path) -> Optional[tuple]:
    """双侧 IRC 端点几何 ((symbols, positions) × 2)，ts_guess strict 口径。

    引擎非 gaussian/orca 或任一侧几何不可得时返回 None。"""
    p = Path(path)
    engine = qm_engine.detect_qm_engine(str(p))
    if engine == "gaussian":
        return gaussian_irc_endpoints_from_frames(irc_frames_for(p))
    if engine == "orca":
        return orca_irc_endpoint_geometries(p)
    return None
```


<a id="s219"></a>

### S219 · `_ordered_graph_matches`

`cloudra/tools/core/irc_evidence.py:207–234`

```python
def _ordered_graph_matches(geometry, mol_block: str, charge: int) -> bool:
    """Associate an independent minimum by its full graph, including H parents."""
    from rdkit import Chem
    from rdkit.Chem import rdDetermineBonds

    from cloudra.tools.core.irc_path import xyz_block

    expected = Chem.MolFromMolBlock(mol_block, removeHs=False)
    if expected is None or any(atom.GetIsotope() for atom in expected.GetAtoms()):
        return False  # XYZ/log element rows cannot prove isotope lineage.
    actual = Chem.MolFromXYZBlock(xyz_block(*geometry))
    if actual is None or actual.GetNumAtoms() != expected.GetNumAtoms():
        return False
    try:
        rdDetermineBonds.DetermineBonds(actual, charge=charge)
    except ValueError:
        return False
    if actual.GetNumBonds() != expected.GetNumBonds():
        return False
    property_name = '_cloudra_evidence_atom_order'
    for molecule in (expected, actual):
        for atom in molecule.GetAtoms():
            atom.SetAtomMapNum(0)
            atom.SetIntProp(property_name, atom.GetIdx())
    parameters = Chem.SubstructMatchParameters()
    parameters.useChirality = True
    parameters.atomProperties = [property_name]
    return actual.HasSubstructMatch(expected, parameters)
```


<a id="s220"></a>

### S220 · `bound_atom_orders`

`cloudra/tools/core/irc_evidence.py:237–257`

```python
def bound_atom_orders(ts, source, target, binding):
    """Return TS→mobile permutations only for the bound complete endpoint graphs."""
    if not binding:
        return None
    from rdkit import Chem

    mapping = binding.get('atom_map', [])
    count = len(ts[0])
    if (len(mapping) != count or any(type(index) is not int for index in mapping)
            or sorted(mapping) != list(range(1, count + 1))):
        return None
    reactant = Chem.MolFromMolBlock(binding['reactant_mol'], removeHs=False)
    if reactant is None or [atom.GetSymbol() for atom in reactant.GetAtoms()] != list(ts[0]):
        return None
    charge = binding['charge']
    if (not _ordered_graph_matches(source, binding['reactant_mol'], charge)
            or not _ordered_graph_matches(target, binding['product_mol'], charge)):
        return None
    identity = list(range(count))
    inverse = [mapping.index(index + 1) for index in range(count)]
    return [identity, identity, identity, inverse]
```


<a id="s221"></a>

### S221 · `iter_direction_verdicts`

`cloudra/tools/core/irc_evidence.py:260–283`

```python
def iter_direction_verdicts(
    irc_ends: tuple,
    ts_geometries: Sequence[tuple],
    from_geometries: Sequence[tuple],
    to_geometries: Sequence[tuple],
    *,
    charge: int = 0, atom_binding=None,
):
    """按确定性顺序（TS → from → to）对全部材料组合逐一做方向区间证明，
    逐个产出 verdict（生成器，调用方 any()/遍历即短回路）。

    原子序无关：每组几何经 align_atom_order 重排进 TS 坐标序（距离指纹 +
    Hungarian，元素多重集不符的组合判 undecidable）——agent 用不同原子序
    重优化的端点极小值不再被误拒。"""
    (syms_a, pos_a), (syms_b, pos_b) = irc_ends
    for ts_syms, ts_pos in ts_geometries:
        for from_geo in from_geometries:
            for to_geo in to_geometries:
                yield prove_irc_endpoint_direction(
                    ts_syms, ts_pos,
                    (syms_a, pos_a), (syms_b, pos_b),
                    from_geo, to_geo, [], charge,
                    atom_orders=bound_atom_orders((ts_syms, ts_pos), from_geo, to_geo, atom_binding),
                )
```


<a id="s222"></a>

### S222 · `_geometry_matches_species`

`cloudra/tools/core/irc_evidence.py:286–306`

```python
def _geometry_matches_species(geometry, smiles: str, *, charge: int) -> bool:
    """Match the full bond graph and stereochemistry of a real geometry."""
    from rdkit import Chem
    from rdkit.Chem import rdDetermineBonds

    from cloudra.tools.core.irc_path import xyz_block

    expected = Chem.MolFromSmiles(smiles)
    actual = Chem.MolFromXYZBlock(xyz_block(*geometry))
    if expected is None or actual is None or any(atom.GetIsotope() for atom in expected.GetAtoms()):
        return False
    if Chem.AddHs(expected).GetNumAtoms() != actual.GetNumAtoms():
        return False
    try:
        rdDetermineBonds.DetermineBonds(actual, charge=charge)
    except ValueError:
        return False
    for molecule in (expected, actual):
        for atom in molecule.GetAtoms():
            atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(Chem.RemoveHs(actual)) == Chem.MolToSmiles(Chem.RemoveHs(expected))
```


<a id="s223"></a>

### S223 · `verify_separated_product_direction`

`cloudra/tools/core/irc_evidence.py:309–381`

```python
def verify_separated_product_direction(
    irc_ends, ts_geometry, source_geometries, product_smiles, component_geometries,
    *, charge: int = 0, atom_binding=None,
) -> dict:
    """Prove the separated product channel without inventing a complex minimum.

    Callers supply only frequency-verified component and source minima. Product
    identity comes from an actual IRC outer geometry; the opposite direction
    retains the existing source-minimum interval predicate.
    """
    from rdkit import Chem

    from cloudra.tools.core.irc_path import align_atom_order, evaluate_endpoint_between
    from cloudra.tools.core.species_identity import chemical_smiles, species_smiles

    failure = dict(is_decidable=False, is_match=False, details=[])
    products = product_smiles.split('.') if isinstance(product_smiles, str) else species_smiles(product_smiles)
    if len(products) < 2:
        return {**failure, 'details': ['The declaration is one species, not separated products.']}
    declared = [Chem.MolFromSmiles(smiles) for smiles in products]
    if any(molecule is None for molecule in declared):
        return {**failure, 'details': ['A declared product SMILES is invalid.']}
    for smiles, molecule in zip(products, declared, strict=True):
        component_charge = sum(atom.GetFormalCharge() for atom in molecule.GetAtoms())
        if not any(_geometry_matches_species(geometry, smiles, charge=component_charge)
                   for geometry in component_geometries):
            return {**failure, 'details': [f'No frequency-verified independent minimum matches product {smiles}.']}

    symbols, positions = ts_geometry
    all_products = chemical_smiles(products)
    details = []
    for name, target, source in (('direct', irc_ends[1], irc_ends[0]),
                                 ('swapped', irc_ends[0], irc_ends[1])):
        if any(sorted(geometry[0]) != sorted(symbols) for geometry in (target, source)):
            details.append('IRC endpoint atom counts or elements differ from the TS.')
            continue
        if not _geometry_matches_species(target, all_products, charge=charge):
            details.append(f'{name}: the actual IRC product endpoint does not match all declared products.')
            continue
        if atom_binding:
            mapping = atom_binding.get('atom_map', [])
            if (len(mapping) != len(symbols) or any(type(index) is not int for index in mapping)
                    or sorted(mapping) != list(range(1, len(symbols) + 1))
                    or list(target[0]) != list(symbols)):
                details.append('The bound product correspondence does not cover the native IRC atom order.')
                continue
            product_order = ([target[0][index - 1] for index in mapping],
                             [target[1][index - 1] for index in mapping])
            if not _ordered_graph_matches(product_order, atom_binding['product_mol'], charge):
                details.append('The actual IRC product endpoint differs from the bound product atom identities.')
                continue
        for minimum in source_geometries:
            identity = list(range(len(symbols))) if atom_binding else None
            if atom_binding and not _ordered_graph_matches(minimum, atom_binding['reactant_mol'], charge):
                continue
            aligned_source = align_atom_order(symbols, positions, *source, atom_order=identity)
            aligned_minimum = align_atom_order(symbols, positions, *minimum, atom_order=identity)
            if aligned_source is None or aligned_minimum is None:
                details.append('The reactant IRC endpoint or minimum cannot be aligned to the TS.')
                continue
            result = evaluate_endpoint_between(symbols, positions,
                [source[1][index] for index in aligned_source[0]],
                [minimum[1][index] for index in aligned_minimum[0]], [], charge)
            if result['is_decidable'] and result['is_between']:
                return dict(is_decidable=True, is_match=True, assignment=name,
                    proof_scope='separated_products', details=[
                        'The actual IRC endpoint matches every declared separated product, each supported '
                        'by an independent zero-imaginary minimum; the reactant direction passes the '
                        'existing interval proof. This does not verify a bound product complex minimum.',
                        *result['details']])
            failure['is_decidable'] = failure['is_decidable'] or result['is_decidable']
            details.extend(result['details'])
    return {**failure, 'details': details or ['No verified reactant minimum supports the IRC direction.']}
```


<a id="s224"></a>

### S224 · `_usable_ts_geometries`

`cloudra/tools/core/irc_evidence.py:384–396`

```python
def _usable_ts_geometries(ts_logs, *, details: list[str]) -> list[tuple]:
    geometries = []
    for path in ts_logs:
        n_imag, geometry = probe_log(path)
        if n_imag == 1 and geometry is not None:
            geometries.append(geometry)
        else:
            details.append(
                f"TS candidate {path} is not usable: a first-order saddle log "
                f"(exactly one imaginary frequency) with a final geometry is "
                f"required; got n_imag={n_imag}, geometry={'yes' if geometry else 'no'}."
            )
    return geometries
```


<a id="s225"></a>

### S225 · `_usable_minimum_geometries`

`cloudra/tools/core/irc_evidence.py:399–411`

```python
def _usable_minimum_geometries(logs, *, side: str, details: list[str]) -> list[tuple]:
    geometries = []
    for path in logs:
        n_imag, geometry = probe_log(path)
        if n_imag == 0 and geometry is not None:
            geometries.append(geometry)
        else:
            details.append(
                f"{side} candidate {path} is not usable: a verified minimum log "
                f"(zero imaginary frequencies) with a final geometry is required; "
                f"got n_imag={n_imag}, geometry={'yes' if geometry else 'no'}."
            )
    return geometries
```


<a id="s226"></a>

### S226 · `_optimization_geometries`

`cloudra/tools/core/irc_evidence.py:414–446`

```python
def _optimization_geometries(path):
    """Native converged Opt input/final geometries, independent of frequency parsing."""
    if not normal_log(path):
        return None
    text = Path(path).read_text(errors='replace')
    engine = qm_engine.detect_qm_engine(str(path))
    if engine == 'orca':
        if orca_frames.opt_converged(text) is not True:
            return None
        index = text.find('CARTESIAN COORDINATES (ANGSTROEM)')
        first = parse_xyz(orca_frames.input_xyz_from_text(text))
        if first is None and index >= 0:
            first = parse_xyz(orca_frames._xyz_block_at(text, index))
        last = parse_xyz(orca_frames.final_xyz_from_text(text))
    elif engine == 'gaussian':
        if ('Optimization stopped.' in text or not any(marker in text for marker in
                ('Optimization completed.', 'Stationary point found.'))):
            return None
        lines = text.splitlines()
        first_rows = next((gaussian_frames._parse_coord_block_after(lines, index + 1, has_type_col=True)
            for index, line in enumerate(lines)
            if 'Input orientation:' in line or 'Standard orientation:' in line), None)
        blocks = gaussian_frames.std_orientation_frames(text)
        last_rows = blocks[-1] if blocks else gaussian_frames._parse_last_input_orientation(text)

        def geometry(rows):
            return parse_xyz(gaussian_frames._coords_to_xyz(
                [row[0] for row in rows], [row[1:] for row in rows])) if rows else None

        first, last = geometry(first_rows), geometry(last_rows)
    else:
        return None
    return (first, last) if first is not None and last is not None else None
```


<a id="s227"></a>

### S227 · `_optimized_minima`

`cloudra/tools/core/irc_evidence.py:449–465`

```python
def _optimized_minima(logs, *, smiles, side, charge, details):
    minima = _usable_minimum_geometries(logs, side=side, details=details)
    if smiles is not None:
        from cloudra.tools.core.species_identity import chemical_smiles
        expected = chemical_smiles(smiles)
        minima = [geometry for geometry in minima if _geometry_matches_species(geometry, expected, charge=charge)]
        if not minima:
            details.append(f'{side}: no zero-imaginary minimum matches the declared species.')
    results = []
    for path in logs:
        geometries = _optimization_geometries(path)
        if geometries is not None and any(same_geometry(geometries[1], minimum) for minimum in minima):
            results.append((geometries[0], geometries[1], path))
    if not results:
        details.append(f'{side}: supply a normally converged Opt log starting from the actual IRC outer frame '
                       'and a zero-imaginary Freq log at that optimization final geometry; combined Opt/Freq is accepted.')
    return results
```


<a id="s228"></a>

### S228 · `_endpoint_optimization_proof`

`cloudra/tools/core/irc_evidence.py:468–519`

```python
def _endpoint_optimization_proof(ends, ts_geometry, source_logs, target_logs, *,
        charge=0, atom_binding=None, reactant_smiles=None, product_smiles=None):
    """Both real IRC sides must terminate in the declared verified minima via Opt."""
    from cloudra.tools.core.irc_path import align_atom_order

    details = []
    source = _optimized_minima(source_logs, smiles=reactant_smiles, side='SOURCE/reactant',
        charge=charge, details=details)
    target = _optimized_minima(target_logs, smiles=product_smiles, side='TARGET/product',
        charge=charge, details=details)
    for name, source_end, target_end in (('direct', ends[0], ends[1]), ('swapped', ends[1], ends[0])):
        for source_start, source_minimum, source_log in source:
            if not same_geometry(source_start, source_end):
                continue
            for target_start, target_minimum, target_log in target:
                if not same_geometry(target_start, target_end):
                    continue
                if atom_binding:
                    # Native Opt rows retain the correspondence of their actual IRC input.
                    # Reorder by the input match, never by similarity of the relaxed minimum.
                    mapping = atom_binding.get('atom_map', [])
                    count = len(ts_geometry[0])
                    if (len(mapping) != count or any(type(index) is not int for index in mapping)
                            or sorted(mapping) != list(range(1, count + 1))):
                        continue
                    source_order = align_atom_order(*source_end, *source_start)
                    target_order = align_atom_order(*target_end, *target_start)
                    if source_order is None or target_order is None:
                        continue
                    source_bound = (source_end[0], [source_minimum[1][index] for index in source_order[0]])
                    target_bound = (target_end[0], [target_minimum[1][index] for index in target_order[0]])
                    target_bound = ([target_bound[0][index - 1] for index in mapping],
                                    [target_bound[1][index - 1] for index in mapping])
                    if (not _ordered_graph_matches(source_bound, atom_binding['reactant_mol'], charge)
                            or not _ordered_graph_matches(target_bound, atom_binding['product_mol'], charge)):
                        details.append('Optimized IRC endpoints differ from the bound complete atom identities.')
                        continue
                result = [f'{name} pairing: both actual IRC outer frames were independently optimized '
                    f'to the correct zero-imaginary minima ({source_log}; {target_log}).']
                try:
                    interval = prove_irc_endpoint_direction(*ts_geometry, *ends, source_minimum, target_minimum,
                        [], charge, atom_orders=bound_atom_orders(ts_geometry, source_minimum, target_minimum, atom_binding))
                    result.extend('[advisory] ' + item for item in interval.get('details', []))
                    if not (interval['is_decidable'] and interval['is_match']):
                        result.append('[warning] Endpoint optimization establishes direction, but the geometric interval '
                            'check failed or is undecidable; inspect the trajectory for suspicious geometry.')
                except Exception as exc:
                    result.append(f'[warning] Endpoint optimization establishes direction, but the geometric interval '
                                  f'could not be evaluated ({exc}); inspect the trajectory.')
                return True, result
    return False, ['The actual IRC outer frames are not connected to both declared zero-imaginary minima '
                   'by converged optimization logs; geometric interval agreement alone is not direction proof.', *details]
```


<a id="s229"></a>

### S229 · `verify_short_irc_direction`

`cloudra/tools/core/irc_evidence.py:522–606`

```python
def verify_short_irc_direction(
    irc_log,
    ts_logs: Sequence,
    endpoint_a_logs: Sequence,
    endpoint_b_logs: Sequence,
    *,
    charge: int = 0,
    atom_bindings=None,
    reactant_smiles: str | list[str] | None = None,
    product_smiles: str | list[str] | None = None,
) -> tuple[bool, list[str]]:
    """同一 TS 双向 IRC 的真实外帧经 Opt/Freq 到正确极小值即方向通过。

    材料：IRC 双侧端点与同一 TS 的单虚频日志；endpoint_a_logs /
    endpoint_b_logs 分别提供产物/反应物的 Opt/Freq 原生日志。首帧须匹配
    真实 IRC 外帧，收敛末帧须匹配零虚频几何，两侧可 direct/swapped 配对。

    返回 (passed, details)：passed=False 时 details 结构化写明缺哪份材料
    或证明为何不成立（缺 TS/端点材料 ⇒ 引导先补对应阶段的绑定证据）。
    """
    details: list[str] = []
    ends = irc_endpoint_geometries(irc_log)
    if ends is None:
        return False, [
            f"the IRC log {irc_log} does not yield usable endpoint geometries on "
            "both sides (Gaussian: outermost coordinated frames on the rx<0 and "
            "rx>0 sides; ORCA: endpoint files or outermost F/B trajectory frames — "
            "an unconverged direction's last frame is a legitimate partial "
            "endpoint); bind the parser output of a finished IRC job log"
        ]
    atom_binding = (atom_bindings or {}).get(str(irc_log))
    ts_geometries = [(geometry, (atom_bindings or {}).get(str(path)))
        for path in ts_logs
        for geometry in _usable_ts_geometries([path], details=details)]
    anchor = irc_start_geometry(irc_log)
    ts_geometries = [item for item in ts_geometries if same_geometry(item[0], anchor)]
    if not ts_geometries:
        details.append('IRC starting saddle is missing or differs from the submitted TS geometry; submit evidence from the same TS calculation geometry.')
    from_geometries = _usable_minimum_geometries(
        endpoint_b_logs, side="endpoint_b (SOURCE/reactant side)",
        details=details,
    )
    to_geometries = _usable_minimum_geometries(
        endpoint_a_logs, side="endpoint_a (TARGET/product side)",
        details=details,
    )
    if not ts_geometries:
        details.append(
            "missing TS material: bind the step's ts_opt/frequency stage evidence "
            "first (a normally terminated first-order saddle log with a final geometry)"
        )
    if not from_geometries:
        details.append(
            "missing endpoint_b material (SOURCE/reactant side): bind endpoint_b "
            "evidence or the source species' geometry stage — a frequency-verified "
            "minimum (zero imaginary frequencies) whose log carries a final geometry"
        )
    if not to_geometries:
        details.append(
            "missing endpoint_a material (TARGET/product side): bind endpoint_a "
            "evidence or the target species' geometry stage — a frequency-verified "
            "minimum (zero imaginary frequencies) whose log carries a final geometry"
        )
    if not (ts_geometries and from_geometries):
        return False, details
    separated = isinstance(product_smiles, list) and len(product_smiles) > 1
    if not separated:
        for ts_geometry, ts_binding in ts_geometries:
            passed, proof_details = _endpoint_optimization_proof(
                ends, ts_geometry, endpoint_b_logs, endpoint_a_logs, charge=charge,
                reactant_smiles=reactant_smiles, product_smiles=product_smiles,
                atom_binding=atom_binding if ts_binding == atom_binding else None,
            )
            if passed:
                return True, proof_details
            details.extend(proof_details)
    if separated:
        for ts_geometry, ts_binding in ts_geometries:
            verdict = verify_separated_product_direction(ends, ts_geometry, from_geometries,
                product_smiles, to_geometries, charge=charge,
                atom_binding=atom_binding if ts_binding == atom_binding else None)
            if verdict["is_match"]:
                return True, verdict["details"]
            details.extend(verdict["details"])
    return False, list(dict.fromkeys(details))
```


<a id="s230"></a>

### S230 · `verify_short_irc_pair`

`cloudra/tools/core/irc_evidence.py:609–667`

```python
def verify_short_irc_pair(forward_log, reverse_log, ts_logs, endpoint_a_logs, endpoint_b_logs, *,
        atom_bindings=None, charge=0, reactant_smiles: str | list[str] | None = None,
        product_smiles: str | list[str] | None = None):
    """Combine native directional logs using the same endpoint-optimization proof."""
    def outer_geometry(path, direction):
        engine = qm_engine.detect_qm_engine(str(path))
        if engine == 'orca':
            orca_frames.extract_irc(str(path))
            endpoints = orca_frames.extract_irc_endpoints(str(path))
            for side in (direction, 'backward' if direction == 'forward' else 'forward'):
                xyz = orca_frames.read_endpoint_geometry(endpoints[side])
                if xyz:
                    return parse_xyz(xyz)
        elif engine == 'gaussian':
            frames = [f for f in irc_frames_for(path) if f.xyz.strip() and f.reaction_coordinate]
            preferred = [f for f in frames if (f.reaction_coordinate > 0) == (direction == 'forward')]
            candidates = preferred or frames
            if candidates:
                return parse_xyz(max(candidates, key=lambda f: abs(f.reaction_coordinate)).xyz)
        return None

    details = []
    try:
        forward = outer_geometry(forward_log, 'forward')
        reverse = outer_geometry(reverse_log, 'backward')
    except (ValueError, OSError) as exc:
        return False, [f'Directional IRC evidence could not be read: {exc}']
    if forward is None or reverse is None:
        return False, ['Both submitted directional logs must supply an outer endpoint geometry.']
    atom_binding = (atom_bindings or {}).get(str(forward_log))
    if atom_binding != (atom_bindings or {}).get(str(reverse_log)):
        atom_binding = None
    ts = [(geometry, (atom_bindings or {}).get(str(path))) for path in ts_logs
          for geometry in _usable_ts_geometries([path], details=details)]
    starts = [irc_start_geometry(path) for path in (forward_log, reverse_log)]
    ts = [item for item in ts if all(same_geometry(item[0], start) for start in starts)]
    source = _usable_minimum_geometries(endpoint_b_logs, side='SOURCE', details=details)
    target = _usable_minimum_geometries(endpoint_a_logs, side='TARGET', details=details)
    if not (ts and source):
        return False, [*details, 'Bind the TS and frequency-verified source/target minimum logs.']
    separated = isinstance(product_smiles, list) and len(product_smiles) > 1
    if not separated:
        for geometry, ts_binding in ts:
            passed, proof_details = _endpoint_optimization_proof((forward, reverse), geometry,
                endpoint_b_logs, endpoint_a_logs, charge=charge,
                reactant_smiles=reactant_smiles, product_smiles=product_smiles,
                atom_binding=atom_binding if ts_binding == atom_binding else None)
            if passed:
                return True, proof_details
            details.extend(proof_details)
    if separated:
        for geometry, ts_binding in ts:
            verdict = verify_separated_product_direction((forward, reverse), geometry, source,
                product_smiles, target, charge=charge,
                atom_binding=atom_binding if ts_binding == atom_binding else None)
            if verdict['is_match']:
                return True, verdict['details']
            details.extend(verdict['details'])
    return False, ['The paired IRC endpoint optimization proof is incomplete.', *details]
```


## `cloudra/tools/core/irc_path.py`

文件 SHA-256：`4b25f7bd0f132d1fa37b4ba2e0b4c1c9d42a7860ef0471159a1b99f2639731b5`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/tools/core/irc_path.py:112–112`

```python
_STRICT_PAIR_DELTA_MIN_ANG = 0.15
```


`cloudra/tools/core/irc_path.py:113–113`

```python
_STRICT_INTERVAL_TOL_ANG = 0.10
```


`cloudra/tools/core/irc_path.py:114–114`

```python
_STRICT_MAX_AUTO_PAIRS = 5
```


`cloudra/tools/core/irc_path.py:115–115`

```python
_STRICT_PAIR_EPS_ANG = 1e-8
```


`cloudra/tools/core/irc_path.py:121–121`

```python
_IDENTICAL_ORDER_COST_MARGIN = 0.5
```


`cloudra/tools/core/irc_path.py:124–134`

```python
COVALENT_RADII = {
    'H': 0.31, 'He': 0.28,
    'Li': 1.28, 'Be': 0.96, 'B': 0.84, 'C': 0.76, 'N': 0.71, 'O': 0.66, 'F': 0.57, 'Ne': 0.58,
    'Na': 1.66, 'Mg': 1.41, 'Al': 1.21, 'Si': 1.11, 'P': 1.07, 'S': 1.05, 'Cl': 1.02, 'Ar': 1.06,
    'K': 2.03, 'Ca': 1.76, 'Sc': 1.70, 'Ti': 1.60, 'V': 1.53, 'Cr': 1.39, 'Mn': 1.39,
    'Fe': 1.32, 'Co': 1.26, 'Ni': 1.24, 'Cu': 1.32, 'Zn': 1.22, 'Ga': 1.22, 'Ge': 1.20,
    'As': 1.19, 'Se': 1.20, 'Br': 1.20, 'Kr': 1.16,
    'Rb': 2.20, 'Sr': 1.95, 'Y': 1.90, 'Zr': 1.75, 'Nb': 1.64, 'Mo': 1.54, 'Tc': 1.47,
    'Ru': 1.46, 'Rh': 1.42, 'Pd': 1.39, 'Ag': 1.45, 'Cd': 1.44, 'In': 1.42, 'Sn': 1.39,
    'Sb': 1.39, 'Te': 1.38, 'I': 1.39, 'Xe': 1.40,
}
```


`cloudra/tools/core/irc_path.py:139–139`

```python
DISTANCE_CONNECTIVITY_FACTOR = 1.25
```


`cloudra/tools/core/irc_path.py:141–149`

```python
_ATOMIC_NUMBER = {
    'H': 1, 'He': 2, 'Li': 3, 'Be': 4, 'B': 5, 'C': 6, 'N': 7, 'O': 8, 'F': 9, 'Ne': 10,
    'Na': 11, 'Mg': 12, 'Al': 13, 'Si': 14, 'P': 15, 'S': 16, 'Cl': 17, 'Ar': 18,
    'K': 19, 'Ca': 20, 'Sc': 21, 'Ti': 22, 'V': 23, 'Cr': 24, 'Mn': 25, 'Fe': 26,
    'Co': 27, 'Ni': 28, 'Cu': 29, 'Zn': 30, 'Ga': 31, 'Ge': 32, 'As': 33, 'Se': 34,
    'Br': 35, 'Kr': 36, 'Rb': 37, 'Sr': 38, 'Y': 39, 'Zr': 40, 'Nb': 41, 'Mo': 42,
    'Tc': 43, 'Ru': 44, 'Rh': 45, 'Pd': 46, 'Ag': 47, 'Cd': 48, 'In': 49, 'Sn': 50,
    'Sb': 51, 'Te': 52, 'I': 53, 'Xe': 54,
}
```


`cloudra/tools/core/irc_path.py:152–156`

```python
_PAULING_EN = {
    'H': 2.20, 'B': 2.04, 'C': 2.55, 'N': 3.04, 'O': 3.44, 'F': 3.98,
    'Si': 1.90, 'P': 2.19, 'S': 2.58, 'Cl': 3.16, 'As': 2.18, 'Se': 2.55,
    'Br': 2.96, 'I': 2.66,
}
```


`cloudra/tools/core/irc_path.py:159–159`

```python
_HEURISTIC_W_EN = 1.0
```


`cloudra/tools/core/irc_path.py:160–160`

```python
_HEURISTIC_W_HEAVY = 0.5
```


`cloudra/tools/core/irc_path.py:161–161`

```python
_HEURISTIC_W_DIST = 1.0
```


`cloudra/tools/core/irc_path.py:162–162`

```python
_HEURISTIC_MAD_K = 2.5
```


`cloudra/tools/core/irc_path.py:213–213`

```python
_ALIGN_MAX_RMSD_ANG = 1.0
```


<a id="s231"></a>

### S231 · `same_geometry`

`cloudra/tools/core/irc_path.py:37–110`

```python
def same_geometry(reference, mobile) -> bool:
    """Same coordinates up to atom order and proper rigid rotation.

    Reuse the existing six-decimal XYZ rounding bound; this is identity of a
    calculation geometry, not a conformer or chemical similarity criterion.
    """
    import numpy as np

    if reference is None or mobile is None:
        return False
    ref_symbols, mob_symbols = reference[0], mobile[0]
    if len(ref_symbols) == 0 or sorted(ref_symbols) != sorted(mob_symbols):
        return False
    ref = np.asarray(reference[1], dtype=float)
    mob = np.asarray(mobile[1], dtype=float)
    ref = ref - ref.mean(axis=0)
    mob = mob - mob.mean(axis=0)
    tolerance = np.sqrt(3) * 10 ** -6

    def proper_rotation(left, right):
        u, _, vt = np.linalg.svd(left.T @ right)
        if np.linalg.det(u @ vt) < 0:
            u[:, -1] *= -1
        return u @ vt

    def matches(perm):
        ordered = mob[perm]
        residual = np.linalg.norm(ordered @ proper_rotation(ordered, ref) - ref, axis=1)
        return bool(np.max(residual) <= tolerance)

    alignment = align_atom_order(*reference, *mobile)
    if alignment is not None and matches(alignment[0]):
        return True

    # Distance-fingerprint ties can choose an improper symmetry, or mix several
    # symmetries. Keep the lineage-aware interval alignment above unchanged, but
    # search alternative strict-identity correspondences here. Two independent
    # centered vectors determine a proper rotation: at most n * (n - 1) anchor
    # pairs, rather than factorial permutations of equivalent atoms.
    d_ref, d_mob = dist_matrix(ref), dist_matrix(mob)
    fp_ref, fp_mob = np.sort(d_ref, axis=1), np.sort(d_mob, axis=1)
    compatible = np.array(mob_symbols)[:, None] == np.array(ref_symbols)[None, :]
    for i in range(len(ref_symbols)):
        # If each atom moves by at most tolerance, a pair distance changes by
        # at most twice that bound. This only prunes correspondence candidates;
        # the original proper-rotation residual remains the acceptance test.
        compatible[:, i] &= np.max(np.abs(fp_mob - fp_ref[i]), axis=1) <= 2 * tolerance
    if not np.all(np.any(compatible, axis=0)):
        return False

    first = int(np.argmax(np.linalg.norm(ref, axis=1)))
    cross = np.linalg.norm(np.cross(ref[first], ref), axis=1)
    second = int(np.argmax(cross))
    for mob_first in np.flatnonzero(compatible[:, first]):
        # Collinear geometries need only one axis; rotation about it is free.
        seconds = np.flatnonzero(compatible[:, second]) if cross[second] > 0 else [None]
        for mob_second in seconds:
            ref_anchors, mob_anchors = [first], [mob_first]
            if mob_second is not None:
                if mob_first == mob_second or abs(
                    d_ref[first, second] - d_mob[mob_first, mob_second]
                ) > 2 * tolerance:
                    continue
                ref_anchors.append(second)
                mob_anchors.append(mob_second)
            rotated = mob @ proper_rotation(mob[mob_anchors], ref[ref_anchors])
            cost = np.linalg.norm(rotated[:, None, :] - ref[None, :, :], axis=2)
            cost[~compatible] = 1e9
            perm = np.argmin(cost, axis=0).tolist()
            if len(set(perm)) != len(perm):
                perm = _hungarian(cost)
            if perm is not None and matches(perm):
                return True
    return False
```


<a id="s232"></a>

### S232 · `parse_xyz`

`cloudra/tools/core/irc_path.py:165–188`

```python
def parse_xyz(text: str) -> Optional[tuple[list[str], list[list[float]]]]:
    """标准 XYZ 块 → (symbols, positions)。首行原子数、次行注释、随后 N 行
    "元素 x y z"；任何一行不合格即返回 None（纯 split，不用正则）。"""
    lines = text.strip().splitlines()
    if not lines:
        return None
    try:
        n = int(lines[0].strip())
    except ValueError:
        return None
    if n <= 0 or len(lines) < n + 2:
        return None
    symbols: list[str] = []
    positions: list[list[float]] = []
    for line in lines[2:2 + n]:
        parts = line.split()
        if len(parts) < 4:
            return None
        try:
            positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
        except ValueError:
            return None
        symbols.append(parts[0])
    return symbols, positions
```


<a id="s233"></a>

### S233 · `xyz_block`

`cloudra/tools/core/irc_path.py:191–196`

```python
def xyz_block(symbols, positions) -> str:
    """(symbols, positions) → 标准 XYZ 块（喂 RDKit MolFromXYZBlock）。"""
    lines = [str(len(symbols)), ""]
    for s, (x, y, z) in zip(symbols, positions):
        lines.append(f"{s} {x:.6f} {y:.6f} {z:.6f}")
    return "\n".join(lines) + "\n"
```


<a id="s234"></a>

### S234 · `pair_label`

`cloudra/tools/core/irc_path.py:199–200`

```python
def pair_label(symbols, pair: tuple[int, int], base: int = 1) -> str:
    return f"{symbols[pair[0]]}{pair[0] + base}-{symbols[pair[1]]}{pair[1] + base}"
```


<a id="s235"></a>

### S235 · `dist_matrix`

`cloudra/tools/core/irc_path.py:203–208`

```python
def dist_matrix(coords):
    import numpy as np

    pos = np.asarray(coords, dtype=float)
    diff = pos[:, None, :] - pos[None, :, :]
    return np.linalg.norm(diff, axis=-1)
```


<a id="s236"></a>

### S236 · `bond_pairs_from_dist`

`cloudra/tools/core/irc_path.py:216–226`

```python
def bond_pairs_from_dist(symbols, d, scale: float = DISTANCE_CONNECTIVITY_FACTOR) -> set[tuple[int, int]]:
    """距离矩阵版共价半径成键判据（0-based，i<j；与 bond_pairs 同一阈值）。"""
    n = len(symbols)
    pairs: set[tuple[int, int]] = set()
    for i in range(n):
        ri = COVALENT_RADII.get(symbols[i], 1.2)
        for j in range(i + 1, n):
            rj = COVALENT_RADII.get(symbols[j], 1.2)
            if float(d[i][j]) <= scale * (ri + rj):
                pairs.add((i, j))
    return pairs
```


<a id="s237"></a>

### S237 · `bond_pairs`

`cloudra/tools/core/irc_path.py:229–231`

```python
def bond_pairs(symbols, positions, scale: float = DISTANCE_CONNECTIVITY_FACTOR) -> set[tuple[int, int]]:
    """共价半径距离判据成键对集合（0-based，i<j）。"""
    return bond_pairs_from_dist(symbols, dist_matrix(positions), scale)
```


<a id="s238"></a>

### S238 · `_rdkit_bonds`

`cloudra/tools/core/irc_path.py:234–252`

```python
def _rdkit_bonds(symbols, positions, charge: int) -> Optional[dict]:
    """rdDetermineBonds 主通道；RDKit 缺失或感知失败返回 None。"""
    try:
        from rdkit import Chem
        from rdkit.Chem import rdDetermineBonds
    except ImportError:
        return None
    try:
        mol = Chem.MolFromXYZBlock(xyz_block(symbols, positions))
        if mol is None:
            return None
        rdDetermineBonds.DetermineBonds(mol, charge=charge)
    except Exception:
        return None
    out: dict[tuple[int, int], float] = {}
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        out[(min(i, j), max(i, j))] = float(bond.GetBondTypeAsDouble())
    return out
```


<a id="s239"></a>

### S239 · `perceive_bonds`

`cloudra/tools/core/irc_path.py:255–264`

```python
def perceive_bonds(symbols, positions, charge: int = 0) -> tuple[dict, str]:
    """键感知 → (bonds {(i,j): order}, source)。

    主通道 RDKit rdDetermineBonds（与 reaction_mapping 同一事实源，需总
    电荷）；失败/无 RDKit 回退共价半径距离判据——source="distance" 的键图
    不得充当 A 层硬证据，只喂 B 层启发项。"""
    bonds = _rdkit_bonds(symbols, positions, charge)
    if bonds is not None:
        return bonds, "rdDetermineBonds"
    return {p: 1.0 for p in bond_pairs(symbols, positions)}, "distance"
```


<a id="s240"></a>

### S240 · `_hungarian`

`cloudra/tools/core/irc_path.py:267–319`

```python
def _hungarian(cost) -> Optional[list[int]]:
    """Kuhn-Munkres 最小权指派（纯 numpy O(n³)，确定性 tie-break）。

    返回 perm：perm[j] = 分配给列 j 的行下标。大数（1e9）表示禁配。
    返回前校验：每列的指派代价 < 1e9（禁配被选中 = 无合法完美匹配）且
    每行恰好被指派一次；违反即返回 None（调用方按 undecidable 处理）。"""
    import numpy as np

    a = np.asarray(cost, dtype=float)
    n = a.shape[0]
    u = np.zeros(n + 1)
    v = np.zeros(n + 1)
    p = np.zeros(n + 1, dtype=int)
    way = np.zeros(n + 1, dtype=int)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(n + 1, np.inf)
        used = np.zeros(n + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = np.inf
            j1 = 0
            for j in range(1, n + 1):
                if used[j]:
                    continue
                cur = a[i0 - 1, j - 1] - u[i0] - v[j]
                if cur < minv[j] - 1e-12:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta - 1e-12:
                    delta = minv[j]
                    j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    perm = [int(p[j]) - 1 for j in range(1, n + 1)]
    if sorted(perm) != list(range(n)):
        return None
    if any(a[perm[j], j] >= 1e9 for j in range(n)):
        return None
    return perm
```


<a id="s241"></a>

### S241 · `align_atom_order`

`cloudra/tools/core/irc_path.py:322–368`

```python
def align_atom_order(ref_symbols, ref_pos, mob_symbols, mob_pos, *, atom_order=None):
    """把 mobile 几何重排到 reference 的原子序（任意原子序输入的对应件）。

    原子数/元素多重集不等 → None（进不了这一层，调用方按 undecidable 处理）。
    对应准则：每原子的距离指纹（到他原子的距离排序向量，旋转平移不变），
    同元素掩码 + Hungarian 最优指派。返回 (perm, rmsd)：perm[ref_idx] =
    mob_idx；rmsd 是重排后距离矩阵均方根差。rmsd 超过保守闸门
    （_ALIGN_MAX_RMSD_ANG）或不存在合法的元素一致指派时也返回 None——
    对齐太差的组合按 undecidable 跳过，不带着可疑对应进区间证明。"""
    import numpy as np

    n = len(ref_symbols)
    if n != len(mob_symbols) or sorted(ref_symbols) != sorted(mob_symbols):
        return None
    d_ref = dist_matrix(ref_pos)
    d_mob = dist_matrix(mob_pos)
    if atom_order is not None:
        if (len(atom_order) != n or any(type(index) is not int for index in atom_order)
                or sorted(atom_order) != list(range(n))
                or any(ref_symbols[i] != mob_symbols[index] for i, index in enumerate(atom_order))):
            return None
        rmsd = float(np.sqrt(((d_ref - d_mob[np.ix_(atom_order, atom_order)]) ** 2).mean()))
        return (list(atom_order), rmsd) if rmsd <= _ALIGN_MAX_RMSD_ANG else None
    fp_ref = np.sort(d_ref, axis=1)
    fp_mob = np.sort(d_mob, axis=1)
    cost = np.full((n, n), 1e9)
    for i in range(n):
        for j in range(n):
            if mob_symbols[j] == ref_symbols[i]:
                cost[i, j] = float(np.linalg.norm(fp_ref[i] - fp_mob[j]))
    col_to_row = _hungarian(cost)
    if col_to_row is None:
        return None
    perm = [0] * n
    for j, i in enumerate(col_to_row):
        perm[i] = j
    if list(mob_symbols) == list(ref_symbols):
        # 元素序列一致：恒等对应（同谱系）天然合法；只有 Hungarian decisively
        # 更好（代价 < margin × 恒等代价）才换序，避免几何噪声造成假换序。
        identity_cost = float(sum(cost[i, i] for i in range(n)))
        hungarian_cost = float(sum(cost[i, perm[i]] for i in range(n)))
        if hungarian_cost >= identity_cost * _IDENTICAL_ORDER_COST_MARGIN:
            perm = list(range(n))
    rmsd = float(np.sqrt(((d_ref - d_mob[np.ix_(perm, perm)]) ** 2).mean()))
    if rmsd > _ALIGN_MAX_RMSD_ANG:
        return None
    return perm, rmsd
```


<a id="s242"></a>

### S242 · `classify_watch_pairs`

`cloudra/tools/core/irc_path.py:371–436`

```python
def classify_watch_pairs(symbols, d_ts, d_int, ts_bonds, int_bonds) -> dict:
    """反应原子对分类：bond_diff（A 层候选）/ distance_top5（回退）/ b（软提名）。

    输入是同一坐标序下的 (符号, TS 距离矩阵, 中间体距离矩阵, 两张键图)。
    - bond_diff：键状态翻转 ∪ 两侧成键且 |Δd|≥阈值的伸缩对；
    - distance_top5：|Δd| 最大的至多 5 对（≥阈值），bond_diff 不可用时的回退；
    - b：其余对按 ΔEN + 重原子 + |Δd|_norm 打分，median + k·MAD 过滤离群低值。
    """
    import statistics

    import numpy as np

    d_ts = np.asarray(d_ts, dtype=float)
    d_int = np.asarray(d_int, dtype=float)
    n = len(symbols)
    all_pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    deltas = {p: abs(float(d_ts[p]) - float(d_int[p])) for p in all_pairs}

    flips = set(ts_bonds) ^ set(int_bonds)
    stretches = {
        p for p in set(ts_bonds) & set(int_bonds)
        if deltas[p] >= _STRICT_PAIR_DELTA_MIN_ANG
    }
    bond_diff = sorted(flips | stretches)

    top5 = sorted(
        (p for p in sorted(all_pairs, key=lambda p: (-deltas[p], p))
         if deltas[p] >= _STRICT_PAIR_DELTA_MIN_ANG),
    )[:_STRICT_MAX_AUTO_PAIRS]

    gated = set(bond_diff) | set(top5)
    max_delta = max(deltas.values()) or 1.0
    bonded_any = set(ts_bonds) | set(int_bonds)
    scores: dict[tuple[int, int], float] = {}
    for p in all_pairs:
        if p in gated:
            continue
        i, j = p
        en = abs(
            _PAULING_EN.get(symbols[i], 0.0) - _PAULING_EN.get(symbols[j], 0.0)
        ) / 3.0
        heavy = min(
            _ATOMIC_NUMBER.get(symbols[i], 0), _ATOMIC_NUMBER.get(symbols[j], 0)
        ) / 6.0
        heavy = min(heavy, 1.0) * (1.0 if p in bonded_any else 0.5)
        scores[p] = (
            _HEURISTIC_W_EN * en
            + _HEURISTIC_W_HEAVY * heavy
            + _HEURISTIC_W_DIST * (deltas[p] / max_delta)
        )
    b_pairs: list[tuple[int, int]] = []
    if scores:
        values = list(scores.values())
        median = statistics.median(values)
        mad = statistics.median([abs(v - median) for v in values])
        if mad > 0:
            cutoff = median + _HEURISTIC_MAD_K * mad
        elif len(values) > 1:
            # MAD=0 退化（对称分子大量并列分）：median + k·MAD 退成 median，
            # 等于不过滤——回退固定上四分位（不随并列退化）。
            cutoff = statistics.quantiles(values, n=4)[2]
        else:
            # 单对无法构成统计过滤：不提名
            cutoff = values[0]
        b_pairs = sorted(p for p, s in scores.items() if s > cutoff)
    return {"bond_diff": bond_diff, "distance_top5": top5, "b": b_pairs}
```


<a id="s243"></a>

### S243 · `evaluate_endpoint_between`

`cloudra/tools/core/irc_path.py:439–576`

```python
def evaluate_endpoint_between(symbols: Sequence[str], ts_pos, end_pos,
                              intermediate_pos, watch_pairs: Sequence[Sequence[int]],
                              charge: int = 0, *, index_base: int = 1, intermediate_molecule=None) -> dict:
    """判断一个部分 IRC 端点是否位于 TS 与某个端点参考几何之间。

    判定对来源（硬闸门）：显式 watch_pairs > 键图 diff（A 层，两侧感知均为
    rdDetermineBonds 时）> distance_top5 回退。B 层提名对只进 details。"""
    import numpy as np

    if intermediate_molecule is not None:
        intermediate_pos = intermediate_molecule.GetConformer().GetPositions()
    n = len(symbols)
    arrays = [np.asarray(pos, dtype=float) for pos in (ts_pos, end_pos, intermediate_pos)]
    if any(pos.shape != (n, 3) for pos in arrays):
        return {
            "is_decidable": False, "is_between": False, "score": float("inf"),
            "pairs": [], "pairs_a": [], "pairs_b": [],
            "pair_layer": "", "perception": "", "warnings": [],
            "details": ["Coordinate dimensions of TS, IRC endpoint, and intermediate do not match."],
        }

    d_ts, d_end, d_int = (dist_matrix(pos) for pos in arrays)
    b_pairs: list[tuple[int, int]] = []
    perception = "explicit_watch_pairs"
    if watch_pairs:
        layer = "explicit"
        pairs = []
        for raw_pair in watch_pairs:
            if len(raw_pair) != 2:
                return {
                    "is_decidable": False, "is_between": False, "score": float("inf"),
                    "pairs": [], "pairs_a": [], "pairs_b": [],
                    "pair_layer": "", "perception": "", "warnings": [],
                    "details": [f"watch_pairs entries must contain two atom indices: {raw_pair}"],
                }
            i, j = int(raw_pair[0]) - index_base, int(raw_pair[1]) - index_base
            if not (0 <= i < n and 0 <= j < n) or i == j:
                return {
                    "is_decidable": False, "is_between": False, "score": float("inf"),
                    "pairs": [], "pairs_a": [], "pairs_b": [],
                    "pair_layer": "", "perception": "", "warnings": [],
                    "details": [f"watch_pairs atom indices invalid: {raw_pair}"],
                }
            pair = (min(i, j), max(i, j))
            if pair not in pairs:
                pairs.append(pair)
        pairs = [pair for pair in pairs if abs(d_int[pair] - d_ts[pair]) > _STRICT_PAIR_EPS_ANG]
    else:
        ts_bonds, src_ts = perceive_bonds(symbols, ts_pos, charge)
        known_graph = intermediate_molecule is not None and not (
            intermediate_molecule.HasProp("cloudra_graph_status")
            and intermediate_molecule.GetProp("cloudra_graph_status") == "unresolved"
        )
        if known_graph:
            int_bonds = {tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))): float(bond.GetBondTypeAsDouble())
                         for bond in intermediate_molecule.GetBonds()}
            src_int = "declared_molecule"
        else:
            int_bonds, src_int = perceive_bonds(symbols, intermediate_pos, charge)
        perception = f"ts={src_ts},intermediate={src_int}"
        cls = classify_watch_pairs(symbols, d_ts, d_int, ts_bonds, int_bonds)
        b_pairs = cls["b"]
        authoritative = src_ts == "rdDetermineBonds" and src_int in {"rdDetermineBonds", "declared_molecule"}
        if authoritative and cls["bond_diff"]:
            pairs, layer = cls["bond_diff"], "bond_diff"
        else:
            pairs, layer = cls["distance_top5"], "distance_top5"

    if not pairs:
        return {
            "is_decidable": False, "is_between": False, "score": float("inf"),
            "pairs": [], "pairs_a": [], "pairs_b": b_pairs,
            "pair_layer": layer, "perception": perception, "warnings": [],
            "details": ["No atom-pair distance change between TS and intermediate is large enough to judge direction."],
        }

    q_ts = np.asarray([d_ts[pair] for pair in pairs])
    q_end = np.asarray([d_end[pair] for pair in pairs])
    q_int = np.asarray([d_int[pair] for pair in pairs])
    lower = np.minimum(q_ts, q_int) - _STRICT_INTERVAL_TOL_ANG
    upper = np.maximum(q_ts, q_int) + _STRICT_INTERVAL_TOL_ANG
    inside = (q_end >= lower) & (q_end <= upper)

    # 失败分级：中间体端仍是共价键的对，任何出区间都是硬失败；
    # 中间体端已超出共价半径判据的对（氢键/弱接触——IRC 不需要保真这类键，
    # 用户决策）无论过冲还是欠程都降级为 warning——弱接触在两个方向上
    # 都是 floppy 的，未完全收敛的端点在上面偏一点是常态。
    warnings: list[tuple[int, int]] = []
    hard_outside: list[tuple[int, int]] = []
    for k, pair in enumerate(pairs):
        if inside[k]:
            continue
        weak_at_intermediate = float(q_int[k]) > DISTANCE_CONNECTIVITY_FACTOR * (
            COVALENT_RADII.get(symbols[pair[0]], 1.2)
            + COVALENT_RADII.get(symbols[pair[1]], 1.2)
        )
        if weak_at_intermediate:
            warnings.append(pair)
        else:
            hard_outside.append(pair)

    dist_ts_to_int = float(np.linalg.norm(q_ts - q_int))
    dist_end_to_int = float(np.linalg.norm(q_end - q_int))
    closer = dist_end_to_int < dist_ts_to_int
    is_between = bool(not hard_outside and closer)
    score = dist_end_to_int / dist_ts_to_int if dist_ts_to_int > 0 else float("inf")

    details = [
        f"{pair_label(symbols, pair, index_base)}: TS={d_ts[pair]:.3f} Å, "
        f"IRC_endpoint={d_end[pair]:.3f} Å, intermediate={d_int[pair]:.3f} Å, "
        f"{'inside interval' if inside[k] else 'outside interval'}"
        for k, pair in enumerate(pairs)
    ]
    for pair in warnings:
        details.append(
            f"[warning] {pair_label(symbols, pair, index_base)}: endpoint deviates from the "
            f"interval on a weak contact (H-bond/non-covalent at the minimum, "
            f"d={d_int[pair]:.3f} Å); IRC need not preserve such pairs."
        )
    details.append(f"Distance-vector ratio endpoint-to-intermediate={score:.3f} (<1 means closer than TS).")
    details.append(f"Gate pairs layer: {layer} (perception: {perception}).")
    for pair in b_pairs:
        details.append(
            f"[advisory-B] {pair_label(symbols, pair, index_base)}: TS={d_ts[pair]:.3f} Å, "
            f"IRC_endpoint={d_end[pair]:.3f} Å, intermediate={d_int[pair]:.3f} Å"
        )
    return {
        "is_decidable": True,
        "is_between": is_between,
        "score": score,
        "pairs": pairs,
        "pairs_a": pairs,
        "pairs_b": b_pairs,
        "pair_layer": layer,
        "perception": perception,
        "warnings": warnings,
        "details": details,
    }
```


<a id="s244"></a>

### S244 · `assign_irc_endpoints`

`cloudra/tools/core/irc_path.py:579–623`

```python
def assign_irc_endpoints(symbols: Sequence[str], ts_pos, end_a_pos, end_b_pos,
                         intermediate_a_pos, intermediate_b_pos,
                         watch_pairs: Sequence[Sequence[int]],
                         charge: int = 0, *, index_base: int = 1, reference_molecules=None) -> dict:
    """尝试 IRC 两端与两个端点参考几何的 direct/swapped 无序配对。"""
    assignments = []
    mol_a, mol_b = reference_molecules or (None, None)
    for name, target_a, target_b, reference_a, reference_b in (
        ("direct", intermediate_a_pos, intermediate_b_pos, mol_a, mol_b),
        ("swapped", intermediate_b_pos, intermediate_a_pos, mol_b, mol_a),
    ):
        result_a = evaluate_endpoint_between(
            symbols, ts_pos, end_a_pos, target_a, watch_pairs, charge, index_base=index_base,
            intermediate_molecule=reference_a,
        )
        result_b = evaluate_endpoint_between(
            symbols, ts_pos, end_b_pos, target_b, watch_pairs, charge, index_base=index_base,
            intermediate_molecule=reference_b,
        )
        assignments.append({
            "name": name,
            "a": result_a,
            "b": result_b,
            "is_decidable": result_a["is_decidable"] and result_b["is_decidable"],
            "is_match": result_a["is_between"] and result_b["is_between"],
            "score": result_a["score"] + result_b["score"],
        })

    decidable = [item for item in assignments if item["is_decidable"]]
    if not decidable:
        details = assignments[0]["a"]["details"] + assignments[0]["b"]["details"]
        return {
            "is_decidable": False, "is_match": False, "assignment": "",
            "details": details,
        }

    matches = [item for item in decidable if item["is_match"]]
    chosen = min(matches or decidable, key=lambda item: item["score"])
    return {
        "is_decidable": True,
        "is_match": bool(matches),
        "assignment": chosen["name"] if matches else "",
        "warnings": chosen["a"].get("warnings", []) + chosen["b"].get("warnings", []),
        "details": chosen["a"]["details"] + chosen["b"]["details"],
    }
```


<a id="s245"></a>

### S245 · `prove_irc_endpoint_direction`

`cloudra/tools/core/irc_path.py:626–677`

```python
def prove_irc_endpoint_direction(
    ts_symbols: Sequence[str],
    ts_pos,
    endpoint_a: tuple[Sequence[str], object],
    endpoint_b: tuple[Sequence[str], object],
    intermediate_a: tuple[Sequence[str], object],
    intermediate_b: tuple[Sequence[str], object],
    watch_pairs: Sequence[Sequence[int]],
    charge: int = 0,
    *, index_base: int = 1, atom_orders=None, reference_molecules=None,
) -> dict:
    """Align four geometries to the TS and apply the shared IRC direction test.

    This is a deterministic geometric diagnostic, not endpoint-optimization
    evidence. Its result is advisory when native IRC → Opt → Freq lineage exists.
    """
    aligned = []
    aligned_molecules = []
    for slot, (label, (symbols, positions)) in enumerate((
        ("IRC endpoint A", endpoint_a),
        ("IRC endpoint B", endpoint_b),
        ("intermediate A", intermediate_a),
        ("intermediate B", intermediate_b),
    )):
        result = align_atom_order(ts_symbols, ts_pos, symbols, positions,
                                  atom_order=atom_orders[slot] if atom_orders else None)
        if result is None:
            return {
                "is_decidable": False,
                "is_match": False,
                "assignment": "",
                "details": [
                    f"{label} differs from the TS in elements or atom counts, or geometry alignment failed."
                ],
            }
        perm, rmsd = result
        aligned.append([positions[k] for k in perm])
        if reference_molecules is not None and slot >= 2:
            from cloudra.tools.core.molecule import renumber_atoms

            reference = reference_molecules[slot - 2]
            aligned_molecules.append(renumber_atoms(reference, list(perm)) if reference is not None else None)

    result = assign_irc_endpoints(
        ts_symbols,
        ts_pos,
        aligned[0], aligned[1], aligned[2], aligned[3],
        watch_pairs,
        charge, index_base=index_base, reference_molecules=aligned_molecules or None,
    )
    result["aligned_positions"] = aligned
    return result
```


## `cloudra/tools/core/molecule.py`

文件 SHA-256：`b2a3811a5c5af9dd707d108a178e1dc7b09b460a8e4a30aa7e23145decb2ff11`


<a id="s246"></a>

### S246 · `_copy_molecule`

`cloudra/tools/core/molecule.py:20–30`

```python
def _copy_molecule(value):
    from rdkit import Chem

    if isinstance(value, str):
        try:
            return Chem.Mol(base64.b64decode(value, validate=True))
        except (ValueError, RuntimeError) as exc:
            raise ValueError("invalid serialized native molecule state") from exc
    if not isinstance(value, Chem.Mol):
        raise ValueError("a molecule or its serialized native state is required")
    return Chem.Mol(value)
```


<a id="s247"></a>

### S247 · `_cartesian_atoms`

`cloudra/tools/core/molecule.py:69–90`

```python
def _cartesian_atoms(rows, *, source):
    from ase import Atoms
    from ase.data import atomic_numbers

    symbols, positions = [], []
    for index, line in enumerate(rows, 1):
        tokens = line.split()
        if len(tokens) != 4:
            raise ValueError(f"{source}: expected Cartesian 'element x y z' at atom {index}; Z-matrix and freeze codes are unsupported")
        if tokens[0] not in atomic_numbers or atomic_numbers[tokens[0]] == 0:
            raise ValueError(f"{source}: unsupported atom {tokens[0]!r}; provide plain element symbols without isotope/dummy annotations")
        try:
            position = [float(value.replace('D', 'E').replace('d', 'e')) for value in tokens[1:]]
        except ValueError as exc:
            raise ValueError(f"{source}: invalid Cartesian coordinates at atom {index}") from exc
        if not all(math.isfinite(value) for value in position):
            raise ValueError(f"{source}: Cartesian coordinates must be finite at atom {index}")
        symbols.append(tokens[0])
        positions.append(position)
    if not symbols:
        raise ValueError(f"{source}: explicit Cartesian geometry is missing; checkpoint geometry is unsupported")
    return Atoms(symbols=symbols, positions=positions)
```


<a id="s248"></a>

### S248 · `_read_gaussian_structure`

`cloudra/tools/core/molecule.py:93–127`

```python
def _read_gaussian_structure(text):
    """Read one explicit Cartesian section, normalizing declared units to Angstrom."""
    from cloudra.tools.core.native_input_sections import (
        gaussian_coordinate_units,
        gaussian_option,
        gaussian_sections,
    )

    lines = [line.strip() for line in text.splitlines()]
    if any(line.lower() == '--link1--' for line in lines):
        raise ValueError("Gaussian Link1/multiple jobs are unsupported; provide one explicit Cartesian structure or convert the intended geometry to XYZ")
    sections = gaussian_sections(text)
    if not sections:
        raise ValueError("Gaussian input is missing its route section; provide a single Cartesian input or XYZ")
    section = sections[0]
    for token in section.route:
        key, options = gaussian_option(token)
        if key == 'opt' and options & {'qst2', 'qst3'}:
            raise ValueError("Gaussian QST2/QST3 jobs contain multiple geometries; provide the intended single Cartesian structure or XYZ")
        if key == 'geom' and options & {'check', 'checkpoint', 'allcheck', 'allcheckpoint'}:
            raise ValueError("Gaussian checkpoint geometry is unsupported; provide explicit Cartesian coordinates or an exported XYZ")
    source_units = gaussian_coordinate_units(section.route)
    if source_units == 'unknown':
        raise ValueError("Gaussian units declarations are unsupported or conflicting; provide Cartesian coordinates in one unambiguous unit, Angstrom or Bohr")
    if section.charge is None:
        raise ValueError("Gaussian charge and multiplicity must be two integers after the title section")
    charge, multiplicity = section.charge
    if multiplicity <= 0:
        raise ValueError("Gaussian multiplicity must be positive")
    atoms = _cartesian_atoms(section.geometry, source='Gaussian')
    if source_units == 'bohr':
        from ase.units import Bohr

        atoms.positions *= Bohr
    return atoms, charge, multiplicity, source_units
```


<a id="s249"></a>

### S249 · `_read_orca_structure`

`cloudra/tools/core/molecule.py:130–162`

```python
def _read_orca_structure(text):
    """Read exactly one inline ORCA Cartesian molecule without inventing identity."""
    from cloudra.tools.core.calculation_intent import _orca_code
    from cloudra.tools.core.native_input_sections import orca_coordinate_units, orca_xyz_sections

    lines = [line.strip() for line in _orca_code(text.lstrip('\ufeff')).splitlines()]
    if any(line.lower().split()[:1] == ['$new_job'] for line in lines):
        raise ValueError('ORCA multiple jobs are unsupported; provide the intended single Cartesian geometry or XYZ')
    headers = [(index, line[1:].split()) for index, line in enumerate(lines) if line.startswith('*') and line != '*']
    if any(tokens and tokens[0].lower() == 'xyzfile' for _, tokens in headers):
        raise ValueError('ORCA xyzfile geometry is an external dependency; export the intended geometry to XYZ before converting')
    if len(headers) != 1 or not headers[0][1] or headers[0][1][0].lower() != 'xyz':
        raise ValueError('Exactly one explicit ORCA * xyz Cartesian geometry is required; internal, external and multiple geometries are unsupported')
    index, _ = headers[0]
    if '*' not in lines[index + 1:]:
        raise ValueError('ORCA Cartesian geometry is missing its closing * marker')
    sections = orca_xyz_sections(text)
    if len(sections) != 1:
        raise ValueError('ORCA charge and multiplicity must be integers in one * xyz section')
    (charge, multiplicity), _ = sections[0]
    end = lines.index('*', index + 1)
    geometry = [line for line in lines[index + 1:end] if line]
    if multiplicity <= 0:
        raise ValueError('ORCA multiplicity must be positive')
    source_units = orca_coordinate_units(text)
    if source_units == 'unknown':
        raise ValueError('ORCA coordinate units are unsupported or conflicting; provide one unambiguous Angstrom or Bohr geometry')
    atoms = _cartesian_atoms(geometry, source='ORCA')
    if source_units == 'bohr':
        from ase.units import Bohr

        atoms.positions *= Bohr
    return atoms, charge, multiplicity, source_units
```


<a id="s250"></a>

### S250 · `_read_xyz_structure`

`cloudra/tools/core/molecule.py:165–190`

```python
def _read_xyz_structure(text):
    import ase.io
    from ase.io.extxyz import XYZError

    lines = text.lstrip('\r\n').splitlines()
    if not lines:
        raise ValueError("XYZ input is empty; provide XYZ, MOL/SDF, or a single Gaussian Cartesian input")
    try:
        count = int(lines[0].strip())
    except ValueError:
        return _cartesian_atoms([line for line in lines if line.strip()], source='XYZ format')
    if count <= 0:
        raise ValueError("XYZ requires a positive atom count")
    atoms = None
    try:
        # ASE owns EXTXYZ property ordering and the existing final-frame rule.
        for atoms in ase.io.iread(StringIO('\n'.join(lines)), format='extxyz'):
            if len(atoms) == 0 or any(number == 0 for number in atoms.numbers):
                raise ValueError("XYZ requires real elements and a positive atom count")
            if not all(math.isfinite(value) for point in atoms.positions for value in point):
                raise ValueError("XYZ coordinates must be finite")
    except (ValueError, IndexError, KeyError, XYZError) as exc:
        raise ValueError(f"Invalid XYZ format: {exc}; check the atom count, comment line, and Cartesian rows") from exc
    if atoms is None:
        raise ValueError("XYZ input has no coordinate frame")
    return atoms
```


<a id="s251"></a>

### S251 · `_looks_like_gaussian`

`cloudra/tools/core/molecule.py:193–215`

```python
def _looks_like_gaussian(text):
    sections = [[]]
    for line in text.splitlines():
        if line.strip():
            sections[-1].append(line.strip())
        elif sections[-1]:
            sections.append([])
    route = [line for line in sections[0] if not line.startswith('%')]
    if not route or not route[0].startswith('#'):
        return False
    head = route[0][1:].strip().lower().split()
    if not head:
        return False
    key = head[0].partition('=')[0].partition('(')[0]
    if len(route) != len(sections[0]) or key in {'p', 'n', 't', 'geom', 'units', 'opt', 'freq', 'irc'}:
        return True
    if len(sections) < 3 or not sections[2] or len(sections[2][0].split()) != 2:
        return False
    try:
        tuple(map(int, sections[2][0].split()))
    except ValueError:
        return False
    return True
```


<a id="s252"></a>

### S252 · `read_molecule`

`cloudra/tools/core/molecule.py:218–298`

```python
def read_molecule(input_path=None, input_text=None, input_format="auto", charge=None):
    """Read a declared graph or coordinate-only Mol; never infer bonds while converting."""
    from rdkit import Chem

    if input_path:
        try:
            text = Path(input_path).read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Input structure file does not exist: {input_path}; check the resolved path or create the structure first") from exc
    elif input_text:
        text = input_text
    else:
        raise ValueError("Must provide input_path or input_text")
    text = text.lstrip('\ufeff')
    fmt = input_format
    native_charge = native_multiplicity = native_units = None
    if fmt == "auto":
        if input_path:
            fmt = Path(input_path).suffix.lower().lstrip(".")
            if fmt == 'inp':
                fmt = 'orca'
            elif fmt not in {"mol", "sdf", "xyz"}:
                from ase.io.formats import extension2format

                native_format = extension2format.get(fmt)
                fmt = native_format.name if native_format else "auto"
        if fmt in {'auto', 'xyz', 'gaussian-in'}:
            lines = text.splitlines()
            counts = lines[3].split() if len(lines) > 3 else []
            if any(token in {"V2000", "V3000"} for token in counts):
                fmt = "sdf" if any(line.strip() == "$$$$" for line in lines) else "mol"
            elif _looks_like_gaussian(text):
                fmt = 'gaussian-in'
            elif any(line.strip().startswith('*') and line.strip()[1:].split()[:1] in (['xyz'], ['xyzfile'])
                     for line in text.lower().splitlines()):
                fmt = 'orca'
            elif fmt == 'auto':
                fmt = "xyz"
    elif fmt == 'xyz' and _looks_like_gaussian(text):
        raise ValueError("Gaussian content does not match input_format='xyz'; use input_format='auto' for a single Cartesian Gaussian input")
    if fmt in {'gaussian-in', 'orca', 'orca-in', 'inp'}:
        reader = _read_gaussian_structure if fmt == 'gaussian-in' else _read_orca_structure
        atoms, native_charge, native_multiplicity, native_units = reader(text)
        if charge is not None and charge != native_charge:
            raise ValueError(f"{'Gaussian' if fmt == 'gaussian-in' else 'ORCA'} charge mismatch: declared charge {charge} differs from native charge {native_charge}")
        mol = from_ase(atoms)
    elif fmt == "mol":
        mol = Chem.MolFromMolBlock(text, removeHs=False)
    elif fmt == "sdf":
        mol = next(Chem.ForwardSDMolSupplier(BytesIO(text.encode("utf-8")), removeHs=False), None)
    else:
        import ase.io

        atoms = _read_xyz_structure(text) if fmt == 'xyz' else ase.io.read(StringIO(text), format=fmt or None)
        mol = from_ase(atoms)
        if fmt == 'xyz' and 'cloudra_total_charge' in atoms.info:
            if atoms.info.get('cloudra_coordinate_units', 'angstrom') != 'angstrom':
                raise ValueError('XYZ molecular-state metadata requires Angstrom coordinates')
            native_charge = int(str(atoms.info['cloudra_total_charge']))
            if charge is not None and charge != native_charge:
                raise ValueError(f'XYZ charge mismatch: declared charge {charge} differs from stored charge {native_charge}')
            if 'cloudra_multiplicity' in atoms.info:
                native_multiplicity = int(str(atoms.info['cloudra_multiplicity']))
                if native_multiplicity <= 0:
                    raise ValueError('XYZ stored multiplicity must be positive')
            native_units = atoms.info.get('cloudra_source_coordinate_units', 'angstrom')
    if fmt not in {'mol', 'sdf'}:
        mol.SetIntProp("cloudra_total_charge", native_charge if native_charge is not None else charge if charge is not None else 0)
        mol.SetProp("cloudra_graph_status", "unresolved")
        if native_multiplicity is not None:
            mol.SetIntProp('cloudra_multiplicity', native_multiplicity)
            mol.SetProp('cloudra_coordinate_units', 'angstrom')
            mol.SetProp('cloudra_source_coordinate_units', native_units)
    if mol is None:
        raise ValueError(f"Could not parse {fmt.upper()} molecule")
    if fmt in {"mol", "sdf"} and charge is not None and charge != total_charge(mol):
        raise ValueError(
            f"Declared charge {charge} differs from the molecule's stored total or formal charge {total_charge(mol)}; "
            "provide the molecular graph for the intended charge state."
        )
    return mol
```


<a id="s253"></a>

### S253 · `total_charge`

`cloudra/tools/core/molecule.py:301–307`

```python
def total_charge(mol) -> int:
    """Return declared total charge for coordinate-only input, otherwise the graph charge."""
    from rdkit import Chem

    if mol.HasProp("cloudra_total_charge"):
        return mol.GetIntProp("cloudra_total_charge")
    return Chem.GetFormalCharge(mol)
```


<a id="s254"></a>

### S254 · `from_ase`

`cloudra/tools/core/molecule.py:310–323`

```python
def from_ase(atoms):
    """Copy atoms and coordinates from ASE without guessing bonds or formal charges."""
    from rdkit import Chem

    mol = Chem.RWMol()
    conf = Chem.Conformer(len(atoms))
    for index, (symbol, position) in enumerate(zip(
        atoms.get_chemical_symbols(), atoms.get_positions(), strict=True,
    )):
        mol.AddAtom(Chem.Atom(symbol))
        conf.SetAtomPosition(index, tuple(map(float, position)))
    out = mol.GetMol()
    out.AddConformer(conf)
    return out
```


<a id="s255"></a>

### S255 · `to_ase`

`cloudra/tools/core/molecule.py:326–333`

```python
def to_ase(mol):
    """Return an independent ASE geometry view; chemistry stays in the molecule."""
    from ase import Atoms

    return Atoms(
        symbols=[atom.GetSymbol() for atom in mol.GetAtoms()],
        positions=mol.GetConformer().GetPositions(),
    )
```


<a id="s256"></a>

### S256 · `to_xyz`

`cloudra/tools/core/molecule.py:336–342`

```python
def to_xyz(mol, comment: str = "") -> str:
    """Render the default conformer in atom order with eight decimal places."""
    positions = mol.GetConformer().GetPositions()
    lines = [str(mol.GetNumAtoms()), comment]
    for atom, position in zip(mol.GetAtoms(), positions, strict=True):
        lines.append(f"{atom.GetSymbol():<4} {position[0]:>14.8f} {position[1]:>14.8f} {position[2]:>14.8f}")
    return "\n".join(lines) + "\n"
```


## `cloudra/tools/core/native_input_sections.py`

文件 SHA-256：`aabbff9c7f8f41fb240084ecf67f18ca1503d062e8ebc6a66c259f6f180b1022`


<a id="s257"></a>

### S257 · `GaussianSections`

`cloudra/tools/core/native_input_sections.py:7–12`

```python
@dataclass(frozen=True)
class GaussianSections:
    route: list[str]
    charge: tuple[int, int] | None
    geometry: list[str]
    trailing: list[str]
```


<a id="s258"></a>

### S258 · `gaussian_option`

`cloudra/tools/core/native_input_sections.py:15–19`

```python
def gaussian_option(token: str) -> tuple[str, set[str]]:
    key, separator, value = token.partition('=')
    if not separator and '(' in token:
        key, _, value = token.partition('(')
    return key, {option.strip() for option in value.strip('()').split(',')}
```


<a id="s259"></a>

### S259 · `gaussian_coordinate_units`

`cloudra/tools/core/native_input_sections.py:22–36`

```python
def gaussian_coordinate_units(route: list[str]) -> Literal['angstrom', 'bohr', 'unknown']:
    """Read declared coordinate units without choosing unknown/conflicting units."""
    unit_names = {'angstrom': 'angstrom', 'angstroms': 'angstrom', 'ang': 'angstrom',
                  'bohr': 'bohr', 'au': 'bohr', 'a.u.': 'bohr'}
    declared = set()
    for key, options in map(gaussian_option, route):
        if key != 'units':
            continue
        unit = unit_names.get(next(iter(options))) if len(options) == 1 else None
        if unit is None:
            return 'unknown'
        declared.add(unit)
    if len(declared) > 1:
        return 'unknown'
    return declared.pop() if declared else 'angstrom'
```


<a id="s260"></a>

### S260 · `gaussian_sections`

`cloudra/tools/core/native_input_sections.py:39–101`

```python
def gaussian_sections(text: str) -> list[GaussianSections]:
    """Read route/title/molecule boundaries without requiring explicit geometry.

    Inspection also reads checkpoint-only and Link1 jobs. Only structure callers
    impose the narrower requirement of one explicit Cartesian molecule.
    """
    from cloudra.tools.core.calculation_intent import native_tokens

    segments = [[]]
    for line in text.lstrip('\ufeff').splitlines():
        line = line.strip()
        if line.lower() == '--link1--':
            segments.append([])
        else:
            segments[-1].append(line)
    sections = []
    for lines in segments:
        index = next((i for i, line in enumerate(lines) if line.startswith('#') and not line.startswith('#!')), None)
        if index is None:
            continue
        route_lines = []
        while index < len(lines) and lines[index]:
            route_lines.append(lines[index])
            index += 1
        route_text = ' '.join(route_lines)[1:]
        head = route_text.split(None, 1)
        if head and head[0].lower() in {'p', 'n', 't'}:
            route_text = head[1] if len(head) > 1 else ''
        try:
            route = native_tokens(route_text)
        except ValueError:
            # A malformed calculation option cannot hide the molecule section.
            # Intent inspection still tokenizes this route strictly; these words
            # only let structure readers identify explicit geometry controls.
            route = route_text.lower().split()
        while index < len(lines) and not lines[index]:
            index += 1
        # Geom=AllCheck omits the title and molecule specification altogether.
        if any(key == 'geom' and options & {'allcheck', 'allcheckpoint'}
               for key, options in map(gaussian_option, route)):
            sections.append(GaussianSections(route, None, [], lines[index:]))
            continue
        while index < len(lines) and lines[index]:
            index += 1  # The entire title section, even titles such as "7 9".
        while index < len(lines) and not lines[index]:
            index += 1
        charge = None
        if index < len(lines):
            tokens = lines[index].split()
            if len(tokens) == 2:
                try:
                    charge = int(tokens[0]), int(tokens[1])
                except ValueError:
                    pass
        if charge is None:
            sections.append(GaussianSections(route, None, [], []))
            continue
        index += 1
        end = index
        while end < len(lines) and lines[end]:
            end += 1
        sections.append(GaussianSections(route, charge, lines[index:end], lines[end:]))
    return sections
```


<a id="s261"></a>

### S261 · `orca_xyz_sections`

`cloudra/tools/core/native_input_sections.py:104–125`

```python
def orca_xyz_sections(text: str) -> list[tuple[tuple[int, int], list[str]]]:
    """Read ORCA's equivalent *xyz and * xyz Cartesian molecule sections."""
    from cloudra.tools.core.calculation_intent import _orca_code

    lines = _orca_code(text.lstrip('\ufeff')).splitlines()
    sections = []
    for index, line in enumerate(lines):
        line = line.strip()
        if not line.startswith('*'):
            continue
        tokens = line[1:].split()
        if len(tokens) != 3 or tokens[0].lower() != 'xyz':
            continue
        try:
            charge = int(tokens[1]), int(tokens[2])
        except ValueError:
            continue
        end = index + 1
        while end < len(lines) and lines[end].strip() not in {'', '*'}:
            end += 1
        sections.append((charge, lines[index + 1:end]))
    return sections
```


<a id="s262"></a>

### S262 · `orca_coordinate_units`

`cloudra/tools/core/native_input_sections.py:128–159`

```python
def orca_coordinate_units(text: str) -> Literal['angstrom', 'bohr', 'unknown']:
    """Read inline Cartesian units from simple input or the native %coords block."""
    from cloudra.tools.core.calculation_intent import _orca_code

    unit_names = {'angs': 'angstrom', 'angstrom': 'angstrom', 'angstroms': 'angstrom',
                  'bohrs': 'bohr', 'bohr': 'bohr', 'au': 'bohr'}
    declared = set()
    in_coords = False
    for line in _orca_code(text).splitlines():
        tokens = line.lower().split()
        if not tokens:
            continue
        if tokens[0] == '!':
            declared.update(unit_names[token] for token in tokens[1:] if token in unit_names)
        elif tokens[0].startswith('!'):
            declared.update(unit_names[token] for token in [tokens[0][1:], *tokens[1:]] if token in unit_names)
        if tokens[0] == '%coords':
            in_coords = True
            tokens = tokens[1:]
        if in_coords:
            for index, token in enumerate(tokens):
                if token != 'units':
                    continue
                unit = unit_names.get(tokens[index + 1]) if index + 1 < len(tokens) else None
                if unit is None:
                    return 'unknown'
                declared.add(unit)
            if 'end' in tokens:
                in_coords = False
    if len(declared) > 1:
        return 'unknown'
    return declared.pop() if declared else 'angstrom'
```


## `cloudra/tools/core/orca_frames.py`

文件 SHA-256：`0d72d9459a583228f8f7dc54c7afa6874b80b7524e4f3af3ff2197479ca236d5`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/tools/core/orca_frames.py:48–48`

```python
_ORCA_KEYWORDS_RE = re.compile(r"^\s*(?:\|\s*\d+>\s*)?!\s*(?P<kw>.+)$", re.M | re.I)
```


`cloudra/tools/core/orca_frames.py:101–101`

```python
_FLOAT = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DdEe][+-]?\d+)?)"
```


`cloudra/tools/core/orca_frames.py:103–112`

```python
_ORCA_THERMO_PATTERNS = {
    "zero_point_correction_hartree": rf"Zero point energy\s+\.\.\.\s+{_FLOAT}\s+Eh",
    "thermal_energy_correction_hartree": rf"^\s*Total correction\s+{_FLOAT}\s+Eh",
    "total_thermal_energy_hartree": rf"Total thermal energy\s+{_FLOAT}\s+Eh",
    "total_enthalpy_hartree": rf"Total [Ee]nthalpy\s+\.*\s*\.\.\.\s+{_FLOAT}\s+Eh",
    "total_gibbs_free_energy_hartree": rf"Final Gibbs free (?:enthalpy|energy)\s+\.\.\.\s+{_FLOAT}\s+Eh",
    "electronic_energy_hartree": rf"^\s*Electronic energy\s+\.\.\.\s+{_FLOAT}\s+Eh",
    "temperature_k": rf"^\s*Temperature\s+\.\.\.\s+{_FLOAT}\s+K",
    "pressure_atm": rf"^\s*Pressure\s+\.\.\.\s+{_FLOAT}\s+atm",
}
```


`cloudra/tools/core/orca_frames.py:123–123`

```python
NORMAL_TERMINATION_MARKER = "ORCA TERMINATED NORMALLY"
```


`cloudra/tools/core/orca_frames.py:145–145`

```python
_OPT_NOT_CONVERGED_MARKER = "The optimization did not converge"
```


`cloudra/tools/core/orca_frames.py:146–146`

```python
_OPT_CONVERGED_MARKER = "THE OPTIMIZATION HAS CONVERGED"
```


`cloudra/tools/core/orca_frames.py:162–164`

```python
_FINAL_ENERGY_RE = re.compile(
    rf"FINAL SINGLE POINT ENERGY(?:\s*\([^)]*\))?\s+{_FLOAT}"
)
```


`cloudra/tools/core/orca_frames.py:168–168`

```python
_CURRENT_ENERGY_RE = re.compile(rf"Current Energy\s+\.+\s*{_FLOAT}\s+Eh")
```


`cloudra/tools/core/orca_frames.py:238–238`

```python
_VIBFREQ_LINE_RE = re.compile(rf"^\s*\d+:\s*{_FLOAT}\s+cm\*\*-1", re.M)
```


`cloudra/tools/core/orca_frames.py:258–258`

```python
_ORCA_MODE_HEADER_RE = re.compile(r"^\s*\d+(?:\s+\d+)*\s*$")
```


`cloudra/tools/core/orca_frames.py:433–433`

```python
_OPT_CYCLE_MARKER = "GEOMETRY OPTIMIZATION CYCLE"
```


`cloudra/tools/core/orca_frames.py:631–633`

```python
_IRCA_ITER_RE = re.compile(
    r"^\s*(\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s*$"
)
```


`cloudra/tools/core/orca_frames.py:635–637`

```python
_IRCA_SUMMARY_RE = re.compile(
    r"^\s*(\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)(?:\s*<=\s*TS)?\s*$"
)
```


`cloudra/tools/core/orca_frames.py:638–638`

```python
_IRCA_BLOCK_RE = re.compile(r"\*\s*(FORWARD|BACKWARD)\s+IRC\s*\*")
```


`cloudra/tools/core/orca_frames.py:639–639`

```python
_IRCA_CONVERGED_RE = re.compile(r"THE IRC HAS CONVERGED")
```


`cloudra/tools/core/orca_frames.py:831–831`

```python
_ORCA_NAME_RE = re.compile(r"^\s*NAME\s*=\s*(?P<path>\S+)\s*$", re.M)
```


<a id="s263"></a>

### S263 · `_collect_keyword_lines`

`cloudra/tools/core/orca_frames.py:51–53`

```python
def _collect_keyword_lines(text: str) -> str:
    """收集输入回显中的 `!` 关键字行（ORCA 在输出开头回显输入文件）。"""
    return " ".join(m.group("kw") for m in _ORCA_KEYWORDS_RE.finditer(text)).lower()
```


<a id="s264"></a>

### S264 · `detect_job_types`

`cloudra/tools/core/orca_frames.py:56–64`

```python
def detect_job_types(log_path: str) -> set[str]:
    """识别 ORCA 日志的任务类型，返回 {"opt","ts","freq","scan","irc","neb","sp"} 的子集。

    ``neb`` 由输入回显的 ``!`` 关键字行识别（``! NEB`` / ``! NEB-TS``）。识别它是为了
    **不让 NEB 日志掉进 ``sp``**：``NEB-TS`` 后续的 TS 优化会让本函数同时给出 ``ts``
    （那时逐帧几何由优化段解析），而只跑路径搜索的 ``! NEB`` 没有优化循环，若不识别就会
    被当成单点——把一整条路径说成一个结构比不报更糟。
    """
    return detect_job_types_from_text(_read_text(log_path))
```


<a id="s265"></a>

### S265 · `detect_job_types_from_text`

`cloudra/tools/core/orca_frames.py:67–94`

```python
def detect_job_types_from_text(text: str) -> set[str]:
    """detect_job_types 的文本变体：调用方已读过日志时避免重复 IO。"""
    keywords = _collect_keyword_lines(text)
    jobs: set[str] = set()

    if re.search(r"\birc\b", keywords) or "IRC ITERATION" in text or "IRC PATH SUMMARY" in text:
        jobs.add("irc")
    if (
        re.search(r"\bscan\b", keywords)
        or "Parameter Scan Calculation" in text
        or "Relaxed Surface Scan" in text
        or "RELAXED SURFACE SCAN STEP" in text
    ):
        jobs.add("scan")
    if re.search(r"\bneb(-ts)?\b", keywords):
        jobs.add("neb")
    if re.search(r"\bopt(ts)?\b", keywords) or "GEOMETRY OPTIMIZATION CYCLE" in text:
        jobs.add("opt")
    if re.search(r"\boptts\b", keywords) or "SADDLE POINT SEARCH" in text.upper():
        jobs.add("ts")
    if (
        re.search(r"\b(freq|numfreq|anfreq)\b", keywords)
        or "VIBRATIONAL FREQUENCIES" in text
    ):
        jobs.add("freq")
    if not jobs & {"irc", "scan", "opt", "ts", "neb"}:
        jobs.add("sp")
    return jobs
```


<a id="s266"></a>

### S266 · `normal_termination`

`cloudra/tools/core/orca_frames.py:126–131`

```python
def normal_termination(text: str) -> bool:
    """原生正常终止且没有原生错误终止；历史正常标记不能覆盖后续失败。"""
    return (
        text.rfind(NORMAL_TERMINATION_MARKER) >= last_job_start(text)
        and "ORCA finished by error termination" not in text
    )
```


<a id="s267"></a>

### S267 · `last_job_start`

`cloudra/tools/core/orca_frames.py:134–140`

```python
def last_job_start(text: str) -> int:
    """Native job headers, excluding input-echo lines containing $new_job."""
    positions = [match.start() for match in re.finditer(
        r"^[ \t]*(?:[-=*]+[ \t]*)?(?:ORCA[ \t]+)?JOB NUMBER[ \t]+\d+\b|"
        r"^[ \t*]*O[ \t]{2,}R[ \t]{2,}C[ \t]{2,}A[ \t*]*$|"
        r"^[ \t]*ORCA VERSION\b", text, re.M)]
    return positions[-1] if positions else 0
```


<a id="s268"></a>

### S268 · `opt_converged`

`cloudra/tools/core/orca_frames.py:149–159`

```python
def opt_converged(text: str) -> bool | None:
    """几何优化/TS 优化的收敛状态（文本权威，不依赖 cclib）。

    True=收敛，False=达到最大步数未收敛，None=非优化任务或日志判不出
    （两个标记都不出现，如中途被 kill 的优化日志）。
    """
    if _OPT_NOT_CONVERGED_MARKER in text:
        return False
    if _OPT_CONVERGED_MARKER in text:
        return True
    return None
```


<a id="s269"></a>

### S269 · `final_energy_hartree`

`cloudra/tools/core/orca_frames.py:171–189`

```python
def final_energy_hartree(text: str) -> float | None:
    """取最终能量（Eh；含外部 MLIP 变体），按文本位置取最后出现的能量行。

    外部 MLIP（ExtOpt/ProgExt）日志没有 SCF 能量段，唯一能量行是
    ``FINAL SINGLE POINT ENERGY (From external program)``。未收敛的优化
    （max-cycles）只打印一次 FINAL SP（起始几何），逐周期能量以
    ``Current Energy .... <E> Eh`` 给出——此时最后的 Current Energy 才是
    最佳几何能量（GH #22）；收敛的优化会在末几何再打印一次 FINAL SP，
    位置在最后，按位置取最后者天然正确，单点/无 Current Energy 的日志
    行为不变。
    """
    best_pos = -1
    energy: float | None = None
    for pattern in (_FINAL_ENERGY_RE, _CURRENT_ENERGY_RE):
        for match in pattern.finditer(text):
            if match.start() > best_pos:
                best_pos = match.start()
                energy = float(match.group(1).replace("D", "E").replace("d", "e"))
    return energy
```


<a id="s270"></a>

### S270 · `extract_thermochemistry_from_text`

`cloudra/tools/core/orca_frames.py:197–228`

```python
def extract_thermochemistry_from_text(text: str) -> dict[str, float]:
    """Keep totals, corrections and conditions in one native thermochemistry block.

    ORCA's ``Thermal Enthalpy correction`` is only RT. The shared enthalpy
    correction means H − E(el), including ZPE and thermal internal energy.
    """
    starts = list(re.finditer(r"^\s*THERMOCHEMISTRY AT\b", text, re.M))
    target = text[starts[-1].start():] if starts else text
    end = re.search(
        r"ORCA TERMINATED NORMALLY|ORCA finished by error termination|"
        r"FINAL SINGLE POINT ENERGY|^\s*\$new_job\b", target, re.M,
    )
    if end:
        target = target[:end.start()]
    values = {
        field: float(match.group(1).replace("D", "E").replace("d", "e"))
        for field, pattern in _ORCA_THERMO_PATTERNS.items()
        if (match := re.search(pattern, target, re.M)) is not None
    }
    zpe = values.get("zero_point_correction_hartree")
    e_el = values.get("electronic_energy_hartree")
    if e_el is not None:
        if zpe is not None:
            values["total_zero_point_energy_hartree"] = e_el + zpe
        for total, correction in (
            ("total_thermal_energy_hartree", "thermal_energy_correction_hartree"),
            ("total_enthalpy_hartree", "thermal_enthalpy_correction_hartree"),
            ("total_gibbs_free_energy_hartree", "thermal_gibbs_correction_hartree"),
        ):
            if total in values and correction not in values:
                values[correction] = values[total] - e_el
    return values
```


<a id="s271"></a>

### S271 · `vibfreqs_from_text`

`cloudra/tools/core/orca_frames.py:241–253`

```python
def vibfreqs_from_text(text: str) -> list[float]:
    """解析最后一个 VIBRATIONAL FREQUENCIES 块的频率（cm⁻¹，负值=虚频）。

    外部 MLIP（ExtOpt NumFreq）日志无 SCF 块，cclib 常整体解析失败，
    频率只能从文本回退（GH #16）。只取最后一个频率块（Opt+NumFreq 的
    日志可能逐周期多次打印）；与 cclib 的差异是保留打头的平动/转动
    零频模式（cclib 会裁掉），调用方按符号拆分实频/虚频即可。无频率块
    时返回空列表——调用方须保持 None 语义，不得当成零虚频。
    """
    idx = text.rfind("VIBRATIONAL FREQUENCIES")
    if idx < 0:
        return []
    return [float(m.group(1)) for m in _VIBFREQ_LINE_RE.finditer(text, idx)]
```


<a id="s272"></a>

### S272 · `vibdisps_from_text`

`cloudra/tools/core/orca_frames.py:261–325`

```python
def vibdisps_from_text(text: str, n_freqs: int, n_atoms: int):
    """解析 ORCA NORMAL MODES 位移块，返回形状 (n_modes, n_atoms, 3) 的数组或 None。

    ORCA 版式：每个子块首行是模式号表头（每行最多 6 个模式），随后是 3N 行，
    每行 = 一个笛卡尔分量（行首是该分量序号 0..3N-1），列 = 该子块内各模式的
    位移；分量 c 属于原子 c//3、方向 c%3。把第 m 列按 (atom, xyz) 填回即得该
    模式的位移——与 cclib 的读法一致（cclib 亦按"每原子读 3 行"读入），只是这里
    直接从文本取、不依赖 cclib（cclib 对 ORCA 6.1 日志整体崩溃）。

    只取最后一个 "VIBRATIONAL FREQUENCIES" 块之后的 NORMAL MODES 段（Opt+Freq
    日志可能逐周期重复打印）。频率数须与 3*原子数一致，且模式块覆盖全部
    n_freqs 个模式，否则返回 None（调用方保持"缺位移"语义）。
    """
    import numpy as np

    if n_freqs <= 0 or n_atoms <= 0 or n_freqs != 3 * n_atoms:
        return None
    freq_idx = text.rfind("VIBRATIONAL FREQUENCIES")
    start = freq_idx if freq_idx >= 0 else 0
    idx = text.find("NORMAL MODES", start)
    if idx < 0:
        return None

    lines = text[idx:].splitlines()
    disps = np.zeros((n_freqs, n_atoms, 3), dtype=float)
    parsed_any = False
    i = 0
    total = len(lines)
    while i < total:
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if _ORCA_MODE_HEADER_RE.match(stripped):
            mode_idx = [int(tok) for tok in stripped.split()]
            i += 1
            rows: list[tuple[int, list[float]]] = []
            while i < total and len(rows) < 3 * n_atoms:
                row = lines[i].strip()
                if not row:
                    break
                parts = row.split()
                if not parts[0].lstrip("-").isdigit() or len(parts) < 1 + len(mode_idx):
                    break
                try:
                    values = [float(tok) for tok in parts[1:1 + len(mode_idx)]]
                except ValueError:
                    break
                rows.append((int(parts[0]), values))
                i += 1
            if len(rows) != 3 * n_atoms:
                return None
            for cartesian, values in rows:
                atom, comp = divmod(cartesian, 3)
                if atom >= n_atoms:
                    return None
                for k, mode in enumerate(mode_idx):
                    if 0 <= mode < n_freqs:
                        disps[mode, atom, comp] = values[k]
            parsed_any = True
            continue
        if parsed_any:
            break
        i += 1
    return disps if parsed_any else None
```


<a id="s273"></a>

### S273 · `_xyz_block_at`

`cloudra/tools/core/orca_frames.py:346–364`

```python
def _xyz_block_at(text: str, idx: int) -> str:
    """从 idx 处的 CARTESIAN COORDINATES (ANGSTROEM) 标题解析一个坐标块，
    返回标准 xyz 文本；块为空返回空串。"""
    rows: list[str] = []
    for line in text[idx:].splitlines()[2:]:  # 跳过标题行与分隔线
        parts = line.split()
        if len(parts) >= 4:
            try:
                float(parts[1])
                float(parts[2])
                float(parts[3])
            except ValueError:
                break
            rows.append(f"{parts[0]} {parts[1]} {parts[2]} {parts[3]}")
        elif rows:
            break
    if not rows:
        return ""
    return f"{len(rows)}\n\n" + "\n".join(rows) + "\n"
```


<a id="s274"></a>

### S274 · `input_xyz_from_text`

`cloudra/tools/core/orca_frames.py:367–390`

```python
def input_xyz_from_text(text: str) -> str:
    """Read the literal inline Cartesian geometry echoed by ORCA, never infer it."""
    rows = []
    in_xyz = False
    for line in text.splitlines():
        prefix, separator, echoed = line.partition('>')
        if not (separator and prefix.strip().startswith('|')
                and prefix.strip()[1:].strip().isdigit()):
            continue
        parts = echoed.split()
        if not in_xyz:
            if len(parts) == 4 and parts[:2] == ['*', 'xyz']:
                in_xyz = True
            continue
        if parts == ['*']:
            return f'{len(rows)}\n\n' + '\n'.join(rows) + '\n' if rows else ''
        if len(parts) != 4:
            return ''
        try:
            coordinates = [float(value) for value in parts[1:]]
        except ValueError:
            return ''
        rows.append(parts[0] + ' ' + ' '.join(str(value) for value in coordinates))
    return ''
```


<a id="s275"></a>

### S275 · `final_xyz_from_text`

`cloudra/tools/core/orca_frames.py:393–407`

```python
def final_xyz_from_text(text: str) -> str:
    """最后一个 CARTESIAN COORDINATES (ANGSTROEM) 块 → 标准 xyz 文本。

    ORCA 每次几何步/作业结束都打印该块，取最后一个即末帧几何；cclib 对
    ORCA 6.1 日志整体解析失败时的文本回退（与 vibfreqs_from_text 同一
    纪律——评分链路不能因 cclib 崩溃而不可判定）。静态计算无该块时
    读取日志原样回显的输入坐标；优化和路径计算不能用输入冒充末帧。"""
    idx = text.rfind("CARTESIAN COORDINATES (ANGSTROEM)")
    if idx >= 0:
        return _xyz_block_at(text, idx)
    # Static jobs evaluate precisely their echoed input geometry. An Opt/IRC/scan
    # input is only its starting point and must never masquerade as a final frame.
    if not detect_job_types_from_text(text) & {'opt', 'ts', 'scan', 'irc', 'neb'}:
        return input_xyz_from_text(text)
    return ''
```


<a id="s276"></a>

### S276 · `final_xyz_with_text_fallback`

`cloudra/tools/core/orca_frames.py:410–424`

```python
def final_xyz_with_text_fallback(log_path: str) -> str:
    """末帧几何（标准 xyz 文本）：cclib 帧解析优先，失败或无坐标帧时回退
    文本权威 CARTESIAN COORDINATES (ANGSTROEM) 块。无几何返回空串。"""
    try:
        frames = extract_frames(log_path)
    except Exception:
        frames = []
    for frame in reversed(frames):
        if frame.xyz.strip():
            return frame.xyz
    try:
        text = _read_text(log_path)
    except OSError:
        return ""
    return final_xyz_from_text(text)
```


<a id="s277"></a>

### S277 · `_extract_opt_frames_native`

`cloudra/tools/core/orca_frames.py:436–476`

```python
def _extract_opt_frames_native(log_text: str) -> list[FrameRecord]:
    """文本权威的优化逐帧提取：cclib 对 ORCA 6.1 日志崩溃（GH #44）时的回退。

    逐周期配对「段内第一个 CARTESIAN COORDINATES 块 + Current Energy 行」；
    收敛后 ORCA 在末段再打印一次最终几何 + FINAL SINGLE POINT ENERGY——与最后
    周期的几何逐字符去重后，作为末帧挂上收敛标记（opt_converged 文本权威）
    与频率（vibfreqs_from_text 文本权威）。未收敛（max-cycles）时没有这份
    尾块，末帧能量即最后一周的 Current Energy（GH #22 口径）。
    """
    segments = log_text.split(_OPT_CYCLE_MARKER)[1:]
    frames: list[FrameRecord] = []
    for segment in segments:
        idx = segment.find("CARTESIAN COORDINATES (ANGSTROEM)")
        if idx < 0:
            continue
        xyz = _xyz_block_at(segment, idx)
        if not xyz:
            continue
        energy: float | None = None
        m = _CURRENT_ENERGY_RE.search(segment)
        if m:
            energy = float(m.group(1).replace("D", "E").replace("d", "e"))
        frames.append(FrameRecord(frame=len(frames), electronic_energy_hartree=energy, xyz=xyz))
    if not frames:
        return []
    converged = opt_converged(log_text)
    freqs = vibfreqs_from_text(log_text)
    final_xyz = final_xyz_from_text(log_text)
    if final_xyz and final_xyz != frames[-1].xyz:
        # 收敛（或后续 freq 段）又打印了一份最终几何：追加为末帧
        frames.append(FrameRecord(
            frame=len(frames),
            electronic_energy_hartree=final_energy_hartree(log_text),
            frequencies_cm=freqs,
            xyz=final_xyz,
            converged=converged,
        ))
    else:
        frames[-1].converged = converged
        frames[-1].frequencies_cm = freqs
    return frames
```


<a id="s278"></a>

### S278 · `_extract_sp_frames_native`

`cloudra/tools/core/orca_frames.py:479–489`

```python
def _extract_sp_frames_native(log_text: str) -> list[FrameRecord]:
    """单点的文本权威回退（cclib 崩溃时）：末帧几何 + FINAL SP + 频率块。"""
    xyz = final_xyz_from_text(log_text)
    if not xyz:
        return []
    return [FrameRecord(
        frame=0,
        electronic_energy_hartree=final_energy_hartree(log_text),
        frequencies_cm=vibfreqs_from_text(log_text),
        xyz=xyz,
    )]
```


<a id="s279"></a>

### S279 · `_extract_opt_frames`

`cloudra/tools/core/orca_frames.py:492–519`

```python
def _extract_opt_frames(log_text: str) -> list[FrameRecord]:
    try:
        data = _ccread_from_text(log_text)
    except ValueError:
        # cclib 对 ORCA 6.1 日志在 SCF 收敛段裸抛 IndexError（GH #44）：
        # 帧提取回退文本权威通道，不让整条格式转换链不可判定。
        return _extract_opt_frames_native(log_text)
    energies = getattr(data, "scfenergies", None)
    atomcoords = getattr(data, "atomcoords", None)
    atomnos = getattr(data, "atomnos", None)
    if energies is None or atomcoords is None or atomnos is None:
        return []
    energies_ev = _as_float_list(energies)
    n = min(len(energies_ev), len(atomcoords))
    converged = opt_converged(log_text)
    freqs = vibfreqs_from_text(log_text) or _get_vibfreqs(data)

    frames = []
    for i in range(n):
        is_last = i == n - 1
        frames.append(FrameRecord(
            frame=i,
            electronic_energy_hartree=energy_ev_to_hartree(energies_ev[i]),
            frequencies_cm=freqs if (is_last and freqs) else [],
            xyz=_coords_to_xyz(atomnos, atomcoords[i], comment=f"opt step={i}"),
            converged=converged if is_last else None,
        ))
    return frames
```


<a id="s280"></a>

### S280 · `_extract_sp_frames`

`cloudra/tools/core/orca_frames.py:571–589`

```python
def _extract_sp_frames(log_text: str) -> list[FrameRecord]:
    try:
        data = _ccread_from_text(log_text)
    except ValueError:
        return _extract_sp_frames_native(log_text)
    energies = getattr(data, "scfenergies", None)
    atomcoords = getattr(data, "atomcoords", None)
    atomnos = getattr(data, "atomnos", None)
    if atomcoords is None or atomnos is None or len(atomcoords) == 0:
        return _extract_sp_frames_native(log_text)
    energy_hartree = final_energy_hartree(log_text)
    if energy_hartree is None and energies is not None and len(energies) > 0:
        energy_hartree = energy_ev_to_hartree(_as_float_list(energies)[-1])
    return [FrameRecord(
        frame=0,
        electronic_energy_hartree=energy_hartree,
        frequencies_cm=vibfreqs_from_text(log_text) or _get_vibfreqs(data),
        xyz=final_xyz_from_text(log_text) or _coords_to_xyz(atomnos, atomcoords[-1], comment="single point"),
    )]
```


<a id="s281"></a>

### S281 · `extract_frames`

`cloudra/tools/core/orca_frames.py:592–601`

```python
def extract_frames(log_path: str) -> list[FrameRecord]:
    """按识别到的任务类型提取关键帧。

    - IRC 的逐点坐标在 trj 边文件（主输出无）：返回空；点数/收敛/能量走 ``extract_irc``。
    - NEB（``! NEB`` / ``! NEB-TS``）：逐图像几何在 ``<作业名>_im<N>.xyz`` 边文件里（主输出
      只有迭代表），这里读那些边文件，并把收敛的 ``<作业名>_NEB-TS_converged.xyz`` 作为带
      ``converged=True`` 的末帧。**读不到边文件时返回空但绝不退化成单点**——把一条路径报成
      一个结构比什么都不报更糟；原因见 ``frames_unavailable_reason``。
    """
    return extract_frames_from_text(_read_text(log_path), log_path=log_path)
```


<a id="s282"></a>

### S282 · `extract_frames_from_text`

`cloudra/tools/core/orca_frames.py:604–623`

```python
def extract_frames_from_text(text: str, *, log_path: str | None = None) -> list[FrameRecord]:
    """extract_frames 的文本变体：调用方已读过日志时避免重复 IO。

    ``log_path`` 仅用于 NEB 分支定位 ``<作业名>_im<N>.xyz`` 边文件；为 None 时
    NEB 路径帧无从读取，返回空（原因由 ``frames_unavailable_reason`` 说明）。
    """
    jobs = detect_job_types_from_text(text)
    if "irc" in jobs:
        return []
    if "neb" in jobs and not (jobs & {"opt", "ts", "scan"}):
        # 逐图像几何在 <作业名>_im<N>.xyz 边文件里；读不到就返回空，但调用方可用
        # frames_unavailable_reason 拿到**具体原因**（不是静默的"没有帧"）
        roots = _orca_sidecar_roots(log_path, text) if log_path else []
        frames, _reason = _neb_image_frames(roots)
        return frames
    if "scan" in jobs:
        return _extract_scan_frames(text)
    if "opt" in jobs or "ts" in jobs:
        return _extract_opt_frames(text)
    return _extract_sp_frames(text)
```


<a id="s283"></a>

### S283 · `_parse_irc_direction_block`

`cloudra/tools/core/orca_frames.py:642–652`

```python
def _parse_irc_direction_block(text: str) -> tuple[int, bool]:
    """解析一个 FORWARD/BACKWARD IRC 块，返回 (点数, 是否收敛)。

    点数为迭代行数（不含表头/阈值行）；收敛以块尾 "THE IRC HAS CONVERGED"
    （HURRAY 段）为准——步数耗尽而终止的块没有该标记。
    """
    n_points = 0
    for line in text.splitlines():
        if _IRCA_ITER_RE.match(line):
            n_points += 1
    return n_points, bool(_IRCA_CONVERGED_RE.search(text))
```


<a id="s284"></a>

### S284 · `extract_irc`

`cloudra/tools/core/orca_frames.py:655–665`

```python
def extract_irc(log_path: str) -> dict:
    """从 ORCA 主输出解析 IRC 元数据，对齐 gaussian_frames.extract_irc 的 meta dict。

    ORCA 把 IRC 逐点的能量/梯度直接打在主输出（FORWARD IRC / BACKWARD IRC
    迭代块 + 结尾 IRC PATH SUMMARY），无需追 `_IRC.log`/`*_trj.xyz` 边文件
    （边文件只额外提供逐点坐标，这里不取）。返回键：
    num_points_forward/backward、forward_converged/backward_converged、
    endpoint_energies_hartree（PATH SUMMARY 首/末行能量）、ts_energy_hartree
    （带 "<= TS" 标记行的能量）。找不到 IRC 段时抛 ValueError。
    """
    return extract_irc_from_text(_read_text(log_path))
```


<a id="s285"></a>

### S285 · `extract_irc_from_text`

`cloudra/tools/core/orca_frames.py:668–716`

```python
def extract_irc_from_text(text: str) -> dict:
    """extract_irc 的文本变体：调用方已读过日志时避免重复 IO。"""
    blocks = list(_IRCA_BLOCK_RE.finditer(text))
    if not blocks:
        raise ValueError("ORCA 日志中未找到 FORWARD/BACKWARD IRC 段。")

    num_points: dict[str, int] = {"FORWARD": 0, "BACKWARD": 0}
    converged: dict[str, bool] = {"FORWARD": False, "BACKWARD": False}
    for i, m in enumerate(blocks):
        direction = m.group(1)
        seg_end = blocks[i + 1].start() if i + 1 < len(blocks) else len(text)
        # 截到 PATH SUMMARY 之前，避免把汇总表行也数进迭代点
        segment = text[m.end():seg_end]
        summary_idx = segment.find("IRC PATH SUMMARY")
        if summary_idx >= 0:
            segment = segment[:summary_idx]
        n, conv = _parse_irc_direction_block(segment)
        num_points[direction] = n
        converged[direction] = conv

    meta: dict = {
        "num_points_forward": num_points["FORWARD"],
        "num_points_backward": num_points["BACKWARD"],
        "forward_converged": converged["FORWARD"],
        "backward_converged": converged["BACKWARD"],
        "ts_energy_hartree": None,
        "rx_coord_range": None,
        "endpoint_energies_hartree": None,
    }

    # PATH SUMMARY：首行=反应物端、末行=产物端、"<= TS" 行=TS 能量。
    # 用 rfind 取最后一次出现（真实输出在文件尾部；避免命中开头注释/回显里的
    # 同名字样），且从该段标题的分隔线之后开始读数据行。
    summary_idx = text.rfind("IRC PATH SUMMARY")
    if summary_idx >= 0:
        summary_rows = []
        for line in text[summary_idx:].splitlines():
            m = _IRCA_SUMMARY_RE.match(line)
            if m:
                summary_rows.append((float(m.group(2)), "<=" in line and "TS" in line))
        if summary_rows:
            meta["endpoint_energies_hartree"] = (
                summary_rows[0][0],
                summary_rows[-1][0],
            )
            ts_rows = [e for e, is_ts in summary_rows if is_ts]
            if ts_rows:
                meta["ts_energy_hartree"] = ts_rows[0]
    return meta
```


<a id="s286"></a>

### S286 · `frames_unavailable_reason_from_text`

`cloudra/tools/core/orca_frames.py:807–824`

```python
def frames_unavailable_reason_from_text(text: str, *, log_path: str | None = None) -> str | None:
    """frames_unavailable_reason 的文本变体：调用方已读过日志时避免重复 IO。

    ``log_path`` 仅用于 NEB 分支定位边文件；为 None 时按"找不到边文件"给原因。
    """
    jobs = detect_job_types_from_text(text)
    if "irc" in jobs:
        return (
            "this is an IRC job: its per-point coordinates live in the *_IRC_F_trj.xyz / "
            "*_IRC_B_trj.xyz side files, and the converged endpoints in *_IRC_F.xyz / *_IRC_B.xyz "
            "(use extract_irc_endpoints or ts_guess strict=True)"
        )
    if "neb" in jobs and not (jobs & {"opt", "ts", "scan"}):
        roots = _orca_sidecar_roots(log_path, text) if log_path else []
        _frames, reason = _neb_image_frames(roots)
        if reason:
            return f"this is an ORCA NEB job, but {reason}"
    return None
```


<a id="s287"></a>

### S287 · `_orca_sidecar_roots`

`cloudra/tools/core/orca_frames.py:834–881`

```python
def _orca_sidecar_roots(log_path: str, text: str) -> list[tuple[str, str]]:
    """ORCA 边文件（IRC 轨迹/端点、NEB 逐图像）的 (目录, 作业名) 候选：优先日志开头输入回显
    的 NAME 记录（harness 捕获的日志名 ``calc-<id>.out.log`` 与 ORCA 作业名无关），
    其次日志自身 stem。

    NAME 只带文件名（相对路径）时，除 NAME 自带目录外还试日志所在目录及其父目录
    ——harness 把 stdout 捕获进 ``<作业目录>/.cloudra/calc-<id>.out.log``，边文件
    留在父目录里，只按 NAME 字面目录解析会永远找不到。"""
    roots: list[tuple[str, str]] = []
    log_dir = os.path.dirname(os.path.abspath(log_path))
    remote_results = Path(log_dir).parent if Path(log_dir).name == '.cloudra' else Path(log_dir)
    remote_map = remote_results.parent / 'path-map.json'
    if remote_results.name == 'results' and remote_map.is_file():
        mapping = json.loads(remote_map.read_text())
        roots.append((str(remote_results), Path(mapping['input_file']).stem))
        for item in mapping.get('files', []):
            if item.get('prefix') and item.get('role') != 'dependency':
                prefix = remote_results / item['staged_path']
                roots.append((str(prefix.parent), prefix.name))
        return roots
    receipt = Path(log_dir).parent / 'evidence.json'
    if receipt.is_file():
        # A frozen compute receipt cannot acquire future geometry from the
        # mutable original NAME directory or from neighboring jobs.
        record = json.loads(receipt.read_text())
        names = {Path(log_path).stem, Path(record.get('input_file', log_path)).stem}
        names.update(record.get('geometry_stems', []))
        match = _ORCA_NAME_RE.search(text[:200_000])
        if match:
            names.add(Path(match.group('path')).stem)
        return [(log_dir, name) for name in sorted(names)]
    m = _ORCA_NAME_RE.search(text[:200_000])
    if m:
        job = os.path.splitext(m.group("path"))[0]
        base = os.path.basename(job)
        dirs = [log_dir, os.path.dirname(log_dir)]
        if os.path.dirname(job):
            dirs.append(os.path.dirname(job))
        for directory in dict.fromkeys(dirs):
            roots.append((directory, base))
    stem = os.path.splitext(os.path.basename(log_path))[0]
    roots.append((log_dir, stem))
    parent = os.path.dirname(log_dir)
    if parent and parent != log_dir:
        # harness 把 stdout 捕获进 <作业目录>/.cloudra/calc-<id>.out.log，
        # 边文件留在上一级。stem 回退也一并进父目录候选，供兜底匹配。
        roots.append((parent, stem))
    return roots
```


<a id="s288"></a>

### S288 · `_sidecar_search_dirs`

`cloudra/tools/core/orca_frames.py:884–891`

```python
def _sidecar_search_dirs(roots: list[tuple[str, str]]) -> list[str]:
    """兜底扫描目录：所有候选根目录 + 它们的父目录（去重、保序）。"""
    dirs: list[str] = []
    for directory, _stem in roots:
        for candidate in (directory, os.path.dirname(directory)):
            if candidate and candidate not in dirs:
                dirs.append(candidate)
    return dirs
```


<a id="s289"></a>

### S289 · `_basename_matches_any_job`

`cloudra/tools/core/orca_frames.py:894–896`

```python
def _basename_matches_any_job(path: str, roots: list[tuple[str, str]]) -> bool:
    name = os.path.basename(path)
    return any(name.startswith(stem) for _directory, stem in roots if stem)
```


<a id="s290"></a>

### S290 · `_irc_endpoint_sidecar`

`cloudra/tools/core/orca_frames.py:899–932`

```python
def _irc_endpoint_sidecar(
    roots: list[tuple[str, str]], suffix: str
) -> tuple[str | None, str | None]:
    """定位一个方向的端点来源：final endpoint 文件优先，trajectory 末帧其次。

    返回 (geometry_ref, origin)；都找不到返回 (None, None)。
    """
    for directory, stem in roots:
        final = os.path.join(directory, f"{stem}{suffix}.xyz")
        if os.path.isfile(final):
            return final, "final_endpoint_file"
    for directory, stem in roots:
        trajectory = os.path.join(directory, f"{stem}{suffix}_trj.xyz")
        if os.path.isfile(trajectory):
            return trajectory, "trajectory_last_frame"
    # 兜底：stdout 日志被 harness 重命名为 calc-<id>.out.log（且日志被截断、
    # 输入回显里没有 NAME 行）时，NAME/stem 都推不出 ORCA 作业名。此时在该
    # 日志目录及其父目录按 *_<suffix>.xyz / *_<suffix>_trj.xyz 匹配——只接受
    # 唯一命中；多命中时优先命中候选作业名前缀者，仍不唯一则拒绝猜测。
    for directory in _sidecar_search_dirs(roots):
        if not os.path.isdir(directory):
            continue
        for pattern, origin in (
            (f"*{suffix}.xyz", "final_endpoint_file_glob"),
            (f"*{suffix}_trj.xyz", "trajectory_last_frame_glob"),
        ):
            hits = sorted(glob.glob(os.path.join(directory, pattern)))
            if len(hits) == 1:
                return hits[0], origin
            if len(hits) > 1:
                named = [h for h in hits if _basename_matches_any_job(h, roots)]
                if len(named) == 1:
                    return named[0], origin
    return None, None
```


<a id="s291"></a>

### S291 · `_ArchivedIrcEndpoint`

`cloudra/tools/core/orca_frames.py:935–940`

```python
class _ArchivedIrcEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str | None
    sha256: str | None
    origin: str | None
    converged: bool | None
```


<a id="s292"></a>

### S292 · `_ArchivedIrcEvidence`

`cloudra/tools/core/orca_frames.py:943–947`

```python
class _ArchivedIrcEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    log_sha256: str
    endpoints: dict[str, _ArchivedIrcEndpoint]
    atom_binding: dict | None = None
```


<a id="s293"></a>

### S293 · `_archived_irc_endpoints`

`cloudra/tools/core/orca_frames.py:950–977`

```python
def _archived_irc_endpoints(log_path: str) -> dict | None:
    """Read the existing IRC archive, including Gaussian's native-log binding."""
    archive = Path(log_path).parent / "irc_endpoints.json"
    if archive.is_file():
        from cloudra.tools.core.qm_engine import detect_qm_engine

        manifest = _ArchivedIrcEvidence.model_validate(json.loads(archive.read_text()))
        if hashlib.sha256(Path(log_path).read_bytes()).hexdigest() != manifest.log_sha256:
            raise ValueError("Archived IRC log hash mismatch")
        if set(manifest.endpoints) != {"forward", "backward"}:
            raise ValueError("Archived IRC requires both direction records")
        result = {}
        for direction, endpoint in manifest.endpoints.items():
            geometry = None
            if endpoint.filename is not None:
                if detect_qm_engine(log_path) == 'gaussian':
                    raise ValueError('Archived Gaussian IRC geometries must come from the native log')
                if Path(endpoint.filename).name != endpoint.filename:
                    raise ValueError("Archived IRC endpoint must be a local filename")
                path = archive.parent / endpoint.filename
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != endpoint.sha256:
                    raise ValueError("Archived IRC endpoint missing or hash mismatch")
                geometry = str(path)
            result[direction] = {"geometry_ref": geometry, "origin": endpoint.origin,
                                 "availability": "available" if geometry else "unavailable",
                                 "converged": endpoint.converged, "atom_binding": manifest.atom_binding}
        return result
    return None
```


<a id="s294"></a>

### S294 · `extract_irc_endpoints`

`cloudra/tools/core/orca_frames.py:980–1015`

```python
def extract_irc_endpoints(log_path: str) -> dict:
    """定位 ORCA IRC forward/backward 端点几何（不命名 reactant/product）。

    返回 {"forward": {...}, "backward": {...}}，每方向含：
    - geometry_ref：端点几何来源路径（final endpoint 文件或 F/B trajectory），
      无来源时 None；
    - origin：final_endpoint_file / trajectory_last_frame，或兜底匹配得到的
      final_endpoint_file_glob / trajectory_last_frame_glob / None；
    - availability：available / unavailable；
    - converged：主输出 IRC 块的收敛标记（无 IRC 段时 None）。仅作记录、
      不是闸门——未收敛方向的轨迹末帧同样是合法的部分端点，方向是否成立
      由调用方的几何区间证明判定。
    """
    archived = _archived_irc_endpoints(log_path)
    if archived is not None:
        return archived
    text = _read_text(log_path)
    roots = _orca_sidecar_roots(log_path, text)
    converged: dict[str, bool | None] = {"FORWARD": None, "BACKWARD": None}
    try:
        meta = extract_irc(log_path)
        converged["FORWARD"] = bool(meta.get("forward_converged"))
        converged["BACKWARD"] = bool(meta.get("backward_converged"))
    except ValueError:
        pass

    result: dict[str, dict] = {}
    for direction, suffix in (("forward", "_IRC_F"), ("backward", "_IRC_B")):
        geometry_ref, origin = _irc_endpoint_sidecar(roots, suffix)
        result[direction] = {
            "geometry_ref": geometry_ref,
            "origin": origin,
            "availability": "available" if geometry_ref else "unavailable",
            "converged": converged["FORWARD" if direction == "forward" else "BACKWARD"],
        }
    return result
```


<a id="s295"></a>

### S295 · `snapshot_irc_endpoints`

`cloudra/tools/core/orca_frames.py:1018–1059`

```python
def snapshot_irc_endpoints(log_path: str, directory: Path) -> None:
    """Preserve the existing IRC archive contract when a compute log is frozen.

    Copy whole native endpoint/trajectory files, preserving their origin and
    frozen atom binding. Missing endpoint evidence stays missing.
    """
    import shutil

    from cloudra.persistence.fs_utils import atomic_write_json

    try:
        extract_irc(log_path)
    except ValueError:
        return
    endpoints = extract_irc_endpoints(log_path)
    roots = _orca_sidecar_roots(log_path, _read_text(log_path))
    # The general reader has a unique-neighbor convenience fallback. A durable
    # execution archive must only bind this job's actual named sidecars.
    allowed = {str(Path(directory) / (stem + suffix)) for directory, stem in roots
               for suffix in ('_IRC_F.xyz', '_IRC_B.xyz', '_IRC_F_trj.xyz', '_IRC_B_trj.xyz')}
    if _archived_irc_endpoints(log_path) is not None:
        allowed.update(endpoint['geometry_ref'] for endpoint in endpoints.values() if endpoint.get('geometry_ref'))
    records = {}
    for direction, endpoint in endpoints.items():
        filename = digest = None
        if endpoint.get('geometry_ref') and endpoint['geometry_ref'] in allowed:
            source = Path(endpoint['geometry_ref'])
            with source.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            filename = digest[:16] + '_' + source.name
            if source.parent == directory and source.name.startswith(digest[:16] + '_'):
                filename = source.name
            if source != directory / filename:
                shutil.copy2(source, directory / filename)
        records[direction] = _ArchivedIrcEndpoint(filename=filename, sha256=digest,
                                                origin=endpoint.get('origin'),
                                                converged=endpoint.get('converged'))
    with Path(log_path).open('rb') as stream:
        log_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    archive = _ArchivedIrcEvidence(log_sha256=log_digest, endpoints=records,
                                   atom_binding=endpoints['forward'].get('atom_binding'))
    atomic_write_json(directory / 'irc_endpoints.json', archive.model_dump())
```


<a id="s296"></a>

### S296 · `read_endpoint_geometry`

`cloudra/tools/core/orca_frames.py:1062–1092`

```python
def read_endpoint_geometry(endpoint: dict) -> str | None:
    """读取 extract_irc_endpoints 返回的一个端点几何（xyz 文本）。

    final_endpoint_file 直接读取；trajectory_last_frame 取多帧 xyz 的最后一帧。
    解析规则只住在这里，调用方（ts_guess strict 等）不复制。"""
    ref = endpoint.get("geometry_ref")
    if not ref:
        return None
    try:
        with open(ref, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return None
    if "trajectory" not in (endpoint.get("origin") or ""):
        return text if text.strip() else None
    frames: list[str] = []
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.isdigit() and i + 1 < len(lines):
            count = int(stripped)
            block = lines[i : i + 2 + count]
            if len(block) == 2 + count:
                frames.append("".join(block))
            i += 2 + count
        else:
            i += 1
    if frames:
        return frames[-1]
    return text if text.strip() else None
```


## `cloudra/tools/core/qm_calculation.py`

文件 SHA-256：`f73c7636d5abbffee4010ec36e5d44ae482d3d210cd25c11e97f2b2843a2601d`


<a id="s297"></a>

### S297 · `QmInputSettings`

`cloudra/tools/core/qm_calculation.py:7–23`

```python
class QmInputSettings(BaseModel):
    """Electronic state and resources shared by native input generators."""

    charge: int | None = Field(default=None,
        description="Total molecular charge. MOL/SMILES may inherit the graph's formal charge; "
                    "an explicit declaration must agree with that graph. XYZ calculations require "
                    "an explicit charge, including 0 for a neutral system.")
    multiplicity: int = Field(default=1, ge=1,
        description="Spin multiplicity (2S+1): singlet=1, doublet=2, triplet=3.")
    electronic_character: Literal['closed_shell', 'open_shell'] | None = Field(default=None,
        description="Declared electronic character, including open-shell singlets. Open-shell "
                    "SMILES skip closed-shell force fields. This does not select a QM method or initialize spin.")
    nproc: int = Field(default=4, ge=1,
        description="Number of CPU cores for parallel compute (Gaussian %nproc / ORCA %pal).")
    mem: str = Field(default='4GB',
        description="Gaussian/ORCA total job memory, e.g. '4GB' or '8192MB'. Gaussian writes %mem; ORCA writes "
                    "%maxcore = mem/nproc. Request the same total memory_mb when submitting.")
```


<a id="s298"></a>

### S298 · `QmCalculation`

`cloudra/tools/core/qm_calculation.py:26–57`

```python
class QmCalculation(BaseModel):
    """Explicit method and basis; native keywords replace, never accumulate."""

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    engine: Literal['orca', 'gaussian', 'xtb']
    method: str = Field(min_length=1, description='One native method token, e.g. B3LYP, B97-3c, HF or GFN2-xTB. Put the basis only in basis_set and additional native settings only in keywords; do not supply a route string.')
    basis_set: str = Field(description='Explicit basis token, e.g. def2-SVP for ORCA, def2SVP for Gaussian, or 6-31G(d). Gaussian rendering also accepts the hyphenated aliases def2-SVP, def2-TZVP, def2-TZVPP, def2-QZVP and def2-QZVPP. Other names keep their native spelling. Use an explicit empty string for a method with no basis; no method or basis is chosen automatically.')
    keywords: str = Field(default='', description='Additional native electronic settings, including explicitly requested dispersion, SCF and solvent settings. Declare the orbital basis only in basis_set; auxiliary fitting bases such as def2/J remain in keywords. This string replaces the previous string when patched; omission in a revision preserves it.')
    frequency_mode: Literal['auto', 'analytic', 'numeric'] = 'auto'
    orca_blocks: str | None = Field(default=None, description='Explicit ORCA native blocks. Omission in a revision preserves them; explicit null clears them.')
    end_setting: str = Field(default='', description='Explicit Gaussian trailing native settings. Omission in a revision preserves them; an explicit empty string clears them.')

    @field_validator('method')
    @classmethod
    def native_method(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('method must be non-empty')
        return value

    @field_validator('basis_set')
    @classmethod
    def native_basis(cls, value):
        value = value.strip()
        return value

    @model_validator(mode='after')
    def engine_settings(self):
        if self.engine == 'xtb' and (self.basis_set or self.keywords or self.frequency_mode != 'auto'
                                     or self.orca_blocks or self.end_setting):
            raise ValueError('native xTB declares an empty basis_set and no ORCA/Gaussian keywords or frequency mode')
        return self
```


## `cloudra/tools/core/qm_engine.py`

文件 SHA-256：`3a96ad467bc2fa6b118efa4cd48e289c99ca5cd69ca5a9a7abe998474f50c2b6`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/tools/core/qm_engine.py:9–9`

```python
_HEAD_BYTES = 16384
```


`cloudra/tools/core/qm_engine.py:11–16`

```python
_GAUSSIAN_MARKERS = (
    "Entering Gaussian System",
    "Gaussian, Inc.",
    "Gaussian 09",
    "Gaussian 16",
)
```


`cloudra/tools/core/qm_engine.py:17–23`

```python
_ORCA_MARKERS = (
    "O   R   C   A",
    "O  R  C  A",
    "* O   R   C   A *",
    "ORCA VERSION",
    "An ab initio, DFT and semiempirical SCF-MO package",
)
```


`cloudra/tools/core/qm_engine.py:24–28`

```python
_XTB_MARKERS = (
    "xtb version",
    "x T B",
    "Mulliken Center for Theoretical Chemistry",
)
```


<a id="s299"></a>

### S299 · `_read_head`

`cloudra/tools/core/qm_engine.py:31–33`

```python
def _read_head(log_path: str) -> str:
    with open(log_path, encoding="utf-8", errors="replace") as f:
        return f.read(_HEAD_BYTES)
```


<a id="s300"></a>

### S300 · `detect_qm_engine`

`cloudra/tools/core/qm_engine.py:36–42`

```python
def detect_qm_engine(log_path: str) -> str:
    """识别日志来源程序，返回 "gaussian" / "orca" / "xtb" / "unknown"。"""
    try:
        head = _read_head(log_path)
    except OSError:
        return "unknown"
    return detect_qm_engine_from_text(head)
```


<a id="s301"></a>

### S301 · `detect_qm_engine_from_text`

`cloudra/tools/core/qm_engine.py:45–57`

```python
def detect_qm_engine_from_text(text: str) -> str:
    """Detect the native program from already-read log text."""
    head = text[:_HEAD_BYTES]
    for marker in _GAUSSIAN_MARKERS:
        if marker in head:
            return "gaussian"
    for marker in _ORCA_MARKERS:
        if marker in head:
            return "orca"
    for marker in _XTB_MARKERS:
        if marker in head:
            return "xtb"
    return "unknown"
```


## `cloudra/tools/core/qm_keywords.py`

文件 SHA-256：`36acec67eb30ea30fb0c97059450e40be44a94bcec4ef3d63ab4969c87107d62`


<a id="s302"></a>

### S302 · `orca_basis_keyword`

`cloudra/tools/core/qm_keywords.py:18–29`

```python
def orca_basis_keyword(basis: str) -> str:
    """Render compact def2 aliases using ORCA's native hyphenated spelling.

    Preserve already-native and other basis names. The declaration stays intact;
    this conversion belongs at input rendering, not in scientific policy.
    """
    basis = basis.strip()
    head, separator, suffix = basis.partition("/")
    lowered = head.lower()
    if lowered.startswith("def2") and len(head) > 4 and not lowered.startswith("def2-"):
        head = "def2-" + head[4:].upper()
    return head + separator + suffix
```


<a id="s303"></a>

### S303 · `gaussian_basis_keyword`

`cloudra/tools/core/qm_keywords.py:32–42`

```python
def gaussian_basis_keyword(basis: str) -> str:
    """Render known def2 aliases using Gaussian's built-in basis keywords."""
    basis = basis.strip()
    aliases = {
        'def2-svp': 'def2SVP',
        'def2-tzvp': 'def2TZVP',
        'def2-tzvpp': 'def2TZVPP',
        'def2-qzvp': 'def2QZVP',
        'def2-qzvpp': 'def2QZVPP',
    }
    return aliases.get(basis.lower(), basis)
```


## `cloudra/tools/core/qm_log_facts.py`

文件 SHA-256：`5d2fdbde2a03a60d23b98c6a9fd69e72f54ddd181f746617f0a62a633ec72025`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/tools/core/qm_log_facts.py:18–18`

```python
_FLOAT = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DdEe][+-]?\d+)?)"
```


`cloudra/tools/core/qm_log_facts.py:19–19`

```python
_ORCA_SCF_ENERGY = re.compile(rf"^\s*(?:Total Energy\s*:|SCF Energy\s*:)\s*{_FLOAT}\s+Eh", re.M)
```


<a id="s304"></a>

### S304 · `QmLogFacts`

`cloudra/tools/core/qm_log_facts.py:22–34`

```python
@dataclass
class QmLogFacts:
    engine: str
    text: str
    normal_termination: bool
    opt_converged: bool | None
    job_types: set[str]
    frequencies_cm: list[float] | None
    scf_energy_hartree: float | None
    electronic_energy_hartree: float | None
    geometry: tuple | None
    parser_data: Any | None
    thermochemistry: dict[str, float]
```


<a id="s305"></a>

### S305 · `read_qm_log`

`cloudra/tools/core/qm_log_facts.py:37–41`

```python
def read_qm_log(path: str | Path) -> QmLogFacts:
    """Read a native log once; parse already-read text off the async loop."""
    with open(path, encoding='utf-8', errors='replace') as handle:
        text = handle.read()
    return parse_qm_log_text(text, source_path=str(path))
```


<a id="s306"></a>

### S306 · `parse_qm_log_text`

`cloudra/tools/core/qm_log_facts.py:44–109`

```python
def parse_qm_log_text(text: str, *, source_path: str | None = None, engine: str | None = None) -> QmLogFacts:
    """Extract explicit native facts; absent data stays unknown, never zero."""
    detected = detect_qm_engine_from_text(text)
    if engine is not None and (engine not in {'gaussian', 'orca', 'xtb'}
                               or detected not in {'unknown', engine}):
        raise ValueError(f'Native log engine {detected!r} does not match {engine!r}.')
    engine = engine or detected
    data = None
    if engine != 'xtb':
        try:
            import cclib
            source = io.StringIO(text)
            if source_path is not None:
                source.name = source_path
            data = cclib.io.ccread(source)
        except Exception:
            pass
    parser = {'gaussian': gaussian_frames, 'orca': orca_frames, 'xtb': xtb_frames}.get(engine)
    normal = parser.normal_termination(text) if parser else False
    converged = parser.opt_converged(text) if parser else None
    jobs = parser.detect_job_types_from_text(text) if parser else set()
    frequencies = (parser.vibfreqs_from_text(text) or None) if parser else None
    geometry = None
    scf = None
    electronic = None
    thermo = {}
    if engine == 'gaussian':
        scf = gaussian_frames.scf_energy_hartree(text)
        electronic = gaussian_frames.electronic_energy_hartree(text)
        geometry = parse_xyz(gaussian_frames.final_xyz_from_text(text))
        thermo = gaussian_frames.extract_thermochemistry_from_text(text)
    elif engine == 'orca':
        matches = list(_ORCA_SCF_ENERGY.finditer(text))
        if matches:
            scf = float(matches[-1].group(1).replace('D', 'E').replace('d', 'e'))
        electronic = orca_frames.final_energy_hartree(text)
        geometry = parse_xyz(orca_frames.final_xyz_from_text(text))
        thermo = orca_frames.extract_thermochemistry_from_text(text)
    elif engine == 'xtb':
        electronic = xtb_frames.final_energy_hartree(text)
        scf = electronic
        geometry = parse_xyz(xtb_frames.final_xyz_from_text(text))
        thermo = xtb_frames.thermochemistry(text)
    if data is not None:
        if frequencies is None:
            values = getattr(data, 'vibfreqs', None)
            if values is not None and len(values):
                frequencies = [float(value) for value in values]
        if geometry is None:
            atomnos = getattr(data, 'atomnos', None)
            coords = getattr(data, 'atomcoords', None)
            if atomnos is not None and coords is not None and len(coords):
                geometry = parse_xyz(gaussian_frames._coords_to_xyz(atomnos, coords[-1]))
    if engine in {'gaussian', 'orca'} and geometry is not None:
        markers = ('Optimization stopped.', 'Optimization completed.', 'Stationary point found.') if engine == 'gaussian' else (
            'The optimization did not converge', 'THE OPTIMIZATION HAS CONVERGED')
        opt_index = max(text.rfind(marker) for marker in markers)
        if opt_index >= 0 and not same_geometry(geometry, _geometry_at_marker(text, engine, opt_index, after=True)):
            converged = None
        frequency_index = text.rfind('Frequencies --' if engine == 'gaussian' else 'VIBRATIONAL FREQUENCIES')
        if frequency_index >= 0 and not same_geometry(geometry, _geometry_at_marker(text, engine, frequency_index)):
            frequencies = None
    return QmLogFacts(engine=engine, text=text, normal_termination=normal,
        opt_converged=converged, job_types=jobs, frequencies_cm=frequencies,
        scf_energy_hartree=scf, electronic_energy_hartree=electronic,
        geometry=geometry, parser_data=data, thermochemistry=thermo)
```


<a id="s307"></a>

### S307 · `_geometry_at_marker`

`cloudra/tools/core/qm_log_facts.py:112–131`

```python
def _geometry_at_marker(text: str, engine: str, index: int, *, after: bool = False) -> tuple | None:
    """Geometry belonging to a native result marker, before another job starts."""
    parser = gaussian_frames if engine == 'gaussian' else orca_frames
    start = parser.last_job_start(text[:index])
    geometry = parse_xyz(parser.final_xyz_from_text(text[start:index]))
    if geometry is not None and not after:
        return geometry
    # Some native optimization summaries precede their final Cartesian printout.
    labels = ('Standard orientation:', 'Input orientation:') if engine == 'gaussian' else (
        'CARTESIAN COORDINATES (ANGSTROEM)',)
    positions = sorted(position for label in labels
                       for position in [text.find(label, index)] if position >= 0)
    if not positions or parser.last_job_start(text[:positions[0]]) > start:
        return geometry
    if after and engine == 'orca' and 'FINAL ENERGY EVALUATION AT THE STATIONARY POINT' not in text[index:positions[0]]:
        return geometry
    following = [position for label in labels
                 for position in [text.find(label, positions[0] + 1)] if position >= 0]
    end = min(following) if following else len(text)
    return parse_xyz(parser.final_xyz_from_text(text[positions[0]:end]))
```


## `cloudra/tools/core/species_identity.py`

文件 SHA-256：`7cbf952efe66d8eb5a8cef7f51b943dcfcea86a91590a031cbaed4f22cc06297`


<a id="s308"></a>

### S308 · `chemical_smiles`

`cloudra/tools/core/species_identity.py:5–7`

```python
def chemical_smiles(value: str | list[str]) -> str:
    """Return the complete chemical graph without changing species grouping."""
    return '.'.join(value) if isinstance(value, list) else value
```


<a id="s309"></a>

### S309 · `species_smiles`

`cloudra/tools/core/species_identity.py:10–12`

```python
def species_smiles(value: str | list[str]) -> list[str]:
    """A scalar is one species, including a dot-joined bound complex."""
    return value if isinstance(value, list) else [value]
```


## `cloudra/tools/core/ts_inputs.py`

文件 SHA-256：`384deae057fd68436e1c2810df3d9ce86b4bcfe6db344b06e8ca7370899da8ab`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/tools/core/ts_inputs.py:50–50`

```python
CalculationValue = QmCalculation | CalculationRef
```


`cloudra/tools/core/ts_inputs.py:111–114`

```python
ConformerSource = Annotated[
    GeneratedConformer | FileConformer | CatalogConformer | RotatedConformer,
    Field(discriminator="kind"),
]
```


`cloudra/tools/core/ts_inputs.py:203–203`

```python
TsGuess = Annotated[XtbPathGuess | ScanGuess | ProvidedGuess, Field(discriminator="kind")]
```


<a id="s310"></a>

### S310 · `InputModel`

`cloudra/tools/core/ts_inputs.py:34–35`

```python
class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
```


<a id="s311"></a>

### S311 · `CalculationRef`

`cloudra/tools/core/ts_inputs.py:38–47`

```python
class CalculationRef(InputModel):
    """Explicitly reuse one complete calculation defined in this TS input."""
    ref: str = Field(min_length=1)

    @field_validator('ref')
    @classmethod
    def reference_name(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError('calculation reference must be a nonblank exact definition name')
        return value
```


<a id="s312"></a>

### S312 · `resolve_calculation`

`cloudra/tools/core/ts_inputs.py:53–64`

```python
def resolve_calculation(value: CalculationValue | dict | None,
                        definitions: Mapping[str, QmCalculation | dict]) -> QmCalculation | None:
    """Resolve local references and return an independent complete snapshot."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = TypeAdapter(CalculationValue).validate_python(value)
    if isinstance(value, CalculationRef):
        if value.ref not in definitions:
            raise ValueError(f'unknown calculation reference {value.ref!r}')
        value = QmCalculation.model_validate(definitions[value.ref])
    return value.model_copy(deep=True)
```


<a id="s313"></a>

### S313 · `TsReaction`

`cloudra/tools/core/ts_inputs.py:67–76`

```python
class TsReaction(InputModel):
    reactant_smiles: str = Field(min_length=1)
    product_smiles: str | list[str] = Field(min_length=1,
        description='A dot-joined SMILES declares a bound complex; a list declares separated products, displayed with +.')
    charge: StrictInt
    multiplicity: StrictInt = Field(ge=1)
    electronic_character: Literal['closed_shell', 'open_shell'] | None = Field(default=None,
        description="Optional declared electronic character, including open-shell singlets. This describes the requested seed state; it does not choose a ground state, wavefunction method or spin initialization.")
    selected_candidate: StrictInt | None = Field(default=None, ge=0, description="Choose an inspected complete concrete mapping candidate by its 0-based index only when correspondence is ambiguous. A unique complete mapping is adopted automatically; omitted/null never silently selects candidate 0.")
    reaction_center: list[tuple[StrictInt, StrictInt]] = Field(default_factory=list, description="Forming/breaking atom pairs in the bound reactant's full coordinate order, 1-based and including explicit hydrogens. Use reaction_mapping.concrete_watch_pairs for the same concrete structure.")
```


<a id="s314"></a>

### S314 · `GeneratedConformer`

`cloudra/tools/core/ts_inputs.py:79–83`

```python
class GeneratedConformer(InputModel):
    kind: Literal["generate"]
    generation: Literal["ETKDGv3"]
    seed: StrictInt
    optimization: CalculationValue | None = None
```


<a id="s315"></a>

### S315 · `FileConformer`

`cloudra/tools/core/ts_inputs.py:86–95`

```python
class FileConformer(InputModel):
    kind: Literal["file"]
    xyz_path: str = Field(min_length=1)
    mol_path: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    optimization: CalculationValue | None = Field(default=None, description=(
        'Optional additional build-stage pre-optimization. Omit or set null to use the supplied file geometry as-is. '
        'This does not certify a minimum or replace later TS/IRC and endpoint verification. '
        'With ts_resume, patch optimization to null to clear a previous request; omitted source fields retain their values.'
    ))
```


<a id="s316"></a>

### S316 · `CatalogConformer`

`cloudra/tools/core/ts_inputs.py:98–102`

```python
class CatalogConformer(InputModel):
    kind: Literal["catalog"]
    catalog_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    optimization: CalculationValue | None = None
```


<a id="s317"></a>

### S317 · `RotatedConformer`

`cloudra/tools/core/ts_inputs.py:105–108`

```python
class RotatedConformer(InputModel):
    kind: Literal["rotate_about_bond"]
    atoms: tuple[StrictInt, StrictInt] = Field(description="Bond-axis atom pair in the bound conformer's full coordinate order, 1-based; do not use SMILES heavy-atom indices.")
    degrees: float
```


<a id="s318"></a>

### S318 · `ConformerGuidance`

`cloudra/tools/core/ts_inputs.py:117–119`

```python
class ConformerGuidance(InputModel):
    ring_order: list[StrictInt] = Field(default_factory=list, description="Ordered ring atoms in the bound reactant's full coordinate order, 1-based.")
    distance_filters: list[DistanceWindowInput] = Field(default_factory=list, description="Distance windows whose atom pairs use the bound reactant's full coordinate order, 1-based, including explicit hydrogen rows.")
```


<a id="s319"></a>

### S319 · `TsConformers`

`cloudra/tools/core/ts_inputs.py:122–125`

```python
class TsConformers(InputModel):
    reactant: ConformerSource | None = None
    product: ConformerSource | None = None
    guidance: ConformerGuidance = Field(default_factory=ConformerGuidance)
```


<a id="s320"></a>

### S320 · `PathSolvation`

`cloudra/tools/core/ts_inputs.py:128–130`

```python
class PathSolvation(InputModel):
    model: Literal["alpb", "gbsa"]
    solvent: str = Field(min_length=1)
```


<a id="s321"></a>

### S321 · `XtbPathGuess`

`cloudra/tools/core/ts_inputs.py:133–137`

```python
class XtbPathGuess(InputModel):
    kind: Literal["xtb_path"]
    method: str = Field(min_length=1)
    solvation: PathSolvation | None = None
    refinement_runs: StrictInt | None = Field(default=None, ge=1, description="xTB path refinement cap; omitted/null uses the runner default of 100. This is a compute limit, not a convergence criterion.")
```


<a id="s322"></a>

### S322 · `ScanGuess`

`cloudra/tools/core/ts_inputs.py:140–194`

```python
class ScanGuess(InputModel):
    kind: Literal["scan"]
    calculation: CalculationValue
    scans: list[ScanCoordinateInput] = Field(min_length=1, max_length=2, description="Coordinates in the concrete scan-input atom order. ORCA references are 0-based; Gaussian/xTB references are 1-based. Convert concrete coordinate indices, not SMILES positions.")
    freeze: list[FrozenCoordinateInput] = Field(default_factory=list, description="Frozen coordinates in the same concrete input atom order and engine-specific numbering as scans.")
    force_constant: float | None = Field(default=None, gt=0, description="xTB restraint force constant in atomic units; explicitly declared")
    mode: Literal["concerted", "sequential", "grid"] | None = Field(default=None, description="Two ORCA coordinates require grid (independent surface) or concerted (simultaneous path, equal steps). xTB supports concerted/sequential. Omit for one coordinate or Gaussian grids.")
    solvation: PathSolvation | None = None

    @model_validator(mode="after")
    def scan_contract(self):
        if isinstance(self.calculation, QmCalculation):
            self.validate_calculation(self.calculation)
        return self

    def validate_calculation(self, calculation: QmCalculation):
        engine = calculation.engine
        if engine != "xtb":
            if self.force_constant is not None or self.solvation is not None:
                raise ValueError("force_constant and solvation are native xTB scan fields")
            if engine == "orca":
                if len(self.scans) == 2:
                    if self.mode not in {"concerted", "grid"}:
                        raise ValueError("Two-coordinate ORCA scans require explicit mode='concerted' (path) or 'grid' (independent surface)")
                    if self.mode == "concerted" and self.scans[0].scan_steps != self.scans[1].scan_steps:
                        raise ValueError("concerted ORCA scans require equal scan_steps")
                elif self.mode is not None:
                    raise ValueError("ORCA scan mode applies only to two scanned coordinates")
            elif self.mode is not None:
                raise ValueError("mode is supported only for native xTB or two-coordinate ORCA scans")
            return self
        if self.mode == "grid":
            raise ValueError("native xTB scans support concerted or sequential, not grid")
        if calculation.method != "GFN2-xTB":
            raise ValueError("native xTB scan currently supports explicitly declared GFN2-xTB")
        if calculation.keywords or calculation.orca_blocks or calculation.end_setting:
            raise ValueError("native xTB scan rejects ORCA/Gaussian directives")
        if self.force_constant is None:
            raise ValueError("force_constant is required for native xTB scan")
        if self.freeze:
            raise ValueError("native xTB scan does not silently reinterpret freeze as a soft restraint")
        if len(self.scans) == 1 and self.mode is not None:
            raise ValueError("mode is derived for a one-coordinate xTB scan")
        if len(self.scans) == 2:
            if self.mode is None:
                raise ValueError("mode is required for two-coordinate xTB scan")
            if self.mode == "concerted" and self.scans[0].scan_steps != self.scans[1].scan_steps:
                raise ValueError("concerted xTB scans require equal scan_steps")
        for row in self.scans:
            if row.scan_start is None or row.scan_steps < 2:
                raise ValueError("native xTB scan requires scan_start and at least two scan points")
        keys = [(row.coord_type, min(tuple(row.atoms), tuple(reversed(row.atoms)))) for row in self.scans]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate scan coordinate")
        return self
```


<a id="s323"></a>

### S323 · `ProvidedGuess`

`cloudra/tools/core/ts_inputs.py:197–200`

```python
class ProvidedGuess(InputModel):
    kind: Literal["provided"]
    xyz_path: str = Field(min_length=1, description="Candidate XYZ in the current bound reactant's full atom order. Coordinates and element labels must refer to the same source atoms; do not combine product-order coordinates with reactant-order labels.")
    evidence_refs: list[str] = Field(min_length=1)
```


<a id="s324"></a>

### S324 · `EndpointSeed`

`cloudra/tools/core/ts_inputs.py:206–210`

```python
class EndpointSeed(InputModel):
    kind: Literal['file']
    xyz_path: str = Field(min_length=1, description='XYZ in the bound endpoint species atom order. The program applies the existing reaction atom map; accepted native IRC endpoint files already use TS working order.')
    mol_path: str | None = Field(default=None, description='MOL defining the XYZ atom order. Use the existing bound species MOL; a MOL already in TS working order is also recognized.')
    evidence_refs: list[str] = Field(min_length=1)
```


<a id="s325"></a>

### S325 · `EndpointVerification`

`cloudra/tools/core/ts_inputs.py:213–216`

```python
class EndpointVerification(InputModel):
    seed: EndpointSeed | None = None
    optimization: CalculationValue | None = None
    frequency: CalculationValue | None = None
```


<a id="s326"></a>

### S326 · `ProductEndpointVerification`

`cloudra/tools/core/ts_inputs.py:219–221`

```python
class ProductEndpointVerification(EndpointVerification):
    component_logs: list[str] = Field(default_factory=list,
        description='Native frequency logs for the independently optimized separated products. The program snapshots the files and matches each real geometry to its declared component; every component must have zero imaginary frequencies. This does not verify a bound complex minimum.')
```


<a id="s327"></a>

### S327 · `TsVerification`

`cloudra/tools/core/ts_inputs.py:224–231`

```python
class TsVerification(InputModel):
    frequency: CalculationValue | None = None
    irc: CalculationValue | None = None
    irc_log: str | None = None
    reactant_endpoint: EndpointVerification = Field(default_factory=EndpointVerification,
        description='The declared reaction.reactant_smiles species, never a fixed IRC A/B direction. An explicit seed uses this species atom order; default IRC sources are provisional until optimization, frequency and direction checks pass.')
    product_endpoint: ProductEndpointVerification = Field(default_factory=ProductEndpointVerification,
        description='The declared reaction.product_smiles species, never a fixed IRC A/B direction. An explicit seed uses this species atom order (or an accepted native IRC working order); the runtime applies the bound atom map.')
```


<a id="s328"></a>

### S328 · `TsExecutionLimits`

`cloudra/tools/core/ts_inputs.py:234–237`

```python
class TsExecutionLimits(InputModel):
    source: str = Field(min_length=1)
    max_compute_actions: StrictInt | None = Field(default=None, ge=0)
    max_model_calls: StrictInt | None = Field(default=None, ge=0)
```


<a id="s329"></a>

### S329 · `TsExecution`

`cloudra/tools/core/ts_inputs.py:240–243`

```python
class TsExecution(InputModel):
    cpus: StrictInt = Field(default=1, ge=1)
    memory_mb: StrictInt = Field(default=4096, ge=1)
    limits: TsExecutionLimits | None = None
```


<a id="s330"></a>

### S330 · `TsInput`

`cloudra/tools/core/ts_inputs.py:246–271`

```python
class TsInput(InputModel):
    reaction: TsReaction
    calculations: dict[str, QmCalculation] = Field(default_factory=dict,
        description='Complete local named calculations. Stages explicitly select a ref; nothing inherits an exploration or formal method automatically.')
    conformers: TsConformers = Field(default_factory=TsConformers)
    guess: TsGuess | None = None
    ts_optimization: CalculationValue | None = None
    verification: TsVerification = Field(default_factory=TsVerification)
    execution: TsExecution = Field(default_factory=TsExecution)

    @model_validator(mode='after')
    def calculation_references(self):
        for name in self.calculations:
            if not name.strip() or name != name.strip():
                raise ValueError('calculation definition names must be nonblank exact names')
        values = [self.ts_optimization, self.verification.frequency, self.verification.irc]
        for role in ('reactant', 'product'):
            endpoint = getattr(self.verification, role + '_endpoint')
            values.extend([endpoint.optimization, endpoint.frequency])
            source = getattr(self.conformers, role)
            values.append(getattr(source, 'optimization', None))
        for value in values:
            resolve_calculation(value, self.calculations)
        if self.guess and self.guess.kind == 'scan':
            self.guess.validate_calculation(resolve_calculation(self.guess.calculation, self.calculations))
        return self
```


## `cloudra/tools/core/ts_process.py`

文件 SHA-256：`5d92cbd59138507089a304e3814750b598c0950c690e62b0ac57f9830bb32d2f`


相关模块级常量 / alias（精确 AST 赋值节点）：


`cloudra/tools/core/ts_process.py:76–79`

```python
TsStage = Literal[
    "declare", "build", "map", "assemble", "guess", "validate",
    "submit", "refine", "verdict",
]
```


`cloudra/tools/core/ts_process.py:80–80`

```python
TsTerminal = Literal["verified", "candidate_only", "search_failed", "invalid_input"]
```


`cloudra/tools/core/ts_process.py:82–82`

```python
PathKind = Literal["", "xtb_path", "xtb_path_failed", "not_attempted", "scan", "provided"]
```


<a id="s331"></a>

### S331 · `TsProcessRecord`

`cloudra/tools/core/ts_process.py:144–220`

```python
class TsProcessRecord(BaseModel):
    """持久运行记录（``ts/<run_id>/process.json``）。"""

    model_config = ConfigDict(extra='forbid')
    format_version: Literal[7] = 7
    run_id: str
    pipeline_id: str = ""
    declaration_revision: int = 1
    optimization_checkpoints: dict[str, OptimizationCheckpoint] = Field(default_factory=dict)
    budget_action_keys: dict[str, str] = Field(default_factory=dict)
    budget_reservations: dict[str, str] = Field(default_factory=dict)
    attempt_history: list[TsAttemptHistory] = Field(default_factory=list)
    catalog_id: str | None = None
    partition_revision: str | None = None
    candidate_attempts: list[AttemptEvidence] = Field(default_factory=list)
    cards_path: str = ""
    product_seed_candidate_id: str | None = None
    selected_candidate_id: str | None = None
    run_dir: str
    workspace_dir: str = Field(default="", description="工作区根（证据快照的沙箱边界）")
    owner_conversation_id: str = Field(
        default="", description="发起项目的 conversation_id（compute_jobs 归属，随记录持久化）"
    )
    owner_session_id: Optional[str] = Field(
        default=None, description="发起 agent 的 session_id（作业终态推送收件人）"
    )
    input: TsInput
    structures: ReactionStructures = Field(default_factory=ReactionStructures)
    provided_guess_binding: TsProvidedGuessBinding | None = None
    failed_attempt: dict | None = None
    method_checks: dict[str, dict] = Field(default_factory=dict)
    warnings: list[dict] = Field(default_factory=list)
    stage: TsStage = "declare"
    stage_records: list[TsStageRecord] = Field(default_factory=list)
    terminal: Optional[TsTerminal] = None
    stop_reason: str | None = None
    blocked: Optional[TsBlocked] = None
    intervention_count: int = 0
    path_kind: PathKind = "not_attempted"
    guidance_attempt: int = 0
    active_attempt_dir: str = ""
    guidance_manifest_path: str = ""
    job_id: Optional[int] = Field(
        default=None, description="提交后的 compute_jobs 作业号（精修作业）"
    )
    job_input_path: str = Field(default="", description="精修输入文件路径")
    waiting_for: str = Field(
        default="",
        description="非空表示正在等某个已提交的作业（如 'job:12'）。**等计算不是阻塞**："
                    "不推事件、不需要 agent 做决策；作业终态由既有 compute 通知路径投递",
    )
    scan_step: Optional["TsJobStep"] = None
    job_steps: list["TsJobStep"] = Field(
        default_factory=list,
        description="精修作业序列（TS Opt/Freq → IRC → 两端 Opt/Freq），每步记 job_id/输入/状态",
    )
    #: 可进入证据集的小产物。**逐迭代帧永远不在这里**（SOP §7 第 2 条）
    evidence_candidates: list[str] = Field(default_factory=list)
    revision: int = 0

    @property
    def compute_cpus(self):
        return self.input.execution.cpus

    @property
    def compute_memory_mb(self):
        return self.input.execution.memory_mb

    @property
    def is_terminal(self) -> bool:
        return self.terminal is not None

    def stage_record(self, stage: TsStage) -> TsStageRecord:
        for record in self.stage_records:
            if record.stage == stage:
                return record
        raise KeyError(f"no record for stage {stage!r}")
```


<a id="s332"></a>

### S332 · `_write_immutable_input`

`cloudra/tools/core/ts_process.py:272–280`

```python
def _write_immutable_input(path: str, content: str | bytes) -> None:
    """A bound engine input may be retried, never silently overwritten."""
    data = content.encode('utf-8') if isinstance(content, str) else content
    existing = Path(path)
    if existing.exists():
        if existing.read_bytes() != data:
            raise ValueError('immutable stage input conflict')
        return
    atomic_write_bytes(path, data)
```


<a id="s333"></a>

### S333 · `stage_calculation`

`cloudra/tools/core/ts_process.py:435–454`

```python
def stage_calculation(record: TsProcessRecord, purpose: str) -> QmCalculation | None:
    if purpose == 'ts_opt':
        value = record.input.ts_optimization
    elif purpose in ('frequency', 'irc'):
        value = getattr(record.input.verification, purpose)
    elif purpose in ('reactant_opt', 'product_opt', 'reactant_frequency', 'product_frequency'):
        side, task = purpose.split('_', 1)
        value = getattr(getattr(record.input.verification, side + '_endpoint'), 'optimization' if task == 'opt' else task)
    elif purpose == 'scan':
        guess = record.input.guess
        value = guess.calculation if guess and guess.kind == 'scan' else None
    elif purpose == 'path':
        guess = record.input.guess
        value = QmCalculation(engine='xtb', method=guess.method, basis_set='', keywords='') if guess and guess.kind == 'xtb_path' else None
    elif purpose in ('candidate_opt', 'candidate_evaluation', 'product_seed_opt'):
        source = getattr(record.input.conformers, 'product' if purpose == 'product_seed_opt' else 'reactant')
        value = getattr(source, 'optimization', None)
    else:
        return None
    return resolve_calculation(value, record.input.calculations)
```


<a id="s334"></a>

### S334 · `_record_calculation_warnings`

`cloudra/tools/core/ts_process.py:1535–1545`

```python
def _record_calculation_warnings(record, purpose, input_path, issues, *, source):
    """Replace current advice per stage/source; preserve it in the durable model receipt."""
    record.warnings = [item for item in record.warnings
        if item.get('input_revision') == record.declaration_revision
        and (item.get('purpose'), item.get('source')) != (purpose, source)]
    for issue in issues:
        item = dict(issue, severity='warning', purpose=purpose, input_path=str(input_path),
            input_revision=record.declaration_revision, source=source)
        if item not in record.warnings:
            record.warnings.append(item)
    record.warnings = record.warnings[-100:]
```


<a id="s335"></a>

### S335 · `_writer_request_errors`

`cloudra/tools/core/ts_process.py:1548–1553`

```python
def _writer_request_errors(record, purpose, request):
    from cloudra.tools.core.calculation_intent import validate_writer_request
    issues = validate_writer_request(request.model_dump())
    _record_calculation_warnings(record, purpose, request.output_path,
        [item for item in issues if item['severity'] == 'warning'], source='writer')
    return [item for item in issues if item['severity'] == 'error']
```


<a id="s336"></a>

### S336 · `_writer_render_error`

`cloudra/tools/core/ts_process.py:1556–1566`

```python
def _writer_render_error(record, purpose, request, content):
    """Expose native uncertainty while preserving the shared renderer-integrity check."""
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter
    from cloudra.tools.core.calculation_intent import inspect_input
    issues = []
    if inspect_input(content, engine=request.engine).certainty == 'unknown':
        issues.append(dict(code='native_task_uncertain', field='keywords',
            message='The preserved native parameters could not be classified; inspect native engine diagnostics before accepting scientific evidence.'))
    _record_calculation_warnings(record, purpose, request.output_path, issues, source='inspection')
    errors = QmInputWriter.validate_rendered_input(request, content, charge=request.charge)
    return 'input internal mismatch: ' + ' | '.join(errors) if errors else ''
```


<a id="s337"></a>

### S337 · `_stage_writer_tasks`

`cloudra/tools/core/ts_process.py:1569–1578`

```python
def _stage_writer_tasks(calculation, default_tasks):
    """A stage supplies its basic task only in the absence of a native declaration."""
    from cloudra.tools.core.calculation_intent import declared_native_tasks
    tasks, unknown = declared_native_tasks(calculation.model_dump())
    if tasks or unknown:
        return calculation, []
    if calculation.engine == 'gaussian' and default_tasks == [{'irc': None}]:
        suboptions, remaining, _ = _extract_gaussian_irc_keywords(calculation.keywords)
        return calculation.model_copy(update={'keywords': remaining}), [{'irc': suboptions}]
    return calculation, default_tasks
```


<a id="s338"></a>

### S338 · `TsJobStep`

`cloudra/tools/core/ts_process.py:1709–1726`

```python
class TsJobStep(BaseModel):
    """精修作业序列里的一步（TS、IRC 与两端极小值验证）。"""

    purpose: Literal[
        "sampling", "path", "candidate_opt", "candidate_evaluation", "product_seed_opt", "scan", "ts_opt", "frequency", "irc", "reactant_opt", "reactant_frequency",
        "product_opt", "product_frequency",
    ]
    job_id: Optional[int] = None
    input_path: str = ""
    state: str = Field(default="", description="compute_jobs 里的状态；终态见 TERMINAL_STATES")
    actual_calculation: QmCalculation | None = None
    source_input_revision: int = 1
    method_contract: dict | None = None
    stage_key: str | None = None
    external_source: dict | None = None
    endpoint_source: EndpointSource | None = None
    atom_binding: dict | None = None
    frequency_analysis: dict | None = None
```


<a id="s339"></a>

### S339 · `_check_calculation_submission`

`cloudra/tools/core/ts_process.py:1853–1948`

```python
def _check_calculation_submission(record, purpose, input_path, job_type):
    from cloudra.runtime_v2.method_policy import check_input_content, check_method
    from cloudra.services.ts_pipeline_context import require_pipeline_authority
    from cloudra.tools.core.calculation_intent import MethodDifference, compare_calculation_input
    policy = require_pipeline_authority(record.owner_conversation_id, record.owner_session_id)
    calculation = stage_calculation(record, purpose)
    if calculation is None:
        raise ValueError(f"{purpose} has no explicit calculation")
    content = Path(input_path).read_text()
    if policy is not None:
        verdict = (check_method(calculation.method, policy) if job_type == 'chem_task' else
            check_input_content(content, policy, filename=input_path, strict=True))
        if not verdict.allowed:
            raise ValueError(verdict.reason)
    issues = []
    trusted_differences = []
    if job_type == 'chem_task':
        from cloudra.runtime.chem_task import ChemTask
        task = ChemTask.model_validate_json(content)
        expected_task = dict(path='xtb_path', scan='xtb_scan', candidate_opt='xtb_opt', product_seed_opt='xtb_opt')
        allowed_tasks = {'xtb_gradient', 'xtb_hessian'} if purpose == 'candidate_evaluation' else {expected_task.get(purpose)}
        if calculation.engine != 'xtb' or calculation.method != 'GFN2-xTB' or calculation.keywords or calculation.orca_blocks or calculation.end_setting:
            raise ValueError('Native chemistry task contract supports explicit GFN2-xTB with no native ORCA/Gaussian directives')
        if _open_shell_singlet(record):
            raise ValueError('The native GFN task cannot represent the accepted open-shell singlet electronic state')
        if task.task not in allowed_tasks or (task.charge, task.multiplicity, task.electronic_character, task.cpus) != (record.input.reaction.charge, record.input.reaction.multiplicity, record.input.reaction.electronic_character, record.compute_cpus):
            raise ValueError('Native chemistry task/charge/multiplicity/electronic character/resources differ from accepted input')
        solvation = task.solvation.model_dump() if task.solvation else None
        expected_solvation = record.input.guess.solvation.model_dump() if purpose == 'path' and record.input.guess.solvation else None
        if solvation != expected_solvation:
            raise ValueError('Native task solvation differs from its own accepted stage input')
        if purpose == 'scan':
            plan = record.input.guess.model_copy(update={'calculation': calculation})
            if task.scan != plan or task.reactant_xyz != Path(_read_built_xyz(record, 'reactant')[2]).read_text():
                raise ValueError('Native scan declaration or bound XYZ differs from accepted input')
        contract = policy.calculation_contracts.get(purpose) if policy is not None else None
        if contract:
            actual = {**calculation.model_dump(mode='json'),
                'charge': task.charge, 'multiplicity': task.multiplicity, 'cpus': task.cpus,
                'scan': task.scan.model_dump(mode='json') if task.scan else None,
                'force_constant': task.scan.force_constant if task.scan else None,
                'mode': task.scan.mode if task.scan else None,
                'solvation': task.scan.solvation.model_dump(mode='json') if task.scan and task.scan.solvation else solvation}
            mismatched = [key for key, value in contract.items() if key not in actual or actual[key] != value]
            if mismatched:
                raise ValueError(f'Native task differs from trusted {purpose} calculation contract: {mismatched}')
        differences = []
    else:
        if job_type != calculation.engine:
            raise ValueError('Actual engine differs from accepted stage input')
        from cloudra.tools.core.calculation_intent import inspect_input
        actual_intent = inspect_input(content, engine=job_type)
        expected_tasks = {'scan': {'relaxed_scan'}, 'ts_opt': {'ts_opt'}, 'frequency': {'frequency'},
            'irc': {'irc'}, 'reactant_opt': {'minimum_opt'}, 'product_opt': {'minimum_opt'},
            'reactant_frequency': {'frequency'}, 'product_frequency': {'frequency'},
            'candidate_opt': {'minimum_opt'}, 'product_seed_opt': {'minimum_opt'}}
        if actual_intent.tasks != expected_tasks.get(purpose, set()):
            issues.append(dict(code='purpose_task_mismatch', field='task_type',
                message=f'Actual task {sorted(actual_intent.tasks)} differs from accepted purpose {purpose}; the native declaration was preserved.'))
        differences = compare_calculation_input(content, calculation.model_dump(), charge=record.input.reaction.charge, multiplicity=record.input.reaction.multiplicity)
        # Complete task/user contracts, when present, come from project settings.
        contract = policy.calculation_contracts.get(purpose) if policy is not None else None
        if contract:
            from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
            from cloudra.tools.core.calculation_intent import declared_native_tasks
            expected_contract = contract
            if 'task_type' in contract:
                template = {key: value for key, value in contract.items()
                    if key in QmInputWriter_input_schema.model_fields}
                template.update(source_type='xyz_file', source_value=input_path, output_path=input_path)
                template.setdefault('charge', record.input.reaction.charge)
                template.setdefault('multiplicity', record.input.reaction.multiplicity)
                written = QmInputWriter._written_calculation(QmInputWriter_input_schema.model_validate(template))
                expected_contract = {**contract, 'keywords': written.keywords,
                    'orca_blocks': written.orca_blocks, 'end_setting': written.end_setting}
            trusted_differences = compare_calculation_input(content, expected_contract,
                charge=contract.get('charge', record.input.reaction.charge),
                multiplicity=contract.get('multiplicity', record.input.reaction.multiplicity))
            contract_tasks, _ = declared_native_tasks(contract)
            if contract_tasks and actual_intent.tasks != contract_tasks:
                trusted_differences.append(MethodDifference(field='task_type', expected=sorted(contract_tasks),
                    actual=sorted(actual_intent.tasks), message='Native task differs from the trusted calculation contract.'))
            differences += trusted_differences
    result = dict(input_revision=record.declaration_revision, purpose=purpose, actual=calculation.model_dump(),
        source='project_method_policy' if policy is not None else 'stage_declaration',
        differences=[d.model_dump() for d in differences], matched=not differences and not issues)
    record.method_checks[input_path] = result
    issues += [dict(code='native_calculation_difference', field=item.field, message=item.message)
        for item in differences]
    _record_calculation_warnings(record, purpose, input_path, issues, source='submission')
    if trusted_differences:
        raise ValueError(f'Native input differs from trusted {purpose} calculation contract: ' +
            '; '.join(item.message for item in trusted_differences))
    structural = [item for item in differences if item.field in {'engine', 'charge', 'multiplicity'}]
    if structural:
        raise ValueError('; '.join(item.message for item in structural))
```


<a id="s340"></a>

### S340 · `_submit_step`

`cloudra/tools/core/ts_process.py:1950–2027`

```python
def _submit_step(record: TsProcessRecord, purpose: str, input_path: str,
                 job_type: str, *, stage_key: str | None = None, action_kind: str | None = None,
                 ) -> tuple[str, int]:
    """准入 + 入库为 ready，并把这一步登记进作业序列。返回 ``(错误, job_id)``。

    归属与 ``submit_compute_job`` 同一纪律：conversation_id 是发起项目、
    session_id 是发起 agent——终态推送（ComputeNotifyBroker）只认这两个字段，
    缺归属的作业是投递不到的死信，宁可拒收也不入库。
    """
    from cloudra.services.compute_admission import admit_job
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.ts_pipeline_context import pipeline_database

    if not record.owner_conversation_id:
        return (
            "this run carries no owner identity (owner_conversation_id is empty), so its "
            "compute jobs would be undeliverable dead letters; refusing to submit. Start the "
            "run through ts_prepare so the calling project/agent is stamped.",
            -1,
        )

    try:
        _check_calculation_submission(record, purpose, input_path, job_type)
    except (ValueError, OSError) as exc:
        return str(exc), -1

    # charge/multiplicity 是 xtb 专属运行参数，orca/gaussian 作业必须留默认——电荷/自旋已经
    # 写在输入文件里，再传一次会被准入 fail-loud 拒收（"绝不静默丢弃"那道门）
    admission = admit_job(
        input_file=input_path,
        job_type=job_type,
        cpus=record.compute_cpus,
        memory_mb=record.compute_memory_mb,
        execution_backend="auto",
    )
    if not admission.ok:
        return admission.message, -1

    db = pipeline_database().init()
    payload = dict(
        conversation_id=record.owner_conversation_id,
        session_id=record.owner_session_id,
        path=input_path,
        state="ready",
        jobtype=job_type,
        node_id=admission.node_id,
        scheduler=admission.scheduler,
        scheduler_options=json.dumps(admission.scheduler_options, ensure_ascii=False),
        priority=0,
        req_cpus=record.compute_cpus,
        req_memory_mb=record.compute_memory_mb,
    )
    if record.pipeline_id:
        from cloudra.services.ts_pipeline_store import bind_stage_job
        effective_stage = stage_key or purpose
        binding = {}
        if record.input.execution.limits is not None:
            from cloudra.services.exploration_budget_store import CostEstimate, reserve_actions
            stages = ['ts_opt','frequency','irc','reactant_opt','reactant_frequency','product_opt','product_frequency'] if purpose == 'ts_opt' else [purpose,purpose.removesuffix('_opt')+'_frequency'] if purpose in ('reactant_opt','product_opt') else [effective_stage]
            tag=f"{record.declaration_revision}:{record.selected_candidate_id or record.run_id}"
            keys={stage:f'{tag}:{stage}' for stage in stages}
            # Subsequent stages consume the previously reserved validation chain.
            if effective_stage not in record.budget_action_keys:
                try:
                    reserved=reserve_actions(db,process_id=record.pipeline_id,decision_id=f'validation:{tag}' if purpose=='ts_opt' else f'{tag}:{effective_stage}',estimates=[CostEstimate(
                        action_key=keys[stage],action_kind=action_kind or ('sampling' if stage=='sampling' else 'path' if stage=='path' else 'ts' if stage=='ts_opt' else 'irc' if stage=='irc' else 'frequency' if 'frequency' in stage else 'optimization'),
                        source='ts_action_count') for stage in stages])
                except ValueError as exc:
                    return str(exc), -1
                for stage in stages:
                    record.budget_action_keys[stage]=keys[stage]
                    record.budget_reservations[stage]=reserved.reservation_id
            binding=dict(reservation_id=record.budget_reservations[effective_stage],action_key=record.budget_action_keys[effective_stage])
        job_id = bind_stage_job(db, process_id=record.pipeline_id, declaration_revision=record.declaration_revision,
                               stage_key=effective_stage, attempt=1, job_payload=payload, **binding)
    else:
        job_id = int(insert_compute_job(db, **payload))
    return "", job_id
```


<a id="s341"></a>

### S341 · `_write_irc_input`

`cloudra/tools/core/ts_process.py:2251–2298`

```python
def _write_irc_input(record: TsProcessRecord, job_dir: str) -> tuple[str, str]:
    """Write the declared IRC using the accepted frequency geometry."""
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema

    declaration = record.input.reaction
    calculation = stage_calculation(record, 'irc')
    if calculation is None:
        return 'Explicit verification.irc required', ''
    frequency_step = next(
        (step for step in record.job_steps if step.purpose == "frequency"), None
    )
    if frequency_step is None:
        return "no frequency job was run, so its same-geometry Hessian cannot be reused", ""
    geometry = os.path.join(os.path.dirname(frequency_step.input_path), "optimized.xyz")
    if not os.path.isfile(geometry):
        return (
            f"the optimised geometry kept next to the frequency job ({geometry}) is missing; "
            "refusing to start IRC from an unverified geometry",
            "",
        )

    input_path = os.path.join(job_dir, f"irc.{'inp' if calculation.engine == 'orca' else 'gjf'}")

    calc_copy, task_type = _stage_writer_tasks(calculation, [{'irc': None}])
    request = QmInputWriter_input_schema(
        **calc_copy.model_dump(mode='json'),
        nproc=record.compute_cpus,
        mem=f"{record.compute_memory_mb}MB",
        source_type="xyz_file",
        source_value=geometry,
        task_type=task_type,
        charge=declaration.charge,
        multiplicity=declaration.multiplicity,
        electronic_character=declaration.electronic_character,
        title=f"IRC from the refined saddle: {declaration.reactant_smiles} | smiles: {declaration.reactant_smiles}",
        output_path=input_path,
    )
    conflicts = _writer_request_errors(record, 'irc', request)
    if conflicts:
        return "IRC input refused: " + " | ".join(
            f"[{c['code']}] {c['message']}" for c in conflicts
        ), ""
    content = QmInputWriter.render_input(request, read_molecule(geometry, charge=declaration.charge))
    error = _writer_render_error(record, 'irc', request, content)
    if error:
        return error, ''
    _write_immutable_input(input_path, content)
    return "", input_path
```


<a id="s342"></a>

### S342 · `_refine`

`cloudra/tools/core/ts_process.py:2623–2850`

```python
def _refine(record: TsProcessRecord) -> TsProcessRecord:
    """推进 TS Opt/Freq → IRC → 端点验证；分离产物复用独立组分日志。**从不轮询**。

    还没到终态时本阶段置 ``waiting`` 并**不推事件**：等计算不算"阻塞"，agent 不该被叫醒。
    作业终态由既有的 compute 通知路径交给系统 driver，
    系统 driver 重新读账本并推进；agent 可在任务尚未启动时主动修订输入。
    """
    from cloudra.services.compute_store import TERMINAL_STATES

    if not record.job_steps:
        return _block(
            record, "refine", "no_job_submitted",
            "the submit stage recorded no job, so there is nothing to refine",
            needs=["method", "engine"],
        )

    # A local endpoint revision can retain the opposite endpoint. Resume from
    # the last contiguous predecessor, rather than whichever job was appended
    # last in an earlier input revision.
    current = None
    separated_products = bool(record.input.verification.product_endpoint.component_logs) or (
        isinstance(record.input.reaction.product_smiles, list) and len(record.input.reaction.product_smiles) > 1)
    formal_order = ('ts_opt', 'frequency', 'irc', 'reactant_opt', 'reactant_frequency')
    if not separated_products:
        formal_order += ('product_opt', 'product_frequency')
    first = next((i for i, purpose in enumerate(formal_order) if any(s.purpose == purpose for s in record.job_steps)), len(formal_order))
    for purpose in formal_order[first:]:
        step = next((s for s in reversed(record.job_steps) if s.purpose == purpose), None)
        if step is None:
            break
        current = step
        if _step_state(record, step) != 'done':
            break
    if current is None:
        return _block(record, 'refine', 'no_job_submitted', 'A TS optimization is required before verification.', needs=['ts_optimization'])
    state = _step_state(record, current)
    current.state = state
    if state not in TERMINAL_STATES:
        record.waiting_for = f"job:{current.job_id}"
        _record_stage(
            record, "refine", "waiting",
            f"waiting for job {current.job_id} ({current.purpose}) to reach a terminal state; "
            "the existing compute notification path advances the system driver, so this stage never polls "
            "and emits no event",
        )
        return record

    record.waiting_for = ""
    if state != "done":
        log_path = _refinement_log_path(record, current)
        failure, details = _native_failure_details(log_path, _step_calculation(record, current).engine)
        _record_candidate_failure(record, failure, current, log_path, details)
        return _block(
            record, "refine", f"job_{state}",
            f"refinement job {current.job_id} ({current.purpose}) ended as {state!r}; plain "
            "per-engine failure classes come from the log below — the run is stopped, not silently "
            "retried",
            atom_details=details,
            needs=[_calculation_field(current.purpose), "execution", "reaction.reaction_center"],
        )

    if current.purpose == "ts_opt":
        if _require_calculation(record, 'frequency', 'refine'):
            return record
        # 优化完成：取优化末帧写频率作业（频率是独立作业，见 skill）
        job_dir = _job_directory(record, "frequency")
        os.makedirs(job_dir, exist_ok=True)
        error, input_path = _write_frequency_input(record, job_dir)
        if error:
            return _block(
                record, "refine", "frequency_input_failed", error, needs=["method", "engine"]
            )
        job_type = stage_calculation(record, 'frequency').engine
        error, job_id = _submit_step(record, "frequency", input_path, job_type)
        if error:
            return _block(
                record, "refine", "compute_admission_rejected", error,
                needs=["method", "engine", "budget"],
            )
        record.job_steps.append(TsJobStep(
            purpose="frequency", job_id=job_id, input_path=input_path, state="ready",
            actual_calculation=stage_calculation(record, 'frequency'), source_input_revision=record.declaration_revision,
        atom_binding=_direction_atom_binding(record)))
        record.waiting_for = f"job:{job_id}"
        _record_stage(
            record, "refine", "waiting",
            f"TS optimisation converged (job {current.job_id}); frequency job {job_id} submitted on "
            "the optimised geometry. Waiting for its terminal state via the existing notification "
            "path",
            [input_path],
        )
        return record

    if current.purpose == "frequency":
        # The frequency-verified TS geometry anchors the declared IRC calculation.
        from cloudra.dag.evidence_ingest import snapshot_evidence_file
        log_path = _refinement_log_path(record, current)
        if not Path(log_path).is_file():
            return _block(record, 'refine', 'frequency_evidence_missing',
                          'TS frequency log is missing; IRC cannot be admitted.', needs=['compute_artifacts'])
        snapshot = snapshot_evidence_file(log_path, workspace_root=record.workspace_dir)
        if snapshot.frequencies is None and snapshot.imaginary_frequencies is None:
            return _block(record, 'refine', 'frequency_evidence_missing',
                          'TS frequency data is unavailable; IRC cannot be admitted.', needs=['compute_artifacts'])
        _record_frequency_analysis(record, current, log_path, snapshot)
        imaginary = snapshot.imaginary_frequencies if snapshot.imaginary_frequencies is not None else [f for f in snapshot.frequencies if f < 0]
        if len(imaginary) != 1:
            _record_candidate_failure(record, 'wrong_mode', current, log_path)
            return _block(record, 'refine', 'wrong_mode',
                          f'TS frequency evidence has {len(imaginary)} imaginary modes; exactly one is required before IRC.', needs=['conformers', 'guess', 'verification.frequency'])
        if _require_calculation(record, 'irc', 'refine'):
            return record
        if record.input.verification.irc_log:
            try:
                record.job_steps.append(_reuse_existing_irc(record))
            except (ValueError, OSError) as exc:
                return _block(record, 'refine', 'irc_source_unconfirmed', str(exc), needs=['verification.irc_log', 'verification.irc'])
            return _refine(record)
        job_dir = _job_directory(record, "irc")
        os.makedirs(job_dir, exist_ok=True)
        error, input_path = _write_irc_input(record, job_dir)
        if error:
            return _block(record, "refine", "irc_input_failed", error, needs=["method", "engine"])
        job_type = stage_calculation(record, 'irc').engine
        error, job_id = _submit_step(record, "irc", input_path, job_type)
        if error:
            return _block(
                record, "refine", "compute_admission_rejected", error,
                needs=["method", "engine", "budget"],
            )
        record.job_steps.append(TsJobStep(
            purpose="irc", job_id=job_id, input_path=input_path, state="ready",
            actual_calculation=stage_calculation(record, 'irc'), source_input_revision=record.declaration_revision,
        atom_binding=_direction_atom_binding(record)))
        record.waiting_for = f"job:{job_id}"
        _record_stage(
            record, "refine", "waiting",
            f"frequency job {current.job_id} finished; IRC job {job_id} submitted "
            "from the same optimised geometry. Waiting for its terminal state via the "
            "existing notification path",
            [input_path],
        )
        return record

    if current.purpose in ("reactant_frequency", "product_frequency"):
        role = "reactant" if current.purpose.startswith("reactant") else "product"
        _minimum, reason = _validated_endpoint_minimum(record, role)
        if _minimum is None:
            _record_candidate_failure(record, 'endpoint_unconfirmed', current, _refinement_log_path(record, current))
            origin = current.endpoint_source
            source = f'IRC side {origin.label}' if origin and origin.kind == 'irc_outer_frame' else 'explicit species seed'
            return _terminal(
                record, "verdict", "candidate_only",
                f"The {role} endpoint candidate from {source} did not qualify as an "
                f"optimized minimum: {reason}. Repair verification.{role}_endpoint.seed "
                f"for the declared {role} {getattr(record.input.reaction, role + '_smiles')}; "
                "IRC A/B labels do not declare species identity.",
            )

    endpoint_next = {
        "irc": ("reactant", "opt"),
        "reactant_opt": ("reactant", "frequency"),
        "reactant_frequency": ("product", "opt"),
        "product_opt": ("product", "frequency"),
    }.get(current.purpose)
    if separated_products and current.purpose == 'reactant_frequency':
        endpoint_next = None
    while endpoint_next is not None:
        role, task=endpoint_next
        purpose=role+'_'+task
        existing=next((s for s in reversed(record.job_steps) if s.purpose==purpose),None)
        if existing is None:
            break
        existing.state=_step_state(record,existing)
        if existing.state=='done':
            endpoint_next={"reactant_opt":("reactant","frequency"),"reactant_frequency":("product","opt"),"product_opt":("product","frequency")}.get(purpose)
            continue
        if existing.state not in TERMINAL_STATES:
            record.waiting_for=f'job:{existing.job_id}'
            return record
        _record_candidate_failure(record, 'endpoint_failed', existing, _refinement_log_path(record, existing))
        return _block(record,'refine','endpoint_failed','Existing endpoint attempt failed; revise or retry through ts_resume.',needs=[f'verification.{role}_endpoint'])
    if endpoint_next is not None:
        role, task = endpoint_next
        purpose = f'{role}_{task}'
        if _require_calculation(record, purpose, 'refine'):
            return record
        job_dir = _job_directory(record, f"{role}_{task}")
        os.makedirs(job_dir, exist_ok=True)
        error, input_path = _write_endpoint_input(record, job_dir, role, task)
        if error:
            if task == "frequency":
                return _terminal(
                    record, "verdict", "candidate_only",
                    f"{role} endpoint optimization cannot support a minimum: {error}. "
                    "Revise this run with an explicit endpoint seed through ts_resume",
                )
            return _block(
                record, "refine", "endpoint_input_failed", error,
                needs=[f"verification.{role}_endpoint", f"reaction.{role}_smiles"],
            )
        job_type = stage_calculation(record, purpose).engine
        purpose = f"{role}_{task}"
        error, job_id = _submit_step(record, purpose, input_path, job_type)
        if error:
            return _block(
                record, "refine", "compute_admission_rejected", error,
                needs=["method", "engine", "budget"],
            )
        record.job_steps.append(TsJobStep(
            purpose=purpose, job_id=job_id, input_path=input_path, state="ready",
            actual_calculation=stage_calculation(record, purpose), source_input_revision=record.declaration_revision,
            endpoint_source=EndpointSource.model_validate_json(Path(job_dir, 'endpoint_source.json').read_text()),
        atom_binding=_direction_atom_binding(record)))
        record.waiting_for = f"job:{job_id}"
        _record_stage(
            record, "refine", "waiting",
            f"Endpoint {role} {task} job {job_id} "
            "submitted; awaiting its compute notification",
            [input_path],
        )
        return record

    _record_stage(
        record, "refine", "done",
        f"refinement sequence complete: {[step.purpose for step in record.job_steps]}",
    )
    return record
```


## `cloudra/calculator.sh`

Bash 无 Python AST；按完整入口块、函数与 dispatch 逐字切片。SHA-256：`3208cf252ce7fdfef9fcc4c57ec780bcee6fdb607214a8fb339c3c8c32d65f18`。


### `入口参数、输入文件检查与工作目录转换`

`cloudra/calculator.sh:18–36`

```bash
set -e

INPUT_FILE="$1"
JOB_TYPE="$2"

if [ -z "$INPUT_FILE" ] || [ -z "$JOB_TYPE" ]; then
    echo "用法: calculator.sh <input_file> <job_type> [xtb: --chrg N --uhf M --task T --parallel N [--alpb NAME]]" >&2
    exit 1
fi

if [ ! -f "$INPUT_FILE" ]; then
    echo "输入文件不存在: $INPUT_FILE" >&2
    exit 1
fi

shift 2

WORKDIR=$(cd "$(dirname "$INPUT_FILE")" && pwd)
cd "$WORKDIR"
```


### `run_gaussian`

`cloudra/calculator.sh:38–76`

```bash
run_gaussian() {
    # Gaussian 可执行文件通常命名为 g16/g09/g26。
    # 统一通过系统 PATH 调用，不依赖工作目录下的本地副本。
    #
    # Link0 会把 .gjf 拷到 $GAUSS_SCRDIR/Gau-$PID.inp。多个本地任务若共用
    # 同一个 GAUSS_SCRDIR（常见全局 ~/…/Utsu），并行时会互相踩 rwf/chk/inp，
    # 表现为 Link1 后立刻 FileIO、日志只有一百多行、零 SCF——不是输入写错。
    # guard 已分配 cloudra_g16_* 时直接用；否则自建子目录，EXIT 后再删。
    local base_scr="${GAUSS_SCRDIR:-$WORKDIR/.g16_scratch}"
    local job_scr
    local own_scratch=0
    if [[ "$(basename -- "$base_scr")" == cloudra_g16_* ]]; then
        job_scr="$base_scr"
        mkdir -p "$job_scr"
    else
        mkdir -p "$base_scr"
        job_scr="${base_scr%/}/cloudra_g16_$$"
        mkdir -p "$job_scr"
        own_scratch=1
    fi
    export GAUSS_SCRDIR="$job_scr"
    if [ "$own_scratch" -eq 1 ]; then
        # shellcheck disable=SC2064
        trap "rm -rf -- $(printf '%q' "$job_scr")" EXIT
    fi
    echo "[calculator] isolated GAUSS_SCRDIR=$GAUSS_SCRDIR" >&2

    if command -v g16 >/dev/null 2>&1; then
        g16 "$INPUT_FILE"
    elif command -v g09 >/dev/null 2>&1; then
        g09 "$INPUT_FILE"
    elif command -v g26 >/dev/null 2>&1; then
        g26 "$INPUT_FILE"
    else
        echo "系统 PATH 中未找到 Gaussian 可执行文件（g16/g09/g26）。" \
             "请安装 Gaussian 并确保对应命令在 PATH 中可用。" >&2
        exit 1
    fi
}
```


### `_resolve_symlink_chain`

`cloudra/calculator.sh:78–97`

```bash
_resolve_symlink_chain() {
    # 把符号链接链展开为真实文件的绝对路径并打印；任一环节失败（悬挂链接、
    # 目录不可达）返回非零。纯 POSIX 展开：不依赖 GNU readlink -f（macOS 无
    # 此选项），也不依赖 python3（guard 环境未必有）。
    local path="$1"
    local link dir
    while [ -L "$path" ]; do
        link=$(readlink "$path") || return 1
        case "$link" in
            /*) path="$link" ;;
            *)
                dir=$(cd "$(dirname "$path")" 2>/dev/null && pwd) || return 1
                path="$dir/$link"
                ;;
        esac
    done
    [ -e "$path" ] || return 1
    dir=$(cd "$(dirname "$path")" 2>/dev/null && pwd) || return 1
    printf '%s/%s\n' "$dir" "$(basename "$path")"
}
```


### `run_orca`

`cloudra/calculator.sh:99–207`

```bash
run_orca() {
    # ORCA external MLIP（输入含 `%method ProgExt`，如 MACE-OMol25）会把能量/梯度
    # 卸载给 Python 侧的 mace/ase：macOS 上其 libomp 与 ORCA 自带 OpenMP 重复装载
    # 会报 OMP Error #15，且 MACE 需要单线程调用（OMP Error #15 探针见
    # deploy/mace_omol25_orca_external_setup.md §3.1）。仅在输入声明外部 MLIP 时注入，
    # 普通 DFT 任务不设 OMP_NUM_THREADS=1，避免锁死 ORCA 的 OpenMP 线程层。
    if grep -qE 'ExtOpt|ProgExt' "$INPUT_FILE"; then
        export KMP_DUPLICATE_LIB_OK=TRUE
        export OMP_NUM_THREADS=1
        echo "[calculator] MLIP external route detected: KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1" >&2
    fi

    local orca_bin=""
    if command -v orca >/dev/null 2>&1; then
        orca_bin=$(command -v orca)
    elif [ -x "./orca" ]; then
        orca_bin="$WORKDIR/orca"
    else
        # command -v 对悬挂符号链接也报找不到（bash 要求可执行）：手工扫 PATH
        # 找回同名条目，交给下方解析/调用阶段给出明确诊断（解析失败回退裸调用，
        # exec 悬挂链接失败按 127 传播，而不是误报"未安装 orca"，GH #15）。
        local _dir
        for _dir in ${PATH//:/ }; do
            if [ -L "$_dir/orca" ] || [ -e "$_dir/orca" ]; then
                orca_bin="$_dir/orca"
                break
            fi
        done
        if [ -z "$orca_bin" ]; then
            echo "系统 PATH 中未找到 orca，运行目录 $WORKDIR 下也无 ./orca 本地副本。" \
                 "请安装 ORCA 并确保 orca 命令在 PATH 中可用，或将 orca 复制到作业目录。" >&2
            exit 1
        fi
    fi

    # 解析符号链接链到真实安装路径，并把真实目录 prepend 到 PATH：
    # 并行 ORCA 拒绝裸名启动（"For parallel runs ORCA has to be called with
    # full pathname"，exit 126），helpers（orca_util/orca_scf/...）也按 orca
    # 可执行文件所在目录定位——conda 符号链接场景两者都会踩（GH #15）。
    # 解析失败（悬挂链接等）时回退裸调用，维持修复前行为。
    local orca_resolved
    if orca_resolved=$(_resolve_symlink_chain "$orca_bin"); then
        orca_bin="$orca_resolved"
        export PATH="$(dirname "$orca_bin"):$PATH"
        echo "[calculator] orca resolved: $orca_bin" >&2
    else
        echo "[calculator] orca 路径解析失败，回退裸调用: $orca_bin" >&2
    fi
    # 显式传播 orca 退出码：bash 3.2（macOS 自带）在 set -e 语义下（含 || 捕获）
    # 会把命令失败的状态统一改写成 1，吞掉 exec 失败的 127 与 orca 真实退出码；
    # 只能暂时关 set -e 取到真实状态再退出（GH #15）。
    #
    # WORKDIR 已切到输入目录。总是用同目录 basename：既避免 ORCA 对
    # 含空白父路径拆词，也避免原生 PropertyIntegralDriver 在长绝对输入
    # 参数下触发栈溢出（相同输入字节的真实 A/B：绝对参数 SIGABRT，basename 正常）。
    # 二进制仍用真实完整路径，满足并行启动要求；原始输入和证据路径不变。
    # basename 本身含空白时继续使用作业目录内的硬链接安全名，并在日志留映射。
    local input_arg
    input_arg=$(basename "$INPUT_FILE")
    local original_stem="${input_arg%.*}"
    local safe_input_name=""
    local safe_stem=""
    case "$input_arg" in
        *[[:space:]]*)
            safe_input_name=$(printf '%s' "$input_arg" | tr '[:space:]' '_')
            safe_input_name=".cloudra_orasafe_$$_$safe_input_name"
            ln "$INPUT_FILE" "$WORKDIR/$safe_input_name"
            input_arg="$safe_input_name"
            safe_stem="${safe_input_name%.*}"
            # Existing same-stem files can be native restart dependencies.
            # Copy rather than hard-link: ORCA may update them during execution.
            local existing suffix
            for existing in "$WORKDIR/$original_stem".*; do
                [ -f "$existing" ] || continue
                [ "$existing" = "$WORKDIR/$(basename "$INPUT_FILE")" ] && continue
                suffix="${existing#"$WORKDIR/$original_stem"}"
                cp -p -- "$existing" "$WORKDIR/$safe_stem$suffix"
            done
            echo "[calculator] orca input mapped to safe execution name: $safe_input_name (original: $INPUT_FILE)" >&2
            ;;
    esac
    set +e
    "$orca_bin" "$input_arg"
    local orca_status=$?
    set -e
    if [ -n "$safe_input_name" ]; then
        # ORCA names native artifacts after the execution stem. Restore that
        # stem even when the engine failed; partial artifacts are evidence too.
        # Preserve an existing destination before replacing it.
        local artifact target suffix backup_dir
        backup_dir="$WORKDIR/.cloudra/orca-name-map-$$"
        mkdir -p "$backup_dir"
        printf '%s\t%s\n' "$safe_input_name" "$(basename "$INPUT_FILE")" > "$backup_dir/mapping.tsv"
        for artifact in "$WORKDIR/$safe_stem"*; do
            [ -e "$artifact" ] || [ -L "$artifact" ] || continue
            [ "$artifact" = "$WORKDIR/$safe_input_name" ] && continue
            suffix="${artifact#"$WORKDIR/$safe_stem"}"
            target="$WORKDIR/$original_stem$suffix"
            if [ -e "$target" ] || [ -L "$target" ]; then
                mv -- "$target" "$backup_dir/$(basename "$target")"
            fi
            mv -- "$artifact" "$target"
            printf '%s\t%s\n' "$(basename "$artifact")" "$(basename "$target")" >> "$backup_dir/mapping.tsv"
            echo "[calculator] orca artifact mapped: $(basename "$artifact") -> $(basename "$target")" >&2
        done
        rm -f "$WORKDIR/$safe_input_name" || true
    fi
    [ "$orca_status" -eq 0 ] || exit "$orca_status"
}
```


### `完整 job_type dispatch`

`cloudra/calculator.sh:294–324`

```bash
case "$JOB_TYPE" in
    gaussian)
        run_gaussian
        ;;
    orca)
        run_orca
        ;;
    vasp)
        run_vasp
        ;;
    cp2k)
        run_cp2k
        ;;
    chem_task)
        if [ "$#" -ne 2 ] || [ -z "$1" ] || [ -z "$2" ]; then
            echo "chem_task requires the trusted executor Python and module root" >&2
            exit 1
        fi
        "$1" -c 'import sys; sys.path.insert(0,sys.argv[1]); from cloudra.runtime.chem_task import run_task; sys.exit(run_task(sys.argv[2]))' "$2" "$INPUT_FILE"
        ;;
    xtb)
        run_xtb "$@"
        ;;
    shell)
        exec bash -- "$INPUT_FILE"
        ;;
    *)
        echo "不支持的 job_type: $JOB_TYPE" >&2
        exit 1
        ;;
esac
```


## 提取与核验方法

临时生成器 `/tmp/build_qm_source_appendix.py` 仅用 Python 标准库：`ast.parse` 定位 class/function，起点含 decorator，终点取 `end_lineno`，直接从原文件行切片；不使用 `ast.unparse` 改写代码。完整 class 已覆盖的方法不再重复；局部嵌套函数随外层完整保留。相关模块赋值按节点引用递归收集，故解析 regex、容差、schema alias 均来自真实源码。Bash 按完整语法单元的行边界取原文。

生成时断言每个 selector 存在，每段源码与原文件对应行逐字一致；另检查索引 anchor 全部存在。该文档是审计工件，未修改任何生产代码、schema或科学判据。探针与结果的归档归主报告；本附录不运行测试、QM 程序或读取凭据。

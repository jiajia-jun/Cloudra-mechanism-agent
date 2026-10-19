# TS 状态机使用与验收

2026-10-19 更新。本文描述当前格式 7 的实际工具接口；输入定义见 `cloudra/tools/core/ts_inputs.py`，工具入口见 `cloudra/tools/Chemtool/ts_search_process.py`。旧设计稿留在 `superpowers/specs/`，不能代替当前 schema。工程回归、计算作业完成和科学验收分别记录。

## 入口与推进

| 工具 | 模型填写的字段 | 行为 |
| --- | --- | --- |
| `ts_prepare` | `input: TsInput`，必填 | 为一条路径创建一次持久记录；成功作业自动接续 |
| `ts_inspect` | `run_id: str`，必填 | 只读查看权威状态、结构原子表、作业、实际方法、证据、费用与下一步，不推进计算 |
| `ts_resume` | `run_id: str`、`reason: str` 必填；`changes: TsInputChanges` 默认 `{}` | 修订同一个 run；失败后可原参数重试，也可修改科学输入探索新路线 |
| `ts_stop` | `run_id: str`、`reason: str`，均必填 | 停止该流程继续推进；撤回排队作业，对运行中作业写 `cancel_requested`，由执行端安全收尾 |

并发版本、调用重放键和摘要均由运行时维护，模型不填写。`ts_prepare` 成功后不要重复创建同一路径；正常链无需反复调用 `ts_resume`。同项目有写权限的 Agent 可接手 run，程序记录 owner 转移；只读角色只能检查状态。

**正式 TS 求解与完整验证优先走 `ts_prepare` / `ts_resume`**；直接 `submit_compute_job` 提交 TS/IRC 仅用于探索性试算或能力探针。普通物种 Opt/Freq、单点和探索扫描仍使用计算队列。候选以 `guess.kind="provided"`、`guess.xyz_path` 和 `guess.evidence_refs` 接回流程，符合来源校验的已有 IRC 可用 `verification.irc_log`；这不是任意 TS/Freq 日志的通用导入接口。阻塞时先 `ts_inspect` 并修订点名声明，不以手动串联替代正式流程。提交成功不代表 TS 已确证或已绑定 DAG。队列兼容回归见 `tests/test_manual_ts_submission.py`。

直接以 `job_type="gaussian"` / `"orca"` 提交的 IRC 在完成冻结后，正常终止且真实双侧可得时自动导出规范 XYZ；完成通知给出两条路径，`query_compute_job` 以 `irc_end_a_path` / `irc_end_b_path` 返回。A/B 不代表反应物/产物，仍须分别无约束 Opt/Freq 并核对身份与方向。若 QM 由 shell 脚本内部启动，shell 回执不解析内部 QM；将原生日志提交 DAG 后，入库快照才生成恢复文件，断链诊断给出具体 Opt 与规范端点路径。程序不修改原生日志或输入，也不放宽几何同一性判据。

## 输入分组

`TsInput` 的实际顶层字段如下；除 `reaction` 外，各组允许先省略，在流程点名需要时补充。缺失的方法或结构不会被自动猜成默认值。

| 字段 | 类型 / 默认 | 含义 |
| --- | --- | --- |
| `reaction` | `TsReaction`，必填 | `reactant_smiles`、`product_smiles`、总 `charge`、总 `multiplicity` 必填；可选 `electronic_character`、`selected_candidate`，`reaction_center` 默认空列表 |
| `calculations` | `dict[str, QmCalculation]`，默认 `{}` | 本次输入内的命名完整计算配置；阶段通过 `{ref: "名称"}` 明确复用，不自动继承 |
| `conformers` | `TsConformers`，默认空组 | 两端结构来源及成环/距离指导；支持 `generate`、`file`、`catalog` 和产物绕键旋转 |
| `guess` | `xtb_path / scan / provided / null`，默认 `null` | 有类型的路径、扫描或有来源的候选结构 |
| `ts_optimization` | `QmCalculation / CalculationRef / null`，默认 `null` | 正式鞍点优化的独立计算配置 |
| `verification` | `TsVerification`，默认空组 | TS 频率、IRC、两端 Opt/Freq；可提供已有 `irc_log`、端点文件种子和分离产物 `component_logs` |
| `execution` | `TsExecution`，默认 CPU 1、内存 4096 MB | `cpus`、`memory_mb` 与可选有来源的动作/模型请求额度；不把资源字段当科学方法声明 |

`reaction.product_smiles="B.C"` 声明络合物，`reaction.product_smiles=["B", "C"]` 声明分离产物，显示为 `B + C`。二者不是相同的极小值证据对象。

完整 `QmCalculation` 必须明确 `engine`、非空 `method` 和 `basis_set`；无基组的方法也显式填 `basis_set=""`。按原生字段分开填写单一方法 token、基组和额外 `keywords`，避免把整段 route 放进 `method`。`keywords` 默认空字符串，`frequency_mode` 默认 `auto`；`orca_blocks` 默认 `null`，用于 ORCA；`end_setting` 默认空字符串，用于 Gaussian。可原样写出的错误、冲突或未知原生参数保留并返回模型可见 warning，包括跨引擎字段误用；不强补求解器选项。必填结构、文件完整性、资源容量和受信 Benchmark 合同仍独立校验。原生 xTB 仍要求空 `basis_set`，不接受 Gaussian/ORCA 关键词、原生块或频率模式。同一命名配置的复用必须明确引用；探索与正式阶段各自选择方法。

复用示例（理论级别须已获用户授权，此例不构成默认推荐；它只是完整输入中的配置片段）：

```json
{
  "calculations": {
    "geometry": {"engine": "orca", "method": "b3lyp", "basis_set": "def2-SVP", "keywords": "TightSCF"}
  },
  "ts_optimization": {"ref": "geometry"},
  "verification": {
    "frequency": {"ref": "geometry"},
    "irc": {"ref": "geometry"}
  }
}
```

## 实际原子编号与结构来源

程序管理两端实际分子的原子对应关系。唯一完整映射自动采用；存在多个完整候选时，先用 `ts_inspect` 查看，再通过 `reaction.selected_candidate` 或 `reaction_mapping(run_id, selected_candidate)` 选择 **0-based** 候选。当前公开输入不再要求模型维护 `atom_map`、`heavy_atom_binding` 或结构摘要。

结构/反应字段使用当前实际原子表的 **1-based 全原子编号**；ORCA 原生 scan/freeze 用 **0-based**，Gaussian/xTB 用 **1-based**。这些是实际 XYZ 中的坐标行，不是 SMILES 重原子序号。修订后以返回的当前原子表为准；历史 QM 文件保留原编号。

`conformers.<role>.kind="file"` 使用传入文件；省略或设置 `optimization:null` 即不额外做构建阶段预优化，不代表它已经是极小值。生成种子显式声明 `generation="ETKDGv3"` 和 `seed`，不暗中添加力场优化。来源字段修订保留省略项，`null` 清空可选项；显式重新声明文件路径会重新导入当前字节，即使路径字符串没变。

程序只在实际分子图对应关系可证明时沿用旧原子身份、转换新输入的坐标编号。来源身份无法对应时清除失效的映射和相关编号声明，点名要求检查；不猜测排列，也不改写外部源文件。需要保留电荷、自由基、同位素或立体身份时同时提供与 XYZ 同序的 MOL/SDF；MOL 声明不能代替实际 XYZ 连通性检查。

`guess.kind="provided"` 的 XYZ 与 `evidence_refs` 在接受时固定原始字节和内部摘要。源文件后来更正或删除，不会悄悄改变已接受候选；需用 `ts_resume.changes.guess` 重新声明来源。副本自身缺失或变化时停止后续推进，现存计算不受影响。

## 路径与扫描

当前原生构象优化、xTB 路径和 xTB 扫描使用显式 GFN2-xTB；其它方法走已有 ORCA/Gaussian 写入器，能力不足时点名暂停。探索方法可与正式 TS 方法不同，但每个阶段都须明确声明。

- `guess.kind="scan"` 独立声明 `calculation`、`scans` 和可选 `freeze`；扫描最多两个坐标，按实际输入几何与对应引擎编号填写。
- 单坐标不填 `mode`。双坐标 ORCA 必须明确 `grid`（独立曲面）或 `concerted`（同步路径且点数相同）；Gaussian 使用独立网格，不填 `mode`。
- 原生 xTB 扫描明确 `calculation={engine:"xtb",method:"GFN2-xTB",basis_set:""}`，每条扫描给起点、终点、点数及正的 `force_constant`；双坐标明确 `concerted` 或 `sequential`。不把冻结坐标静默解释成软约束。
- 实际命令、版本、逐点收敛、电子能与约束势分开留证。二维网格不自动挑一个峰当 TS；所有扫描峰、路径候选和提供的峰帧都须经过新的无约束正式 TS 优化和科学验证。

## 修订、失败与在途作业

同一计算配置内，省略字段保留旧值；`keywords=""`、`orca_blocks:null`、`end_setting=""` 显式清除。改变 `engine`、`method` 或 `basis_set` 使用 `{replace: 完整配置}`；更换引用使用 `{replace: {ref: "名称"}}`。`changes.calculations` 按名称合并，`null` 只删除不再被引用的配置；坐标补丁无需重复计算配置。

失败不是路径的永久终点。可用 `changes={}` 重试失败尝试，或修订扫描、结构和初猜验证新假设；旧失败、输入、日志、作业和费用自动保留。当前接口没有 `scan_recovery` 字段，也不要求另交修复文档。执行修复被接受不代表科学失败原因已经解决。

运行中或 `cancel_requested` 作业阻止修订；仅排队的 `ready` 作业允许修订，程序在事务内撤回已被替代的排队作业，不杀正在运行的计算。停止用 `ts_stop`；等待执行端收尾后再继续。

失效范围由依赖决定：结构或初猜变更重建其下游；TS 方法变更重跑正式链；TS 频率变更保留 TS Opt；IRC 变更保留 TS/Freq；单侧端点配置变更只重算该侧。旧作业的实际配置快照与历史证据保持原样。

## 方法、电子态与权限

每个计算入队前读取实际原生方法、关键词/溶剂设置、电荷和自旋，与本阶段声明比较。只有显式属于 Benchmark 的项目叠加该题 `MethodPolicy` 和可选受信 `calculation_contracts`；普通研究项目没有默认方法/基组白名单。缺失的方法不从全局配置、示例或历史任务推断。

`reaction.charge` 与 `reaction.multiplicity` 描述总电子态，可显式声明 `electronic_character="open_shell"` 或 `"closed_shell"`；程序不替用户选择基态、初始自旋分布或新阈值。未优化 ETKDG 种子可交给已授权量化方法；开壳层/自由基结构不做 MMFF/UFF 打分，闭壳层卡宾的几何准备也保守跳过力场。

GFN-xTB/CREST 的 `--uhf` 只表达总 α/β 电子数差，不能用 `--uhf 0` 表达开壳层单重态；不支持的输入在提交前暂停。可改用有来源的外部初猜或明确支持该电子态的 ORCA/Gaussian 声明，不能把准备成功当成电子态已确证。相关原生说明见 [xTB](https://xtb-docs.readthedocs.io/en/latest/spgfn.html) 与 [CREST](https://crest-lab.github.io/crest-docs/page/examples/standard_sp.html)。

只读角色不能提交或修订，也不能借有更大权限的 Agent 绕过；每次自动续接重新检查权限与阶段声明。撤销写权限只阻止新提交，现有量化进程继续运行。

## 科学验收

1. TS Opt 原生正常结束且优化收敛；TS Freq 有且仅有一个虚频，并检查振动是否对应目标反应。一虚频只证明一阶鞍点，不独立证明路径身份。
2. 同一已验证 TS 的真实双向 IRC 必须有可用外帧，IRC 起点与该 TS 几何匹配。两侧真实末帧分别作为无约束优化起点，收敛到身份/立体化学正确且零虚频的极小值；保留 IRC、起始帧、优化与频率之间的真实来源关系。
3. 上述端点优化链成立即接受方向证明。IRC 本身可以如实 `partial`，不要求两向到底收敛；几何区间只作提示，异常或无法判断时发出警告并建议检查轨迹，不否决已成立的端点优化证据。几何区间吻合本身也不能替代真实端点优化链。
4. 独立物种种子即使零虚频，也不能冒充真实 IRC 外帧优化。缺来源、端点身份或频率证据时保持 `candidate_only`，不把作业 `done` 当成科学通过。

分离产物用列表声明，并可经 `verification.product_endpoint.component_logs` 提供每个组分独立正常终止、零虚频且身份正确的日志。系统固定副本，结合真实 IRC 的实际分离产物端点与反应物侧证据单独检查；只证明 `B + C` 通道，不证明 `B.C` 络合物极小值。组分能量也不能拼成络合物能量。

频率完成后，`frequency_analysis` 复用同一作业的原生日志模式解析，记录虚频运动原子、反应中心占比与键向投影；占比是未加质量权重位移平方和比例。缺位移的 `missing` 不代表方向不符，`modes:null` 不代表占比零。`mode_alignment` 的 `misaligned` / `undecidable` 通知所属 Agent 判断，不自动禁止 IRC、不自动取消计算，也不添加新占比阈值。

既有窗口与碰撞判据不因本次文档更新改变。初始 Hessian 只使用同理论级别真实产物；模型、溶剂等完整声明不同须重新计算，不以位移末帧代替中心导数。

## 权威状态、费用与历史

`prepare / resume / inspect` 共用 `status`、`stage`、`result`、`waiting_for`、`available_results`、`structures`、`blocked`、`failed_attempt`、`next`、`methods`、`frequency_analysis`、`usage` 与导出信息。`result.verified=true` 才表示已记录科学检查通过；工具 `is_success=true` 不表示 TS 已确证。

数据库账本是权威来源；`process.json` 是导出快照，过期时返回明确提示，不以旧 JSON 反推新状态。`methods` 展示计划配置与作业不可变实际快照，完成作业的原生日志经 `available_results` 返回；保留它们供直接证据送审。

不设预计墙钟/CPU 小时准入和介入次数上限；保留已授权的实际计算动作数和模型请求数限制。`runtime_seconds` 是经过时间，`allocated_cpu_hours` 是申请核数乘经过时间，`measured_cpu_hours` 缺测为 `null`，不能冒充实测。

格式 6 及更早记录按历史原输入和作业只读保留，自动接续与修订隔离；不迁移旧科学输入、不影响现存计算和排他锁。当前成功、失败、停止和范围交付仍是不同状态。

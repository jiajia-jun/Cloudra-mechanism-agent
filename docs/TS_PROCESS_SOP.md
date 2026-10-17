# TS 状态机使用与验收

2026-10-09：统一显式计算配置、命名引用和保留遗漏字段的修订接口使用格式 5。原生 xTB 柔性扫描此前已接通；真实 D1 路径与 ORCA/Gaussian 全链尚未验收。上游接口语义见 `superpowers/specs/2026-10-02-ts-state-machine-interface-design.md` 和 `superpowers/specs/2026-10-08-ts-atom-binding-and-scan-contract-design.md`。不新增化学阈值或默认理论方法。

## 三个入口

- `ts_prepare(input)`：创建路径一次，接受显式输入并保存 checkpoint；运行时用稳定工具调用身份去重重放。
- `ts_inspect(run_id)`：读取同项目权威状态、实际结构原子表、作业、方法、证据、费用和下一步；只读审查员可检查别人的 run。不会推进、重新解析或提交计算。
- `ts_resume(run_id, changes, reason, scan_recovery)`：原 owner 修订同一个 run；并发版本和稳定重放键由运行时管理，不要求模型填写。正常成功链自动推进，无需调用 resume。失败扫描必须提供绑定失败尝试及真实修复产物的 `scan_recovery`；其他失败阶段按既有恢复契约处理。运行时负责工作目录和稳定重放键。

普通 Opt/Freq/单点/探索扫描仍用已有计算入口；手动 TS/IRC 提交暂时关闭，含 TS/QST2/QST3/OptTS/ScanTS/NEB-TS/IRC。不得通过其他 Agent 或 bash 绕过。关闭限制前须保留真实 TS 优化频率、双向 IRC 和两端 Opt/Freq 及身份验证产物；单测不构成真实引擎验收。

## 输入分组

| 组 | 明确含义 |
| --- | --- |
| reaction | 两端 SMILES、电荷、总多重度、可选 electronic_character、全原子 atom_map、reaction_center |
| calculations | 本次 TS 输入中的命名完整计算配置；阶段通过 `{ref: "名称"}` 显式选用，不自动继承 |
| conformers | 两端 generate（显式 ETKDGv3 和 seed）、file、精确 catalog/partition/candidate 或已支持的 product 绕键旋转；可单独声明 optimization；guidance 为成环顺序/距离窗口 |
| guess | 判别式 kind：xtb_path（显式 GFN2-xTB、可选溶剂/迭代数）、scan（独立 calculation/scans/freeze）、provided（XYZ 和证据引用） |
| ts_optimization | 正式鞍点优化的独立 calculation |
| verification | 独立 TS frequency、irc、各向 endpoint.optimization/frequency；可声明已完成的 irc_log 或端点 file seed（XYZ、可选 MOL、证据） |
| execution | 计算节点/CPU/内存和可选有来源的动作、模型请求、介入次数额度 |

完整 `calculation` 明确 `engine`、单一原生 `method` token 和 `basis_set`；无基组的方法也必须显式填 `basis_set=""`。`method` 不接受方法/基组拼接或整段 route。`keywords`、`frequency_mode` 和对应原生 `orca_blocks`/`end_setting` 分开填写。阶段可直接给完整配置，也可给 `{ref: "名称"}` 指向本输入的 `calculations`。同一配置复用必须明确引用；探索与正式阶段仍各自选择。当前 native 构象优化、路径与扫描能力只支持显式 GFN2-xTB；其他明确方法使用已有 ORCA/Gaussian 写入器，能力不足点名阻塞。缺失方法不填默认。构象生成不暗中做力场优化；带指导的构象使用已声明约束优化方法。

结构字段 1-based；ORCA 原生 scan/freeze 字段 0-based，Gaussian/xTB 1-based。atom_map 含全部氢，产物第 k 个原子映射到反应物 atom_map[k-1]。`structures` 返回实际 XYZ 的完整 1-based 原子表和结构摘要；对称外部结构可在 `conformers.<role>.heavy_atom_binding` 只填写 SMILES 重原子顺序对应的完整结构编号；摘要由程序维护。只填跨端点 atom_map 不会消除本侧身份歧义。

xTB 柔性扫描复用 `guess.kind=scan`：`calculation={engine:"xtb",method:"GFN2-xTB",basis_set:""}`，每条 scans 明确起点、终点、点数，并显式给正的 `force_constant`。单坐标不需 `mode`；双坐标明确选择 `concerted` 或 `sequential`。不要求 Agent 填优化等级或原生命令；实际命令、xTB 版本、逐点收敛、电子能与约束势分开留证。完成扫描只可能提供未经验证的 TS 初猜；正式方法需在独立 `ts_optimization` 中声明。

计算配置部分修订保留省略的字段；`keywords=""`、`orca_blocks=null`、`end_setting=""` 显式清除对应设置。改变 `engine`、`method` 或 `basis_set` 必须使用 `{replace: 完整配置}`；换引用使用 `{replace: {ref: "名称"}}`。`changes.calculations` 按名称合并，省略的配置保留，null 只能删除不再被引用的配置。扫描坐标补丁可以只填 `changes.guess.scans`，无需重复 method 或其他扫描字段。结构来源仍按其原有完整声明替换；未知字段 fail loud，不解释为旧接口。

`guess.kind=provided` 的 `xyz_path` 和 `evidence_refs` 路径只供首次导入。接受时程序按原始字节保存副本，并在运行记录的内部 `provided_guess_binding` 中自动记录原路径、副本路径和 SHA-256；Agent 不填写摘要。后续原文件更正或删除、以及未重新声明 guess 的修订/重试，均继续引用已接受的副本。需要采用更正后的来源时，通过 `ts_resume.changes.guess` 明确重新声明完整 provided guess，即使路径相同也会建立新绑定并保留旧历史；副本自身缺失或摘要变化时停止后续推进，现存计算不受影响。

复用示例（已由用户选定的理论级别，名称不构成默认推荐）：

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

在同一理论级别内，`changes={"ts_optimization":{"keywords":"TightSCF D3BJ"}}` 只改变关键词，已有原生块和频率模式保留。更换理论级别则提交完整 `replace` 对象。变更共享配置只使引用它的阶段失效；旧作业的实际配置快照和日志保持原样。

## 声明式电子态与自旋耦合

2026-10-09：`reaction.charge` 与 `reaction.multiplicity` 指定体系总电荷和总多重度；可显式设置 `electronic_character="open_shell"` 或 `"closed_shell"`。系统按总电子数检查 α/β 电子数是否非负、整数且符合范围。RDKit 局域自由基数只作结构记录，不要求等于多重度减一，因此可准备低自旋耦合、开壳层单重态及具有可解析声明图的金属/离域体系。显式电子态优先于图自由基启发；例如声明闭壳层的单重态卡宾不会因图自由基标记而被拒绝。

建议先明确总电子态，再提供保留电荷、自由基、同位素与立体化学身份的 MOL/SDF 和同序 XYZ。这类体系不能只凭 XYZ 推断键级或电子态。独立几何检查只验证键对连通性，返回记录会注明键级来自声明图；准备成功不代表计算电子态或 TS 已确证。显式原子绑定和来源编号仍优先；无来源标签的开壳层对称结构只有穷尽枚举并证明全部候选保留完整身份后，才选确定的代表元。枚举不完整仍要求显式绑定。

未优化 ETKDG 种子可用于后续用户指定的量化方法；开壳层或图含局域自由基时不做 MMFF/UFF 打分，不生成虚构能量。公共构象工具的力场复合物装配不支持这类输入。闭壳层卡宾虽然可按声明进入量化路径，几何准备仍保守跳过力场。

当前原生 GFN-xTB/CREST 接口的 `--uhf` 只传递总 α/β 电子数之差，不能用 `--uhf 0` 表达开壳层单重态。该输入会在种子优化、路径或扫描提交前进入 `electronic_state_backend_unsupported` 检查点；公共 CREST 入口也在启动前拒绝。可改用有来源的外部初猜或显式支持该电子态的 ORCA/Gaussian 方法，并由输入提供破缺对称、多参考方法或初始自旋设置。系统不自动选择基态、方法、初始自旋分布或新的自旋污染阈值。[xTB 电子态说明](https://xtb-docs.readthedocs.io/en/latest/spgfn.html)、[CREST 电子结构说明](https://crest-lab.github.io/crest-docs/page/examples/standard_sp.html)。

修订 `electronic_character` 会废弃依赖的旧计算证据并重新执行声明；实际计算清单保留该字段，并在准入时与当前输入逐项比较。频率、IRC、端点身份和热力学证据要求保持原有语义；本次回归覆盖工程契约，未进行真实开壳层 TS/IRC 科学验收。

## 持续推进、失败与修订

declare → build → map → assemble → guess → validate → submit → refine → verdict。方法、结构、方向和证据缺失均点名暂停；waiting 是等待系统作业而非 Agent 决策。计算终态通知和重启 reconcile 自动接续，重复事件不重复建作业。后续变化继续用同一 run，不用重新 prepare。

verified / candidate_only / search_failed / invalid_input 是一次尝试的结果，不封死路径。修订将原输入、失败、作业和证据归档，生成新 input_revision 和结构化 receipt。并发版本由工具读取权威快照；运行时稳定调用键先去重再检查过期，键冲突报错。回执先持久化，随后提交副作用。原生输入文件和旧证据不可覆盖。换结构来源或覆盖外部 XYZ/MOL 时，旧原子编号声明自动清空；重建后 inspect 新原子表，再明确填写新编号。

在途 READY/running/cancel_requested 作业禁止修订，不终止计算。固定依赖失效：构象变更重建下游；映射/初猜变更重跑探索及正式链；TS 方法重跑正式链；TS Freq 变更保留 TS Opt；IRC 变更保留 TS/Freq；单侧端点变更只重算该侧 Opt/Freq，另一侧及 TS/IRC 保留。

失败扫描的修订或重试须提供 `scan_recovery`：只填写真实修复产物的路径列表；当前失败身份、原输入/日志指纹和修复文件摘要由程序内部绑定。`reason`、扫描 7 点改 8 点或 `changes={}` 都不足以通过这一闸门；修复产物的科学充分性仍由原授权范围约束。其他失败阶段按既有契约修订或重试。旧失败、日志和费用保留，接受执行修复不等于失败原因已科学解决。计算正常退出但虚频不合格仍记录失败。

既有 IRC 来源须来自同项目 authoritative done 作业，输入摘要、原生正常结束、自己的方法契约、TS 频率参考几何和双向外帧全部可核验；几何按写入器已有 8 位坐标精度比较。复制为不可变证据并保留来源；不重新提交 IRC，不从无来源路径直接接受 verdict。

## 科学证据与权限

实际结构图与坐标先绑定输入版本和摘要；同元素排列不等于同物种。未标记对称绑定通常保持 inconclusive，开壳层例外须满足上述穷尽身份证明；由既有 atom_identity 表生成的结构或明确旋转可使用构造绑定。每次搜索和正式提交前重查实际结构。普通闭壳层外部 XYZ 的图由既有键感知器确定并保留 MOL；需要保留声明电子身份时须提供 MOL/SDF。歧义须补充实际结构来源，不猜映射。最终端点身份、立体化学与方向证明仍独立验证。

每个计算入 READY 前读取实际原生方法、全部关键词/溶剂设置/电荷/自旋，与本阶段声明比较。只有显式标识为 Benchmark 的项目才叠加该题实际的 MethodPolicy；其中可选 calculation_contracts 为各 purpose 提供完整受信原生契约。普通研究项目没有默认方法/基组白名单，不从全局配置、示例或历史任务推断限制，方法选择遵循用户当前要求和预算。扫描方法可与正式方法不同，各阶段须明确声明；Benchmark 还需符合当前题目策略。缺少阶段声明时停止。基组等价拼写规范化，不接受未知额外方法。资源字段不充当科学契约。

只读 Agent 可查状态/发证据但不能提交、修订、spawn/call 能力更大的 producer，证据 post 不唤醒 producer。自动续接每次提交也重新检查当前 owner 权限与本阶段声明；Benchmark 另需检查当前题目 MethodPolicy。权限撤销只停止新提交，关联量化进程继续运行。

## 保留的物理验收

TS Opt 须原生正常结束并收敛；TS Freq 有且仅有 1 个虚频。双向 IRC 须有真实可用外帧，各向经无约束 Opt/Freq 确认为收敛的零虚频极小点，物种与立体化学吻合，且相对 TS 与对应极小点的方向区间吻合。IRC 本身可如实 partial，无须双向到底收敛；缺证据只到 candidate_only。路径/扫描/提供的峰帧均不直接作为已验证 TS。

频率完成后，管线复用 `log_parser` 的模式解析，随该频率作业记录组成报告；`ts_inspect` 及其他 TS 工具的返回视图通过 `frequency_analysis` 读取同一记录。报告包含原日志路径/摘要、作业与输入修订、1-based 反应中心对、每条虚频的前五个运动原子及其占比、反应中心去重原子占比（`watch_atom_fraction`），并保留键向投影摘要。原子占比是原生日志位移的未加质量权重平方和比例，不等同于质量加权贡献；`modes=null` 表示缺少可解析位移或几何，不能当成占比为零。一虚频只支持一阶鞍点，Agent 仍须结合组成和 IRC 判断是否属于所研究的反应；组成报告不新增自动拒绝阈值，也不替代已有 IRC 与端点验收。

复用现有成环非键合窗口 1.6–3.0 Å、组分接触图 1.7×vdW、碰撞下限 1.0 Å；显式错误窗口 fail loud。候选不代表平衡构象。初始 Hessian 仅取同理论级别真实产物，不以位移末帧代替中心导数。xTB 路径相对 kcal/mol 与候选绝对 Eh 分开记录；原生收敛和正常终止标记决定结果。

## 观测与费用

prepare / resume / inspect / 终态通知共用状态投影：status、stage、result、waiting_for、available_results、structures、blocked、failed_attempt、next、methods、usage、details_path/export_revision。`methods` 展示已解析引用的 planned 配置、实际作业的不可变配置快照和输入契约；单独保存的 scan_step 也包括在内。完成扫描的原始日志通过 `available_results` 返回，完成作业不等于 TS 已验证。完整输入、历史和证据在权威账本与 process.json 快照；导出 revision 与账本分开展示。

删除 estimated wall/CPU hours、time_budget_hours、预计 CPU 小时准入及缺估计阻塞。动作数、实际模型请求（含 transport 重试）、介入次数保留。runtime_seconds 是经过时间；allocated_cpu_hours 是申请核数×经过时间；measured_cpu_hours 缺测量为 null，不能冒充实测。历史和约束优化的各梯度/Hessian 作业都计入真实动作。当前统一配置接口使用格式 5；格式 4 及更早记录保留原始字段供只读查看，自动续接与修订隔离，现存计算、原始输入和排他锁不动；不迁移/默默兼容旧科学输入。


失败恢复区分执行修复与新路线探索。后续作业仍需原生正常终止；已知 wrong_mode 的频率修复必须满足对应一虚频/零虚频证据。失败 scan/path 改为 provided 时须提供新候选 XYZ 及其来源证据；改为 xtb_path 时仍使用两端已绑定结构。旧路线无需先成功，新路线仍经过正常准入和最终科学校验。

MOL 的键图不能代替实际 XYZ 连通性证据。预优化、映射和端点校验沿用同一既有连通性判据；无法证明时保持 inconclusive。IRC 复用 Hessian 要求完整科学方法声明相同，包括原生溶剂等设置块；不同声明重新计算 Hessian。

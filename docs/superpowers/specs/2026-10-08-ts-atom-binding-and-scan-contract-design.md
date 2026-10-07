# TS 原子绑定与原生 xTB 柔性扫描设计

日期：2026-10-08

状态：已按最小 Agent 接口实施；原生 xTB 6.7.1 的独立测试分子扫描已运行，真实 D1 路径与 TS 科学验收仍未运行。用户确认原子身份/编号与 xTB 扫描入口两项均需处理，并要求补上原生 xTB 柔性扫描能力。

## 1. 目标与边界

目标：让 Agent 根据实际结构的权威原子表完成声明，在输入阶段获得可操作的错误；不再通过反复改 SMILES、复制坐标文件和试填编号来寻找可通过的组合。

本规格包含两个相连但可独立验收的修复：

1. 明确并贯通端点身份绑定、具体结构编号、跨反应原子映射及其失效规则。
2. 为 `guess.kind=scan` 接通原生 xTB 柔性扫描：类型化输入、已有账本执行、原生结果解析、候选提取和 TS 后续接线；使公开 schema 与实际能力一致。

不包含：xTB 路径轮数默认值、`--path` 不收敛诊断、多候选搜索调度、除原生 xTB 外的其他新扫描后端、方法/基组选择、构象或连通性阈值、Benchmark 评分、现有任务恢复。不得借本次修复放宽物种、立体化学、频率或 IRC 判据。

交付范围是输入契约、诊断投影、原生 xTB 扫描完整接线、对应回归和使用说明；不引入通用工作流或能力注册框架。

## 2. 真实问题与证据边界

案例：本地 `benchmark:D1`，project `prj_43a77b32828e4187`，路径 `ts_0001`，工作区 `sandboxes/D1/batch_d10ba1106aa947af`。时间均为 UTC+8，证据来自 2026-10-08 的事件账本、不可变结构和 process 历史。

| 时间/阶段 | 已观察事实 | 设计含义 |
| --- | --- | --- |
| 04:23 首次 prepare | `guess.kind=scan`、`calculation.engine=xtb` 通过模型解析，随后 `normalize_ts_input_atoms` 抛出 `Unknown atom numbering context: 'xtb'`；已用实际入参只运行校验复现 | schema 暴露了扫描器不能执行的引擎 |
| 04:30–04:35 build/map | 缺完整映射；随后将 SMILES 重原子序号当成分组加氢后的坐标序号，出现 C→H 映射 | 具体原子表未成为修订时足够直接的输入依据 |
| 同阶段 | 外部端点分别有 4 个、2 个对称重原子绑定；只补全跨端点 `atom_map` 或只给 MOL 加标签不能消除声明到结构的歧义 | 存在两个不同的映射问题，当前接口容易混淆 |
| 同阶段 | 自动生成结构有过近片间接触；部分替代文件不存在；某份 MOL 键序与实际几何不一致 | 这些是独立的真实输入问题，不能通过取消身份门禁解决 |
| 04:35:52 | SMILES 与 MOL 使用相应映射标签后通过 map 阶段 | 保持严格校验仍然存在可行路径，不需要任取对称映射 |

本次调查不证明所有历史阻塞都是软件缺陷。已存在 `_bound_input_structure` 对 `generate` 来源的构造身份恢复，应复用并补回归，不能把它误写成尚未实现的能力。

现有实现依据：

- `cloudra/tools/core/structure_builder.py::AtomIdentity`：已经区分输出位置、输入原子与加氢来源。
- `cloudra/tools/core/ts_process.py::_bound_input_structure/_check_input_binding/_map`：具体几何、端点身份与跨端点映射校验。
- `cloudra/tools/Chemtool/reaction_mapping.py::_identity_and_binding`：标签绑定或唯一图匹配；对称歧义保留 inconclusive。
- `cloudra/tools/core/ts_inputs.py::ScanGuess/normalize_ts_input_atoms`：通用 `TsCalculation` 允许 xtb，但扫描编号函数只支持 ORCA/Gaussian。
- `cloudra/tools/Chemtool/ts_guess.py::_scan_prepare`：已有 Gaussian/ORCA 扫描写入器。

### 2.1 xTB 原生能力与当前接入边界

2026-10-08 核对 [xTB 官方 PES 扫描文档](https://xtb-docs.readthedocs.io/en/latest/scan.html) 和 [约束输入说明](https://xtb-docs.readthedocs.io/en/latest/xcontrol.html)：独立 xTB 原生支持 relaxed scan，使用 `$constrain`/`$scan` 配合 `--opt`，可扫描距离、角度和二面角，输出 `xtbscan.log` 中的几何和能量。

多坐标可用 `concerted` 同步推进（各坐标点数相同），或 `sequential` 依次推进。同步扫描是一条耦合路径，并非二维笛卡尔网格扫描。约束通过势函数实现，实际几何可能偏离目标值。

因此本次错误是 **Cloudra 没有接通独立 xTB 扫描的写入、执行与解析契约**，不是 xTB 软件不支持扫描。用户已要求补齐该能力；第 7 节据此替换了仅限制入口的初始方案。

必须保存目标与实际坐标、约束设置及能量语义；扫描帧存在或进程 exit 0 不足以认定逐点收敛。约束强度、扫描范围与方法仍需显式声明，不能由本规格作者自行给出科学默认值。文档确认的是原生能力，本次 spec 编写尚未运行真实扫描，逐点格式和能量语义的本机验收属于实施完成条件。

## 3. 方案选择

| 方案 | 优点 | 问题 |
| --- | --- | --- |
| 仅改工具说明和提示词 | 改动少 | 不能消除 schema 接受非法引擎、缺少显式绑定入口和旧引用复用的问题 |
| **复用原子身份表，补端点绑定输入；原生 xTB 扫描沿现有计算账本接入** | 覆盖 D1 输入故障，并使已有公开扫描意图能被实际执行 | 需同步输入、执行、结果解析与真实扫描验收 |
| 将所有工具改成全局 atom ID 接口并重写候选系统 | 引用形式统一 | 超出本次需求，涉及大量无关工具和持久化结构 |

推荐第二项。保留现有 `ts_prepare → ts_inspect → ts_resume` 流程，不增加工具入口。

## 4. 原子引用的三个概念

### 4.1 端点内部身份绑定

问题：声明的某个 SMILES 重原子，对应这一份具体 XYZ/MOL 的哪个原子？

这项绑定不能由另一端的结构或 `reaction.atom_map` 代替。对称分子出现多个匹配时，必须来自构造来源、相符的显式标签或调用者明确指定的有效绑定。

### 4.2 反应物到产物的对应关系

`reaction.atom_map` 保持现有语义：数组第 k 项表示产物具体结构第 k 个原子对应反应物具体结构的哪个原子。必须覆盖全部原子，包括氢；检查元素、同位素和排列完整性。

不得自动按相邻重原子补出跨反应氢映射；质子转移、同位素和立体化学可能依赖具体氢身份。自动生成的映射建议仍是建议，不因本规格而自动获准。

### 4.3 几何坐标引用

| 字段 | 引用对象 | 对外编号 |
| --- | --- | --- |
| `reaction.atom_map` 的数组位置和值 | 产物/反应物完整坐标原子表 | 1-based |
| `reaction.reaction_center` | 反应物完整坐标原子表 | 1-based |
| `conformers.guidance.ring_order/distance_filters` | 反应物完整坐标原子表 | 1-based |
| 产物 `rotate_about_bond.atoms` | 被旋转的反应物结构 | 1-based |
| ORCA `guess.scans/freeze` | 反应物完整坐标原子表 | 0-based |
| Gaussian `guess.scans/freeze` | 反应物完整坐标原子表 | 1-based |
| xTB `guess.scans` | 反应物完整坐标原子表 | 1-based |

内部继续使用 0-based。对外表与输入字段明确标注基准；不得将同一输入重复转换，或因为更换正式 TS 引擎而重新解释已归一化的扫描编号。

## 5. 权威原子表与端点绑定

### 5.1 原子表由实际输入快照生成

在 build 获得某侧结构后，即持久化该侧的原子表；另一侧缺失或 map 阻塞不妨碍返回已获得的表。`ts_prepare`、`ts_resume`、`ts_inspect` 和系统通知共用这一投影。

复用既有 `AtomIdentity`、来源快照与摘要，不从规范化后的 SMILES 重新猜坐标顺序。每侧表包含：

- role、来源种类、生成该表的 input revision；
- XYZ/MOL 快照路径与内容摘要；
- `structure_digest`，见下节；
- 完整原子数、组分数、表中编号基准；
- 每行的具体结构序号、元素/同位素、组分，以及有证据支持的输入原子来源或加氢来源；
- 端点身份状态、绑定来源，以及已确认的 SMILES 重原子到结构原子对应表。

未知来源字段为空，不能按位置合成“稳定身份”。外部文件的组分数来自已验证的分子图，不能因为旧 metadata 的 `components=[]` 就显示为单组分。

完整表写入 run 目录内的 JSON 产物；`TsProcessView` 新增 `structures`，返回两侧摘要、表路径和当前阻塞涉及的行。`ts_inspect` 只读取已经存储的表，不重新建模、改状态或提交计算。文件读取和 RDKit 工作继续离开异步事件循环。

### 5.2 外部文件的显式绑定入口

在 `FileConformer` 新增可选 `heavy_atom_binding`，其唯一用途是明确本侧声明到具体结构的身份：

```text
heavy_atom_binding
  structure_digest: 非空字符串
  indices: 严格整数数组
```

数组按声明 SMILES 的重原子解析顺序排列，值为具体结构完整原子表的 **1-based** 序号。对应顺序会在原子表中明确给出，不要求 Agent 从规范 SMILES 推算。

D1 反应物 `C=CC=C.C=C` 的已观察分组加氢顺序中，六个重原子对应 `indices=[1,2,3,4,11,12]`。这只是该具体文件的例子，不能硬编码为该反应的固定映射。

`structure_digest` 由现有内容摘要函数对 role、声明 SMILES 原文、电荷/多重度，以及核验所得结构的原子属性、键图和 XYZ 坐标计算。路径不参与摘要；XYZ/MOL 原始字节摘要另存原子表。无 MOL 时使用已成功解析的图；图不明确就不能通过绑定。该摘要由工具返回，调用者不能用占位值。

摘要用于拒绝把旧表上的绑定套到新文件；不代表文件天然可信。仅修改内容相同文件的路径不使绑定失效；声明顺序、坐标或分子图变化使摘要变化。

处理规则：

1. 验证摘要、数组长度、唯一性、范围和重原子覆盖；拒绝 bool、负数、重号、漏号和指向氢的值。
2. 检查该指定对应是否保持端点图的元素/同位素、键连接、键序、形式电荷及现有立体化学约束；不能只检查元素相同。
3. MOL 图仍须通过现有实际 XYZ 连通性检查；显式绑定不豁免几何核验。
4. 若已有有效标签也确定了绑定，两者必须一致；冲突直接报错，不按优先级覆盖。
5. 有效后写入既有 `input_binding`，记录来源 `explicit`；随后仍独立检查跨端点全原子 `reaction.atom_map`。

复用 `_identity_and_binding` 的图核验，实现一份端点绑定逻辑。独立 `reaction_mapping` 工具增加同语义的两侧可选绑定字段，让 Agent 可先验证再提交 TS；不得另写一套宽松匹配器。

### 5.3 已有其他来源

- `generate`：复用构建器记录的输入原子来源建立绑定，不要求 Agent 给自动生成的结构手动标号。已有标签不得被无检查地覆盖；内部临时标签只用于保持已证明的构造对应。
- 相符的 SMILES/MOL 映射标签：保留现有入口，同时核验标签指定的对应保持图关系；重复、部分、冲突标签不得被静默忽略后任取匹配。
- 无标签但唯一图匹配的外部结构：沿用唯一匹配，不强制增加输入。
- 无标签且对称歧义的外部结构：返回原子表，要求明确本侧绑定；不挑第一个同构匹配，不把跨端点映射当成本侧绑定。
- `catalog`：复用可核验的候选原子身份与来源。仅有字符串 atom ID 或 geometry hash 不足以证明它与当前 SMILES 的对应；缺乏来源时保持阻塞，可改用同一候选的 file 入口明确绑定。本次不扩展候选库存储协议。
- `rotate_about_bond`：从已绑定反应物继承原子身份，仍验证声明物种、实际几何和立体化学。

## 6. 校验顺序、修订与诊断

### 6.1 进入计算前的顺序

1. Pydantic 验证已提供字段的类型及扫描引擎/参数组合；错误不创建 run、revision 或计算作业。
2. 解析并快照化文件来源，建立能获得的原子表；缺文件返回其精确字段和路径。
3. 检查各端点图、几何与声明的身份及其绑定。
4. 依据实际表核对所有已提供的原子引用。任何一个已提供引用错误，都应在种子预优化、扫描或路径提交前报出。
5. 依赖某阶段的字段未提供，沿用检查点等待补充；不因后续未提供的科学方法而阻止读取或保存路径。

有结构但缺映射可以创建可检查的记录和原子表。结构通过身份核验不代表极小值或 TS 已验收。

### 6.2 修订失效

- 稳定 request key 由运行时工具调用身份承担；保留 Agent 已观察的 expected revision、owner、在途作业保护和不可变历史。
- 换结构、MOL、声明原子顺序或候选来源后，旧 `input_binding` 必须失效；相同元素序列不证明原子身份和顺序未变。
- 仅坐标变化且有可验证的同一来源原子身份/顺序时，可保留数值引用，但重新验证几何及新的结构摘要。
- 无法证明顺序连续时，当前输入中的旧 `atom_map`、reaction center、guidance、guess 引用自动清空；历史输入原样保留，不静默重排或重新解释数字。重建后 `next.required_inputs` 指向缺失声明，Agent 对新表填写编号。
- 外部源文件在原路径被改写也触发上述失效，不因修订 JSON 数值未变而沿用旧快照。绑定仍有效时，重复相同请求沿用现有幂等行为。
- 本规格不改变失败作业是否允许原输入重试的现行策略；文件补齐后的检查不会自动重启历史计算。

### 6.3 结构化错误

扩展既有 `TsBlocked` 的原子相关诊断，不新增错误服务。使用类型化 `issues`，记录 code、field、role、structure digest，以及按 code 区分的具体事实；不靠解析 message 决定恢复操作。

至少区分：

| code | 返回事实与下一步 |
| --- | --- |
| `source_missing` | 来源字段、路径；补文件或完整替换来源 |
| `atom_reference_invalid` | 字段、输入编号、基准、具体原子/有效范围 |
| `endpoint_binding_ambiguous` | 有歧义的一侧、原子表与本侧绑定字段；诊断中的匹配数量枚举触顶时标为至少该数，不冒充精确总数 |
| `endpoint_binding_invalid` | 重号/漏号/图或标签冲突的具体事实 |
| `atom_map_missing` | 来源变更后旧图映射被清空；读取新表并重交完整 atom_map |
| `endpoint_geometry_invalid` | 实际接触或键图异常、具体原子对和既有检查依据 |

在同一次输入核验中汇总可独立检测的问题，不为汇总而猜缺失信息；缺文件时跳过该文件下游检查。顶层 `blocked.needs/next.required_inputs` 从这些 issue 的修复字段生成。

本次范围内的提示只使用真实存在的 `changes.reaction`、`changes.conformers`、`changes.guess` 字段。说明完整来源对象需整体替换，不能让 Agent 只补一个子字段后再次遇到 schema 错误。

## 7. 原生 xTB 柔性扫描完整接入

### 7.1 首批支持范围

| 声明 | 本次契约 |
| --- | --- |
| `scan + engine=orca` | 保留现有单坐标扫描，编号 0-based |
| `scan + engine=gaussian` | 保留现有 1–2 坐标扫描，编号 1-based |
| `scan + engine=xtb` | 新增原生距离/角度/二面角柔性扫描，1–2 个扫描坐标，编号 1-based |
| xTB `concerted` | 两坐标同步推进，点数必须一致；一条耦合扫描曲线 |
| xTB `sequential` | 按声明顺序扫描各坐标，前一坐标保留在末值；分别记录各段 |
| `xtb_path` 与已有 xTB 构象优化 | 保留现有路线，不改成扫描，不受此次新增能力影响 |

首批执行沿用现有 native ChemTask 已支持的 GFN2-xTB；调用者必须显式声明该方法，不填默认。其他 xTB 方法尚未接通时精确报告能力限制，不把它们偷偷改成 GFN2-xTB。范围限制是现有执行实现的边界，不代表化学方法推荐。

不增加完整二维网格、任意集体变量、自适应扫描或新的 TS 优化算法。ORCA 执行的 GFN2-xTB 与独立 xTB 引擎保持区别。

### 7.2 公开输入

保持已有 `guess.kind=scan` 和 `calculation`；engine 包含 orca、gaussian、xtb。Agent 只声明科学上不可推导的值，内部执行参数由系统从既有资源声明和 xTB 原生行为生成：

```text
guess
  kind: scan
  calculation
    engine: xtb
    method: 显式 GFN2-xTB
  scans: 1–2 个已有 ScanCoordinateInput
  force_constant: 正的有限数，原生 xcontrol force constant 的原子单位（必填）
  mode: concerted | sequential（仅双坐标必填；单坐标由系统推导）
  solvation: 可选的已有 alpb/gbsa + solvent 结构；省略表示不添加溶剂模型
```

`keywords` 与 `freeze` 可省略；xTB 分支拒绝非空 Gaussian/ORCA 原生设置及 `freeze`，不把严格冻结暗改为有限势常数。首批不公开额外软约束、优化等级或步数上限；xTB 原生默认由保存的实际命令与引擎版本追溯，不在 Cloudra 自造科学默认值。扫描区间由每个 scan 的 `scan_start/scan_end/scan_steps` 表达。xTB 分支要求 start 和 end 均显式提供，`scan_steps` 为原生扫描点数且至少为 2；距离使用 Å，角度/二面角使用度。不得将反向扫描自动翻转，或无提示归一化跨周期二面角区间。

单坐标时模式对 Agent 不构成选择；双坐标必须显式选择 concerted 或 sequential。原生严格 Cartesian 固定与附加软约束不纳入首批接口。

校验要求：

- concerted 的两项 scan_steps 相等；sequential 允许不同点数。
- 坐标原子数、重复原子、有限数值和结构表范围由已有类型/显式逻辑校验。
- 同一坐标不得重复扫描；识别距离/角度/二面角反向书写的等价原子序列，保持有向二面角的已声明数值语义。
- xTB 不接受 ORCA blocks、Gaussian end_setting 或任意命令行字符串；所有 native 参数由受控字段渲染。
- orca/gaussian 不接受 xTB 专有字段；保留已有引擎的维数和原生块限制。
- prepare、resume、独立工具与 JSON Schema 使用相同扫描类型；新扫描计算类型纳入原子性替换集合，guess 整体替换，不能遗留上一引擎参数。
- 原先 D1 输入缺少 `force_constant` 或双坐标 `mode` 时报告精确字段；补齐后可生成原生任务包，不能再报 Unknown atom numbering context。

### 7.3 输入文件与已有计算账本

在 `runtime/chem_task.py` 的类型化任务中新增 `xtb_scan`，复用 ComputeDB、调度器、Guard、资源/节点选择及结果清单。保持 stage purpose=`scan`，仍归 `guess` 阶段；不新增独立调度服务。

新增扫描专用 writer/runner，唯一消费者为 ChemTask 与扫描工具的准备/解析入口。接受完整科学声明及已绑定起始 XYZ，生成不可变的任务清单、输入 XYZ 和 xcontrol。命令参数使用 argv 数组，不接收 shell 字符串。xcontrol 显式写入 `$constrain`、`$scan`、`$opt` 和结束标记；执行形式为 `xtb input.xyz --gfn 2 --opt --input scan.inp`，电荷、自旋、资源与可选溶剂来自声明。未额外指定优化等级，原生默认行为由所存命令和版本追溯。

扫描只依赖已绑定的反应物起始结构，不额外要求先提供产物几何才能调用独立扫描工具；TS 主流程的两端身份/最终方向证明仍遵循正常依赖。不为执行扫描偷偷增加一次无约束端点优化；需要预优化时由既有 conformer.optimization 显式声明并记录。

提交前 `_check_calculation_submission` 增加 purpose scan→task xtb_scan 的契约，逐项比对：方法、绑定结构、坐标与编号、mode、区间/点数、势常数、溶剂、电荷、自旋、资源。仍检查 owner 权限和受信 Benchmark 方法政策；通用计算契约存在时必须兑现，不能因为使用 chem_task 就跳过。

实际 native 命令和 xcontrol 只能由该受控清单生成，保存引擎版本、实际输入摘要和产物清单。在 guard 启动前核对清单与输入文件；执行期间不重读可能被修改的用户源文件。

由于旧格式 3 曾能保存缺少原生扫描势常数的 `scan+xtb` 声明，新记录使用格式 4；旧记录可只读检查但不自动接续或按新合同解释。已有计算作业、日志与排他锁保持原样。

正常结束后由既有完成事件驱动流程；读 inspect 不触发执行。重复通知和同 request key 不创建重复扫描。取消仍只走账本 cancel_requested 和现有远端收尾协议，禁止新 runner 的异常处理或超时路径擅自 kill 计算。取消/中断保留部分产物，不自动重新运行整个扫描。

### 7.4 独立工具与 TS 流程共享实现

`ts_guess(mode=scan_prepare, engine=xtb)` 只准备完整 typed manifest 并返回供提交的路径；原生 xcontrol 在 Guard 执行时从该清单生成并留存。现有 `submit_compute_job` 增加显式 `job_type=chem_task` 接受该清单，复用权限、DAG 入口、方法政策与执行契约；不得假装它是普通 `job_type=xtb` 的裸 XYZ，也不得通过 bash 绕过账本执行。

该 public chem_task 入口只开放本次需要的 `xtb_scan`，不能顺便暴露全部内部化学任务。所有外部路径限定在已授权工作区；从反序列化清单推导任务意图并校验，绝不信任调用者传来的“已经审核”字段。

`ts_guess(mode=scan_parse, engine=xtb)` 解析原生日志、扫描轨迹与清单。`ts_prepare/ts_resume` 调用同一 writer/parser，自动提交同一类作业。`read_task_result` 要覆盖扫描产物的路径重定位及摘要校验，支持已有远端下载布局；不得保留不可访问的远端绝对路径给下游。

### 7.5 逐点结果与收敛判定

解析器使用原生主日志中的扫描点/优化段边界，并与 `xtbscan.log` 帧对应。沿用原生正常终止、SCC 和几何优化收敛标记；不能用整个文件中的最后一次 CONVERGED 覆盖所有扫描点。原生日志可按日志解析规范处理，结构化入参与状态仍不得使用正则。

每点保存以下字段：

- 点序号、扫描段序号、该点目标坐标集合与实际测量值，附单位；
- 对应帧路径/序号、原子身份摘要和几何摘要；
- 每点 SCC 与几何优化是否具有原生收敛证据；缺证据记入 issues，扫描不可标为 complete；
- 原生报告能量、单位、能量来源及是否包含约束势；能独立提取时另存约束势能；
- mode、当前全部软约束目标及约束参数，避免 sequential 后续段丢失前段末值条件。

轨迹帧按原子数和原子记录严格解析；缺帧、多帧、非有限值、原子数/顺序不符和无法唯一对应日志点时均报明确不完整状态。验证扫描点数和首末目标必须使用已核实的 native 点数语义，不能通过凑帧数掩盖不同引擎的差异。

进程结束、扫描完成、候选可用三个状态独立保存：

1. `process_exit_code`、`normal_termination`：原生执行事实。
2. `scan_status=complete|incomplete`：全部计划点是否有可核验的正常收敛产物；进程失败仍按独立的返回码记录。
3. `usable_as_guess`：是否有符合现有峰值规则、来源明确的候选几何。

文件中的 `SCF done` 注释不等于该点几何已收敛。缺少逐点收敛证据时标 unknown；即使进程 exit 0、轨迹帧数足够，也不得自动发布可用初猜。

### 7.6 能量与候选提取

`xtbscan.log` 的能量字段不得套用现有 `xtbpath.xyz` 相对 kcal/mol 的解析语义。通过目标版本原生输出/来源和固定几何校验明确其单位与约束势组成；逐点 `energy_kind=electronic|unresolved`，原生偏置总能与约束势分别留字段。约束势缺失用 null，不填 0，不从可能不同点的能量相减。

已知为 biased_total 时可以展示明确标注的受约束势能曲线，并按该来源提取探索候选；不能将其差值标成真实反应能垒。若 energy_kind=unresolved，则保存原值和轨迹，阻止自动峰值候选发布。禁止静默补跑无约束单点或更换方法来修正曲线。

自动候选仅从 scan_status=complete 的序列提取，复用当前内部峰值、边界峰值、单调性及不连续诊断；不新增能垒或几何偏差阈值。记录目标与实际几何偏差，但不把“数值不完全相等”直接当成软约束失败。

concerted 按单条曲线处理；sequential 各段分别判断峰值，段间条件变更处不能当成内部峰值。零个可用峰时返回 scan_no_candidate；多段均有可用峰时返回各自候选及来源，由 Agent 显式选择并通过已有 provided 入口接续，不自动跨段选最高峰。

每个候选绑定具体帧、原子表、方法/约束声明、日志和摘要。只生成未验证 TS 初猜；后续解除扫描约束，按独立声明的正式 TS 优化→频率→IRC→端点验证继续。缺正式方法时停在对应检查点，不继承半经验扫描方法。

### 7.7 修订、错误与可重复性

任何 scan/mode/势常数/溶剂或起始结构变化，均形成新的输入版本并使 scan 与其下游结果失效；保持未受影响证据和费用历史。切换 xtb_path↔scan 使用原有 guess 整体替换规则。

无效扫描参数在类型化输入阶段报字段错误；可执行程序缺失由计算准入报告；引擎失败、逐点未收敛、产物不完整与无内部峰分别由作业状态、逐点 `issues`、`scan_artifacts_incomplete` 和 `scan_no_candidate` 呈现。错误直接给出实际字段和点/段证据，不能笼统提示“增加轮数”或引用旧 adjustment 字段。

无效 prepare 不建立流程；无效 resume 不修改 revision、声明、介入数或作业。结果缺失和格式不支持不自动换后端；底层计算有锁时继续保活，不能把解析失败当成杀进程的依据。

## 8. 改动落点

| 位置 | 职责 |
| --- | --- |
| `tools/core/ts_inputs.py` | 文件绑定类型、扫描专用类型、原子性补丁与字段说明 |
| `tools/core/geometry_inputs.py` | 增加 xTB 的 1-based 边界转换，与实际扫描后端一起交付 |
| `tools/core/ts_process.py` | 快照/原子表、绑定校验、扫描分派、提交契约、候选接续与准确组分投影 |
| `tools/core/xtb_scan_runner.py`（新增） | 专用类型化 writer、runner 和逐点 parser；不另建后端抽象框架 |
| `runtime/chem_task.py` | xtb_scan 任务、执行与结果清单、摘要核验及远端产物路径重定位 |
| `tools/Chemtool/submit_compute_job.py` | 限定 xtb_scan 的显式 chem_task 提交入口，复用权限及政策检查 |
| `tools/Chemtool/reaction_mapping.py` | 单份端点显式绑定与图校验；独立工具复用 |
| `tools/core/ts_revision.py` | 绑定/引用失效与显式重绑定，保留既有作业保护 |
| `tools/core/ts_state_view.py` | 共用 structures/issues 投影，不在 inspect 中重新计算 |
| `tools/Chemtool/ts_search_process.py` | 工具边界、精确字段提示、prepare/resume 同契约 |
| `tools/Chemtool/ts_guess.py` | 独立扫描入口与共享限制一致 |
| `docs/TS_PROCESS_SOP.md` | 只同步本规格涉及的编号、绑定和扫描契约段落 |

新 schema 生效后拒绝非法旧请求，不添加旧字段别名、模糊猜测或兼容开关。若实施改变了持久记录的必需语义，显式升级记录格式并隔离旧记录的自动续接；不得把缺失的新绑定证据自动补成有效。运行中的量化作业仍按原账本和锁保护，部署/恢复现有会话不属于本规格授权范围。

## 9. 验收矩阵

| 编号 | 场景 | 必须满足 |
| --- | --- | --- |
| A1 | D1 的 generate 来源、分组加氢结构 | 返回反应物重原子表 1,2,3,4,11,12；复用构造身份，不要求手工修改生成文件的标签 |
| A2 | 把 SMILES 中 5/6 当成上述结构中的碳 | 在任何新计算前指出其实际为 H；返回正确表，不自动猜替换编号 |
| A3 | 对称外部端点且仅有跨端点 atom_map | 仍不通过身份绑定；精确指出是哪一侧缺声明到结构绑定 |
| A4 | 对称外部端点提供有效显式绑定 | 不修改 SMILES/XYZ/MOL 即通过端点绑定；完整反应映射仍单独核验 |
| A5 | 显式绑定重复、缺失、越界、C→H、同元素但错误键对应或错误立体化学 | 全部拒绝，不提交计算 |
| A6 | 合法标签与显式绑定冲突；重复/部分标签 | 冲突或不完整事实可见，不通过任取图匹配掩盖 |
| A7 | 坐标/MOL 被改写，或同元素原子换序 | 旧摘要/引用失效；错误几何不能靠正确 MOL 或绑定数组放行 |
| A8 | 文件缺失后补齐；换来源；过期 revision | 正确报告文件错误，按现有显式修订流程重查；过期请求不覆盖新状态 |
| A9 | 片间过近或现有键序检查失败 | 保留原门禁；明确区分几何问题与映射歧义 |
| A10 | 更换正式 TS 引擎而未换扫描声明 | 已归一化原子引用不变、不发生二次减一 |
| A11 | prepare/resume/inspect/通知 | 相同 revision 返回同一原子表与 issue；inspect 零计算副作用 |
| B1 | D1 最初的 scan+xtb 输入及补齐参数后的版本 | 识别合法引擎；缺 force_constant 或双坐标 mode 时精确报字段；补齐后生成原生任务包，不再进入 Unknown atom numbering context 分支 |
| B2 | 相同非法扫描作为 resume | 原记录、revision、作业与介入数不变 |
| B3 | ORCA/Gaussian 合法扫描及 ORCA 双坐标非法扫描 | 原有合法行为保留；不支持组合在副作用前拒绝 |
| B4 | 独立 scan_prepare→提交→scan_parse 与 TS 自动扫描 | 共享输入、writer/parser 与账本契约；公开 schema 支持范围一致；方法不被自动替换 |
| B5 | xtb_path 与已支持的 xTB 构象优化 | 原有入口与执行契约保持有效 |
| B6 | xTB 距离、角度、二面角原子引用 | 外部 1-based→内部编号→原生 1-based 只转换一次；越界及重复原子在提交前拒绝 |
| B7 | concerted 与 sequential 双坐标扫描 | 前者点数不等时拒绝且零提交；后者各段点数、顺序和前段末值条件正确保存 |
| B8 | 截断日志、缺帧、非有限数、单点未收敛及 exit 0 但证据缺失 | 保留逐点 failed/unknown 证据；不得判 complete 或自动发布初猜 |
| B9 | 含约束势或语义未知的原生能量 | 正确标注单位/来源，不套用 path 的 kcal/mol 语义；未知语义阻止候选自动发布，不伪称反应能垒 |
| B10 | 清单/结构/参数被篡改，或无权提交内部任务 | 提交与执行前核验拒绝；chem_task 不绕过 owner、DAG 和受信 Benchmark 政策 |
| B11 | 远端产物回收、重复完成事件与重复 request key | 产物可访问且摘要相符；无重复扫描或重复阶段推进 |
| B12 | 单调曲线、边界峰和 sequential 多段峰 | 复用诊断；不把段间跳变当峰；多个候选要求显式选择并保留来源 |
| C1 | 有在途量化作业时尝试修订 | 维持原有拒绝与锁保护，绝不杀计算进程 |

测试落点：`test_ts_inputs.py`、`test_geometry_inputs.py`、`test_ts_input_evidence.py`、`test_reaction_mapping.py`、`test_ts_resume_transitions.py`、`test_ts_guess.py`、`test_chem_task.py`，新增 `test_xtb_scan_runner.py`，并覆盖对应状态投影、提交权限和政策入口。

在 `tests/agent_scenarios.py` 增加 D1 反应物 16 原子顺序的输入恢复场景：ScriptedProvider 触发缺少 xTB 势常数的字段错误、读取原子表、明确两侧端点绑定、提交完整全原子映射和扫描声明，推进到模拟 xtb_scan 账本作业。两侧在此接口 fixture 中使用同一张图，以隔离编号恢复；它不检验 D1 产物或真实反应路径。只断言事件、字段、状态与提交次数，不断言模型自然语言。该脚本证明接口可完成恢复，不证明真实模型必然一次成功。

fixture 仅抽取 D1 所需的声明、16 原子结构及映射事实，存放在隔离测试数据中；不能把本机数据目录写进测试，不能读取运行会话作为测试依赖。依赖 RDKit 的测试在缺安装时显式跳过；真实 ORCA/xTB 不作为契约回归的运行前提。

实施后遵循 `compileall → ruff → 相关模块/新增场景测试`，不跑全套。若另行开展真实 D1 验证，单独报告结构绑定通过、扫描输入被接受、路径收敛、TS 科学验收四层结果；本规格不将前两层等同于后两层。

原生接入必须另有真实 xTB 冒烟验收：使用来源明确的测试分子与测试参数，覆盖单二面角、双坐标 concerted 和 sequential，记录二进制版本、完整输入、逐点输出、首末目标、实际坐标与能量语义核对结果。测试参数仅为 fixture，不成为生产科学默认值。缺少 xTB 时相关集成测试通过探针跳过；此时只能报告契约/单测通过，原生接入尚未完成验收。不得为验收擅自恢复或改写现有 D1 作业。

## 10. 完成定义

1. Agent 可从同一份实际原子表填写结构字段和引擎坐标，不必通过文件改名或反复标号寻找可接受输入。
2. 外部对称结构有明确、可校验、绑定具体产物的端点身份表达方式；无证据的歧义仍然被拦截。
3. 扫描声明的 schema、prepare/resume 与实际执行能力一致，非法组合在副作用前失败。
4. D1 故障得到定点回归覆盖；既有科学判据、历史证据与计算进程保护保持有效。
5. 原生 xTB 扫描经已有账本实际执行，逐点证据与能量语义完成验收；独立工具及 TS 流程共用实现，产物可以追溯。
6. 扫描完成、初猜可用与 TS 科学确证分别报告；没有频率与 IRC 证据时不得宣称找到已验证过渡态。

以上是设计建议。实施时不得自行新增科学阈值、替换理论方法或自动选择化学映射；这些不在本草案中授权。

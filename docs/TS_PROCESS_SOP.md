# TS 状态机使用与验收

2026-10-02：分组接口已接通并以测试替代计算器验证；真实 ORCA/Gaussian 全链尚未验收。上游接口语义见 `superpowers/specs/2026-10-02-ts-state-machine-interface-design.md`。不新增化学阈值、默认理论方法或兼容旧字段。

## 三个入口

- `ts_prepare(input, request_key, workspace_dir?)`：创建路径一次，接受显式输入并保存 checkpoint；同一个幂等键重放返回原 run。
- `ts_inspect(run_id, workspace_dir?)`：读取同项目权威状态、作业、方法、证据、实际费用和下一步；只读审查员可检查别人的 run。不会推进、重新解析或提交计算。
- `ts_resume(run_id, changes, reason, request_key, expected_revision, recovery?, workspace_dir?)`：原 owner 修订同一个 run。正常成功链自动推进，无需调用 resume；空修订报错引导 inspect。非空但值不变不消耗介入次数、不推进、不写回执。

普通 Opt/Freq/单点/探索扫描仍用已有计算入口；手动 TS/IRC 提交暂时关闭，含 TS/QST2/QST3/OptTS/ScanTS/NEB-TS/IRC。不得通过其他 Agent 或 bash 绕过。关闭限制前须保留真实 TS 优化频率、双向 IRC 和两端 Opt/Freq 及身份验证产物；单测不构成真实引擎验收。

## 输入分组

| 组 | 明确含义 |
| --- | --- |
| reaction | 两端 SMILES、电荷、自旋、全原子 atom_map、reaction_center |
| conformers | 两端 generate（显式 ETKDGv3 和 seed）、file、精确 catalog/partition/candidate 或已支持的 product 绕键旋转；可单独声明 optimization；guidance 为成环顺序/距离窗口 |
| guess | 判别式 kind：xtb_path（显式 GFN2-xTB、可选溶剂/迭代数）、scan（独立 calculation/scans/freeze）、provided（XYZ 和证据引用） |
| ts_optimization | 正式鞍点优化的独立 calculation |
| verification | 独立 TS frequency、irc、各向 endpoint.optimization/frequency；可声明已完成的 irc_log 或端点 file seed（XYZ、可选 MOL、证据） |
| execution | 计算节点/CPU/内存和可选有来源的动作、模型请求、介入次数额度 |

`calculation` 明确 engine/method/keywords；可带对应原生 orca_blocks/end_setting。方法不从其他组继承；不替 Agent 决定半经验扫描方法。当前 native 构象优化和路径能力只支持已有 GFN2-xTB；其他明确方法使用已有 ORCA/Gaussian 写入器，能力不足点名阻塞。缺失方法不填默认。构象生成不暗中做力场优化；带指导的构象使用已声明约束优化方法。

结构字段 1-based；ORCA 原生 scan/freeze 字段 0-based，Gaussian 1-based。atom_map 含全部氢，产物第 k 个原子映射到反应物 atom_map[k-1]。

部分修订：省略保留；可选 null 清除；列表、方法、判别式来源及 guess 整体替换。未知字段 fail loud，不解释为旧接口。

## 持续推进、失败与修订

declare → build → map → assemble → guess → validate → submit → refine → verdict。方法、结构、方向和证据缺失均点名暂停；waiting 是等待系统作业而非 Agent 决策。计算终态通知和重启 reconcile 自动接续，重复事件不重复建作业。后续变化继续用同一 run，不用重新 prepare。

verified / candidate_only / search_failed / invalid_input 是一次尝试的结果，不封死路径。修订将原输入、失败、作业和证据归档，生成新 input_revision 和结构化 receipt。expected_revision 来自 inspect；相同 request_key 先去重再检查过期，键冲突报错。回执先持久化，随后提交副作用。原生输入文件和旧证据不可覆盖。

在途 READY/running/cancel_requested 作业禁止修订，不终止计算。固定依赖失效：构象变更重建下游；映射/初猜变更重跑探索及正式链；TS 方法重跑正式链；TS Freq 变更保留 TS Opt；IRC 变更保留 TS/Freq；单侧端点变更只重算该侧 Opt/Freq，另一侧及 TS/IRC 保留。

恢复必须绑定 `failed_attempt="输入版本:purpose:job_id"` 和工作区内实际 evidence_refs。单纯 reason、扫描 7 点改 8 点或自由文本“环境修好了”不能清除第一点 SHARK/临时文件失败。可核验的后续同输入成功执行证明环境已恢复；改种子须有相关成功原生计算或精确归档候选资格。计算正常退出但虚频不合格同样记录失败。历史失败和费用不清零。

既有 IRC 来源须来自同项目 authoritative done 作业，输入摘要、原生正常结束、自己的方法契约、TS 频率参考几何和双向外帧全部可核验；几何按写入器已有 8 位坐标精度比较。复制为不可变证据并保留来源；不重新提交 IRC，不从无来源路径直接接受 verdict。

## 科学证据与权限

实际结构图与坐标先绑定输入版本和摘要；同元素排列不等于同物种。未标记对称绑定保持 inconclusive；由既有 atom_identity 表生成的结构或明确旋转可使用构造绑定。每次搜索和正式提交前重查实际结构。外部 XYZ 的图由既有键感知器确定并保留 MOL；歧义须补充实际结构来源，不猜映射。最终端点身份、立体化学与方向证明仍独立验证。

每个计算入 READY 前读取实际原生方法、全部关键词/溶剂设置/电荷/自旋，与本阶段声明和当前受信 Project MethodPolicy 比较。可选 calculation_contracts 给各 purpose 完整受信原生契约；方法来源不明停止。扫描方法可与正式方法不同，但都须明确且被允许。基组等价拼写规范化，不接受未知额外方法。资源字段不充当科学契约。

只读 Agent 可查状态/发证据但不能提交、修订、spawn/call 能力更大的 producer，证据 post 不唤醒 producer。自动续接每次提交也重新检查当前 owner 权限和方法政策；权限撤销只停止新提交，关联量化进程继续运行。

## 保留的物理验收

TS Opt 须原生正常结束并收敛；TS Freq 有且仅有 1 个虚频。双向 IRC 须有真实可用外帧，各向经无约束 Opt/Freq 确认为收敛的零虚频极小点，物种与立体化学吻合，且相对 TS 与对应极小点的方向区间吻合。IRC 本身可如实 partial，无须双向到底收敛；缺证据只到 candidate_only。路径/扫描/提供的峰帧均不直接作为已验证 TS。

复用现有成环非键合窗口 1.6–3.0 Å、组分接触图 1.7×vdW、碰撞下限 1.0 Å；显式错误窗口 fail loud。候选不代表平衡构象。初始 Hessian 仅取同理论级别真实产物，不以位移末帧代替中心导数。xTB 路径相对 kcal/mol 与候选绝对 Eh 分开记录；原生收敛和正常终止标记决定结果。

## 观测与费用

prepare / resume / inspect / 终态通知共用状态投影：status、stage、result、waiting_for、available_results、blocked、failed_attempt、next、methods、usage、details_path/export_revision。完整输入、历史和证据在权威账本与 process.json 快照；导出 revision 与账本分开展示。

删除 estimated wall/CPU hours、time_budget_hours、预计 CPU 小时准入及缺估计阻塞。动作数、实际模型请求（含 transport 重试）、介入次数保留。runtime_seconds 是经过时间；allocated_cpu_hours 是申请核数×经过时间；measured_cpu_hours 缺测量为 null，不能冒充实测。历史和约束优化的各梯度/Hessian 作业都计入真实动作。旧格式记录停止自动接续，现存计算和排他锁不动；不迁移/默默兼容旧科学输入。

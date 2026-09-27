# 过渡态搜索 SOP（process 包）规格

> 状态：流程已实现；2026-09-27 增加扫描接管与统一编号。正式引擎的新扫描语法尚未端到端实跑。上游依据
> `docs/superpowers/plans/2026-09-11-chemical-structure-and-ts-workflow.md` 与
> `docs/TS_BACKEND_SELECTION_GATE.md`。
>
> 设计原则（用户明确要求）：**杜绝过度工程**；暴露给 agent 的接口必须最简洁；
> **不替 agent 做决定，只诱导它走上正确的路**；走对路也失败时必须鲁棒（终态不伪造）；
> **不设查询接口**，状态经事件注入上下文。

## 1. 定位

SOP 是**一条可被 agent 在阻塞处接管的自主流水线**，不是固定脚本。从属关系：

```
agent 的 JS 程序（易失，agent 写）   ← 起一次、阻塞后调整再续
        ↓ 调用库函数
TS SOP（runtime 侧持久状态）          ← 阶段推进、校验、提交、派发、记账
        ↓ 提交作业
现有计算链路 submit_compute_job → scheduler → guard → 引擎
```

- **JS 是驱动器，进程状态不住在 JS 堆里**：`js_runtime` 的既有语义是「堆不跨重启恢复、
  失败程序不自动重跑」，而一次 TS 搜索横跨几十分钟计算、中途等 agent 决策。状态是
  runtime 侧的持久记录，JS 程序可以重建。
- **不新增实例**（用户要求奥卡姆）：不加守护进程、不加服务、不加 policy stage、不加
  pending broker、不加长驻脚本、不加状态库。复用 `compute.db`（计算句柄）、既有通知路径
  （`compute_notify`）、既有唤醒语义（run 休眠 / `wait_background` / SUCCEEDED ≠ 任务完成）、
  既有事件持久化与上下文投影。

## 2. Agent 可见接口：两个函数

```js
ts.prepare({reactant, product, charge, multiplicity, method, budget, reaction_center?})
  -> { run_id }

ts.resume(run_id, adjusted)
  -> { ok }
```

| 函数 | 语义 |
|---|---|
| `ts.prepare` | 起一次搜索。进程随后**自主**跑完：建结构 → 映射 → 组装 → 路径初猜 → TS 精修/频率/IRC → 两端 Opt/Freq → 连通性判定 |
| `ts.resume` | 进程在**阻塞**处停下后，带上调整过的声明从当前位置继续 |

`ring_order` 和 `distance_filters` 可以各自使用，也可叠加。二者均引导生成并严格验收最终候选；filter 本身不声明成键。ring 还保留有序环构象入口。六元环自动返回 chair-like、boat-like 等最近参考族，详细几何描述落 manifest；标签不证明稳定性或 TS 有效性。

流程所有原子字段统一 **Gaussian 1-based / ORCA 0-based**，包含氢，涵盖 map、reaction_center、ring、filter、scan、freeze 和产物旋转。独立结构工具使用 1-based，转入 ORCA 时减一。内部记录固定 0-based，旧无版本记录明确拒绝恢复。

缺省非键合环边窗口仍为 `AssemblyParameters.reaction_center_window` 的 **1.6–3.0 Å**，显式错误窗口直接失败。组分整体按 **1.7×vdW** 接触图连通性验收，碰撞下限仍为 1.0 Å。候选不是平衡构象；IRC 端点仍需无约束 Opt/Freq 和身份验证。

需要扫描时，在 `ts_prepare.declaration.scan` 或受阻后的 `ts_resume.adjustment.scan` 声明 `{method, scans, freeze}`。扫描方法显式给出；freeze 只声明坐标类型和原子，冻结当前值。流程负责提交、等通知、解析内峰，再做不继承 freeze 的无约束 TS 精修和既有验证。正常收到计算通知后，只需 `ts_resume({run_id})`，不消耗干预次数。无内峰、缺日志或缺几何会明确阻塞；扫描峰不等于 TS。

几何引导改变后清除旧扫描状态、重建初猜，新旧产物留档；在途作业或已提交精修时拒绝修改。补扫描不会跳过未完成的 build/map/assemble。

要点：

- **`submit` 不是 agent 的函数，是流程内部的阶段。** 校验与提交都由进程自己做——校验是
  流程自己的职责（用户明确），只有校验**失败**才交给 agent 调整、再 `resume`。提交时机由
  声明里的 method/budget 决定，不需要一个 agent 的"扣扳机"动作。
- **method/budget 放进声明**：有界推进要求进程一开始就知道预算上限。
- **`resume` 只接受局部覆盖**，不是重新声明整条反应。

### 状态经事件注入，不设查询接口

**没有 `status`**：状态变更以**事件注入 agent 上下文**。理由（用户指出）：暴露查询接口就是
在**诱导轮询**——模型会反复问，浪费轮次与上下文。这也与既有实现一致：作业终态本来就是经
`compute_notify` 推给 agent 的，不是让它查。

**推事件也有反面失败模式：推得太勤就是污染上下文。** 所以触发集必须窄：

| 推 | 内容 |
|---|---|
| **阻塞**（需要 agent 才能继续） | 失败分类 + 当前 stage + **原子级细节** |
| **终态** | 四态之一 + verdict + 证据引用 |

**不推**：阶段推进、中间进度。这些只留在 process 记录里，agent 需要时自己读那一个文件，
不走上下文。

`path_kind` ∈ `scan` / `xtb_path` / `xtb_path_failed` / `idpp_fallback` / `not_attempted` 随**事件**报送
（`xtb_path_failed` = 引擎确实跑过但没产出可用初猜，与"根本没搜"的 `not_attempted` 分开）：
**初猜是怎么来的必须写明**，不许静默降级。

## 3. 阶段

前两列是 agent 视角：只有 `prepare` 与「阻塞后 `resume`」两个入口，其余全自主。

| 阶段 | 谁触发 | 做什么 | 产出 |
|---|---|---|---|
| `declare` | `prepare` | 记录两端 SMILES、电荷/多重度、method/budget、反应中心（可选） | 声明记录 + `run_id` |
| `build` | 流程 | `structure_builder` 建两端结构（拆分/加氢/稳定原子身份/逐组分优化） | 结构 + 轨迹 + 身份表 |
| `map` | 流程 | 核对声明的 `atom_map` 能把产物**重排到与反应物同序**；缺映射/错映射则**阻塞** | 校验结果 |
| `assemble` | 流程 | `complex_assembly` 反应模式：反应中心引导的预组织复合物 | 组装候选 |
| `guess` | 流程 | 路径初猜：优先 xTB `--path`（MTD，**需目标几何**），xTB 缺失退回 IDPP 插值；失败即阻塞并在消息里点名下一步（通过 `ts_resume.adjustment.scan` 声明扫描是默认补救路线，`interpolate` 只在两端几何与全原子映射都可信时用），引擎崩溃留下的中间帧只作可发现性上报、不作初猜 | 多帧路径 + 随机种子 + `path_kind` |
| `validate` | 流程 | 第 4 节的校验；失败则**阻塞** | 校验报告（进 process 记录） |
| `submit` | 流程 | 经 `submit_compute_job` 提交精修作业（OptTS / NEB-TS） | `job_id` |
| `refine` | 计算链 | TS Opt/Freq → IRC → 两端各自无约束 Opt/Freq | 引擎日志、末帧几何 |
| `verdict` | 流程（自动） | TS 频率与 IRC 双向 → 两端优化收敛、零虚频和物种身份 → 区间证明 | 终态 + 证据引用 |

### 为什么 `map` 是必需的，不是形式

构建器按**连通分量**拼装两端，所以两端的原子顺序本来就不一样（本机实测：
`[F-].CCl` → `[F,C,Cl,H,H,H]`，`CF.[Cl-]` → `[C,F,H,H,H,Cl]`）。而路径搜索要求两端是
**同一套、同序**的原子。所以 `guess` 阶段必须先按 `atom_map` 重排产物，重排后的几何落在
`path/product_reordered.xyz` 供复查；`map` 阶段则把错映射**点名到原子**地报出来
（"产物第 k 个原子是 X，但映射指向反应物第 j 个原子是 Y"），而不是拿着错序去跑。

### guess 阶段已落地的实现与实测事实

初猜的便宜端已实现为 `cloudra/tools/core/xtb_path_runner.py`（持久运行目录 + 分层失败分类，
与 `crest_runner` 同构；测试见 `tests/test_xtb_path_runner.py`）。本机 xtb 6.7.1 实测：

- **xTB 没有 NEB**，只有 `--path`（元动力学路径搜索），调用形式
  `xtb reactant.xyz --path product.xyz`；**两个几何必需**，元素序列必须一致。
- 产出 `xtbpath.xyz`（路径逐帧）与 `xtbpath_ts.xyz`（TS **候选**，不是鞍点）。
- **两个文件注释里的能量单位不同**，这是最容易静默出错的地方：
  `xtbpath.xyz` 是**相对输入几何的 kcal/mol**（实测某帧注释 52.271 对应真实能量差
  52.272 kcal/mol）；`xtbpath_ts.xyz` 是**绝对 Eh**（实测与单点一致到 1e-12）。
  运行器把两者放在**不同字段**（`rel_energy_kcal` / `ts_candidate_energy_eh`），绝不合并。
- 成功标记 `normal termination of xtb` 落在 **stderr**，计时块落在 stdout：
  标记必须在两个流上一起扫，只看 stdout 会把正常运行判成失败。
- MTD 随机：结果按采样看待，命令与 stdout 全量落盘备查。
- **路径精修必须跑到引擎自己判收敛，不能沿用内建默认 3 轮**（这条是实测踩出来的坑，改动见
  `xtb_path_runner` 的 `DEFAULT_REFINEMENT_RUNS` / `RefinementTermination`）：xTB 的路径是
  **迭代精修**的，内建上限只有 3 轮，3 轮后打印的 `terminated because max. # cycles reached`
  是**被截断**、不是收敛。M1（2,2'-二甲基联苯，声明 `product_geometry = rotate_about_bond(_, 180°)`）
  实测：

  | 精修轮数上限 | 引擎结局 | barrier (kcal/mol) | 最高帧 θ | 送去 ORCA `OptTS` |
  |---|---|---|---|---|
  | 3（内建默认） | 触顶截断 | **44.865** | −108°（离起点仅 21°，仍在反应物盆地里） | 56 轮不收敛，滑回极小值 |
  | 10 | 触顶截断 | 26.629 | — | — |
  | 30 | 触顶截断 | 18.290 | — | — |
  | 100 | **引擎自判收敛**（第 31 轮） | **18.299** | **−5.7°（平面构型，正是扭转极大）** | **9 轮收敛到一阶鞍点，+16.03 kcal/mol** |

  即：**"MTD 生成不了接近过渡态的初猜"是机时上限造成的假象，不是方法本身的问题**；把上限放开到
  引擎自判收敛，同一对端点就给出可用的初猜（barrier 落进独立弛豫扫描给出的 14.3–18.3 区间）。
  因此运行器**总是**写一份 `$path`（`nrun=<上限>`）传给引擎，并把 `converged` /
  `cycles_exhausted` **分开分类**：触顶一律报 `path_not_converged` 且 `usable_as_guess=False`
  （现场保留供复查），绝不把截断路径当初猜。`$path` 认得的键实测只有 `nrun` / `npoint` /
  `kpush` / `kpull`（`alpha` 要用 `alp`）；`$scan` / `$fix` 在本 build 被**静默忽略**。
  全套逐字证据 + 可重跑脚本 + 自查脚本在 `docs/evidence/ts_guess_mtd_artifact/`。

## 4. 校验：流程自己的职责

校验**是流程内部的闸门**，不是交给 agent 的决策点。走同一套校验器，不管几何是自动生成的
还是 agent 给的：

- 元素与原子数守恒（两端 + 路径每一帧）
- 原子身份守恒（用构建器登记的稳定身份，不用数组下标）
- 片间最小原子间距 ≥ 1.0 Å（既有判据；issue #33 实测互穿到 0.1392 Å）
- 路径几何合法性：无原子对穿、能量有限
- 反应中心距离落在合理区间
- 映射是真置换

**失败时交给 agent 调整，然后 `resume`。** 阻塞事件必须**点名到原子**，这才是"诱导"而不是
"拦截"。例如：

> `reaction_center` 声明的 (0,1) 对在组装后距离 0.31 Å，低于 1.0 Å 碰撞判据；第 3 与第 5
> 号原子间距 0.12 Å。

agent 据此才知道该改哪一项声明（换组装候选？改反应中心？改映射？），而不是靠猜。

## 5. 失败分类 → 干预派发表

失败分类沿用已实现的 `crest_runner` 分层（精确整行/token 比对）。阻塞事件带分类，
agent 据此决定：

| 分类 | 通常的干预 |
|---|---|
| `initial_optimization_failed` | 查几何（多半是校验漏掉的互穿）；换组装候选 |
| `initial_topology_change` | 复核声明的成断键是否与实际一致；查 `topology_change` 逐条变化 |
| `search_failed` | 换后端 / 加采样 / 改路径初猜 |
| `timeout` | 提预算 / 缩体系 |
| `incomplete_artifacts` | 一般不可干预，报错 |
| `unknown_failure` | 保留原文，agent 读日志判断 |

## 6. 干预记账（不新增存储）

干预是 runtime 的**事件**，走既有事件持久化，不新建 `interventions.jsonl`。
每条记：触发的失败分类、agent 改了什么声明、重跑后的终态。

理由不只是整洁——**"要不要 agent 补救"本身就是要测的指标**。不记账就无法区分
"系统自己跑通的"和"agent 救了三次才跑通的"。

## 7. 目录约定

逐迭代帧只在一个子树里，绝不平铺：

```
ts/<run_id>/
  process.json        # 状态机：阶段进度、阻塞、预算账、干预计数（每运行一份，不新建存储）
  declare.json        # 声明（两端、电荷/多重度、method/budget、反应中心、atom_map）
  build/<role>/       # 两端构建产物；逐迭代帧在 build/<role>[/assembly]/trajectories/
  path/               # 初猜路径 + 随机种子 + product_reordered.xyz + xtb_path_runs/
  jobs/<job_id>/      # 计算现场（沿用既有 calc-<id>.out.log 约定）
  verdict/            # 频率/IRC 判定
```

两条纪律：

1. **逐迭代帧集中在 `build/trajectories/`**；路径与组装阶段只留阶段首末帧。
2. **别把万帧文件拷进 `.cloudra/evidence`**：证据快照是 `copy2` + sha256，绑万帧文件
   既慢又没信息量。verdict 只绑**小而有意义**的产物（末帧几何、能量剖面、日志）。

顺带收掉一个现存不一致：`conformer_search` 用 `structure_build/`，
`smiles_to_mol` / `qm_input_writer` 用 `<stem>_build/`——统一成一个名字。

## 8. 终态

四态，且**搜索失败 ≠ 反应不可能**：

| 终态 | 含义 |
|---|---|
| `verified` | TS 频率恰好 1 个虚频 + 双向 IRC 真实最外帧分别无约束 Opt/Freq，确认两侧极小点及声明物种身份 + 两向最外帧相对 TS 和对应极小点的方向区间证明；IRC 可如实标为 partial，无须自身双向收敛 |
| `candidate_only` | 拿到候选鞍点但证据不足（缺一侧可用 IRC 几何、频率缺失、优化后端点身份不符或方向未证实）；仅 IRC 未到自身收敛标记不构成此判定 |
| `search_failed` | 搜索没跑出来——**不构成"该反应不可能"的结论** |
| `invalid_input` | 输入本身不成立（歧义未解、电荷/自旋矛盾） |

## 9. 有界推进

必须有界：已生效的最大干预次数、路径精修轮数与作业资源限制；未实现的总机时字段已删除。否则退化成无收敛保证的循环。
上限来自声明的 `budget`；耗尽即落终态，不无限续。计算作业完成通知引起的空调整
`ts_resume` 不计入人工干预次数。

## 10. 本规格明确不做

- 不新增 agent 可见工具动词（只暴露上述两个 JS 函数）
- 不提供 status / 查询接口（状态经事件注入，避免诱导轮询）
- 不禁止 agent 提供几何，只要求**过同一套校验器 + provenance 记账**
- 不另起绕过 scheduler 的执行链；SOP 绝不自己 spawn 引擎
- 不在任何阶段把"没验证"标成 `verified`
- 不在选型未定时引入新依赖

## 10.5 实现进度（`cloudra/tools/core/ts_process.py`）

| 阶段 | 状态 |
|---|---|
| `declare` / `build` / `map` / `assemble` / `guess` / `validate` | **已实现**（测试 `tests/test_ts_process.py`） |
| `submit` | **已实现**：写精修输入 → **复用**唯一一份准入校验 → 入库为 `ready`（归属随 `TsStartRequest` 盖章：项目 conversation_id + 发起 agent 的 session_id，缺归属 fail-loud 拒收） |
| `refine` | 作业序列 TS 优化 → 频率 → 双向 IRC → **各向真实最外帧**分别无约束 Opt/Freq，每步都等终态；**从不轮询**——未到终态时本阶段置 `waiting` 且**不推事件**，作业终态由既有 compute 通知路径投递，agent 收到后调 `ts_resume`（无需调整）继续 |
| `verdict` | 四态判定只读交付物。TS 非一虚频、缺一侧可用 IRC 几何、任一外帧 Opt 未收敛或 Freq 非零虚频/缺失、优化后物种身份变化或方向区间证明失败，都只到 `candidate_only`；单纯 IRC partial 不降级，路径初猜绝不直接充当极小值 |

`submit` 的准入与 `submit_compute_job` **共用** `services/compute_admission.admit_job`
（唯一实现：输入存在、xtb 参数、节点/调度器解析、资源硬校验、申请量不得低于输入自述、
引擎可用性）；精修输入复用 `qm_input_writer` 的构建器与 `validate_writer_request` +
`inspect_input` 一致性核对——**没有第二套输入语法**。引擎各自的 TS 写法照
`skills/dft-calculation/references/{orca,gaussian}-inputs.md`：ORCA 用 `{"opt":"ts"}` +
`%geom Calc_Hess true`；**频率是后续独立作业**，因此归 `refine`，不和 TS 优化挤在一个作业里。

`refine` 的输入都复用 `qm_input_writer` 的构建器，配方照
`skills/dft-calculation/references/{orca,gaussian}-inputs.md`：频率是**独立作业**且几何取
TS 优化末帧；IRC 复用**同一几何**的 Hessian——Hessian 分支由**证据**决定（频率作业真的落下了
同名 `.hess` 就用 `InitHess read` + `Hess_Filename`，否则按 skill 用 `InitHess calc_numfreq`），
不是偏好；Gaussian 走 `irc=calcfc`，不硬编码统一的 `MaxPoints`。IRC 长度按方向证据、路径特点及计算成本权衡，原生收敛状态仍须保留并如实报告。
两端从双向 IRC 的**真实最外帧**分别提交无约束 Opt，Freq 输入取对应 Opt 日志的收敛末帧；
forward/backward 只是轨迹标签，须依据优化后结构身份与声明物种匹配，不能预设哪侧是反应物或产物。
终判时还须核对 Opt 日志几何、保存的频率源几何和 Freq 日志几何一致。
现有物种身份检查核对连接关系与键级，不独立区分同 SMILES 的构象身份；
此类任务仍须审查优化后的实际构象，不能把 `verified` 当作完整构象或动力学证明。

已实现的部分含：内化校验（失败即阻塞并点名到原子）、只推阻塞/终态两类事件、四态终态、
按声明预算的有界推进（干预次数耗尽即落 `search_failed` 并注明"搜索失败 ≠ 反应不可能"）、
目录约定（逐迭代帧只允许在 `build/**/trajectories/` 下，有测试守）、
证据候选只含小产物（逐迭代帧永不入内，有测试守）。

## 11. 待定

1. **`ts_guess` 默认改 xTB 路径**——**已落地**。`mode` 默认 `xtb_path`；误导性的 `xtb_neb`
   别名已删除（`xtb_neb` 现在会被 schema 直接拒掉）；输出 schema 增 `path_kind`
   （`xtb_path` / `idpp_fallback`）；xTB 缺失时退回 `interpolate` 并在 `path_kind` 与 message
   里**显式标注**降级；xTB 存在但跑失败时**不**换兜底充数，而是报出分层分类与持久运行目录。
   新增 `timeout` 字段（`xtb_path` 是 ts_guess 里唯一跑子进程的模式，必须有界）。
   测试见 `tests/test_ts_guess.py` 末尾的 guess 阶段用例。
2. **构建产物目录命名已统一**为 `<父目录>/structure_build/<slug>/`
   （`structure_builder.BUILD_DIR_NAME` + `build_artifact_dir` 是唯一事实来源，
   `smiles_to_mol` / `qm_input_writer` / `conformer_search` 共用；`slug` 层避免同一目录下
   多个结构互相覆盖）。
3. **xTB `--path` 的 MTD 随机性**：需记录种子并当采样看待；同一输入重跑路径不同。
   是否多次采样取最优，属预算决策，需批准。
4. **ORCA NEB 输出的解析**：已确认并已处理一半——
   `orca_frames.detect_job_types` 现在会从输入回显的 `!` 行识别 `neb`（`! NEB` / `! NEB-TS`），
   并且只跑路径搜索的 `! NEB` 日志**返回空而不是退化成单点**（把一条路径报成一个结构比
   什么都不报更糟）；`! NEB-TS` 会同时给出 `ts`，逐帧几何由后面的 TS 优化段正常解析。
   **仍未实现**：只跑 `! NEB` 时逐图像的几何提取（那段几何在 ORCA 的路径输出文件里，
   主输出只有逐迭代能量表）。本机没有真实 ORCA NEB 日志可对照，按项目规则不凭猜测写解析器；
   补这块需要一次真实的 ORCA NEB 运行。

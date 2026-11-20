# 过渡态（TS）流程与科学验收

本文档说明 Cloudra 过渡态求解流程（格式 7）的实际用法和科学验收红线。工具参数以 `cloudra/tools/core/ts_inputs.py` 和 `cloudra/tools/Chemtool/ts_search_process.py` 为准。

## 四个核心工具

| 工具 | 怎么用 | 干什么用 |
| --- | --- | --- |
| `ts_prepare` | 填 `input: TsInput` | 为一条反应路径建档并自动往前推进；作业算完后自动接下一阶段 |
| `ts_inspect` | 填 `run_id` | 只读查看当前状态、原子编号表、作业列表、实际方法、已有证据和下一步建议 |
| `ts_resume` | 填 `run_id`、`reason` 和可选 `changes` | 修订同一个 run：失败了可以原样重试，也可以换初猜、改扫描或调方法继续探索 |
| `ts_stop` | 填 `run_id` 和 `reason` | 停掉后续自动推进；撤回排队作业，给运行中作业写 `cancel_requested` 等它安全退出 |

并发版本、防重放键和摘要全由程序管，模型不用填。`ts_prepare` 建好一次就别重复建，正常跑完会自动续接，不需要反复调 `ts_resume`。

**什么时候走 `ts_prepare`，什么时候直接交计算**：正式求 TS 和做完整验证优先走 `ts_prepare` / `ts_resume`；普通物种优化、单点能和试探性扫描直接用 `submit_compute_job`。手头已经有外部候选结构时，通过 `guess.kind="provided"` 接回流程；有合格的已有 IRC 日志时填 `verification.irc_log`。如果你直接用 `submit_compute_job` 跑了 Gaussian/ORCA 的 IRC，算完正常结束且双向都有帧时，系统会自动导出规范的两端 XYZ（`irc_end_a_path` / `irc_end_b_path`），但 A/B 还不等于反应物/产物，必须再分别做无约束 Opt/Freq 确认身份。

## `TsInput` 里要填什么

除了 `reaction` 必填外，其他字段都可以先空着，流程走到需要时再补；程序绝不会偷偷替你猜泛函和基组。

- **`reaction`（必填）**：`reactant_smiles`、`product_smiles`、总 `charge` 和总 `multiplicity`；可选 `electronic_character`、`selected_candidate`、`reaction_center`。注意产物写 `"B.C"` 代表络合物，写 `["B", "C"]` 代表分离产物（`B + C`），两者对应的极小值证据完全不同。
- **`calculations`（可选字典）**：给整套计算配置起个名字，后面阶段用 `{"ref": "名字"}` 明确复用，避免重复抄写。每套 `QmCalculation` 必须写清 `engine`、`method` 和 `basis_set`（不需要基组的方法显式写 `basis_set=""`），不要把整行 route 硬塞进 `method`；额外选项放 `keywords`，ORCA 块放 `orca_blocks`，Gaussian 末尾输入放 `end_setting`。
- **`conformers`（可选）**：不填就从 SMILES 用 ETKDGv3（默认种子 42）自动生成起点；也可以指定已有文件、构象库或旋转/成环指导。
- **`guess`（可选）**：选初猜方式——`xtb_path`、`scan` 或 `provided`（外部候选结构）。
- **`ts_optimization`（可选）**：正式鞍点优化的计算配置（或引用）。
- **`verification`（可选）**：TS 频率、IRC、两端无约束 Opt/Freq 的配置，以及可选的已有 `irc_log` 或分离产物 `component_logs`。
- **`execution`（可选）**：CPU 核数和内存（默认 1 核、4096 MB）。

复用配置示例（仅演示格式，不代表默认方法推荐）：

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

## 原子编号、映射与结构来源

- **编号规则千万别混**：Cloudra 结构字段、Gaussian 和 xTB 都是 **1-based** 全原子编号（对应 XYZ 行号，不是 SMILES 重原子序号）；只有 ORCA 原生 scan/freeze 是 **0-based**。以 `ts_inspect` 返回的当前原子表为准。
- **原子映射**：未指定时程序自动选得分最高的完整映射并在消息里说明；想手动切候选时，用 **0-based** 的 `reaction.selected_candidate` 或 `reaction_mapping`。没填 `reaction_center` 时会从映射自动推导出成断键。
- **结构不可变留底**：`guess.kind="provided"` 接受时会固定原始字节和摘要，事后改源文件不会悄悄污染已接受的候选；真要换文件就走 `ts_resume` 重新声明。需要保电荷、自由基或立体信息时，连同与 XYZ 同序的 MOL/SDF 一起给。

## 路径、扫描与中途修订

- 探索方法可以和正式 TS 方法不同，但每个阶段都要自己说清楚。原生 xTB 构象/路径/扫描固定用 `GFN2-xTB`（`basis_set=""`）。
- 扫描最多两个坐标：双坐标 ORCA 必须标明 `grid`（网格）或 `concerted`（同步路径）；原生 xTB 扫描必须给正的 `force_constant`，双坐标标明 `concerted` 或 `sequential`。二维扫描绝不会自动拿最高点当 TS，所有初猜峰都必须再做正式的无约束 TS 优化。
- **失败了怎么修**：直接用 `ts_resume`（`changes={}` 可原样重试，也可以改结构、改扫描或用 `{replace: ...}` 换方法），历史失败和日志都会保留。有作业正在运行或取消中时不能修订；只排队的 `ready` 作业会在修订时被安全撤回重排，绝不强杀正在跑的计算。
- **改了什么重算什么**：换结构/初猜会重算下游；换 TS 方法重跑正式链；只改频率保留 TS Opt；只改 IRC 保留 TS/Freq；只改一侧端点只重算那一侧。

## 电子态与方法核对

每个作业入队前都会拿实际写入的输入文件核对方法、溶剂、电荷和自旋。普通科研项目没有方法白名单，只有 Benchmark 项目会额外叠加题目方法约束。

注意开壳层体系：GFN-xTB / CREST 的 `--uhf` 只表示总自旋电子数差，不能用来算开壳层单重态，遇到不支持的电子态会在提交前暂停提醒，改用 ORCA/Gaussian 或外部初猜即可。开壳层/自由基和闭壳层卡宾都会保守跳过力场打分。

## 科学验收

判断一个过渡态“真正成立”，必须同时满足下面这几条硬条件：

1. **TS 本身过关**：TS 优化原生正常结束且收敛；同一几何的频率计算有且仅有 **1 个虚频**，并且振动模式确实对应目标成断键（仅有 1 个虚频只证明它是一阶鞍点，不代表就是你要的反应）。
2. **真实双向 IRC + 端点优化确证**：以这个已验证的 TS 为起点跑真实双向 IRC，拿到两侧可用的外帧，再把两头末帧分别拿去做无约束优化和频率计算，最终收敛到身份、立体化学都正确且 **0 虚频** 的反应物和产物极小值。
3. **方向证明怎么算过**：只要上面这条“TS → 真实 IRC 末帧 → 无约束 Opt/Freq 收敛到正确零虚频端点”的证据链成立，就认可方向证明。IRC 本身可以如实处于 `partial`（不强求两端一路到底收敛）；几何距离窗口只是辅助提醒，不会推翻已经成立的端点优化，反过来也不能用几何看起来像来代替真正的端点优化。
4. **不能拿独立物种冒充端点**：单独算出来的反应物/产物零虚频极小值，不能冒充从 IRC 末帧优化出来的端点。缺来源、缺身份匹配或缺频率时，状态只停在 `candidate_only`，作业跑完（`done`）绝不等于科学验收通过。

分离产物（`["B", "C"]`）可以通过 `verification.product_endpoint.component_logs` 交齐各组分的正常结束、零虚频日志，与真实 IRC 分离产物端点一起校验，只证明 `B + C` 通道，不证明 `B.C` 络合物。

频率算完后，`frequency_analysis` 会解析虚频位移在反应中心上的占比（未加质量权重的位移平方和比例）；如果方向看起来偏了（`misaligned`）或数据不足（`undecidable`），系统会通知 Agent 人工/自主判断，不会擅自强停计算。初始 Hessian 必须来自完全相同理论级别的真实计算产物，不能拿位移末帧凑数。

## 状态与费用口径

- `result.verified=true` 才表示通过了科学检查；工具返回 `is_success=true` 只说明命令调用没报错。
- 数据库账本是唯一权威状态，`process.json` 只是导出快照；旧版本（格式 6 及更早）只读保留。
- 费用统计里，`runtime_seconds` 是墙钟耗时，`allocated_cpu_hours` 是申请核数乘耗时，`measured_cpu_hours` 没实测到就是 `null`，绝不拿估算冒充实测。

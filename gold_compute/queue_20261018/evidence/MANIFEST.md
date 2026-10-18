# gold 证据包 · 清单

打包时间：2026-10-18 18:4x（本机 WSL Ubuntu，仓库 `gold-fill-artifacts` @ `3768348e`）

## 包内结构

```
results/<ID>/            四道替换题的完整原生证据（NR1 / NY3 / HI1 / HL1）
  REPORT.txt             该题的完整报告（证据链、判据、缺口、口径）
  mechanism_graph.json   机理图 + 每条边的 barrier_kcal_mol
  CURRENT_STATE.md       状态快照
  jobs/                  每个计算作业的 .gjf 输入与 .log 原生日志
  geoms/ work/ logs/     几何、构建溯源、日志副本
campaign/
  DECISION_LOG.md        裁决台账（D1–D91+），含主协调的误判与更正
  ASSESSMENT_REPORT.md   旧战役的方法学对照（已退出活跃题库）
  CAMPAIGN_DASHBOARD.md  交付状态看板
task_gold/               当前题库 gold 真值快照
  normal/ hard/          NR1 NY3 HI1 HL1 等正式题
  impossible/            12 道 impossible 题（含 IB9）
```

**未包含**：`.chk` 二进制（110 MB，可由 .log 重建）、`.cloudra` 运行锁、`.lock`。
**未包含**：`impossible` 十二题的计算结果 —— 本轮未启动（见下「缺口」第 6 条）。

## 当前能垒（`mechanism_graph.json` 的 `barrier_kcal_mol`，纯电子能 kcal/mol）

| 题 | 已填 | 各边 |
|---|---|---|
| **NR1** | 4/4 | e1=46.32, e2=22.8, e3=7.25, e4=**68.85**（旧 64.93 留作 conformer-specific）|
| **NY3** | 3/3 | e1=36.79, e2=11.06, e3=43.13 |
| **HI1** | 2/3 | e1_erythro_syn=16.62, e2_threo_syn=15.85, **e3_erythro_regio=null** |
| **HL1** | 2/2 | e_exo=**16.18**, e_endo=**10.77** |

合计 **11/12**。分母口径：**统一取本步稳定中间体**（用户 08:2x 裁决）；旧分母值以
`barrier_conformer_specific_kcal_mol` 并列保留，不删不覆盖。

## 已知缺口 → 各自去哪里看

### 1. HI1 两条边：产物端优化 / 零虚频 / E-Z 身份证明不完整
- **证据位置**：`results/HI1/REPORT.txt` §9（e1 状态）与 §8/§10（两次分母更正）
- **原文口径**：`(c) reactant end VERIFIED (0 imaginary, identity above); product end still pending`
- **产物端作业**：`#1333 product_opt`、`#1334 product_frequency`、`#1335 product_frequency`
  —— 三个都已 `done`（结束于 08:21–08:37），日志在 `results/HI1/jobs/`
- **E/Z 身份证明**：`#1325 HI1_Z_2phenyl2butene_optfreq`、`#1326 HI1_E_2phenyl2butene_optfreq`
  在 `results/HI1/jobs/`
- ⇒ **要复核的是**：这三个产物端作业的 **0 虚频** 与 **CIP/E-Z 指派** 是否已写进 REPORT 的 (c) 部分

### 2. NY3 首步：实际连到的反应物构象与参考能垒用的构象不同
- **证据位置**：`results/NY3/mechanism_graph.json` 的 `e1.note`，原文：
  > `BARRIER DENOMINATOR: RC (job 1152, -244.935406907) = this step's own starting minimum.
  > Note that the reactant minimum DIRECTLY connected to TS1 is the HNCO.H2O water-rotamer
  > minimum (-244.926200303, +5.78 kcal/mol above RC, job 1294); the rotamer -> RC link is ...`
- ⇒ **缺口就是这句 "the rotamer → RC link"**：这一步的构象连接尚未补证
- 相关作业日志在 `results/NY3/jobs/`

### 3. NR1 末步（e4）与 HL1：证据关联 / 工具验收未闭环
- **NR1 e4**：`results/NR1/REPORT.txt` §40 与 §82–96（分母由 INT-1c 改 INT1a 的记录）；
  TS 虚频 −1923.6069、四列净投影、端点证明均写在该 REPORT
- **HL1**：`results/HL1/REPORT.txt` §8.1–8.3 与「九、分母口径统一（09:00）」；
  两面共用 RC 分母，ΔΔE‡ = 16.18 − 10.77 = **5.41 kcal/mol**

### 4. IB9 首步（采用 5.65，参照存在软虚频，人工采信）
- **证据位置**：`task_gold/impossible/IB9.json`
- 本仓库 `results/` 下**没有 IB9 的计算目录** —— 该值来自旧批次，属人工采信
- ⇒ 若要严格验收，需要把 IB9 首步的原始 TS 频率与软模信息补进来（本包不含）

### 5. 两条普通档 PT 边有意不设数值参考（按设计，不是缺口）
- 见 `task_gold/normal/` 对应 JSON 里 `barrier_kcal_mol = null` 的边

### 6. impossible 十二题：本轮未启动计算
- `task_gold/impossible/` 只有当前 gold 真值，**没有本轮新算的原生日志**
- 台账 `campaign/DECISION_LOG.md` 的 **D76** 定了梯队与顺序（第一梯队 7 题可给可信 gold，
  第二梯队 5 题只给诊断），但优先给了四道反应题


## ★ ts_runs/ —— 审阅 (a)(b)(c) 的核心证据（本包最要紧的部分）

四题的 TS 工作流目录都在 `ts/ts_00xx/` 下，**不在 `results/` 里**。本包含以下 12 个：

| run | 归属 | 内容 |
|---|---|---|
| `ts_0027` | NY3 E1 | 水加成 TS 的 guess/scan/ts_opt/frequency/IRC/两端 Opt+Freq |
| `ts_0028` | NY3 E2 | 氨基甲酸 O–H 构象边（转子鞍点，构象边）|
| `ts_0029` | NY3 E3 | 分解步 TS |
| `ts_0032` | NR1 TS1 | 甲酰胺 → 甲亚胺酸（N→O 质子转移）|
| `ts_0033` | NR1 TS2 | INT-1a ↔ INT-1b 构象边 |
| `ts_0034` | NR1 TS3 | INT-1b ↔ INT-1c 构象边 |
| `ts_0035` | NR1 TS4 | INT-1c 脱水步（多次尝试，含转子落点与二维网格）|
| `ts_0036` | HL1 exo | C10 反侧面 TS + IRC + 两端 |
| `ts_0037` | HL1 endo | C10 同侧面 TS + IRC + 两端 |
| `ts_0038` | HI1 erythro | (2R,7R) 底物的 syn 消除 TS |
| `ts_0039` | HI1 threo | (2R,7S) 底物的 syn 消除 TS |
| `ts_0040` | HI1 regio | 区域异构通道 TS（**未收敛，step 167/169**）|

每个目录结构：
```
jobs/declaration_NNNN/<stage>/   stage ∈ {path, ts_opt, frequency, irc,
                                          reactant_opt, reactant_frequency,
                                          product_opt, product_frequency}
  *.gjf      该步输入
  *.log      Gaussian 原生日志（可据此重算全部数字）
  endpoint_source.json / state_*.json   该步的溯源与状态
```

**审阅入口建议**：
- 核「TS 恰 1 虚频」→ `*/ts_opt/*.log` 找 `Optimization completed` + `*/frequency/*.log` 找 `imaginary frequencies`
- 核「端点 0 虚频」→ `*/reactant_frequency/*.log`、`*/product_frequency/*.log`
- 核「IRC 方向」→ `*/irc/*.log` 的 `Point Number N in FORWARD/REVERSE path direction` 与逐帧几何
- 核「末端身份」→ 各 `endpoint_source.json` 里的 `irc_log` sha256

**未包含**：`.chk`（可由对应 `.log` 的 `%chk` 与几何重建）、`.cloudra` 运行锁。

## 口径提醒（读报告时请注意）

1. `barrier_kcal_mol = null` 一律表示 **尚未写入**，不是「算不出来」的结论。
2. 「已填」只表示文档里写了非 null 值，**是否通过项目判据要看各题 REPORT 的证据链**。
3. 两个非对映底物（HI1 erythro / threo）的能垒**严禁相减**，`favored` 保持 null。
4. HL1 两面共用同一分母；络合物结合能单列，不进选择性。
5. 所有能垒均为 **纯电子能**，不含 ZPE / 热校正。

## 复核建议的入口顺序

1. `campaign/CAMPAIGN_DASHBOARD.md` —— 30 秒看清 11/12 与各边值
2. `results/<ID>/REPORT.txt` —— 该题完整的证据链与缺口
3. `results/<ID>/mechanism_graph.json` —— 机器可读的边与 note
4. `results/<ID>/jobs/*.log` —— 需要时可从原生日志重算

## 本分支相对完整本地证据刻意排除的内容

为了让包只含**可定量复核的 Gaussian 证据**，以下筛选用产物未入库（本地仍在）：

| 排除内容 | 体积 | 排除理由 |
|---|---|---|
| `xtb_path_runs/` 与 `xtbopt.log` | 24.3 MB | xTB 只用于**路径搜索/筛选**，按项目铁律不得作为定量 gold |
| `work/*/trajectories/*/frames.xyz` | 23.3 MB | MMFF94 构象生成轨迹，非电子结构证据 |
| `*.chk` | 110 MB | 二进制，可由对应 `.log` 与几何重建 |

**保留的**是所有 Gaussian `.gjf` 输入与 `.log` 原生日志（TS 优化、频率、IRC、端点 Opt+Freq），
足以独立复算四题的全部能垒、虚频与端点身份。

若需要被排除的筛选用产物，可在原机 `gold_compute/queue_20261018/results/` 与 `ts/ts_00xx/` 下找到。

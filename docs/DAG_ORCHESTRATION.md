# 机理图编排（`dag_record` 与 `dag_guided`）

本文说明 Cloudra 机理图子系统（`cloudra/dag/`）是怎么工作的。在 Web 界面的项目设置里可以随时切换编排模式（或在创建项目时指定 `orchestration_mode`）。

## 为什么要引入机理图

有机反应机理研究通常要跑几十步计算：构象搜索、过渡态初猜、结构优化、频率、IRC、端点确认和能量校正。如果只靠普通聊天窗口，聊得一长、上下文一压缩或者服务一重启，模型很容易忘记哪些算完了、哪些只是嘴上说说还没真算。

Cloudra 的做法是把**已经算出来的化学事实和证据**直接落盘到一张持久化的机理图（Delivery DAG）里，而不是让模型全靠记忆撑着：

- **节点（`SpeciesNode`）**代表一个完整的体系状态（单分子、络合物 `"B.C"`，或者分离物种集合 `["B", "C"]`）。注意这里是“整个反应体系的状态”，不是孤立催化剂，所以图保持无环。
- **边（`ElementaryStepEdge`）**代表一步基元转化，连接起点和终点状态。
- **没有“任务排产图”**：系统只记“化学结论和证据到哪一步了”，不把 Coordinator 绑死在死板的工作流排班表上；怎么拆任务、先算哪条路，由 Coordinator 自己决定。
- **内部字段不甩给模型**：版本号、审查 ID、文件哈希、阶段数组全由程序维护；模型只需要说清楚物种、步骤、文件路径和科学理由。

## 三种模式的区别

| 模式 | 行为 | 适合什么时候用 |
| --- | --- | --- |
| `standard`（默认） | 不读写机理图，不启动 Supervisor | 普通问答、查文献、写脚本或自由试算 |
| `dag_record` | Coordinator 自己提案并建图（系统自动通过草稿），自己把算好的日志送进证据库，没有 Supervisor | 想留下一张干净的机理图和证据账本，但不需要额外审稿人 |
| `dag_guided` | Coordinator 提案后即可先算，但草稿和送审证据都需要只读的 Supervisor 复核把关 | 严谨的机理探索、需要双角色互相挑刺，以及 Benchmark 消融实验 |

## 典型推进流程与分工

1. **提出机理草稿**：Coordinator 调用 `dag_propose_mechanism` 给出物种、基元步和理由，图立刻落盘，所有元素初始为 `pending`，此时就能直接开始探索计算（`dag_record` 下草稿自动接受，`dag_guided` 下交给 Supervisor 审）。
2. **开展计算并送审证据**：Coordinator 或子 Agent 算完量化日志后，调用 `dag_submit_species_evidence` 或 `dag_submit_step_evidence` 把文件路径交上来。子 Agent 只管干活和交日志，不直接改图拓扑。
3. **程序硬核自检**：内核先把日志文件拷贝一份不可变快照到 `.cloudra/evidence/` 并算 SHA-256（哪怕以后原文件被覆盖也不受影响），再跑物理检查：
   - 基态物种必须正常结束、零虚频（`n_imag == 0`）且实际三维结构匹配声明物种；
   - 过渡态（TS）必须原生优化收敛、正好一个虚频（`n_imag == 1`），且频率日志和优化几何一致；
   - 默认基元步还要求真实的 `short_irc` 方向证明（具体判据统一以 [TS 科学验收](TS_PROCESS_SOP.md#科学验收) 为准）；
   - 仅仅提交了作业（`submit_compute_job`）绝不算完成证据。
4. **Supervisor 裁决（仅 `dag_guided`）**：Supervisor 在程序冻结好的当前审查上下文里调用 `dag_accept_mechanism`、`dag_review_step` 或 `dag_review_species`，给出 `supported` / `rejected` 和必须非空的理由。裁决结果和通知同事务落盘发回原提交者（如果对方已经 `failed` 或 `cancelled`，通知留在信箱里但不强行唤醒）。注意：Supervisor 对图只读，而且**就算 Supervisor 点了同意，也不能把没通过物理自检的计算变成合格**。
5. **结题门禁**：不管是调 `stop` 工具还是直接发文字收尾，系统都会跑一遍覆盖率门禁。只要还有 `pending`、`rejected` 或缺少必需物理证据的步骤，系统就会拦住不让假装结题。

## 物种与步骤的状态含义

- `pending`：还没交合格证据。
- `supported`：已通过真实量化计算、内核物理自检（以及 `dag_guided` 下的 Supervisor 复核）。
- `rejected`：被 Supervisor 驳回（必须写理由），算作**未解决的缺口**，不能靠驳回来结题。
- `skipped`：能算但经科学判断主动放弃（必须写理由，例如强多参考体系超出当前方法范围）。
- `not_applicable`：这一步对当前体系不适用（必须写理由，例如无能垒步骤不需要 TS）。

默认情况下，物种要求 `geometry`，基元步要求 `ts_opt + frequency + short_irc`。`ts_guess` 只是辅助建议，既不卡流程，也不能抵充正式 TS 或频率。

**分离物种怎么交证据**：先把产物声明成列表 `smiles=["B", "C"]`（不要写成络合物 `"B.C"`），再用 `dag_submit_species_evidence(species_name="P", opt_file=["B.out", "C.out"])` 一次提交所有组分的正常结束、零虚频日志（优化与频率分开时 `freq_file` 列表一一对应）。之后交这一步的 TS 和双向 IRC 时，系统会自动复用目标物种绑定的组分证据，不会把分散组分硬拼成络合物。

## 最终交付文件与审批

在 DAG 模式下，如果工作区里有 `mechanism_graph.json`（Benchmark 必须提交），结题审计会把它和数据库里的权威 DAG 一一核对：节点和边不能重复或冲突，需要 TS 的步骤不能靠删掉 `via` 蒙混过关，`energy_hartree` 和 `evidence_log` 必须与本次绑定的不可变证据一致。如果只是部分交付、带跳过或豁免项，最终只会标成 `scope_completed` 或 `partial`，不会冒充完整的科学验证通过。

## 常用 DAG 工具速查

- **建图与改图（Coordinator）**：`dag_propose_mechanism`、`dag_add_species`、`dag_add_step`、`dag_remove_edge`（删边必填理由，永久记入变更日志）、`dag_update_delivery_element`。
- **交计算证据**：`dag_submit_species_evidence`、`dag_submit_step_evidence`。
- **审稿裁决（仅 Supervisor）**：`dag_accept_mechanism`、`dag_review_step`、`dag_review_species`、`dag_review_evidence`。
- **查看与沟通**：`dag_view`、`dag_delivery_report`、`dag_view_evidence`、`dag_message_supervisor`。

持久化数据全部存在 SQLite 专用表中（`dag_graphs`、`dag_nodes`、`dag_edges`、`dag_changelog`、`dag_drafts`、`dag_call_reviews`、`dag_evidence_bindings`、`dag_review_requests`）。

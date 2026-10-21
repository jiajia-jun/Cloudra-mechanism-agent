# 消融运行手册（runbook）

每臂一次独立运行，互不污染；所有数字都能从落盘数据复算。

## 1. 目录与命名

```
~/cloudra-ablation-<yyyymmdd>-<arm>/
    benchmark.db          # 行级结果
    benchmark.log         # agent/工具日志
    sandboxes/<task>/<batch>/   # 每个沙箱的交付与证据
    arm.json              # 臂定义快照（见下）
```

`arm.json` 至少记录：

```json
{
  "arm": "A3-full",
  "commit": "<git rev-parse HEAD>",
  "scoring": "graded+discovery+energy_fallback",
  "binding": "required",
  "orchestration": "dag_guided",
  "model": {"coordinator": "...", "follower": "..."},
  "tasks": "easy",
  "concurrency": 6,
  "started_at": "...",
  "batch_id": "<benchmark.db 的 batches.batch_id>"
}
```

## 2. 启动（重跑臂）

```bash
cd /home/ly/cloudra-bench-20261019
export PATH=/home/ly/.local/bin:/home/ly/bin:/home/ly/g16:/home/ly/xtb-6.5.0/bin:$PATH
export g16root=/home/ly GAUSS_SCRDIR=/home/ly/g16/scratch
export GAUSS_EXEDIR=/home/ly/g16/bsd:/home/ly/g16

.venv/bin/python -m cloudra.benchmark \
  --backend runtime_v2 \
  --tasks-dir ideapool/tasks/easy \
  --data-dir ~/cloudra-ablation-<date>-<arm> \
  --concurrency 6 \
  > ~/cloudra-ablation-<date>-<arm>/benchmark.log 2>&1 &
```

启动后立刻写 `arm.json`（commit/配置/批次 id）。**每臂一个全新 data-dir**，不复用旧库。

## 3. 监控

```bash
# 进程与进度
ps -p $(cat <dir>/.benchmark.pid) -o pid,etime,pcpu
sqlite3 <dir>/benchmark.db 'select task_id,round(final_score,3) from runs order by ts desc limit 5'
# 或（没有 sqlite3 CLI 时）
.venv/bin/python -m … dump_runs.py <dir>/benchmark.db
```

停止条件：
- 全部题目落库；或
- 连续 90 分钟无新落库且无 g16 进程（判定卡死，记录现场再重启该题）。

## 4. 离线重算（E1 评分臂）

同一批沙箱分别用四个口径重算，**不重跑 agent**。实现方式二选一：

- 代码开关（推荐）：`--scoring-arm legacy|graded_no_discovery|graded_no_energy|full`；
- 或 git worktree 切到对应 commit（必须记录 commit）。

产物：每臂一个 CSV（`task, graph, passed, selfc_score, accuracy, final, undelivered, notes_hash`）。

## 5. 负控（E2）

在 `<dir>/sandboxes/` 下构造合成沙箱：

- N1：图数值正确、无日志；
- N2：图正确、日志来自另一题；
- N4：声明与日志冲突且证据对不上参考。

跑同一个 `score_sandbox`，断言 `accuracy == 0` / fail-loud / 无证据倒扣。**负控不通过则停止后续重跑。**

## 6. 数据导出与归档

- 每臂结束后 `tar czf <dir>.tar.gz <dir>`；
- 导出 CSV 到 `~/ablation-results/<date>/`；
- `benchmark.db` 与 `sandboxes/` 永久保留（不要清理旧批次）。

## 7. 复现检查清单

- [ ] commit 与 `arm.json` 一致
- [ ] 环境变量（PATH/g16）与实际运行一致
- [ ] 批次 id 已记录
- [ ] 题目数量与 `--tasks-dir` 一致
- [ ] 导出 CSV 能由 `benchmark.db` 重算得到

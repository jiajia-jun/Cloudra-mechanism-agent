# 三臂消融设计（v1）

## 1. 被检验的命题（唯一一个）

> **把"持久计算契约 + 化学证据图 + 独立评分交付"耦合起来，是否提升可靠性、并让成本更可控？**

不谈评分器宽严、不谈基准本身是不是创新——那些是方法与仪器。这里只回答耦合有没有用。

## 2. 三个臂（同一套题，只改执行方式）

| 臂 | 代码开关 | 保留 | 去掉 |
|---|---|---|---|
| **standard**（普通） | `--orchestration-mode standard` | 全部几何/路径工具；原生日志可自行读取解析 | `ts_guess` 的 `verify`/`strict` 判定（harness 不再告诉它对错）；DAG 工具对模型隐藏 |
| **dag_record**（记录） | `--orchestration-mode dag_record` | 工具 + 机理图 + 主动化学校验；DAG 工具可**主动调用**，用来自查计算是否正确 | supervisor 审核；完成门禁——不要求交付工件/证据索引，`complete`/`partial` 都可收工 |
| **dag_guided**（完整） | `--orchestration-mode dag_guided` | supervisor 对抗性审查 + DAG 护栏（阶段契约、证据绑定、完成度判定） | — |

三臂共用同一题库与同一评分器；任务 JSON 不改，`with_orchestration_mode()` 只在运行时强制臂。

## 3. 指标（可靠性 + 成本）

**可靠性**
- `accuracy`：能垒与 Gold 的加权分；
- `graph`：机理图 GED；
- `passed`：证据链自洽（布尔）；
- **幻觉率**：交付里声称完成/可达、但 `passed=False` 或 `accuracy` 无日志支撑的比例（"说得比算得多"）。

**成本**
- 计算作业数、工具调用数、wall time；tokens 仅作参考（上下文注入策略会污染它）。

**交付完备性**
- `undelivered` 比例；
- 每臂失败归因分布（`short_irc` / TS 选错 / 参考态定义 / 格式 / 基建）。

## 4. 运行

```bash
cd /home/ly/cloudra-bench-20261019
export PATH=/home/ly/.local/bin:/home/ly/bin:/home/ly/g16:/home/ly/xtb-6.5.0/bin:$PATH
export g16root=/home/ly GAUSS_SCRDIR=/home/ly/g16/scratch
export GAUSS_EXEDIR=/home/ly/g16/bsd:/home/ly/g16

for ARM in standard dag_record dag_guided; do
  .venv/bin/python -m cloudra.benchmark \
    --backend runtime_v2 --tasks-dir ideapool/tasks/easy \
    --orchestration-mode "$ARM" \
    --data-dir ~/cloudra-ablation-$(date +%Y%m%d)-$ARM \
    --concurrency 6 > ~/cloudra-ablation-$(date +%Y%m%d)-$ARM/benchmark.log 2>&1
done
```

每臂记录 commit、`--orchestration-mode`、batch_id；数据目录独立，旧批次不清。

## 5. 预期与反证

| 观察 | 结论 |
|---|---|
| guided 的幻觉率/undelivered 明显低于另两臂，正确率不降 | 耦合有价值（护栏换来可靠交付） |
| guided 正确率与 record 持平但成本显著更高 | 护栏的代价大于收益 → 需要重新设计门禁粒度 |
| standard 正确率不低于 guided | 化学校验与护栏没有增益，核心主张被推翻 |
| record ≈ guided 且更便宜 | 门禁可以退化为"建议"（本次松绑方向正确） |

**在任何一臂跑完前，不预设结论。**

## 6. 规模与预算

- 第一轮：**easy 20 题 × 3 臂**（先验证差异是否存在，再扩档）；
- 预计每臂 4–6 h（6 并发，含真实 QM）；总计约 15–20 h 墙钟；
- `dag_record` 不写 `mechanism_evidence.json`，这些行会标 `undelivered=True`，属预期行为。

## 7. 与旧文档的关系

本文件取代此前的"单命题能力评价"版本：能力评价是仪器读数，这里才是论文要回答的因果问题。

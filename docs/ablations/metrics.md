# 指标与比较方法

## 1. 指标定义（与评分器字段一一对应）

| 指标 | 来源 | 含义 |
|---|---|---|
| `passed` | `runs.selfconsistency_passed` | 科学验收：每条边的一阶鞍点 + IRC 方向 + 端点链全部成立（布尔） |
| `final` | `runs.final_score` | 综合分 = 0.1·graph + 0.3·selfconsistency_score + 0.6·accuracy |
| `accuracy` | `runs.accuracy_score` | 边能垒与 Gold 的高斯加权分（双来源核对后） |
| `graph` | `runs.graph_score` | 机理图 GED（含节点证据绑定质量） |
| `selfc` | `runs.selfconsistency_score` | 分级自洽：0.35 鞍点 + 0.15 IRC 起点 + 0.50 端点链 |
| `undelivered` | `runs.undelivered` | 交付未发布 per-step 证据索引（仅报告，不直接扣分） |
| 成本 | 运行日志 | tokens、wall time、g16 CPU 时间、重试次数 |

**汇报顺序固定**：先 `passed`（科学），再 `final`（综合），最后成本。不得用 `final` 替代 `passed`。

## 2. 单臂汇总模板

```
arm: <name>  commit: <sha>  tasks: <n>
passed:  xx/n (xx%)
final:   mean xx.xx  median xx.xx  [min, max]
accuracy mean xx.xx   graph mean xx.xx   selfc mean xx.xx
undelivered: x/n
cost: tokens xx.x M   wall xx.x h
failures: short_irc x, ts_selection x, reference_definition x, format x, infra x
```

## 3. 臂间比较（配对）

同一题跨臂比较，逐题求差 `d_i = score_i(arm) − score_i(base)`：

- 报告 `mean(d)`、`median(d)`、配对 bootstrap 95% CI（10000 次重采样，按题重采样）；
- n=20 的功效有限：只在 `|mean(d)| ≥ 0.15` 且 CI 不跨 0 时下结论；
- 同时报告"改善/恶化/不变"的题数（阈值 0.05）。

禁止：把不同题集、不同 commit、不同并发下的均值直接相减。

## 4. 失败归因分类

从 `runs.notes` 自动归类（另写脚本），至少区分：

| 类别 | 识别关键词 |
|---|---|
| `short_irc` 证据缺失/不完整 | "IRC", "atom binding", "outer frames" |
| TS 选错/数值不符 | "log-derived ... vs gold" 且 penalty ≥ 0.5 |
| 参考态/构象定义差异 | "definition mismatch"、"answer-definition" |
| 物种表示不匹配 | "no delivered step matches its endpoint species" |
| 交付/格式失败 | "no parseable mechanism graph"、"declares no barrier" |
| 基建失败 | "crashed"、"cancelled by batch stop" |

每臂输出一张 类别×题数 表；归因表必须能由 `notes` 复算。

## 5. 反证规则（什么时候停）

- E1：若 G3/L2 在 A3 相对 A0 上升 ≥0.15，判定"分级口径奖励错误"，停止重跑并回退；
- E2：若任一负控 > 0.3，停止重跑，先修评分器；
- E3/E4：若同题重复方差 > 0.15，先补 E5（重复 2 次）再比较。

## 6. 结果存放

```
~/ablation-results/<yyyymmdd>/
    <arm>.csv            # 逐题明细
    <arm>.summary.json   # 汇总
    compare.md           # 臂×题 对照表 + 结论
```

# 本战役范围外任务（用户 2026-09-16 指令：已做完，勿重复计算）

| task | 状态 | 说明 |
|---|---|---|
| F1  | 已填 | 文献值 30.4 kcal/mol (Eisenstein 1982) -> F1.json |
| NU6 | 外部完成 | E1/E2 不在本地战役范围；gold 仓库边值仍为 None，待外部结果回填 |
| NY3 | 外部完成 | E2/E3 同上（本机 04:00 前的部分中间产物保留于 gold_compute/jobs/NY3_*） |
| NU3 | 外部完成 | E1 同上（本机部分中间产物保留于 gold_compute/jobs/NU3_*） |
| HA1 | 外部完成 | E1/EM1 从未在本地开工 |

协调者已相应处置 DAG：NU3/NY3 元素标记 skipped；未再派发 NU6/HA1。
继续计算的任务：NA2 NA5 NO3 NQ1 NR1 NU5 NU3已停 HG2 HE3 HL1 中尚未排除者（详见 progress.md 台账）。

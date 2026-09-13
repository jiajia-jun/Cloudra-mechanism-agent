# gold_compute/ — gold 能垒锚点计算战役目录

目标：为 benchmark 题库补齐/核实 `reference_computation.barrier_kcal_mol`
（口径：TS 相对反应物络合物，B3LYP/def2-SVP）。

- 题源：`ideapool/tasks/{normal,hard}/*.json`（18 题无 gold 能垒）、
  `ideapool/tasks/easy/*.json`（10 题 unverified/partial 待核）。
- 每题一个工作子目录（`<task_id>/`），计算产物保留原始日志。
- 结果回填 `cloudra/benchmark/*_registry/`，回填后必须重跑对应生成器
  （`test_*_tasks_regenerate_identically` 守卫同步）。
